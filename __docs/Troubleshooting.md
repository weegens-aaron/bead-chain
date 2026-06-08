# Troubleshooting (maintainer)

Diagnostic guide for when bead-chain misbehaves. Symptoms are grouped by the
subsystem they surface in; each row links to the doc that explains the intended
behavior. **Almost every entry has a "this is correct, not a bug" sibling** —
bead-chain is deliberately conservative, so a stall is usually the safety net
working, not failing.

> [!IMPORTANT]
> Golden rule of diagnosis: reach for `bd show <id> --json` first. The JSON
> view exposes `status`, `issue_type`, and `dependencies[].status` — the three
> fields every selection/gate/close decision is actually made from. The
> human-readable views can lag bd's per-parent tree cache; the JSON does not.

---

## Fast triage table

| Symptom | First check | Deep dive |
|---------|-------------|-----------|
| `/bead-chain` does nothing / "already running" | `state.active` wedged from a prior run | [ChainIterationLoop](Flows/ChainIterationLoop.md#common-issues) |
| Loop ends immediately with `No ready beads` | only containers left, or all work blocked | [ContainerTypeExclusion](Concepts/ContainerTypeExclusion.md) |
| Same `in_progress` bead re-driven every run | tier-0 recovery has a strand to drain | [StrandedBeadRecovery](Flows/StrandedBeadRecovery.md#common-issues) |
| "refused to activate … open blocker(s)" on a ready-looking bead | a `blocks`/`waits-for` edge added after `bd ready` | [BeadClaimAndBlockerRecheck](Flows/BeadClaimAndBlockerRecheck.md#common-issues) |
| "excluded container type" refusal | an epic/milestone/gate/molecule leaked the frontier | [ContainerTypeExclusion](Concepts/ContainerTypeExclusion.md) |
| A blocking bug isn't jumping the queue | bug has no dependents, or wrong type | [BlockingBugPriority](Features/BlockingBugPriority.md) |
| Bead state invisible on another machine | `bd dolt push` never ran at session close | [SessionCloseDurability](Concepts/SessionCloseDurability.md) |
| A `patrol`/recurring epic got auto-closed | epic missing its recurrence marker | [RecurringMoleculeProtection](Concepts/RecurringMoleculeProtection.md) |
| Fan-out-gated bead refused with all children "done" | a child isn't actually `closed`, or gate-mode ambiguity | [Fan-out gates](#fan-out-gates-the-write-only-mode-trap) |

---

## Chain won't start or won't advance

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `/bead-chain` does nothing / "already running" | `state.active` is still `True` from a prior run that didn't stop cleanly | The chain auto-stops on empty queue / cap / cancel; if it's wedged, cancel the turn (Ctrl+C) to fire the cancel hook, then re-engage. |
| Loop ends immediately with `No ready beads` | the only items are container types, or all work is blocked/pinned | `bd ready` to inspect; containers are filtered by design — see [ContainerTypeExclusion](Concepts/ContainerTypeExclusion.md). |
| Chain won't advance past a pinned bead | the current bead was `pinned` mid-flight; close is refused to honor the park | Unpin (`bd update <id> --unpin`) if it should proceed; otherwise the chain correctly drops it and moves on. |
| `--max` ignored | invalid value (non-int / ≤0) refused the engage, OR the cap was hit and `stop()` reset it to `None` | Pass `--max=N` with a positive integer each run; the cap is intentionally **not** sticky across runs. |
| Queue "empty" but you expected work | targets are held behind unresolved gates | The loop re-probes gates once on empty (`probe_resolved_gates`); a genuinely unresolved gate keeps its target out of `bd ready` until it closes. See [SessionEndEpicRollup](Flows/SessionEndEpicRollup.md). |

See [ChainIterationLoop](Flows/ChainIterationLoop.md) for the full loop.

---

## Selection picks the "wrong" bead

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Chain keeps re-picking the same `in_progress` bead | tier-0 recovery is firing: a prior run left a strand the judges never closed | Finish or `bd close <id>` the strand; tier 0 only yields while a recoverable strand exists. |
| Chain hops out of an epic mid-way | tier 2 only fires when an *unblocked* sibling exists; all remaining siblings are blocked or done | `bd ready --parent=<epic_id>`; blocked siblings correctly defer to the global frontier. See [EpicAffinity](Features/EpicAffinity.md). |
| Epic affinity never kicks in | the just-closed bead had no `parent`/`parent_id`/`epic_id` | Confirm the bead is actually parented; standalone beads correctly skip tier 2. |
| Waterfall returns `None` though `bd ready` shows work | tier-3 candidate was found blocked at recheck (no fall-through), or every ready bead is a container | `bd show <head> --json` and inspect `dependencies[].status`. See [NextBeadSelectionWaterfall](Flows/NextBeadSelectionWaterfall.md). |
| A blocking bug isn't jumping the queue | the bug has `dependent_count == 0`, or its type isn't in `BLOCKING_BUG_TYPES` (`("bug",)`) | `bd show <id> --json`; confirm `issue_type == "bug"` and at least one bead depends on it; add the dependency edge. See [BlockingBugPriority](Features/BlockingBugPriority.md). |

---

## Claim, blocker recheck, and the close guard

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| "refused to activate … open blocker(s)" on a ready-looking bead | a `blocks`/`waits-for` edge was added after `bd ready` ran, or bd version drift leaked a blocked bead | `bd show <id> --json`; only `closed` blockers satisfy. The post-ready recheck is the backstop. |
| `bd update --claim` fails and the chain halts | another agent claimed it in the race window, bd connectivity dropped, or the bead was deleted | `bd show <id>`; if already claimed elsewhere, stopping is correct. Restore bd connectivity and re-run. |
| "excluded container type" refusal | an upstream filter leaked an epic/milestone/gate/molecule onto the frontier | This is a real bug if it recurs — the waterfall must never return containers. See [ContainerTypeExclusion](Concepts/ContainerTypeExclusion.md). |
| A blocked bead got driven anyway | `open_blocker_ids` fail-opens on a flaky `bd show` | The close-time guard (`close_guard.py`) is the backstop; check bd connectivity. See [CloseGuard](Features/CloseGuard.md). |

See [BeadClaimAndBlockerRecheck](Flows/BeadClaimAndBlockerRecheck.md) for the recheck contract.

---

## Stranded-bead recovery

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| A crashed-on bead got re-run from scratch | the agent ignored `_RECOVERY_PREAMBLE`, or the bead was reverted to `open` (open blockers) so it returned as a *fresh* claim | Confirm status at restart with `bd show <id>`. |
| A `hooked` bead never gets recovered | running a pre-FB-12 build that queried only `--status=in_progress` | Recovery now enumerates `RECOVERABLE_STATUSES = (in_progress, hooked)`; upgrade. |
| Two beads stuck `in_progress`, only one moves per run | residue from a hard crash; recovery deliberately drains one head per iteration | Expected — extras drain one-at-a-time via tier 0. Let the chain run. |
| A stranded bead with a closed blocker still got reverted | stale `bd show` cache, or the blocker isn't actually `closed` | `bd show <id> --json`; only `closed` satisfies (`SATISFIED_BLOCKER_STATUSES`). |
| Recovery silently did nothing on startup | the strand query hit a bd outage and soft-failed | Look for `couldn't enumerate in_progress beads`; fix bd and re-run. Startup falls through to `next_ready` rather than halting. |

See [StrandedBeadRecovery](Flows/StrandedBeadRecovery.md) and [RecoveryMode](Features/RecoveryMode.md).

---

## Session-end rollup, durability, and sync

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Bead state (claim/close/revert) invisible on another machine | `bd dolt push` never ran — `git push` only carries `refs/heads/*`, not `refs/dolt/data` | Run `bd dolt push` at session close (gated on a configured Dolt remote). See [SessionCloseDurability](Concepts/SessionCloseDurability.md). |
| Interrupted chain's mutations missing | a Ctrl+C / crash skipped session-close, so the push never ran | Documented behavior — the **next** session-close pushes them. Don't rely on the drain path; bead-chain is a queue driver, not a sync engine. |
| A `patrol`/recurring epic got auto-closed | the epic carries none of the recurrence markers `is_recurring_epic` checks | Tag the molecule's epic with a `patrol` / `recurring` / `mol-type:patrol` label. See [RecurringMoleculeProtection](Concepts/RecurringMoleculeProtection.md). |
| Eligible epics didn't close this session | `bd epic close-eligible` errored (caught → warning), returned `[]`, or the queue never drained | Confirm `bd epic close-eligible --dry-run --json` returns valid JSON. See [SessionEndEpicRollup](Flows/SessionEndEpicRollup.md). |
| A parent epic closed one session late | rollup is once-per-session (`bead_chain-tfn`); cascade is single-pass to avoid sweeping unrelated epics | Expected trade-off (data safety over single-pass cascade); next session catches it. |

---

## Goal-prompt enrichment

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No `## Persistent Memories` block despite memories existing | this `bd` build lacks the `memories` subcommand, or it errored | Confirm `bd memories --json` works; the block is suppressed on any `BeadsError`. See [GoalPromptEnrichment](Features/GoalPromptEnrichment.md). |
| LLM graded against criteria it never saw | the bead's `acceptance_criteria` was empty, so the block rendered empty | Populate `acceptance_criteria`; the block only renders for a non-empty value. |
| `## Related Context` missing an edge | the edge type isn't one of the six in `_CONTEXT_EDGE_GLOSSES`, or it's a gating edge (`blocks`/`parent-child`) | Only non-gating context edges surface by design; gating edges are deliberately excluded. See [GoalPromptConstruction](Flows/GoalPromptConstruction.md). |

---

## Fan-out gates: the write-only-mode trap

> [!WARNING]
> `bd create --waits-for-gate any-children|all-children` **accepts** a mode but
> does **not** surface it anywhere machine-readable (verified on bd 1.0.5).
> `bd show --json` reports only `dependency_type: "waits-for"` and `bd dep list`
> prints just "via waits-for" — no `gate_mode`/`fan_out` field. So at read time
> you **cannot** distinguish `any-children` from `all-children`.

Practical consequences when a fan-out-gated bead (like this finalize bead)
behaves unexpectedly:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Gated bead refused though all children look done | a spawned child isn't actually `closed`, or a stale `bd list` view | `bd list --json` and check **every** issue with `parent == <spawner>`; close any non-`closed` straggler. |
| Gated bead "should" be ready under `any-children` but isn't | the chosen gate mode is invisible at read time, so the conservative path waits for all | Known bd limitation; recheck after a bd upgrade by looking for a `gate_mode` field in `bd show --json` `.dependencies[]`. |

---

## When in doubt

1. `bd show <id> --json` — status, type, and `dependencies[].status` drive every decision.
2. `bd ready` / `bd ready --parent=<epic>` — what the frontier actually offers.
3. `bd list --json` — to verify fan-out children are all `closed`.
4. Watch for soft-fail warnings (`couldn't …`) — bead-chain degrades gracefully and logs rather than halting, so the warning is your breadcrumb.

## Related

- [Architecture](Architecture.md) — system overview and component map.
- [CloseGuard](Features/CloseGuard.md) — the close-time backstop.
- [ContainerTypeExclusion](Concepts/ContainerTypeExclusion.md) — why containers never reach the frontier.
- [StrandedBeadRecovery](Flows/StrandedBeadRecovery.md) — recovery tier behavior.
- [SessionCloseDurability](Concepts/SessionCloseDurability.md) — the `bd dolt push` contract.
