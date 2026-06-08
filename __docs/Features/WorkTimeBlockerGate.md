# WorkTimeBlockerGate

## What It Does

bead-chain refuses to claim or drive any bead that still has an **open
work-time blocker** — an inbound `blocks` or generic `waits-for` dependency
edge whose target is not yet `closed`. The check runs at *claim/start time*
(every selection and activation site), not just when `bd close` would later
refuse, and a blocked stranded bead is reverted to `open` instead of being
re-driven.

## Why It Exists

This is the **bdboard-oals** fix. The chain used to claim and fully execute a
bead whose `blocks` dependencies were still open, only discovering the problem
when `bd close` refused with *"blocked by open issues"* — after a full
agent run had already burned cycles on stale inputs. Two paths can surface a
blocked bead even though `bd ready` filters them server-side:

1. The **recovery tier** reads `bd list --status=in_progress`, which ignores
   the `bd ready` frontier. A bead claimed *while* ready, then re-blocked
   (its blocker reopened, or a `blocks`/`waits-for` edge wired after the claim),
   would be picked back up and re-driven.
2. **bd version drift.** If a future `bd ready` ever leaked a blocked bead, the
   chain would barrel straight into the same close-time failure.

The gate prevents the wasted run; bd's native close-time refusal stays as the
final safety net.

## How It Works

### User Perspective

The user never sees a blocked bead get worked. Instead, when a blocked bead
reaches any claim site, the chain emits a warning naming the bead and its open
blocker ids, reverts the bead to `open` (so it re-enters the queue *behind* its
blockers), and either skips to the next eligible candidate or stops the chain
cleanly. A genuinely ready leaf is worked instead; nothing blocked is ever
driven to a doomed `bd close`.

### System Perspective

Every claim path resolves a candidate's live blockers via
`beads.open_blocker_ids(bead_id)`, which re-fetches the bead with
`bd show <id> --json` (the only call that carries each dependency's `status`
*and* `dependency_type`) and returns the ids of every inbound edge whose type
is in `BLOCKING_DEP_TYPES` and whose status is not in
`SATISFIED_BLOCKER_STATUSES`. A non-empty list means "blocked".

```mermaid
sequenceDiagram
    participant Loop as ChainIterationLoop
    participant Pick as lifecycle.pick_next_bead
    participant Strand as lifecycle._unblocked_strands
    participant Gate as beads.open_blocker_ids
    participant Show as beads.show (bd show --json)
    participant Act as lifecycle.activate_next_bead

    Loop->>Pick: pick_next_bead(just_closed)
    Pick->>Strand: tier 0 — enumerate recoverable strands
    Strand->>Gate: open_blocker_ids(strand_id)
    Gate->>Show: bd show <id> --json
    Show-->>Gate: dependencies[] (id, status, dependency_type)
    Gate-->>Strand: [blocker ids] or []
    alt strand blocked
        Strand->>Strand: revert_to_open(id) + drop (warn)
    else strand clear
        Strand-->>Pick: return strand (recover)
    end
    Pick->>Gate: tiers 1-3 — _reject_if_blocked(candidate)
    Gate-->>Pick: blocked? skip to next tier : keep
    Pick-->>Act: chosen bead (or None)
    Act->>Gate: last-line recheck open_blocker_ids(id)
    alt blocked at activation
        Act->>Act: revert_to_open(id) (non-recovery) + state.stop()
    else clear
        Act->>Act: claim + arm /goal
    end
```

## Key Data Shapes

`open_blocker_ids` reads the inbound dependency records as emitted by
`bd show <id> --json`. Each entry is a full dependency dict (unlike the bare
edge records on `bd ready` / `bd list`, which omit `status`):

```json
{
  "id": "bead_chain-h4eq",
  "dependencies": [
    { "id": "bead_chain-30vz", "status": "open",        "dependency_type": "blocks" },
    { "id": "bead_chain-w1",   "status": "in_progress", "dependency_type": "waits-for" },
    { "id": "bead_chain-ilmb", "status": "closed",      "dependency_type": "blocks" },
    { "id": "bead_chain-uiwu", "status": "open",        "dependency_type": "parent-child" }
  ]
}
```

For the record above, `open_blocker_ids` returns the open *hard* edges only —
`["bead_chain-30vz", "bead_chain-w1"]`: the `closed` blocks edge is satisfied
and dropped, and the `parent-child` edge (the parent epic) is structural, not a
work-time block.

The function's own return shape is a flat list of blocker ids:

```json
["bead_chain-30vz", "bead_chain-w1"]
```

An empty list `[]` means *ready to work* (no unresolved work-time dependency).

## API Surface

