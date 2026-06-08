# BeadClaimAndBlockerRecheck

## What Happens

Once the [NextBeadSelectionWaterfall](NextBeadSelectionWaterfall.md) has handed
back a single candidate bead, bead-chain does **not** blindly arm `/goal` with
it. It runs a short *activation gauntlet* that re-validates the candidate one
last time and then atomically claims it. In order: (1) refuse excluded
container types (epic / milestone / gate / molecule), (2) **re-check work-time
blockers fresh from `bd show`** even though `bd ready` already filtered them
server-side, (3) refuse unsatisfied molecule fan-out gates, (4) claim the
parent epic first then the bead itself with `bd update <id> --claim`, (5) stash
the bead as `current_bead`, apply its execution hints, and arm wiggum's `/goal`
loop.

The defining move is the **belt-and-suspenders blocker recheck**: `bd ready`
is the source of tiers 1-3, and it already excludes blocked beads server-side,
so this recheck should *never* fire. It exists because two things can lie — bd
version drift, and a `blocks` edge wired in the tiny window between the `bd
ready` probe and now. This is the `bdboard-oals` fix carried to the activation
boundary: bead-chain respects work-time blocks **at claim time, not just at
close time**. A blocked candidate is reverted to `open` (if it isn't a recovery
bead) and the chain stops rather than barrelling into a `bd close` that bd would
later reject.

> [!IMPORTANT]
> **Recovery beads skip the claim.** A bead surfaced by tier 0
> ([StrandedBeadRecovery](StrandedBeadRecovery.md)) is already `in_progress`, so
> calling `bd update --claim` again is at best a no-op and at worst a bd error.
> `is_recovery_bead` (`lifecycle.py:64`) gates the claim and the revert-on-block
> path: recovery beads are activated `recovery=True` and are exempt from the
> revert (they were already blocker-filtered upstream in `_unblocked_strands`).

## Trigger

This flow runs at **two** call sites, both armed with the candidate the
selection waterfall returned:

1. **Chain startup.** `register_callbacks.handle_bead_chain_command`
   (`register_callbacks.py:169`) probes once with `enforce_single_in_progress()`
   then `next_ready()`, then runs the same excluded-type / blocker /
   recovery-claim sequence inline before arming the first `/goal`
   (`register_callbacks.py:204`-`287`).
2. **Every subsequent iteration.** `lifecycle.activate_next_bead`
   (`lifecycle.py:544`) calls `pick_next_bead` (`lifecycle.py:460`) and then runs
   the activation gauntlet on its result (`lifecycle.py:660` onward) before
   handing the wheel to wiggum.

The two sites are deliberate near-duplicates: the startup path is the *first*
activation (no `just_closed` epic affinity yet), and `activate_next_bead` is
*every* activation thereafter. Both end at the identical claim + arm sequence.

## Outcome

Exactly one of the following happens to the candidate bead:

- **Claimed and armed.** A fresh, unblocked, non-container, non-fan-out-gated
  bead has its parent epic claimed (`ensure_epic_in_progress`,
  `lifecycle.py:398`), then itself claimed via `bd update <id> --claim`
  (`beads.py:claim`, `beads.py:731`). It becomes `state.current_bead`, its
  execution hints are applied (`apply_execution_hints`), and
  `format_bead_as_goal(bead, recovery=False)` arms wiggum's `/goal` mode.
- **Recovered and armed (no claim).** A recovery bead (already `in_progress`)
  skips the `claim` call entirely but follows the same arm path with
  `recovery=True`, prepending `_RECOVERY_PREAMBLE`.
- **Reverted + chain stopped (blocked).** A candidate found blocked at recheck is
  reverted to `open` via `revert_to_open` (`beads.py:736` →
  `bd update <id> --status=open`) — *unless* it's a recovery bead, which is left
  `in_progress` for inspection — and `state.stop()` halts the chain.
- **Refused + chain stopped (container leak).** A candidate that is an excluded
  container type (epic/milestone/gate/molecule) is refused outright and the
  chain stops — an upstream filter leak is a bug, not something to drive.
- **Refused + reverted (fan-out gate).** A candidate whose `waits_for:
  children-of(<spawner>)` gate has unclosed children is reverted (non-recovery)
  and the chain stops; the gate will satisfy once the children close.

No source files are touched — this flow only reads bd JSON and mutates bead
*status* (claim = `open`→`in_progress`; revert = `in_progress`→`open`).

