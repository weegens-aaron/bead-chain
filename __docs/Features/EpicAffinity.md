# EpicAffinity

## What It Does

After bead-chain closes a bead, it prefers the next ready *sibling* under that
bead's parent epic over whatever the global `bd ready` queue would hand it next —
so a chain finishes the epic it's already inside before wandering off to
unrelated work.

## Why It Exists

bead-chain's natural default is "take the top of `bd ready`," but raw
queue-order optimality produces *incoherent* sessions: it can close one child of
epic A, then a child of epic B, then back to A, hopping between unrelated bodies
of work. That fragments commits and PRs (each touches a different feature area),
forces the agent to reload context every iteration, and leaves half-finished
epics scattered across the board.

Epic affinity encodes the "finish what you start" rule: when the just-closed
bead belonged to an epic that *still has ready siblings*, stay inside that epic.
The result is coherent, reviewable units of work — one epic drained to
completion (or to its current blocker frontier) before the chain falls back to
the global queue. It is **tier 2** of the four-tier `pick_next_bead` waterfall,
deliberately ranked below stranded-bead recovery (tier 0) and blocking-bug
priority (tier 1) — coherence matters, but not more than recovering orphaned
work or unblocking downstream beads.

Critically, affinity is a *preference*, not a trap: if the epic's remaining
siblings are all blocked or done, affinity yields and the chain falls through to
the global queue. The chain never strands itself inside an epic with no workable
children.

## How It Works

### User Perspective

The user never invokes this directly. They observe its effect in the `/bead-chain`
log: right after a bead closes, if a ready sibling exists under the same epic,
the chain prints

```
bead-chain: epic affinity -> staying inside <epic_id>
```

and the next bead it claims is from that epic rather than the top of the global
queue. When the epic runs dry (all siblings blocked or done), that line stops
appearing and the chain resumes picking from `bd ready` at large.

### System Perspective

Affinity is a stateless, two-call lookup wired into the selection waterfall, with
no bespoke graph-walking — bd owns the priority/blocker math. The just-closed
bead dict is threaded through from `close_current_bead_success` →
`activate_next_bead(just_closed=…)` → `pick_next_bead(just_closed)`. Inside the
waterfall, *after* tier 0 (stranded recovery) and tier 1 (blocking bug) decline:

1. `extract_parent_epic_id(just_closed)` reads the canonical `parent` field (with
   `parent_id` / `epic_id` fallbacks). No parent ⇒ skip tier 2 entirely.
2. `next_ready_in_epic(epic_id)` shells `bd ready --parent=<epic_id>
   --exclude-type=epic,milestone,gate,molecule --json` and returns the top
   non-container child, inheriting bd's own ordering and blocker resolution.
3. `_reject_if_blocked(sibling, "epic affinity")` is a belt-and-suspenders
   recheck (via `open_blocker_ids`) against bd version drift. A clean sibling is
   returned and the affinity log line emitted; a blocked one is refused and the
   waterfall falls through to tier 3 (global `next_ready`).