| Method | Path | Purpose | -> Endpoint doc |
|--------|------|---------|-----------------|
| `call` | `beads.open_blocker_ids(bead_id) -> list[str]` | Re-fetch via `bd show` and return the ids of every still-open `blocks` / `waits-for` blocker | N/A — no HTTP surface |
| `call` | `beads.is_blocked(bead_id) -> bool` | Boolean convenience wrapper over `open_blocker_ids` | N/A — no HTTP surface |
| `call` | `lifecycle._reject_if_blocked(bead, tier) -> bool` | Belt-and-suspenders recheck for the non-recovery tiers (1-3) | N/A — no HTTP surface |
| `call` | `lifecycle._unblocked_strands() -> list[dict]` | Tier-0 recovery filter: revert + drop any blocked stranded bead | N/A — no HTTP surface |
| `call` | `lifecycle.pick_next_bead(just_closed) -> dict \| None` | Four-tier picker that applies the gate to every tier | N/A — no HTTP surface |
| `call` | `lifecycle.activate_next_bead(just_closed=None) -> dict \| None` | Activation boundary's last-line blocker recheck | N/A — no HTTP surface |
| `call` | `register_callbacks.handle_bead_chain_command(command) -> str \| bool` | Startup-time first-activation recheck | N/A — no HTTP surface |
| `call` | `beads.revert_to_open(bead_id) -> None` | Unwind a blocked bead's claim back to `open` | N/A — `bd update <id> --status=open` |
| `shell` | `bd show <id> --json` | The per-bead fetch carrying each dependency's `status` + `dependency_type` | N/A — `bd` subprocess |

## Implementation Map

| Responsibility | File path | Symbol |
|----------------|-----------|--------|
| Canonical open work-time blocker lookup (re-fetch + filter) | `beads.py:476` | `open_blocker_ids` |
| Boolean convenience wrapper | `beads.py:550` | `is_blocked` |
| Re-fetch a bead with `bd show <id> --json` | `beads.py:639` | `show` |
| Unwind a claimed/blocked bead back to `open` | `beads.py:736` | `revert_to_open` |
| Hard (gating) dependency-edge types | `beads.py:165` | `BLOCKING_DEP_TYPES` |
| Statuses that satisfy (no longer gate) a blocker | `beads.py:170` | `SATISFIED_BLOCKER_STATUSES` |
| Recoverable in-flight statuses fed into the gate | `beads.py:198` | `RECOVERABLE_STATUSES` |
| Tier-0 recovery filter: revert + drop blocked strands | `lifecycle.py:88` | `_unblocked_strands` |
| Startup invariant guard that evicts blocked strands | `lifecycle.py:138` | `enforce_single_in_progress` |
| Four-tier picker applying the gate to every tier | `lifecycle.py:460` | `pick_next_bead` |
| Belt-and-suspenders recheck for tiers 1-3 | `lifecycle.py:521` | `_reject_if_blocked` |
| Activation-boundary last-line recheck + revert/stop | `lifecycle.py:544` | `activate_next_bead` |
| Startup first-activation recheck + revert | `register_callbacks.py:169` | `handle_bead_chain_command` |

## Configuration

| Key | Default | Effect |
|-----|---------|--------|
| `BLOCKING_DEP_TYPES` | `("blocks", "waits-for")` | Inbound edge types treated as hard work-time blocks. `parent-child` / `discovered-from` / `related` are deliberately excluded. Tuple-constant so a new gating type (e.g. `"requires"`) is a one-line edit |
| `SATISFIED_BLOCKER_STATUSES` | `frozenset({"closed"})` | Blocker statuses that no longer gate work. `open` / `in_progress` / `blocked` all still gate; only `closed` is satisfied. Compared case-insensitively |
| `RECOVERABLE_STATUSES` | `("in_progress", "hooked")` | The stranded in-flight statuses tier-0 enumerates before running each through the gate |
| soft-fail behavior | return `[]` | On any `bd show` infrastructure error, `open_blocker_ids` treats the bead as unblocked so a transient bd blip can't strand the chain — the close-time guard is the backstop |

## Edge Cases

> [!WARNING]
> **The molecule fan-out gate is a *different* mechanism.** A molecule's
> `waits_for: children-of(...)` *field* marker is NOT an inbound `waits-for`
> edge — it is checked separately by `lifecycle._has_fan_out_gate_issue`, not by
> `open_blocker_ids`. Do not conflate the two: a generic `waits-for` edge (from
> `bd dep add B A --type=waits-for`) gates here; the molecule field marker does
> not appear in this gate at all.

> [!WARNING]
> **The parent epic is never a blocker.** A bead's `parent-child` edge to its
> epic is structural, not a work-time dependency. Counting it would block every
> child of every epic forever — so `parent-child` is excluded from
> `BLOCKING_DEP_TYPES` (pinned by `test_parent_child_edge_is_not_a_blocker`).

> [!WARNING]
> **Recovery beads are exempt from the revert path at activation.** A bead that
> entered via tier-0 recovery was already blocker-filtered in
> `_unblocked_strands`; if one somehow reaches `activate_next_bead` blocked, the
> chain stops and leaves it `in_progress` for inspection rather than reverting
> it (it represents real partial work on disk).