```mermaid
flowchart TD
    Pick([candidate from selection waterfall<br/>pick_next_bead lifecycle.py:460]) --> CapChk{--max cap reached?<br/>activate_next_bead}
    CapChk -->|Yes| Stop1([emit_success; state.stop; return None])
    CapChk -->|No| Excl{is_excluded_type?<br/>beads.py:138}
    Excl -->|epic/milestone/<br/>gate/molecule| Stop2([refuse: emit_warning;<br/>state.stop; return None])
    Excl -->|No| Rec[recovery = is_recovery_bead<br/>lifecycle.py:64]
    Rec --> Blk[blockers = open_blocker_ids id<br/>beads.py:476<br/>bd show id --json]
    Blk --> HasBlk{open blocker(s)?}
    HasBlk -->|Yes & not recovery| Revert1[revert_to_open id<br/>beads.py:736<br/>bd update --status=open]
    HasBlk -->|Yes & recovery| LeaveIP[leave in_progress]
    Revert1 --> Stop3([state.stop; return None])
    LeaveIP --> Stop3
    HasBlk -->|No| Fan{_has_fan_out_gate_issue?<br/>lifecycle.py:733}
    Fan -->|Yes & not recovery| Revert2[revert_to_open]
    Fan -->|Yes| Stop4([state.stop; return None])
    Revert2 --> Stop4
    Fan -->|No| Epic[ensure_epic_in_progress bead<br/>lifecycle.py:398<br/>claim parent epic first]
    Epic --> Claim{recovery?}
    Claim -->|No| DoClaim[claim id<br/>beads.py:731<br/>bd update --claim]
    Claim -->|Yes| Skip[skip claim]
    DoClaim --> Cur[state.current_bead = bead]
    Skip --> Cur
    Cur --> Hints[apply_execution_hints bead]
    Hints --> Goal[format_bead_as_goal recovery=recovery<br/>prompt.py:613]
    Goal --> Arm([wiggum_state.start mode=goal<br/>return continuation dict])
```

## Step-by-Step

| # | What | Where (file:symbol) | Failure mode |
|---|------|---------------------|--------------|
| 1 | Safety brake: if `completed_count + 1 > max_iterations`, stop before touching the queue | `lifecycle.py:activate_next_bead` (`state.get_state().max_iterations`) | None — pure arithmetic on the singleton; emits the cap message and `state.stop()` |
| 2 | Pick the candidate via the four-tier waterfall | `lifecycle.py:activate_next_bead` → `lifecycle.py:pick_next_bead` | `BeadsError` → `emit_warning("bd ready failed")` + `state.stop()` + `return None` |
| 3 | Refuse excluded container types (epic/milestone/gate/molecule) | `lifecycle.py:activate_next_bead` → `beads.py:is_excluded_type` (`EXCLUDED_TYPES`, `beads.py:52`) | A leaked epic here would cause `cannot close epic: N open child issue(s)` downstream → refuse + `state.stop()` |
| 4 | Classify recovery vs fresh (status ∈ `{in_progress, hooked}`) | `lifecycle.py:is_recovery_bead` (`_RECOVERY_STATUSES` ← `beads.RECOVERABLE_STATUSES`, `beads.py:198`) | None — pure dict read; missing/empty status ⇒ `False` (treated as fresh) |
| 5 | **Blocker recheck:** re-fetch live blockers with `bd show <id> --json` and walk `dependencies[]` | `lifecycle.py:activate_next_bead` → `beads.py:open_blocker_ids` (`beads.py:476`) | `open_blocker_ids` soft-fails to `[]` on any `bd show` blip — close-guard is the backstop |
| 6 | If blocked: revert to `open` (non-recovery only) and stop the chain | `lifecycle.py:activate_next_bead` → `beads.py:revert_to_open` (`beads.py:736`) | Revert raises `BeadsError` → `emit_warning("also couldn't revert …")`; chain still stops |
| 7 | Refuse unsatisfied molecule fan-out gates (`waits_for: children-of(...)` with unclosed children) | `lifecycle.py:_has_fan_out_gate_issue` (`lifecycle.py:733`) | Soft-fails to `False` (treat as satisfied) on any `bd show`/`bd list` blip; revert (non-recovery) + `state.stop()` when it fires |
| 8 | Claim the **parent epic first** so bd's per-parent tree never goes stale | `lifecycle.py:ensure_epic_in_progress` (`lifecycle.py:398`) → `beads.py:claim` | Soft-fails internally — any error is swallowed; the child claim still proceeds |
| 9 | Claim the bead atomically (skipped for recovery beads) | `beads.py:claim` (`bd update <id> --claim`, `beads.py:731`) | `BeadsError` → `emit_warning("couldn't claim …")` + `state.stop()` + `return None` |
| 10 | Stash as current and apply execution hints (effort/model/agent_type) | `state.py:get_state().current_bead`; `execution_hints.py:apply_execution_hints` | Hints soft-fail per-hint; no-op when none present |
| 11 | Render the goal prompt and arm wiggum's `/goal` loop | `prompt.py:format_bead_as_goal(recovery=recovery)` (`prompt.py:613`); `wiggum_state.start(..., mode="goal")` | None — pure string assembly + state flip; returns the continuation dict |