Affinity walks only the **direct** parent epic — there is no recursion up the
epic tree. The just-closed dict is the affinity key regardless of whether the
`bd close` actually succeeded (we *intended* to finish that epic's work).

```mermaid
sequenceDiagram
    participant Loop as ChainIterationLoop
    participant Close as lifecycle.close_current_bead_success
    participant Act as lifecycle.activate_next_bead
    participant Pick as lifecycle.pick_next_bead
    participant Ex as beads.extract_parent_epic_id
    participant NRE as beads.next_ready_in_epic
    participant Bd as bd CLI
    participant Rej as lifecycle._reject_if_blocked

    Loop->>Close: close current bead
    Close-->>Loop: just_closed dict (with "parent")
    Loop->>Act: activate_next_bead(just_closed)
    Act->>Pick: pick_next_bead(just_closed)
    Note over Pick: tier 0 (strands) + tier 1 (blocking bug) decline
    Pick->>Ex: extract_parent_epic_id(just_closed)
    Ex-->>Pick: epic_id (or None ⇒ skip tier 2)
    alt epic_id present
        Pick->>NRE: next_ready_in_epic(epic_id)
        NRE->>Bd: ready --parent=<epic_id> --exclude-type=… --json
        Bd-->>NRE: ready children []
        NRE-->>Pick: top non-container sibling (or None)
        alt sibling found
            Pick->>Rej: _reject_if_blocked(sibling, "epic affinity")
            alt sibling unblocked
                Rej-->>Pick: False
                Pick-->>Act: sibling (emit "epic affinity -> staying inside …")
            else sibling blocked
                Rej-->>Pick: True (warn) ⇒ fall through to tier 3
            end
        end
    end
    Note over Pick: tier 3: next_ready() global queue
```

## Key Data Shapes

The affinity key is the **just-closed bead dict** returned by
`close_current_bead_success`. Only the parent field is read here:

```json
{
  "id": "bead_chain-mol-bps.4",
  "issue_type": "task",
  "status": "in_progress",
  "title": "FlowDoc maintainer: Feature: EpicAffinity",
  "parent": "bead_chain-mol-bps"
}
```

`next_ready_in_epic` consumes a `bd ready --parent=<id> --json` array; each
element is a ready child bead. The first non-container element is returned:

```json
[
  {
    "id": "bead_chain-mol-bps.5",
    "issue_type": "task",
    "status": "open",
    "title": "FlowDoc maintainer: Feature: BeadChaining",
    "parent": "bead_chain-mol-bps"
  }
]
```

The chosen sibling dict (same shape as above) becomes the next `current_bead`.
There is no affinity-specific DTO — the feature is pure dict-field plumbing over
bd's own ready payloads.

## API Surface

> [!NOTE]
> bead-chain is a terminal Code Puppy plugin with **no HTTP endpoints**. This
> feature's "surface" is in-process Python plus `bd` subprocess calls, not
> routes — so the `-> Endpoint doc` column is N/A by design (see the Endpoints
> note in the [FlowDoc Manifest](../_Manifest.md)).

| Method | Path | Purpose | -> Endpoint doc |
|--------|------|---------|-----------------|
| `call` | `lifecycle.pick_next_bead(just_closed) -> dict \| None` | Four-tier waterfall; tier 2 *is* epic affinity | N/A — no HTTP surface |
| `call` | `lifecycle.activate_next_bead(just_closed=None) -> dict \| None` | Threads `just_closed` into the picker, then claims/arms the winner | N/A — no HTTP surface |
| `call` | `lifecycle.close_current_bead_success() -> dict \| None` | Returns the just-closed dict that seeds affinity | N/A — no HTTP surface |
| `call` | `beads.extract_parent_epic_id(bead) -> str \| None` | Resolve the direct parent epic id (`parent` + fallbacks) | N/A — no HTTP surface |
| `call` | `beads.next_ready_in_epic(epic_id) -> dict \| None` | Top ready non-container child under `epic_id` | N/A — no HTTP surface |
| `call` | `lifecycle._reject_if_blocked(bead, "epic affinity") -> bool` | Belt-and-suspenders blocker recheck on the sibling | N/A — no HTTP surface |
| `shell` | `bd ready --parent=<epic_id> --exclude-type=epic,milestone,gate,molecule --json` | The per-epic ready query behind tier 2 | N/A — `bd` subprocess |

## Implementation Map

| Responsibility | File path | Symbol |
|----------------|-----------|--------|
| Four-tier waterfall; epic affinity is the third branch (after strands + blocking bug) | `lifecycle.py:508` | `pick_next_bead` |
| Threads `just_closed` into the picker, then claims + arms wiggum | `lifecycle.py:544` | `activate_next_bead` |
| Returns the just-closed bead dict that becomes the affinity key | `lifecycle.py:201` | `close_current_bead_success` |
| Resolve direct parent epic id from `parent` / `parent_id` / `epic_id` | `beads.py:460` | `extract_parent_epic_id` |
| Per-epic ready query (server + client container double-filter) | `beads.py:441` | `next_ready_in_epic` |
| Blocker recheck that lets a blocked sibling fall through to tier 3 | `lifecycle.py` | `_reject_if_blocked` |
| Open work-time blocker lookup used by the recheck | `beads.py` | `open_blocker_ids` |
| `--exclude-type` arg builder shared by every ready query | `beads.py:209` | `_exclude_type_arg` |
| Canonical parent-field name | `beads.py:226` | `PARENT_EPIC_KEY` |
| Fallback parent field names | `beads.py:231` | `_PARENT_EPIC_FALLBACK_KEYS` |

## Configuration

| Key | Default | Effect |
|-----|---------|--------|
| `PARENT_EPIC_KEY` | `"parent"` | Canonical top-level field read first to find the just-closed bead's parent epic |
| `_PARENT_EPIC_FALLBACK_KEYS` | `("parent_id", "epic_id")` | Extra parent-field names checked, in order, for cross-version bd safety |
| `EXCLUDED_TYPES` | `("epic", "milestone", "gate", "molecule")` | Container types stripped from the per-epic ready query so affinity returns only doable leaf work |
| tier rank | tier 2 (hard-coded order in `pick_next_bead`) | Affinity sits below stranded recovery (0) and blocking bug (1), above global ready (3) |
| epic depth | direct parent only (no recursion) | Affinity walks exactly one level up; nested epics are not climbed |

## Edge Cases

> [!WARNING]
> **Affinity follows the *direct* parent only — it does not climb the epic
> tree.** If `just_closed` lives in a sub-epic L2 nested under L1, closing L2's
> last child finds no sibling in L2 and falls straight through to the global
> queue; it does **not** promote to L1's other children. Under recursive pours
> the chain can therefore ping-pong across branches. This is a known limitation
> (see `notes/recursive-pours-spike-t1z.md`), not a bug.

> [!WARNING]
> **The just-closed dict is the affinity key even if `bd close` failed.**
> `close_current_bead_success` returns the dict regardless of close success,
> because the *intent* was to finish that epic's work. (On a real close failure
> the chain stops anyway, so this only matters in the pinned / excluded-type
> drop paths where the chain keeps trotting.)