> [!CAUTION]
> **The gate soft-fails to "unblocked" on a bd outage.** If `bd show` errors,
> `open_blocker_ids` returns `[]` so a transient blip never strands the chain.
> This means a blocked bead *could* slip through during a bd outage — by design,
> because bd's native close-time refusal remains the final safety net.

## Error Scenarios

| Trigger | Behavior | User sees |
|---------|----------|-----------|
| A stranded `in_progress` bead has an open blocker (tier 0) | `_unblocked_strands` reverts it to `open` and drops it from the workable set | `bead-chain: stranded in_progress bead <id> is blocked by open issue(s) [<ids>] -- refusing to re-drive it and reverting to open (work-time blocks must be respected, not just at close-time).` |
| A tier 1-3 candidate from `bd ready` is unexpectedly blocked | `_reject_if_blocked` returns `True`; the tier is skipped and selection falls through to the next tier | `bead-chain: <tier> candidate <id> has open blocker(s) [<ids>] -- refusing to claim it (bd ready leaked a blocked bead; respecting work-time blocks anyway).` |
| A bead is blocked at the mid-chain activation boundary | `activate_next_bead` reverts (non-recovery) and stops the chain | `bead-chain refused to activate <id>: it has open blocker(s) [<ids>]. Respecting work-time blocks at claim time, not just at close. Stopping chain.` |
| A bead is blocked on the very first startup activation | `handle_bead_chain_command` reverts (non-recovery) and refuses to start | `bead-chain refused to start with <id>: it has open blocker(s) [<ids>]. Respecting work-time blocks at claim time, not just at close.` |
| `bd show` fails while resolving blockers | `open_blocker_ids` soft-fails to `[]` (treated as unblocked); close-time guard backstops | *(no gate warning; bd's own close-time refusal is the fallback if the bead really was blocked)* |
| The revert itself fails after a block is detected | best-effort — the bead is still dropped from this pass | `also couldn't revert <id> (still dropping it from this pass): <err>` |

## Testing

Three suites pin the gate at each layer:

- **`tests/test_blocker_gate.py`** — unit tests for `beads.open_blocker_ids`
  against the real `bd show --json` dependency shape: open `blocks` reported,
  `in_progress` blocker still gates, `closed` satisfied, `parent-child` /
  `discovered-from` / `related` ignored, case-insensitive type+status, empty/
  missing/soft-fail paths. Runs standalone (`python3 tests/test_blocker_gate.py`)
  because `beads.py` is pure-stdlib.
- **`tests/test_waits_for_blocker.py`** — bead_chain-i0v / FB-10 regression:
  proves `"waits-for"` is in `BLOCKING_DEP_TYPES` and that a generic `waits-for`
  edge gates identically to `blocks`, including the recovery-tier path
  (`_unblocked_strands` reverts a `waits-for`-gated strand, keeps a satisfied
  one).
- **`tests/test_pick_respects_blocks.py`** — selection-layer regression over
  `lifecycle.pick_next_bead`: blocked global-ready / blocking-bug / epic-affinity
  candidates are skipped, a blocked stranded `in_progress` bead is reverted (not
  re-driven), and `enforce_single_in_progress` evicts a blocked recovery bead.
- **`tests/test_blocker_gate_e2e.py`** — end-to-end against a *real* `bd`
  database: B blocked by open A never hits the `bd ready` frontier,
  `open_blocker_ids` still detects A while B is `in_progress`, and B becomes
  unblocked + ready only once A closes.

Run the whole suite with `pytest -q`.

## Related

- [BeadClaimAndBlockerRecheck](../Flows/BeadClaimAndBlockerRecheck.md) — the
  claim-time gauntlet that runs this gate at both the startup and mid-chain
  activation sites.
- [NextBeadSelectionWaterfall](../Flows/NextBeadSelectionWaterfall.md) — the
  four-tier picker whose tier-0 strand revert and tiers 1-3 `_reject_if_blocked`
  recheck enforce this gate.
- [RecoveryMode](RecoveryMode.md) — the feature whose blocked-strand revert
  path is one of this gate's enforcement sites.
- [StrandedBeadRecovery](../Flows/StrandedBeadRecovery.md) — tier 0 in depth:
  how `_unblocked_strands` reverts+drops a blocked stranded bead instead of
  re-driving it.
- [BlockingBugPriority](BlockingBugPriority.md) — escalation never overrides a
  work-time block: a blocked blocking bug is skipped by `_reject_if_blocked`.
- [EpicAffinity](EpicAffinity.md) — a blocked affinity sibling is skipped by the
  same recheck and falls through to the global ready queue.
- [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md) — the sibling
  defence-in-depth pattern (server-side filter + client-side recheck) applied to
  container types rather than blockers.
- [Features Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