## Data Transformations

The flow consumes one candidate bead dict and bd's `show` JSON, and produces
either an armed `/goal` continuation, a status mutation, or `None`. The hops:

- **candidate dict → claim verdict.** `is_recovery_bead` lowercases
  `bead["status"]` and tests membership in `_RECOVERY_STATUSES`
  (`{"in_progress", "hooked"}`). `True` ⇒ skip `claim`, arm `recovery=True`;
  `False` ⇒ claim then arm `recovery=False`.
- **`bead["id"]` → blocker id list.** `open_blocker_ids` re-fetches with
  `bd show <id> --json` (only `show` carries each dependency's `status` +
  `dependency_type`), then walks `bead["dependencies"]`: for each edge whose
  `dependency_type` ∈ `BLOCKING_DEP_TYPES` (`("blocks", "waits-for")`,
  `beads.py:165`) and whose `status` ∉ `SATISFIED_BLOCKER_STATUSES`
  (`frozenset({"closed"})`, `beads.py:170`), it collects `dep["id"]`. A
  non-empty list ⇒ revert + stop; empty ⇒ proceed.
- **`bead["waits_for"]` → fan-out gate verdict.** `_has_fan_out_gate_issue`
  (`lifecycle.py:733`) parses `"children-of(<spawner_id>)"`, then runs
  `bd list --json` and tests
  whether any issue with `parent == spawner_id` has `status != "closed"`. Any
  unclosed child ⇒ gate unsatisfied ⇒ revert + stop.
- **fresh bead → `in_progress` status.** `claim(str(bead["id"]))` shells
  `bd update <id> --claim`; the bead leaves `bd ready` and becomes the single
  in-flight bead.
- **blocked/gated bead → `open` status.** `revert_to_open(str(bead["id"]))`
  shells `bd update <id> --status=open`; the bead re-enters `bd ready` behind
  its blockers/gate.
- **claimed bead → goal prompt.** `format_bead_as_goal(bead, recovery=recovery)`
  renders the `Complete beads issue <id>: <title> …` body (with
  `_RECOVERY_PREAMBLE` prepended iff `recovery=True`) and the continuation dict
  `{"prompt", "clear_context": True, "delay": 0.5, "reason": "bead_chain"}`.

A representative `bd show <id> --json` record that `open_blocker_ids` inspects
(only `dependency_type`, `status`, and `id` of each dep are read):

```json
{
  "id": "bead_chain-mol-bps.12",
  "status": "open",
  "issue_type": "task",
  "title": "FlowDoc maintainer: Flow: BeadClaimAndBlockerRecheck",
  "parent": "bead_chain-mol-bps",
  "dependencies": [
    { "id": "bead_chain-bu5", "dependency_type": "blocks", "status": "closed" },
    { "id": "bead_chain-x3g", "dependency_type": "waits-for", "status": "open" }
  ]
}
```

The continuation dict this flow returns to the runner on a successful claim:

```json
{
  "prompt": "Complete beads issue bead_chain-mol-bps.12: ...",
  "clear_context": true,
  "delay": 0.5,
  "reason": "bead_chain"
}
```

## Performance Characteristics

- **Synchronous, in-process, every iteration.** The gauntlet runs on the
  calling thread inside `activate_next_bead` (and once inline at startup). No
  async, no threading.
- **Bounded `bd` round-trips per activation.** In the steady-state fresh-bead
  case: **1** `bd show` (blocker recheck via `open_blocker_ids`), **1** `bd show`
  + **1** `bd list` for the fan-out gate check (`_has_fan_out_gate_issue` — both
  early-return cheaply when the bead has no `waits_for` field, the common case),
  **≤1** `bd list` + **1** `bd update --claim` for the epic
  (`ensure_epic_in_progress`), and **1** `bd update --claim` for the bead. The
  fan-out `bd list --json` is the heaviest single call (it scans all issues),
  but it is skipped entirely unless the candidate carries a `waits_for` field.
- **Recovery beads are cheaper.** They skip the `claim` spawn entirely and are
  exempt from the revert path.
