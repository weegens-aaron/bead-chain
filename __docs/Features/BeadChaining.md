# BeadChaining

## What It Does

BeadChaining drives your entire `bd ready` queue through wiggum's `/goal` mode
**one bead at a time** — probing for the next ready bead, claiming it, handing it
to the LLM-judged goal loop, closing it when the judges pass, and trotting on to
the next — until the queue drains (or a `--max=N` cap, an empty-queue, or
`Ctrl+C` halts it).

## Why It Exists

`bd ready` knows *what* should be worked next; wiggum's `/goal` mode knows *how*
to drive a single task to LLM-judged completion. Nothing connected the two — a
human had to eyeball `bd ready`, copy a bead's prompt into `/goal`, wait for the
judges, run `bd close`, and repeat by hand for every bead. BeadChaining is that
missing belt: it turns a queue plus a goal engine into an unattended,
steady-progress worker that respects beads' own ordering (priority, blockers,
gates) and never closes a bead the judges didn't sign off on.

Crucially, BeadChaining is **a queue driver, not a goal engine** — it owns only
the boundaries *between* beads (pick → claim → close → next) and delegates the
work-and-grade loop to wiggum. That single boundary is the design spine of the
whole plugin (see
[QueueDriverNotGoalEngine](../Concepts/QueueDriverNotGoalEngine.md)): the driver
must never grade completion itself, and must stop anyone *else* from grading by
fiat (that enforcement is [CloseGuard](CloseGuard.md)).

## How It Works

### User Perspective

The user types `/bead-chain` (optionally `/bead-chain --max=N`) from any repo
that uses `bd`. bead-chain announces itself, names the first bead, and then the
familiar `/goal` stream takes over. From there it is hands-off: each time a
bead's goal completes, bead-chain closes it and announces the next one. The user
sees a running tally (`#N completed this run`), epic start/rollup notices, and —
on drain — a `Good boy!` sign-off. `Ctrl+C` halts the chain at any point and
leaves the in-flight bead `in_progress` for recovery on the next run.

```
bead-chain starting…
BEAD-CHAIN ENGAGED!
First bead: bead_chain-mol-bps.1 — FlowDoc maintainer: Feature: BeadChaining
Will claim → /goal → close → repeat until `bd ready` is empty.
Press Ctrl+C to halt.
…(/goal stream for bead 1)…
bead-chain closed bead_chain-mol-bps.1 (#1 completed this run)
bead-chain claimed bead_chain-xyz — Next ready bead
…
bead-chain: no more ready beads. Closed 7 this run. Good boy!
```

### System Perspective

BeadChaining is a three-phase state machine wired entirely in
`register_callbacks.py` and implemented in `lifecycle.py`:

