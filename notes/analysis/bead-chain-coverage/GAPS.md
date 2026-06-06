# bead-chain Coverage — Consolidated Issues & Gaps

**Synthesis bead:** `bead_chain-hkb` · **Epic:** `bead_chain-10f`
**Inputs:** the 9 completed section findings in this directory (`01`–`09`).
**Nature:** a mechanical merge — every gap below is traceable to a section row;
no new analysis, just consolidation, dedup, severity × value ranking, and
concrete follow-up bead recommendations. This file files **no beads itself**;
it hands a planner a ready-to-pour shortlist.

---

## Executive summary

bead-chain is a **serial queue driver**: it chains the `bd ready` frontier into
code-puppy/wiggum's `/goal` loop, one bead at a time. Measured against the full
bd 1.0.4 feature surface (the 9-chapter field guide), it leverages a **thin but
correct slice** — `blocks`-edge gating (with defence-in-depth), atomic `--claim`,
`in_progress` recovery, judge-only close, and once-per-session epic rollup. On
its hot path it is sound.

The gaps cluster into **three stories**:

1. **Container/handle beads leak onto `bd ready` and stall the chain.** Three
   independent sections (anatomy `milestone`, gates `gate`, swarms `molecule`)
   independently discovered the *same bug class*: `EXCLUDED_TYPES = ("epic",)`
   only excludes epics, so other non-task container/handle types can be handed
   to `/goal` as if they were code work — they have nothing to do, and the
   close-guard then blocks closing them, **stranding the loop**. This is the
   single highest-leverage fix: **one constant edit closes three P1 hazards.**

2. **bd is already holding free data that bead-chain drops on the floor.** The
   `bd ready --json` dict carries `acceptance_criteria` and `labels`; the goal
   prompt reads neither. The agent is judged on a "done" contract the prompt
   never showed it. Surfacing `acceptance_criteria` is near-zero-cost, high-value.

3. **Sync durability falls through a seam.** Nobody in the documented
   end-to-end loop — not bead-chain, not the `AGENTS.md` session-close protocol
   — actually runs `bd dolt push`. On a single dev box this is harmless; on a
   fresh clone / CI / second machine every claim/close/revert is stranded
   locally. This needs a human *policy* call (where should sync live?), not just
   code.

