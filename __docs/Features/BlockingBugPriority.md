# BlockingBugPriority

## What It Does

Lets any **ready bug that has at least one dependent** cut to the front of the
chain's work queue: before bead-chain picks ordinary work, it asks bd for the
top ready bug with `dependent_count > 0` and, if one exists, claims *that*
instead — because fixing a bug that other beads are waiting on unblocks the most
downstream work.

## Why It Exists

bd's own `bd ready` frontier is priority-ordered, but priority alone doesn't
capture *blast radius*: a P1 feature with no dependents and a P1 bug that three
other beads are blocked on look identical to a naive "take the next ready bead"
loop. Without an explicit escalation, the bug would wait its turn in queue order
while the beads that depend on it sit stranded — the chain would burn iterations
on work that can't actually merge cleanly until the bug is gone.

This feature encodes the heuristic "**unblock the graph first**" as **tier 1**
of the four-tier `pick_next_bead` waterfall (only the stranded-recovery tier 0
outranks it). It is the *consumer* half of the bug story: the
[BugDiscoveryProtocol](BugDiscoveryProtocol.md) tells an agent how to *file* a
blocking bug (P1 + `--blocks=<id>` so it gains a dependent); this feature is
what later notices that filed bug and jumps it to the head of the line. The two
are deliberately split — filing is prompt text the agent runs, escalation is a
read-only selection query bead-chain runs.

## How It Works

### User Perspective

The user never triggers this directly. They see its effect in the run log: at
the top of an iteration, instead of the usual global-ready pick, the chain emits

```
bead-chain: blocking bug detected -> prioritising bead_chain-ab2
```

and the next agent is handed that bug's goal prompt. If the escalation candidate
turns out to be (wrongly) blocked itself, the user instead sees a warning and
the chain quietly falls through to the next tier:

```
bead-chain: blocking bug candidate bead_chain-ab2 has open blocker(s) [bead_chain-x1] -- refusing to claim it ...
```

### System Perspective

Each iteration, `lifecycle.pick_next_bead` runs its waterfall. After tier 0
(stranded recovery) finds nothing, it calls `beads.next_blocking_bug()`. That
function loops over `BLOCKING_BUG_TYPES` (`("bug",)`), runs
`bd ready --type=bug <--exclude-type=…> --json` so bd does priority/blocker
ordering and container filtering server-side, then applies the one predicate bd
can't express — `dependent_count > 0` — client-side, returning the **first**
(highest-priority) bug that has a dependent. `pick_next_bead` then passes that
candidate through `_reject_if_blocked`, a defence-in-depth recheck via
`beads.open_blocker_ids` that refuses the candidate if a `blocks`/`waits-for`
edge was wired between the `bd ready` query and now (bd version drift). If it
survives, the bug is returned, claimed, and armed exactly like any other bead.
No source or bead is mutated — this is a pure read-only selection query.

```mermaid
sequenceDiagram
    participant Loop as ChainIterationLoop
    participant Pick as lifecycle.pick_next_bead
    participant NBB as beads.next_blocking_bug
    participant Bd as bd CLI (bd ready --type=bug)
    participant Rej as lifecycle._reject_if_blocked
    participant OBI as beads.open_blocker_ids

    Loop->>Pick: pick_next_bead(just_closed)
    Note over Pick: tier 0 (stranded recovery) found nothing
    Pick->>NBB: next_blocking_bug()
    loop for issue_type in BLOCKING_BUG_TYPES
        NBB->>Bd: bd ready --type=bug --exclude-type=… --json
        Bd-->>NBB: ready bugs (priority-ordered)
        NBB->>NBB: first bead with dependent_count > 0?
    end
    alt a blocking bug exists
        NBB-->>Pick: that bug dict
        Pick->>Rej: _reject_if_blocked(bug, "blocking bug")
        Rej->>OBI: open_blocker_ids(bug.id)
        OBI-->>Rej: [] (no open blockers)
        Rej-->>Pick: False (not blocked)
        Pick-->>Loop: emit "blocking bug detected -> prioritising <id>"; return bug
    else none ready / candidate blocked
        NBB-->>Pick: None
        Pick->>Pick: fall through to tier 2 (epic affinity) / tier 3 (global ready)
    end
```

## Key Data Shapes

This feature consumes ordinary `bd` bug records from `bd ready --json`; there is
no bespoke DTO. The only fields the code reads are `id`, `issue_type` (must be in
`BLOCKING_BUG_TYPES`), and `dependent_count` (must be `> 0`). A qualifying
candidate as `next_blocking_bug` sees it:

```json
{
  "id": "bead_chain-ab2",
  "issue_type": "bug",
  "priority": 1,
  "title": "<short title>",
  "status": "open",
  "dependent_count": 1,
  "dependencies": []
}
```