- **No N+1.** The one-bead-at-a-time discipline means exactly one candidate is
  activated per iteration — there is no per-collection fan-out here.
- **Every spawn rides the single chokepoint.** All `bd show` / `bd list` /
  `bd update` calls flow through `beads.py:_run_bd` (`beads.py:280`) with
  `DEFAULT_TIMEOUT = 30.0` and `MAX_ATTEMPTS = 3` retry/backoff — see
  [BdSubprocessTransport](../Concepts/BdSubprocessTransport.md).
- **No persistence here.** This flow flips bead status at most; it never
  pushes/pulls/exports. Durability is a session-close concern — see
  [SessionCloseDurability](../Concepts/SessionCloseDurability.md).

## Failure Handling

- **Blocker recheck is fail-open, backstopped at close.** `open_blocker_ids`
  returns `[]` on any `bd show` blip, so a transient failure can't strand the
  chain by mis-flagging a workable bead. The close-time guard
  (`close_guard.py`) is the final net that refuses to close a bead with open
  blockers.
- **Fan-out gate check is fail-safe-open.** `_has_fan_out_gate_issue` returns
  `False` (treat as satisfied) on any `bd show`/`bd list` error — it never halts
  the chain on infra noise; it only stops when it *positively* confirms an
  unclosed child.
- **Claim failure halts the chain cleanly.** A `BeadsError` from `claim` is not
  swallowed: `emit_warning("couldn't claim …")` + `state.stop()` + `return
  None`. We never drive a bead we couldn't claim.
- **Epic claim is best-effort.** `ensure_epic_in_progress` swallows every error
  internally — a failure to claim the parent epic never blocks the child claim
  or the chain (the epic just stays whatever it was; UI may show a stale tree).
- **Revert is best-effort.** If `revert_to_open` raises while unwinding a blocked
  or gated candidate, the warning fires but the chain still stops; the next run's
  recovery tier re-attempts the revert.
- **Container-type leak is a hard stop, not a revert.** An excluded type that
  reaches activation is a sign of an upstream filter bug; the chain refuses and
  stops rather than trying to "fix" it.
- **No compensation/rollback of disk work.** This flow only mutates bead status;
  `revert_to_open` is the clean inverse of `claim`. There is nothing else to
  undo.

## Key Log Messages

> [!NOTE]
> The live source log strings are emoji-prefixed (chain-link, no-entry, and
> test-tube glyphs). Emojis are omitted from this doc per the project's
> no-emoji-in-writes convention; the text after the prefix is verbatim.

| Log line | Where | Means |
|----------|-------|-------|
| `bead-chain refused to activate <id>: it has open blocker(s) [<ids>]. Respecting work-time blocks at claim time, not just at close. Stopping chain.` | `lifecycle.py:activate_next_bead` (`emit_warning`) | The mid-chain blocker recheck fired — a candidate `bd ready` should have filtered was found blocked; it's reverted (non-recovery) and the chain stops (`bdboard-oals` fix). |
| `bead-chain refused to start with <id>: it has open blocker(s) [<ids>]. Respecting work-time blocks at claim time, not just at close.` | `register_callbacks.py:handle_bead_chain_command` (`emit_warning`) | Same recheck, fired at startup on the very first candidate. |
| `reverted <id> to open` | `lifecycle.py:activate_next_bead` / `register_callbacks.py:handle_bead_chain_command` (`emit_info`) | A blocked/gated non-recovery candidate was successfully unwound back to the ready queue. |
| `also couldn't revert <id>: <exc>` | `lifecycle.py:activate_next_bead` / `register_callbacks.py` (`emit_warning`) | The revert itself failed; the chain still stops. |
| `bead-chain refused to activate <id>: it has an unsatisfied fan-out gate (waits_for: children-of(...) with unclosed spawned children). The gate will be satisfied once all children close. Stopping chain to avoid driving work that isn't ready yet.` | `lifecycle.py:activate_next_bead` (`emit_warning`) | The molecule fan-out gate check (`bead_chain-9sc` workaround) caught a spawner with unclosed children. |
| `bead-chain refused to activate <id>: it's an excluded container type (<issue_type>). An upstream filter leaked an epic into the chain — this is a bug.` | `lifecycle.py:activate_next_bead` (`emit_warning`) | A container bead (epic/milestone/gate/molecule) reached activation — refuse and stop. |
| `bead-chain couldn't claim <id>: <exc> — stopping.` | `lifecycle.py:activate_next_bead` (`emit_warning`) | `bd update --claim` failed; the chain stops cleanly rather than driving an unclaimed bead. |
| `bead-chain couldn't claim <id>: <exc>` | `register_callbacks.py:handle_bead_chain_command` (`emit_warning`) | The startup claim failed; `state.stop()` and `/bead-chain` aborts. |
| `bead-chain claimed <id> — <title>` | `lifecycle.py:activate_next_bead` (`emit_info`) | Happy path: the fresh bead was claimed and `/goal` is armed. |
| `bead-chain recovered <id> — <title>` | `lifecycle.py:activate_next_bead` (`emit_info`) | Happy path for a recovery bead: claim skipped, `/goal` armed with the recovery preamble. |
| `execution hints: <hints>` | `lifecycle.py:activate_next_bead` / `register_callbacks.py` (`emit_info`) | The bead carried recognized `execution_*` metadata that was applied to this `/goal` pass. |