Everything else is either a **deliberate boundary** (sequential-only is the
plugin's whole contract; not owning sync/hygiene is the queue-driver SRP stance)
or a **narrow-window enrichment** (soft-edge context, memory injection,
`execution_*` hints, mid-flight status strands).

### The single biggest insight

> **bead-chain's biggest gap is not a missing feature — it's that three
> different bd container/handle types (`milestone`, `gate`, `molecule`) all leak
> onto `bd ready` through the same one-line hole (`EXCLUDED_TYPES = ("epic",)`),
> and the close-guard then makes each leak a chain *stall*. One constant edit
> plus a regression test closes three P1 hazards at once. The second-biggest is
> free: `acceptance_criteria` is already on the ready dict and the goal prompt
> just doesn't render it — so LLM judges grade beads against a contract the
> prompt withheld.**

(Recorded to the kennel and recommended for `bd remember`.)

---

## Capability matrix

The filled matrix lives in [`README.md`](./README.md#capability-matrix-filled-by-the-synthesis-bead-bead_chain-hkb).
Compact restatement (A = Available, L = Leveraged):

| # | Area | A? | L? | Top sev | Gaps | Headline |
|---|------|----|----|---------|------|----------|
| 1 | Anatomy |  | Partial (6/~35 fields) | **P1** | 7 | drops `acceptance_criteria`/`labels` it already holds; `milestone` not excluded |
| 2 | Dependency graph |  | Partial (`blocks` full) | P2 | 5 | 10 advisory edges never surfaced as context; generic `waits-for` unhonored off `bd ready` |
| 3 | Status lifecycle |  | Partial (1/7 statuses) | P2 | 7 | only `in_progress` inspected; `pinned`/`hooked` mid-flight strands invisible |
| 4 | Memories & recall |  | **None** | P2 | 3 | zero memory bridged into the goal prompt; no `bd remember` nudge |
| 5 | Formulas & molecules |  | Partial (rollup only) | P2 | 5 | `mol-type` blindness; 3-segment-id fear disproven |
| 6 | Gates & coordination |  | Partial (`blocks` implicit) | **P1** | 6 | `gate` beads leak as work; `bd gate check` never advances gates |
| 7 | Swarms |  | Partial (atomic claim) | **P1** | 5 | `molecule` beads leak as work; `execution_*` hints dropped |
| 8 | Data layer (Dolt) |  | Partial (local writes) | **P1** | 5 | no `bd dolt push` anywhere in the documented loop |
| 9 | Quality & hygiene |  | **None** (graph hygiene) | P2 | 6 | no `bd lint` gate — drives beads missing `## Acceptance Criteria` |

---

## Severity × value ranking (the deduped inventory)

Every gap from the 9 sections, deduped and ordered by **severity first, then
value/leverage** (cheap-fix-closing-real-hazard beats expensive nice-to-have).
"Source" cites the originating section + its local gap number.

### P1 — silently dropped where it changes which bead runs or how it's framed

| Rank | Gap (deduped) | Source(s) | Value / leverage | Recommended follow-up |
|------|---------------|-----------|------------------|-----------------------|
| 1 | **Container/handle types leak onto `bd ready` and stall the chain.** `EXCLUDED_TYPES = ("epic",)` (`beads.py:41`) doesn't exclude `milestone` (anatomy), `gate` (gates), or `molecule` (swarms). Each is a ready leaf with no code work; close-guard then blocks closing it → stall. | anatomy#4, gates#2, swarms#1 (3× P1, same bug class) | **Highest.** One constant edit + one regression test closes 3 P1 stall hazards. | **FB-1** (below) |
| 2 | **`acceptance_criteria` dropped from the goal prompt** though it's already a key on the `bd ready --json` dict. Agent re-derives "done" from the description; LLM judges grade against criteria the prompt never showed. | anatomy#1 | **High, near-zero cost** (data in hand). Pairs with lint gap (ch09#1). | **FB-2** |
| 3 | **`bd gate check` is never run.** Resolvable-but-unresolved timer/`gh:run`/`gh:pr` gates keep their target out of `bd ready` → chain sees an empty queue and stops short of ready-pending-poll work. | gates#1 | Medium. One shell-out on the probe pass before declaring queue empty. | **FB-3** |
| 4 | **Nobody runs `bd dolt push`.** Neither bead-chain (drain path `lifecycle.py:517-524`) nor the `AGENTS.md` session-close loop (which pushes `refs/heads/*`, not `refs/dolt/data`). Cross-machine durability falls through the seam; embedded Dolt DB is git-ignored. | data-layer#1, data-layer#2 (2× P1) | High **but needs a policy decision** (where should sync live?). | **FB-4** |

### P2 — feature unused where leveraging it would materially improve goal quality

| Rank | Gap (deduped) | Source(s) | Recommended follow-up |
|------|---------------|-----------|-----------------------|
| 5 | **No `bd lint` gate at claim.** bead-chain drives beads missing required template sections (e.g. a `task` with no `## Acceptance Criteria`) — the exact case the project memory hit after a `--graph` import. Tight pairing with P1#2. | quality#1 | **FB-5** |
| 6 | **No memory injection / no `bd remember` nudge.** Goal prompt bridges *none* of bd's memory layer; the done-checklist never tells the agent to record a durable insight. Every bead starts cold. | memories#1, memories#2, memories#3 | **FB-6** |
| 7 | **`design` and `labels` dropped** from the prompt though `labels` is on the ready dict and `design` is the conventional home for `decision`/`spike` beads. (bead-chain even hand-rolls a `[bead-chain:triaged]` *description* sentinel because labels were "unverified" — now verified present.) | anatomy#2, anatomy#3 | **FB-7** (can ride with FB-2) |
| 8 | **`execution_*` metadata hints dropped.** `execution_model`/`effort`/`agent_type`/`mode` (free-form `metadata`) never read, so they can't shape even the single `/goal` pass. Serial-compatible — no parallelism needed. | swarms#2 | **FB-8** |
| 9 | **`mol-type` blindness — `patrol` & wisp.** A poured `patrol` molecule (recurring monitor) is driven as plain `work` and then *closed* by `close-eligible`, defeating its recurrence; leaked wisp-type beads are neither excluded nor promotable/burnable. | formulas#2, formulas#4 (swarm sub-case → FB-1) | **FB-9** |
| 10 | **Generic `waits-for` edges unhonored off `bd ready`.** `open_blocker_ids` checks only `blocks`; `_has_fan_out_gate_issue` matches only the `children-of(...)` string. A stranded `in_progress` bead re-gated by a generic `waits-for` would be re-driven (the bdboard-oals class for a second gating edge). | dependency#1 | **FB-10** |
| 11 | **Soft context edges never surfaced.** The 6 context-bearing edges (`related`, `relates-to`, `tracks`, `discovered-from`, `caused-by`, `validates`) are never put in the goal prompt — the agent works blind to provenance, causal bug links, and validating tests. (Correct to ignore for *gating*; the gap is *context*.) | dependency#2 | **FB-11** |
| 12 | **`pinned`/`hooked` mid-flight strands are invisible.** Recovery only queries `--status=in_progress`; a bead moved to `hooked`/`pinned` mid-flight is invisible to both `bd ready` and recovery. A `pinned` bead reaching `close()` would also fail (needs `--force`) and halt. | lifecycle#1, lifecycle#2 | **FB-12** |
| 13 | **Fan-out aggregation mode hardcoded all-children.** An any-children waiter that should be READY after the first child closes is wrongly refused/reverted. (Partly upstream: bd doesn't surface the mode.) | gates#3 | **FB-13** (gated on bd surfacing the mode) |

### P3 — minor gap; workaround exists or impact is narrow

| Gap (deduped) | Source(s) | Disposition |
|---------------|-----------|-------------|
| `supersedes` ignored — could drive redundant work on a superseded-but-open bead. | dependency#3 | Optional soft-exclusion bead. |
| `dependent_count` composition unverified — blocking-bug escalation may fire on soft-edge-only dependents. | dependency#4 | Verification spike (don't mutate live DB). |
| `deferred`/`defer`/`undefer` unused — `revert_to_open` risks a re-pick loop for "picked but not-now" beads. | lifecycle#3 | Consider `bd defer` for clean unwind. |
| `bd dep cycles`/`graph check` never run — write-time prevention has documented bypasses. | quality#2 | One-shot `graph check` at startup. |
| `bd orphans` never run — commit↔bd drift invisible. | quality#3 | Report-only at drain. |
| No `mol stale --blocking` probe — complete-but-unclosed mols can wedge the frontier. | formulas#5 | Probe-pass bead. |
| Once-per-session rollup keeps a parent epic open one session longer. | formulas#6 | Accepted `bead_chain-tfn` tradeoff; monitor. |
| `bd audit record`/`label` never called — empty SFT/RL trail despite richest interaction stream. | swarms#3 | Opt-in audit emit. |
| Ctrl+C leaves bead `in_progress` with no sync — invisible to machine B. | data-layer#3 | Document; optional push-on-cancel. |
| No `issues.jsonl` fallback (`export.auto=false`) — local Dolt DB is the only copy. | data-layer#4 | Document; deliberate `export.auto` if a git audit trail is wanted. |
| Fan-out workaround scans all issues per `waits_for` bead — O(all issues). | gates#6 | Narrow to `--parent=<spawner>`. |
| `notes`/`context` never surfaced — cross-iteration scratch invisible. | anatomy#5 | Fold into recovery preamble. |
| Done-checklist nudges code linters but not graph hygiene (`bd lint`/`graph check`). | quality#6 | Extend close-out reminder. |

### P4 — cosmetic / future-proofing / deliberate boundary / disproven

| Gap | Source(s) | Disposition |
|-----|-----------|-------------|
| **3-segment formula-epic id rollup** ("the suspected headline gap"). | formulas#1 | **DISPROVEN** — no id parsing exists; bd rolls up 2- & 3-segment ids identically. Regression-locked by `test_formula_epic_rollup.py`. **Do not reintroduce id parsing.** |
| `estimate`/`due`/`defer`, `assignee` dropped. | anatomy#6, anatomy#7 | YAGNI for a serial single-agent loop. |
| `--defer <when>` flag unused on `bd create`; operational-state axis untouched; `revert_to_open` freeform jump; close-guard only polices `closed`. | lifecycle#4,#5,#6,#7 | Document as intentional; revisit only if observed. |
| `external:proj:cap` cross-project deps unaddressed. | dependency#5 | Out of scope for single-repo driver. |
| No `bd dolt pull` at startup. | data-layer#5 | Future-proof once remotes are in use. |
| Merge-slot / cross-rig `bead` gates / federation wake-ups unhandled. | gates#4, gates#5 | Out of scope for single-rig drains. |
| `bd swarm validate`/`status` observability; `## Required Skills` prose not parsed. | swarms#4, swarms#5 | Intentional — routing is meaningless for one worker; bd doesn't route either. |
| `bd preflight` correctly unused (contributor checklist, not a graph gate). | quality#5 | **Non-gap** — never wire it into the loop. |
| **Sequential-only / no wave parallelism.** | swarms (boundary) | **Deliberate, load-bearing boundary** — the single-in_progress invariant *is* the plugin. Not a defect. |

---

## Dedup & cross-section reconciliation notes

- **Three P1s → one root cause.** anatomy#4 (`milestone`), gates#2 (`gate`), and
  swarms#1 (`molecule`) are the same `EXCLUDED_TYPES` hole. Merged into **FB-1**.
  The `epic` exclusion already in place is the proven template.
- **`acceptance_criteria` appears twice.** anatomy#1 (don't *render* it) and
  quality#1 (don't *lint* for it) are two faces of the same contract. FB-2 (render
  what's there) and FB-5 (lint for what's missing) are complementary, not dupes.
- **`swarm` mol-type blindness** is recorded in both formulas#3 and swarms#1;
  it's subsumed by the `molecule`-type exclusion in **FB-1** (excluding the
  `molecule` type means poured/swarm molecules are never driven as leaf work).
- **`waits-for` is split correctly across sections** by design: the *edge*
  semantics are dependency#1 (FB-10); the *fan-out gate* mode is gates#3 (FB-13);
  the *molecule* origin is formulas (gate-shaped, not mol-shaped). No double count.
- **`blocked` is two things** — the chapter-3 *status* (never set by bead-chain)
  vs the chapter-2 *edge* (fully honored). Counted once each, in their own areas.
- **`close-eligible` is not ch09 hygiene** — chapter 9 never mentions it; it's a
  formulas/lifecycle rollup whose data-layer effects are audited in section 08.
  Section 09 records this explicitly so the matrix doesn't credit it as a
  hygiene tool.
- **`until` is correctly ignored** (dependency notes) — non-gating per the guide;
  recorded as a *non-gap* so synthesis doesn't mistake it for a missed edge.

---

## Prioritized top-gaps shortlist → recommended follow-up beads

Concrete, ready-to-pour. **Recommendations only** — a planner/human should
review scope before filing (per the framework, the synthesis bead files none).
Each carries a suggested `bd create` and a rationale.

### FB-1 — Exclude all non-workable container/handle types from the queue ⭐ TOP

*Closes 3 P1 stall hazards (anatomy#4, gates#2, swarms#1) with one constant edit.*

```bash
bd create --type=bug --priority=1 \
  --title='Exclude milestone/gate/molecule from EXCLUDED_TYPES (chain stall on leaked container beads)' \
  --description='EXCLUDED_TYPES = ("epic",) (beads.py:41) only excludes epics. milestone (anatomy#4), gate (gates#2), and molecule (swarms#1) are container/handle types that can appear as ready leaves on bd ready; next_ready() hands them to /goal as if they were code work. They have nothing to do, and close_guard then blocks closing them -> the chain stalls. Fix: extend EXCLUDED_TYPES to ("epic","milestone","gate","molecule"); the existing server-side --exclude-type + client-side is_excluded_type double filter already supports a tuple. Add a regression test mirroring the epic-exclusion tests. ## Acceptance Criteria\n- EXCLUDED_TYPES covers epic, milestone, gate, molecule\n- a ready milestone/gate/molecule is never returned by next_ready()/pick_next_bead\n- regression test asserts each type is filtered server- and client-side'
```

### FB-2 — Render `acceptance_criteria` in the goal prompt ⭐ HIGH/CHEAP

```bash
bd create --type=task --priority=1 \
  --title='Surface acceptance_criteria in format_bead_as_goal (judges grade on a hidden contract)' \
  --description='acceptance_criteria is already a key on the bd ready --json dict but format_bead_as_goal (prompt.py:258) never reads it. LLM judges verify completion against criteria the prompt never showed. Render bead["acceptance_criteria"] as an "## Acceptance Criteria" block when present. ## Acceptance Criteria\n- when the bead dict has non-empty acceptance_criteria, the goal prompt includes it under a clear heading\n- absent/empty -> no change\n- unit test on prompt assembly'
```

### FB-3 — Run `bd gate check` on the probe pass before declaring the queue empty

```bash
bd create --type=task --priority=1 \
  --title='Tick bd gate check before declaring the ready queue empty' \
  --description='bead-chain never runs bd gate check, so resolvable timer/gh:run/gh:pr gates keep their targets out of bd ready and the chain stops short. Add a bd gate check (opt-in --escalate) on the empty-queue probe pass (lifecycle.py:517-524), soft-fail on error. ## Acceptance Criteria\n- on empty queue, bd gate check runs once before stop\n- newly-resolved gates re-open their targets for the next iteration\n- failure warns, never halts (mirror rollup soft-fail)'
```

### FB-4 — Decide & wire Dolt sync policy (needs a human call first)

```bash
bd create --type=decision --priority=1 \
  --title='Where should bd dolt push live in the bead-chain end-to-end loop?' \
  --description='Nobody in the documented loop runs bd dolt push: bead-chain drain (lifecycle.py:517-524) does not, and AGENTS.md session-close pushes refs/heads/* not refs/dolt/data. On a single box this is fine; on fresh clone/CI/second machine every claim/close/revert is stranded locally. DESIGN: choose between (a) bead-chain pushes on successful drain when bd dolt remote list is non-empty (soft-fail), (b) add bd dolt push to the AGENTS.md session-close protocol, or (c) explicitly document local-only as intended. Then file the implementing task. ## Success Criteria\n- a written decision on where sync responsibility lives\n- if (a)/(b): a follow-up task filed with the concrete change'
```

### FB-5 — Lint beads at claim time (pairs with FB-2)

```bash
bd create --type=task --priority=2 \
  --title='Run bd lint <id> at claim time and surface warnings into the goal prompt' \
  --description='bead-chain drives beads off bd ready without checking the template contract; project memory records bd lint flagging every task "Missing: ## Acceptance Criteria" after a --graph import. Run bd lint <id> on claim; inject warnings into the prompt (or skip+warn). ## Acceptance Criteria\n- claim path runs bd lint <id>\n- warnings appear in the goal prompt or cause a logged skip\n- soft-fail if bd lint is unavailable'
```

### FB-6 — Bridge bd memory into the loop (inject digest + nudge `bd remember`)

```bash
bd create --type=task --priority=2 \
  --title='Inject a bd memories/prime digest into the goal prompt and nudge bd remember at done' \
  --description='bead-chain bridges none of bd memory (memories#1/2/3). Prepend a bd memories (or bd prime "## Persistent Memories") digest into format_bead_as_goal, and add a "record durable insights via bd remember --key=" step to the done-checklist. Decide the bd-memories <-> host Kennel policy (bridge vs document the split). ## Acceptance Criteria\n- goal prompt includes a memory digest when memories exist\n- done-checklist nudges bd remember\n- a one-line policy note on the bd/Kennel split'
```

### FB-7 — Surface `design` + `labels` in the prompt (can ride with FB-2)

```bash
bd create --type=task --priority=2 \
  --title='Surface design and labels in the goal prompt; reconsider the description-based triage sentinel' \
  --description='labels is on the ready dict and design is the conventional decision/spike field; neither reaches the prompt (anatomy#2/#3). Surface both when populated, and reconsider moving the [bead-chain:triaged] marker from a description sentinel onto a real bd label (now that labels are verified present). ## Acceptance Criteria\n- labels and non-empty design appear in the prompt\n- a recommendation on the triage-marker-as-label migration'
```

### FB-8 — Map `execution_*` hints onto the serial drive

```bash
bd create --type=task --priority=2 \
  --title='Read execution_* metadata hints to shape the single /goal pass' \
  --description='execution_model/effort/agent_type/mode (free-form metadata, swarms#2) are never read. Map recognized keys onto the serial drive (effort->reasoning budget, model->model select, agent_type->agent). No parallelism required. ## Acceptance Criteria\n- recognized execution_* keys influence the /goal invocation\n- unknown keys ignored; absent metadata -> no change'
```

### FB-9 — Protect `patrol` molecules + handle leaked wisps

```bash
bd create --type=task --priority=2 \
  --title='Exclude patrol molecules from close-eligible rollup; handle leaked wisp-type beads' \
  --description='A poured patrol molecule (recurring monitor) is driven as plain work and then closed by close_eligible_epics (beads.py:526), defeating recurrence (formulas#2). Detect mol-type=patrol (or template label) and exclude from bd epic close-eligible. Also confirm whether wisp-type beads surface on bd ready; if so, add them to the exclusion filter (formulas#4). ## Acceptance Criteria\n- patrol-type molecule epics are not auto-closed by rollup\n- wisp leakage onto bd ready is confirmed/closed'
```

### FB-10 — Honor generic `waits-for` as a work-time blocker

```bash
bd create --type=task --priority=2 \
  --title='Treat generic waits-for edges as work-time blockers in open_blocker_ids' \
  --description='open_blocker_ids checks only BLOCKING_DEP_TYPES=("blocks",) (beads.py:75) and _has_fan_out_gate_issue only matches the children-of(...) string, so a generic waits-for edge (bd dep add B A --type=waits-for) is honored only by bd ready server-side -- bypassed by the recovery tier (dependency#1). Add "waits-for" to BLOCKING_DEP_TYPES. ## Acceptance Criteria\n- a stranded in_progress bead gated by a generic waits-for is reverted, not re-driven\n- regression test for the recovery-tier path'
```

### FB-11 — Fold soft context edges into the goal prompt

```bash
bd create --type=task --priority=2 \
  --title='Surface non-gating context edges (discovered-from/caused-by/validates/related) in the prompt' \
  --description='The 6 context-bearing edges are never surfaced (dependency#2); the agent works blind to provenance, causal bug links and validating tests. Fold a bead'"'"'s non-gating edges into a "related context" block in the goal prompt. Correct to ignore for gating; this is about context. ## Acceptance Criteria\n- when present, discovered-from/caused-by/validates/related appear as context\n- gating behavior unchanged'
```

### FB-12 — Widen recovery to `wip`/`frozen` strands; guard `pinned` close

```bash
bd create --type=task --priority=2 \
  --title='Detect hooked/pinned mid-flight strands and avoid pinned-close halts' \
  --description='Recovery only queries --status=in_progress (beads.py:251); a bead moved to hooked/pinned mid-flight is invisible to both bd ready and recovery (lifecycle#2). Also, closing a pinned bead requires --force, so a pinned bead reaching close() would halt the loop (lifecycle#1). Widen the stranded-work query (e.g. also enumerate hooked) and skip/handle pinned at pick time. ## Acceptance Criteria\n- hooked/pinned strands are surfaced to recovery or explicitly handled\n- a picked pinned bead does not halt the chain'
```

### FB-13 — Honor any-children fan-out mode (gated on bd surfacing it)

```bash
bd create --type=task --priority=2 \
  --title='Honor any-children waits-for-gate mode once bd surfaces it' \
  --description='_has_fan_out_gate_issue hardcodes all-children (gates#3); an any-children waiter that should be READY after the first child closes is wrongly refused/reverted. bd v1.0.4 does not surface the mode in show/dep list, so until then skip the revert when the mode is unknown; honor any-children once available. ## Acceptance Criteria\n- when mode is unknown, do not wrongly revert an otherwise-ready waiter\n- when bd exposes any-children, it is honored'
```

> **P3/P4 items** (the two lower tables above) are recorded for completeness but
> are **not** recommended for immediate filing — they're either narrow-window,
> deliberate boundaries, or disproven. A planner can promote any of them later;
> the verbatim follow-up lines live in each section's GAPS table.

---

## What is explicitly NOT a gap (so a future planner doesn't re-litigate)

- **Sequential-only.** The single-in_progress invariant is the plugin's contract;
  wave parallelism needs many worker agents — a different architecture.
- **3-segment formula-epic id rollup.** Disproven; regression-locked. No id
  parsing exists and bd rolls up both shapes identically.
- **`until` ignored for gating.** Correct per the field guide (non-gating edge).
- **`bd preflight` unused.** It's a beads-codebase contributor checklist, not a
  graph gate. Never wire it into the drive loop.
- **Not owning sync / graph hygiene as a *whole*.** The queue-driver SRP stance.
  The gaps are specific seams (FB-3/4/5), not a mandate to absorb every bd verb.