1. **Engage (once).** `handle_bead_chain_command` parses `--max=N`, runs the
   recovery/ready probe (`enforce_single_in_progress` → `next_ready`), runs the
   activation gauntlet (excluded-type refusal, work-time blocker recheck,
   recovery detection), **lazily registers** the turn-end / cancel hooks (so they
   land *after* wiggum's startup-registered hook), claims the bead, applies
   execution hints, arms `wiggum_state.start(prompt, mode="goal")`, and *returns
   the goal-prompt string* — the CLI runs it as the user's prompt, kicking off
   iteration 1.
2. **Iterate (every turn).** wiggum's `interactive_turn_end` hook runs first;
   bead-chain's `_on_interactive_turn_end` runs **after** and reads
   `wiggum_state.is_active()`. Still active ⇒ return `None`, let wiggum's
   continuation win. Just stopped ⇒ the judges passed, so
   `close_current_bead_success` closes the bead, then `activate_next_bead` picks
   the next via the four-tier waterfall (recovery → blocking bug → epic affinity
   → global ready), claims it, and returns a continuation dict.
3. **Halt.** Queue empties (`activate_next_bead` probes resolved gates, rolls up
   eligible epics, stops), the `--max=N` cap trips, or the user hits `Ctrl+C`
   (`_on_interactive_turn_cancel` stops the chain and leaves the bead
   `in_progress`).

```mermaid
sequenceDiagram
    participant User
    participant Cmd as handle_bead_chain_command
    participant BD as beads.py (bd CLI)
    participant State as state (BeadChainState)
    participant Wiggum as wiggum /goal + LLM judges
    participant Hook as _on_interactive_turn_end
    participant LC as lifecycle (close/pick/activate)

    User->>Cmd: /bead-chain [--max=N]
    Cmd->>BD: enforce_single_in_progress() / next_ready()
    BD-->>Cmd: ready bead dict (or None)
    Cmd->>BD: claim(bead_id) (bd update --claim)
    Cmd->>State: start(); current_bead = bead
    Cmd->>Wiggum: wiggum_state.start(goal_prompt, mode="goal")
    Cmd-->>User: returns goal prompt → CLI runs it
    loop every interactive turn
        Wiggum->>Hook: interactive_turn_end fires (wiggum first)
        Hook->>State: is_active()? / wiggum_state.is_active()?
        alt wiggum still cooking
            Hook-->>Wiggum: return None (let /goal continue)
        else wiggum stopped (judges passed)
            Hook->>LC: close_current_bead_success()
            LC->>BD: close(bead_id) (bd close --reason)
            Hook->>LC: activate_next_bead(just_closed)
            LC->>BD: pick_next_bead waterfall + claim
            alt next bead found
                LC->>Wiggum: wiggum_state.start(next prompt)
                LC-->>Hook: continuation dict
            else queue empty
                LC->>BD: probe_resolved_gates() + rollup_completed_epics()
                LC->>State: stop()
                LC-->>Hook: None
            end
        end
    end
    User-->>Hook: Ctrl+C → interactive_turn_cancel → state.stop() (bead left in_progress)
```

## Key Data Shapes

bead-chain never invents its own schema — it consumes the JSON `bd` emits and
produces exactly one dict (the runner continuation). A **ready/show bead dict**
(the shape `next_ready`, `show`, and `current_bead` carry) looks like:

```json
{
  "id": "bead_chain-mol-bps.1",
  "title": "FlowDoc maintainer: Feature: BeadChaining",
  "issue_type": "task",
  "status": "open",
  "priority": 2,
  "parent": "bead_chain-mol-bps",
  "dependent_count": 0,
  "waits_for": null,
  "labels": ["discover", "docs", "flowdoc"],
  "description": "Write __docs/Features/BeadChaining.md …",
  "acceptance_criteria": "file exists … manifest updated"
}
```

The **continuation dict** bead-chain returns from `activate_next_bead` to hand
wiggum the next bead (the only object bead-chain authors):

```json
{
  "prompt": "<the next bead's /goal prompt string>",
  "clear_context": true,
  "delay": 0.5,
  "reason": "bead_chain"
}
```

The in-process **chain state** singleton (`state.BeadChainState`) that gates
every turn:

```json
{
  "active": true,
  "current_bead": { "id": "bead_chain-mol-bps.1", "...": "full bead dict" },
  "completed_count": 1,
  "max_iterations": null
}
```

## API Surface

> [!NOTE]
> bead-chain is a terminal Code Puppy plugin with **no HTTP endpoints** (see the
> Endpoints note in the [FlowDoc Manifest](../_Manifest.md)). Its "surface" is
> one slash command plus host hooks and the `bd` subprocess contract, so the
> `-> Endpoint doc` column is N/A by design.

| Method | Path | Purpose | -> Endpoint doc |
|--------|------|---------|-----------------|
| `command` | `/bead-chain [--max=N]` → `register_callbacks.handle_bead_chain_command(command) -> str \| bool` | Engage the chain: probe, claim first bead, arm wiggum, return the goal prompt | N/A — no HTTP surface |
| `hook` | `register_callbacks._on_interactive_turn_end(agent, prompt, result, *, success, error) -> dict \| None` | Per-turn driver: close on judge-pass, pick + claim + arm next bead | N/A — host hook |
| `hook` | `register_callbacks._on_interactive_turn_cancel(prompt, *, reason) -> None` | Ctrl+C handler: stop the chain, leave the in-flight bead `in_progress` | N/A — host hook |
| `call` | `lifecycle.close_current_bead_success() -> dict \| None` | Close the just-finished bead (or halt on close-failure / pin / epic leak) | N/A — in-process |
| `call` | `lifecycle.activate_next_bead(just_closed) -> dict \| None` | Pick → claim → arm next bead, or drain (gate probe + epic rollup) and stop | N/A — in-process |
| `call` | `lifecycle.pick_next_bead(just_closed) -> dict \| None` | Four-tier selection waterfall (recovery → blocking bug → epic affinity → global) | N/A — in-process |
| `call` | `beads.next_ready() -> dict \| None` | `bd ready --exclude-type=… --json`, epic-refiltered client-side | N/A — `bd` subprocess |
| `call` | `beads.claim(id)` / `beads.close(id, reason=…)` / `beads.revert_to_open(id)` | `bd update --claim` / `bd close --reason` / `bd update --status=open` | N/A — `bd` subprocess |

## Implementation Map

| Responsibility | File path | Symbol |
|----------------|-----------|--------|
| `/bead-chain` entry: parse `--max`, probe, gauntlet, claim, arm wiggum, return prompt | `register_callbacks.py` | `handle_bead_chain_command` |
| `--max=N` flag parsing (`None` / int / `_PARSE_ERROR` sentinel) | `register_callbacks.py` | `_parse_max_iterations` |
| Lazy hook registration *after* wiggum (load-bearing ordering) | `register_callbacks.py` | `_ensure_hooks_registered` |
| Per-turn driver loop (close → next) | `register_callbacks.py` | `_on_interactive_turn_end` |
| Ctrl+C handler: stop chain, leave bead `in_progress` | `register_callbacks.py` | `_on_interactive_turn_cancel` |
| Close the just-finished bead; halt on close-failure / pin / epic-leak | `lifecycle.py` | `close_current_bead_success` |
| Pick → claim → arm next; drain (gate probe + rollup) + cap check | `lifecycle.py` | `activate_next_bead` |
| Four-tier next-bead waterfall | `lifecycle.py` | `pick_next_bead` |
| Startup single-in_progress invariant guard | `lifecycle.py` | `enforce_single_in_progress` |
| Recovery-vs-fresh decision (status ∈ recoverable) | `lifecycle.py` | `is_recovery_bead` |
| Parent-first epic claim for a true "what am I on" signal | `lifecycle.py` | `ensure_epic_in_progress` |
| `bd ready` head, epic-refiltered | `beads.py` | `next_ready` |
| `bd update --claim` / `bd close --reason` / `bd update --status=open` | `beads.py` | `claim` / `close` / `revert_to_open` |
| Single subprocess chokepoint (timeout + retry + JSON) | `beads.py` | `_run_bd` |
| Container-type refusal (epic/milestone/gate/molecule) | `beads.py` | `is_excluded_type` / `EXCLUDED_TYPES` |
| Chain state singleton (`active`, `current_bead`, `completed_count`, `max_iterations`) | `state.py` | `BeadChainState` |
| Per-bead execution hints (effort/model/agent_type) applied before arming | `execution_hints.py` | `apply_execution_hints` |
| Bead-dict → `/goal` prompt (+ recovery preamble) | `prompt.py` | `format_bead_as_goal` |

## Configuration

| Key | Default | Effect |
|-----|---------|--------|
| `--max=N` (CLI flag) | `None` (no cap) | Stop the chain after `N` beads complete this run; invalid/zero/negative values refuse to start (`_PARSE_ERROR`) |
| `EXCLUDED_TYPES` (`beads.py`) | `("epic", "milestone", "gate", "molecule")` | Container types filtered from `bd ready` server-side **and** re-filtered client-side; never claimed/closed |
| `DEFAULT_TIMEOUT` (`beads.py`) | `30.0` (seconds) | Per-`bd`-invocation timeout in `_run_bd` |
| `MAX_ATTEMPTS` (`beads.py`) | `3` | Initial try + up to 2 retries on **timeout only** (not on errors), with backoff |
| `state.max_iterations` | `None` | In-memory mirror of `--max=N`; reset to `None` on every `stop()` |
| `state.completed_count` | `0` | Per-run tally; reset on every `start()`, bumped only on a successful `close` |

> [!NOTE]
> There is no config file, env var, or `pyproject.toml`. The only runtime knob
> is `--max=N`; everything else is a module-level constant a maintainer edits in
> source. `bd` itself inherits the local user's repo + Dolt credentials.

## Edge Cases

> [!WARNING]
> **Hook registration order is load-bearing.** The turn-end hook is registered
> *lazily* on the first `/bead-chain` (`_ensure_hooks_registered`) precisely so
> it appends **after** wiggum's startup-registered hook. Register it eagerly at
> import and the order flips — bead-chain would read `wiggum_state.is_active()`
> *before* wiggum decides its fate and close every bead a turn early.

> [!WARNING]
> **An excluded container type must never reach `/goal`.** Driving wiggum at an
> epic/milestone/gate/molecule produces the `cannot close epic: N open child
> issue(s)` failure that halts the chain after wasted tokens. `is_excluded_type`
> is asserted at *three* boundaries (startup, pick, activate) as belt-and-
> suspenders against `bd ready` server-side filter leaks (see
> [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md)).

> [!WARNING]
> **A bead can be re-blocked or pinned *after* it was claimed.** `bd ready`
> filters blockers server-side, but a `blocks` edge or `pinned` flag can land
> between probe and claim. bead-chain rechecks `open_blocker_ids` at claim and
> activate time (reverting non-recovery blocked beads to `open`) and re-reads
> `is_pinned` at close time (respecting the pin, dropping the bead, trotting on
> without bumping the count) — see [WorkTimeBlockerGate](WorkTimeBlockerGate.md).

> [!IMPORTANT]
> **bead-chain's own closes bypass CloseGuard, but agent-issued ones don't.**
> `beads.close` shells out via `subprocess.run`, never traversing code_puppy's
> command runner, so [CloseGuard](CloseGuard.md) never fires on the chain's
> legitimate close. Any *agent*-issued `bd close` during a run is blocked — only
> the LLM judges (via this loop) may close a bead.

> [!CAUTION]
> **A drain is not a session boundary — bead state stays local until session
> close.** The loop never runs `bd dolt push`. Durability/sync is session-close's
> job, so an interrupted (Ctrl+C) chain's mutations live only in the local Dolt
> DB until the next session-close pushes them (see
> [SessionCloseDurability](../Concepts/SessionCloseDurability.md)).

> [!CAUTION]
> **Epic rollup runs ONCE per session, at drain — never per-bead.** Calling
> `bd epic close-eligible` after every child close let its server-side cascade
> sweep up unrelated epics (over-close bug `bead_chain-tfn`). The trade-off:
> parent epics may not close until the next session's rollup.

## Error Scenarios

| Trigger | Behavior | User sees |
|---------|----------|-----------|
| `bd` unreachable during the startup probe | `enforce_single_in_progress`/`next_ready` raise `BeadsError`; command bails before claiming anything | `bead-chain can't reach \`bd\`: …` |
| `bd ready` empty at start | Probe returns `None`; chain never engages | `No ready beads — bead-chain has nothing to fetch.` |
| First/next bead is an excluded container type | `is_excluded_type` true → refuse to arm wiggum; chain stops (or never starts) | `bead-chain refused … excluded container type (epic) …` |
| Bead has open work-time blockers at claim/activate | Reverted to `open` (unless recovery), chain refuses/stops | `bead-chain refused … open blocker(s) […]` |
| `bd close` fails after judges pass | Bead left `in_progress`; chain stops for inspection; recovered next run | `bead-chain couldn't close <id>: …` + `Bead … left in_progress` |
| Bead pinned mid-flight | Pin respected; bead dropped as current, count **not** bumped; chain keeps trotting | `bead <id> was pinned mid-flight -- respecting the pin …` |
| User hits `Ctrl+C` | `_on_interactive_turn_cancel` stops the chain; bead stays `in_progress` | `bead-chain halted due to cancelled.` + `Bead … left in_progress` |
| `--max=N` cap reached | `activate_next_bead` stops before picking another bead | `bead-chain: --max=N cap reached … Good boy!` |
| `--max` value invalid (non-int / ≤0) | `_parse_max_iterations` returns `_PARSE_ERROR`; refuse to start | `bead-chain: --max requires a positive integer …` |
| Queue empties (clean drain) | Gate re-probe → epic rollup → `state.stop()` | `bead-chain: no more ready beads. Closed N this run. Good boy!` |

## Testing

The suite is hermetic — it mocks the `bd` subprocess, so no live `bd` is needed:
`python -m pytest -q`. Key suites that exercise BeadChaining's behavior:

- `tests/test_pick_respects_blocks.py` — the four-tier waterfall honors
  work-time blockers across tiers.
- `tests/test_over_close_bug.py` / `tests/test_over_close_bug_e2e.py` — the
  once-per-session rollup (no per-bead cascade).
- `tests/test_hooked_pinned_strands.py` — recovery includes `hooked` strands;
  mid-flight pins are respected.
- `tests/test_gate_check_empty_queue.py` — empty-queue gate re-probe before
  declaring the chain done.
- `tests/test_excluded_container_types.py` — epics/milestones/gates/molecules
  never reach `/goal`.
- `tests/test_execution_hints.py` — hints applied before arming wiggum.

To smoke-test end to end: from a repo with at least one `bd ready` bead, run
`/bead-chain --max=1` and confirm it claims one bead, drives `/goal`, closes on
judge-pass, and stops at the cap with the ` … cap reached` message.

## Related

- [QueueDriverNotGoalEngine](../Concepts/QueueDriverNotGoalEngine.md) — the SRP
  boundary BeadChaining embodies: own the bead boundaries, delegate grading.
- [ChainStateSingleton](../Concepts/ChainStateSingleton.md) — the two
  singletons (`state` + `wiggum_state`) every turn is gated on.
- [ContainerTypeExclusion](../Concepts/ContainerTypeExclusion.md) — why epics
  never enter the chain (the three-boundary refusal).
- [BdSubprocessTransport](../Concepts/BdSubprocessTransport.md) — the
  `_run_bd` chokepoint behind every `bd` call.
- [SessionCloseDurability](../Concepts/SessionCloseDurability.md) — why the loop
  never pushes Dolt; durability is session-close's job.
- [ExecutionHints](../Concepts/ExecutionHints.md) — per-bead hints applied
  before arming wiggum.
- [RecoveryMode](RecoveryMode.md) — how a stranded `in_progress` bead is resumed.
- [WorkTimeBlockerGate](WorkTimeBlockerGate.md) — claim-time blocker recheck.
- [EpicAffinity](EpicAffinity.md) — staying inside an epic between beads.
- [BlockingBugPriority](BlockingBugPriority.md) — bugs with dependents cut the line.
- [CloseGuard](CloseGuard.md) — blocks agent-issued closes mid-chain.
- [EpicRollup](EpicRollup.md) — once-per-session drain-time epic auto-close.
- [BugDiscoveryProtocol](BugDiscoveryProtocol.md) — file-don't-close bug handling baked into every prompt.
- [GoalPromptEnrichment](GoalPromptEnrichment.md) — what `format_bead_as_goal` injects.
- [ChainIterationLoop](../Flows/ChainIterationLoop.md) — the step-by-step flow of this loop.
- [NextBeadSelectionWaterfall](../Flows/NextBeadSelectionWaterfall.md) — the pick waterfall in detail.
- [BeadClaimAndBlockerRecheck](../Flows/BeadClaimAndBlockerRecheck.md) — atomic claim + blocker safety.
- [StrandedBeadRecovery](../Flows/StrandedBeadRecovery.md) — startup recovery of in-progress work.
- [SessionEndEpicRollup](../Flows/SessionEndEpicRollup.md) — drain-time rollup flow.
- [GoalPromptConstruction](../Flows/GoalPromptConstruction.md) — assembling the `/goal` prompt.
- [Features Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