`_reject_if_blocked` then re-fetches the full record via `bd show <id> --json`
(the only call that carries each dependency's `status` + `dependency_type`) and
inspects the `dependencies` array for still-open `blocks`/`waits-for` edges:

```json
{
  "id": "bead_chain-ab2",
  "issue_type": "bug",
  "dependencies": [
    {
      "id": "bead_chain-x1",
      "dependency_type": "blocks",
      "status": "open"
    }
  ]
}
```

`next_blocking_bug` returns the **bug dict** unchanged (or `None`);
`pick_next_bead` returns that same dict to the runner. No structured object is
constructed by this feature.

## API Surface

> [!NOTE]
> bead-chain is a terminal Code Puppy plugin with **no HTTP endpoints**. This
> feature's "surface" is in-process Python plus `bd` subprocess calls, not
> routes — so the `-> Endpoint doc` column is N/A by design (see the Endpoints
> note in the [FlowDoc Manifest](../_Manifest.md)).

| Method | Path | Purpose | -> Endpoint doc |
|--------|------|---------|-----------------|
| `call` | `beads.next_blocking_bug() -> dict \| None` | Tier-1 selection: top ready bug with `dependent_count > 0` | N/A — no HTTP surface |
| `call` | `lifecycle.pick_next_bead(just_closed) -> dict \| None` | Four-tier waterfall; tier 1 is this feature | N/A — no HTTP surface |
| `call` | `lifecycle._reject_if_blocked(bead, tier) -> bool` | Defence-in-depth: refuse a candidate that has open blockers | N/A — no HTTP surface |
| `call` | `beads.open_blocker_ids(bead_id) -> list[str]` | The blocker-status check `_reject_if_blocked` consults | N/A — no HTTP surface |
| `shell` | `bd ready --type=bug --exclude-type=<containers> --json` | Server-side: priority-ordered ready bugs minus container types | N/A — `bd` subprocess |
| `shell` | `bd show <id> --json` | Re-fetch full record (with dep status) for the blocker recheck | N/A — `bd` subprocess |

## Implementation Map

| Responsibility | File path | Symbol |
|----------------|-----------|--------|
| Which issue types count as "bug" for escalation | `beads.py:206` | `BLOCKING_BUG_TYPES` |
| Tier-1 query: top ready bug with `dependent_count > 0` | `beads.py:593` | `next_blocking_bug` |
| Container `--exclude-type=…` arg threaded into the query | `beads.py:209` | `_exclude_type_arg` |
| Re-fetch dep status & list still-open blockers | `beads.py:476` | `open_blocker_ids` |
| Four-tier waterfall; tier 1 wiring + log line | `lifecycle.py:460` | `pick_next_bead` |
| Defence-in-depth blocker recheck on the candidate | `lifecycle.py:521` | `_reject_if_blocked` |
| Caller — every later bead hand-off runs the waterfall | `lifecycle.py:574` | `activate_next_bead` |

## Configuration

| Key | Default | Effect |
|-----|---------|--------|
| `BLOCKING_BUG_TYPES` | `("bug",)` (`beads.py:206`) | Issue types eligible for tier-1 escalation; a tuple so adding a sibling type (e.g. `"regression"`) is a one-line change (DRY) |
| `dependent_count` predicate | `> 0` (hard-coded in `next_blocking_bug`) | A bug must have at least one dependent to escalate; a dependent-less bug is treated as ordinary work |
| `EXCLUDED_TYPES` (via `_exclude_type_arg`) | epic/milestone/gate/molecule | Container types stripped from the `bd ready --type=bug` query so a container never escalates as a "blocking bug" |
| `BLOCKING_DEP_TYPES` | `blocks`, `waits-for` (`beads.py`) | Which inbound edge types `open_blocker_ids` counts when `_reject_if_blocked` rechecks the candidate |
| Waterfall tier rank | tier 1 of 4 (after tier-0 recovery) | Blocking bugs outrank epic-affinity and global-ready, but never pre-empt recovering a stranded in_progress bead |

## Edge Cases

> [!WARNING]
> **A bug with no dependents does NOT escalate.** The `dependent_count > 0`
> predicate is the whole point — a P1 bug filed *without* a `--blocks` edge has
> zero dependents and is picked up by the ordinary global-ready tier in priority
> order, not jumped to the front.

> [!WARNING]
> **Stranded recovery (tier 0) always outranks this.** A bug that is *both*
> stranded `in_progress` *and* a blocking bug is recovered first — recovery is
> tier 0, blocking-bug escalation is tier 1. The bug only escalates once it's
> back to a clean `open`/ready state.

> [!WARNING]
> **`bd` supplies the priority order; bead-chain only picks the first.**
> `next_blocking_bug` returns the *first* ready bug with a dependent, trusting
> bd's server-side priority ordering. bead-chain never re-sorts bd's frontier
> (queue-driver-not-goal-engine) — so two blocking bugs resolve in bd's order,
> not any order this feature invents.

> [!WARNING]
> **A malformed `dependent_count` degrades to "not blocking".** A non-int /
> missing `dependent_count` is coerced to `0` inside `next_blocking_bug`, so a
> garbage value can only ever cause a bug to be *skipped*, never wrongly
> escalated.

> [!WARNING]
> **Container types can't sneak in as bugs.** `_exclude_type_arg` strips
> epic/milestone/gate/molecule server-side, and `next_blocking_bug` re-asserts
> `issue_type in BLOCKING_BUG_TYPES` client-side — a belt-and-suspenders guard
> against a future bd that ignored `--type`/`--exclude-type`.

> [!CAUTION]
> **Escalation never overrides a work-time block.** If the chosen bug is itself
> blocked (a `blocks`/`waits-for` edge wired after the `bd ready` snapshot),
> `_reject_if_blocked` refuses it and the waterfall falls through — bead-chain
> respects blocks at *claim* time, not just at close (the bdboard-oals fix). A
> blocking bug never gets to barrel past its own open blocker.

## Error Scenarios

| Trigger | Behavior | User sees |
|---------|----------|-----------|
| A ready bug has `dependent_count > 0` and no open blockers | Returned from tier 1, claimed, armed | `bead-chain: blocking bug detected -> prioritising <id>` |
| No ready bug has any dependents | `next_blocking_bug` returns `None`; fall through to epic-affinity / global-ready | (silent) normal tier-2/3 pick |
| Candidate bug is itself blocked (edge wired post-snapshot) | `_reject_if_blocked` returns `True`; waterfall falls through | `bead-chain: blocking bug candidate <id> has open blocker(s) [...] -- refusing to claim it ...` |
| Bug also stranded `in_progress` | Tier-0 recovery wins; bug recovered before any escalation | `bead-chain: found stranded in_progress bead <id> -- recovering before picking new work.` |
| `dependent_count` missing / non-int on a candidate | Coerced to `0`; bug skipped as non-blocking | (silent) bug stays in ordinary queue |
| Container leaks past `--type`/`--exclude-type` (bd drift) | Client-side `issue_type in BLOCKING_BUG_TYPES` check skips it | (silent) container never escalates |
| `bd ready` infra failure (bd missing/timeout/garbage JSON) | `BeadsError` propagates out of the waterfall | ` bead-chain stopping — \`bd ready\` failed: <err>` |

## Testing

The escalation tier has dedicated coverage:

- `tests/test_pick_respects_blocks.py` —
  `test_blocked_blocking_bug_is_skipped_falls_through` pins that a blocking-bug
  candidate flows through tier 1 of `pick_next_bead` and is refused *only* when
  it is itself blocked (then the waterfall falls through to the global-ready
  bead `A`). The harness wires `lifecycle.next_blocking_bug` and
  `open_blocker_ids` via monkeypatch to drive the exact tier under test.
- `tests/test_wisp_exclusion.py` —
  `test_blocking_bug_scan_never_includes_ephemeral` asserts
  `next_blocking_bug()` actually queries `bd` and never passes
  `--include-ephemeral`, so ephemeral wisps can't escalate.
- `tests/test_hooked_pinned_strands.py` neutralises the tier by stubbing
  `lifecycle.next_blocking_bug -> None`, confirming tiers 0/2/3 behave when no
  blocking bug exists.

To eyeball it manually: build a dict `{"id": "x", "issue_type": "bug",
"dependent_count": 1}`, monkeypatch `beads._run_bd` to return `[that dict]`,
and call `beads.next_blocking_bug()` — it should return the dict; flip
`dependent_count` to `0` and it should return `None`. Run the whole suite with
`pytest -q` (245 tests).

## Related

- [BugDiscoveryProtocol](BugDiscoveryProtocol.md) — the *filing* half of the bug
  story: how an agent files a blocking bug (P1 + `--blocks`) so it gains the
  dependent this feature escalates on.
- [NextBeadSelectionWaterfall](../Flows/NextBeadSelectionWaterfall.md) — the
  full four-tier waterfall this feature is tier 1 of, narrated step by step.
- [StrandedBeadRecovery](../Flows/StrandedBeadRecovery.md) — tier 0, which
  always outranks blocking-bug escalation (recovery beats every other rule).
- [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md) — why
  `_exclude_type_arg` keeps epics/milestones/gates/molecules out of the
  `bd ready --type=bug` escalation query.
- [QueueDriverNotGoalEngine](../Concepts/QueueDriverNotGoalEngine.md) — the SRP
  boundary behind "trust bd's priority order, only re-rank by blast radius" —
  the chain picks from bd's frontier, it never invents goals.
- [BdSubprocessTransport](../Concepts/BdSubprocessTransport.md) — the transport
  behind the `bd ready --type=bug` and `bd show` spawns this feature makes.
- [Features Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