> [!WARNING]
> **A blocked sibling does not stall the chain.** `_reject_if_blocked` is
> belt-and-suspenders against bd version drift: if `bd ready --parent` ever
> leaks a blocked sibling, affinity refuses it and falls through to tier 3
> rather than barreling into a close-time failure. So tier 2 can decline even
> when a sibling technically exists.

> [!WARNING]
> **Container siblings never win affinity.** `next_ready_in_epic` applies the
> same server-side `--exclude-type` *and* client-side `is_excluded_type`
> double-filter as the global `next_ready`, because the server flag has leaked
> containers in the wild. A child epic/milestone/gate/molecule under the parent
> is skipped, not driven.

> [!CAUTION]
> **Affinity is read-only routing — it mutates nothing.** It performs no claim,
> no close, no `bd dolt push`. The downstream `activate_next_bead` does the
> claim; durability lives in session-close (see
> [SessionCloseDurability](../Concepts/SessionCloseDurability.md)).

## Error Scenarios

| Trigger | Behavior | User sees |
|---------|----------|-----------|
| `just_closed` is `None` (first bead of the run) | `extract_parent_epic_id` returns `None`; tier 2 skipped entirely | No affinity line; selection proceeds to tier 3 |
| Closed bead has no `parent`/`parent_id`/`epic_id` | `extract_parent_epic_id` returns `None`; tier 2 skipped | No affinity line; standalone beads correctly use the global queue |
| Epic has no ready siblings (all blocked/done) | `next_ready_in_epic` returns `None`; fall through to tier 3 | No affinity line; chain hops to the global queue |
| Sibling returned but carries an open blocker (bd ready leak) | `_reject_if_blocked` warns and returns `True`; fall through to tier 3 | `bead-chain: epic affinity candidate <id> has open blocker(s) [...] -- refusing to claim it ...` |
| Leaked container child under the parent epic | `next_ready_in_epic` filters it out (server + client); treated as no sibling | No affinity line; falls through (or returns a later non-container sibling) |
| `bd ready --parent` raises `BeadsError` (bd missing/timeout/junk) | Propagates out of `pick_next_bead`; `activate_next_bead` catches it, warns, and stops the chain | ` bead-chain stopping — \`bd ready\` failed: <exc>` |

## Testing

The selection logic is exercised with monkeypatched `beads.*` surfaces so no
real bd is required (`python3 -m pytest tests/`):

- `tests/test_pick_respects_blocks.py` —
  `test_blocked_epic_sibling_is_skipped_falls_through` pins the tier-2 contract:
  a blocked affinity sibling is rejected and selection falls to the global ready
  bead. The `_install` helper wires `next_ready_in_epic`, `next_blocking_bug`,
  `list_recoverable_strands`, `next_ready`, and `open_blocker_ids` to assert the
  full waterfall order.
- `tests/test_excluded_container_types.py` —
  `test_next_ready_in_epic_drops_leaked_container_bead` proves the per-epic
  query re-filters every leaked container type (`epic`/`milestone`/`gate`/
  `molecule`), so a container sibling never wins affinity.

To exercise affinity by hand: create an epic with two ready children, run
`/bead-chain`, and confirm the second iteration logs
`bead-chain: epic affinity -> staying inside <epic_id>` and claims the sibling
rather than an unrelated ready bead. Run the whole suite with `pytest -q`.

## Related

- [NextBeadSelectionWaterfall](../Flows/NextBeadSelectionWaterfall.md) — the full
  four-tier flow that contains this feature as tier 2.
- [BlockingBugPriority](BlockingBugPriority.md) — tier 1, which outranks affinity:
  a ready bug with dependents cuts the line first.
- [EpicRollup](EpicRollup.md) — what happens to the epic *after* affinity drains
  its children: the drain-time courtesy close.
- [GoalPromptEnrichment](GoalPromptEnrichment.md) — also reads
  `extract_parent_epic_id` to surface the parent epic in the `/goal` prompt.
- [ChainIterationLoop](../Flows/ChainIterationLoop.md) — passes the just-closed
  dict that seeds affinity into `activate_next_bead`.
- [BeadClaimAndBlockerRecheck](../Flows/BeadClaimAndBlockerRecheck.md) — the
  activation gauntlet that claims the sibling affinity selects.
- [WorkTimeBlockerGate](WorkTimeBlockerGate.md) — the gate that rechecks the
  affinity sibling via `_reject_if_blocked`; a blocked sibling is skipped and
  affinity falls through to the global ready queue.
- [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md) — why the
  per-epic ready query skips container-type siblings.
- [QueueDriverNotGoalEngine](../Concepts/QueueDriverNotGoalEngine.md) — the SRP
  boundary: affinity reorders bd's frontier by preference, it never invents goals.
- [BdSubprocessTransport](../Concepts/BdSubprocessTransport.md) — the transport
  behind the `bd ready --parent` spawn.
- [Features Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