## Common Issues

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Chain stops with "refused to activate … open blocker(s)" on a bead that looks ready | A `blocks`/`waits-for` edge was added after `bd ready` ran, or bd version drift leaked a blocked bead | `bd show <id> --json` and inspect `dependencies[].status`; only `closed` satisfies a blocker. Close/relax the blocker, then re-run `/bead-chain`. |
| `bd update --claim` fails and the chain halts | Another agent claimed the bead in the race window, bd connectivity dropped, or the bead was deleted | Check `bd show <id>`; if already claimed by someone else it's correct to stop. Resolve bd connectivity and re-run. |
| A recovery bead got reverted to `open` unexpectedly | It shouldn't — recovery beads are exempt from the revert path; if it happened, it was reclassified as fresh | Verify `is_recovery_bead` sees status ∈ `{in_progress, hooked}` (`bd show <id>`); a status typo/drift would make it look fresh. |
| Chain refuses with "excluded container type" | An upstream filter (`--exclude-type` / `is_excluded_type`) leaked an epic/milestone/gate/molecule | This is a real bug — the selection waterfall must not return containers. See [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md); file a bead. |
| A bead with a satisfied fan-out gate still got refused | Stale `bd list` view, or a spawned child isn't actually `closed` | `bd list --json` and check every issue with `parent == <spawner>`; any non-`closed` child gates. Close the stragglers. |
| Parent epic shows wrong child counts after a claim | bd's per-parent tree cache lags; `ensure_epic_in_progress` claims the epic first to minimize this, but UI can still lag | Navigate back to the parent in bd to refresh; the data is consistent, only the cached view lags. |
| Execution hints didn't apply | The bead's `execution_*` metadata key wasn't recognized, or a per-hint soft-fail | See [ExecutionHints](../Concepts/ExecutionHints.md); check the bead's metadata field names against the recognized set. |

## Related

- [NextBeadSelectionWaterfall](NextBeadSelectionWaterfall.md) — the four-tier
  picker that produces the single candidate this flow then claims.
- [StrandedBeadRecovery](StrandedBeadRecovery.md) — tier 0; its recovery beads
  enter this flow already `in_progress` and skip the claim. Shares
  `open_blocker_ids` / `revert_to_open`.
- [ChainIterationLoop](ChainIterationLoop.md) — the outer loop that calls
  `activate_next_bead` (and thus this flow) on every iteration.
- [GoalPromptConstruction](GoalPromptConstruction.md) — consumes the claimed
  bead this flow surfaces and renders it as the `/goal` prompt.
- [SessionEndEpicRollup](SessionEndEpicRollup.md) — the opposite end of the
  loop: what runs when the picker (and thus this flow) has nothing left to claim.
- [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md) — why epics /
  milestones / gates / molecules are refused at the activation boundary.
- [ExecutionHints](../Concepts/ExecutionHints.md) — the `execution_*` metadata
  applied to the serial drive right after the claim, before arming `/goal`.
- [BdSubprocessTransport](../Concepts/BdSubprocessTransport.md) — the transport
  behind the `bd show` / `bd list` / `bd update` spawns this flow makes.
- [ChainStateSingleton](../Concepts/ChainStateSingleton.md) — holds
  `current_bead` (set here) and `max_iterations` (the safety brake).
- [QueueDriverNotGoalEngine](../Concepts/QueueDriverNotGoalEngine.md) — the SRP
  boundary: this flow claims and arms but never owns durability or goal logic.
- [SessionCloseDurability](../Concepts/SessionCloseDurability.md) — why this
  flow flips status but never pushes bead state.
- [RecurringMoleculeProtection](../Concepts/RecurringMoleculeProtection.md) —
  related fan-out/molecule handling the gate check guards against.
- [Flows Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
