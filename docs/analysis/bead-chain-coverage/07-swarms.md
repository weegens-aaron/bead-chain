# Swarms & Multi-Agent Execution — Coverage Findings

| Field            | Value                                                              |
| ---------------- | ----------------------------------------------------------------- |
| Capability area  | `swarms`                                                          |
| Field-guide ref  | `field-guide-07-swarms.html` (chapter 7)                          |
| Bead-chain owner | `bead_chain-jmo`                                                  |
| Primary modules  | `beads.py`, `lifecycle.py`, `register_callbacks.py`, `prompt.py`  |
| Status           | `done`                                                            |

---

## 1. AVAILABLE — what the field guide documents

Chapter 7 ("Swarms & Multi-Agent Execution") is the home of bd's *parallel,
many-agent* model. Citing `field-guide-07-swarms.html`:

- **§ I — A swarm is a molecule, not an epic.** `bd swarm create <epic>` does
  **not** mutate the epic; it mints a brand-new bead whose `issue_type` is
  literally **`molecule`** with `mol_type=swarm`, linked to the epic by a single
  **`relates-to`** edge, and stores the coordinator as the molecule's
  `assignee`. `molecule`/`swarm` are **internal types** — `bd types` does not
  list them; you cannot hand-create one. The epic + its children DAG is the
  *work*; the molecule is a *claim ticket* for a coordinator. (Cross-ref Vol V,
  `mol-type`.)
- **§ II — Four swarm verbs.** `bd swarm create / list / status / validate`.
  `create` takes a **positional** epic-id (no `--epic` flag), plus
  `--coordinator` and `--force`, and **auto-wraps** a non-epic single issue in a
  wrapper epic. `list --json` → `{schema_version, swarms:[…]}`. `status` is
  **computed live from the children** (accepts an epic *or* molecule id, follows
  the `relates-to` link) and buckets Completed / Active / Ready / Blocked.
- **§ III — Waves are bd's *real* parallel groups.** `bd swarm validate`
  computes **ready fronts** (waves) from the DAG topology: Wave 1 = issues with
  no open blockers, Wave 2 = unlocked once Wave 1 closes, etc. It reports
  *estimated worker-sessions*, *max parallelism* (widest wave), *total waves*
  (DAG depth), and a *Swarmable: YES/NO* verdict. **Crucially (§ III.3 / D4):**
  this wave model — backed by real `parallel_group(s)` types in the bd binary —
  is a *different thing* from the `execution_parallel_group` metadata string.
- **§ IV — Atomic claim + computed status.** There is **no `bd swarm claim`**;
  agents claim ordinary child beads with `bd update <id> --claim` (atomic
  assignee+status flip = the race guard so two agents can't grab one bead). For
  the rarer same-file race, the **merge-slot** of Vol VI serializes.
- **§ V — Skills routing is prose, not a field (D3).** `bd create --skills
  frontend` is folded into the **description** as a `## Required Skills` section.
  There is **no `skills` JSON key**; bd does **not** route, filter, or validate
  on it. "Skills routing" is an *orchestrator convention*: a coordinator reads
  the line and assigns a capable worker. bd provides the *channel* (description
  text + atomic claim), not the *router*.
- **§ VI — Execution metadata hints are free-form, NOT recognized by bd (D4).**
  The five canonical keys — `execution_parallel_group`, `execution_agent_type`,
  `execution_model`, `execution_effort`, `execution_mode` — ride in the bead's
  free-form `metadata` JSON (`--set-metadata k=v`). bd does **not** special-case
  them (an invented key stores identically; `strings` on the binary finds zero
  `execution_*` literals). They are a **shared vocabulary between bead authors
  and orchestrators**, transparent to bd.
- **§ VII — The audit interaction log.** `bd audit record` appends `int-xxxx`
  entries to an append-only `.beads/interactions.jsonl` (`kind` = `llm_call`
  with `model/prompt/response`, or `tool_call` with `tool_name/exit_code`);
  `bd audit label <id> --label=good|bad --reason=…` appends a `label` entry with
  `parent_id` — the reward signal for SFT/RL datasets. This is the *"why did the
  agent do that"* trail, **distinct** from a bead's per-issue event history.

## 2. LEVERAGED — what bead-chain actually uses

bead-chain consumes **exactly one** of chapter 7's primitives — the **atomic
`--claim`** of § IV — and is otherwise, by construction, blind to the entire
swarm/parallel/skills/audit surface. **No `bd swarm` verb and no `bd audit`
verb is called anywhere in the codebase.**

- **§ IV atomic claim — leveraged.** `claim()` shells out to
  `bd update <id> --claim` (`beads.py:471-473`); it is the chain's ownership
  primitive, called at every drive site (`lifecycle.py:603`, and the epic-claim
  helper `ensure_epic_in_progress` at `lifecycle.py:363`). This is the same
  race-safe assignee+status flip the guide names in § IV.1 — bead-chain gets it
  right, just for a single serial worker rather than a fleet.
- **§ V skills prose — passed through, not parsed.** bead-chain injects the
  bead's **full `description`** verbatim into the goal prompt
  (`prompt.py:306`). So if a bead carries a `## Required Skills` section, that
  text *reaches the LLM as part of the description* — implicit pass-through.
  What bead-chain does **not** do is *read* or *route* on it (it has no `skills`
  parse, and as the sole worker it has nobody to route to). Since bd doesn't
  route on it either (§ V), pass-through is the honest ceiling here.
- **Serial selection, one bead at a time (the deliberate boundary).**
  `pick_next_bead()` (`lifecycle.py:379-437`) returns **a single** bead via a
  strict tier order — tier-0 recovery → ready sibling under the active epic
  (`next_ready_in_epic`) → global `next_ready()` — and `next_ready()`
  (`beads.py:211-225`) shells `bd ready --exclude-type=epic --json` and returns
  the **first** workable item. `activate_next_bead()` (`lifecycle.py:463`) then
  claims that one bead and arms wiggum's `/goal`. The single-in_progress
  invariant is enforced explicitly (`enforce_single_in_progress`,
  `lifecycle.py:121`). bead-chain is a *one-agent serial driver* — the README
  byline is literally "one bead at a time."
- **NOT leveraged (explicitly stated):**
  - `bd swarm create / list / status / validate` — **never called**. bead-chain
    neither creates nor inspects swarm molecules, and never computes/consults
    **waves** (§ III). It never parallelizes a `parallel_group` (it can't — see
    the single-in_progress invariant).
  - `mol_type=swarm` discriminator (§ I) — **never read**. `EXCLUDED_TYPES =
    ("epic",)` (`beads.py:41`) excludes epics but **not** the `molecule` type,
    so a swarm/poured molecule is not specifically recognized **or** filtered
    (see Gap 1). Mirrors the `mol-type` blindness flagged in
    [`05-formulas-molecules.md`](./05-formulas-molecules.md) (Gap 3).
  - `execution_*` metadata hints (§ VI) — **never read**. The goal prompt
    surfaces only `type`, `priority`, and parent-epic
    (`prompt.py:289-293`); the bead's `metadata` JSON is never fetched or
    interpreted, so `execution_agent_type/model/effort/mode` are dropped
    (see Gap 2).
  - `bd audit record / label` + `.beads/interactions.jsonl` (§ VII) — **no
    references at all**. bead-chain runs the single richest source of
    `llm_call`/`tool_call` interactions *and* an LLM-judge verdict (a perfect
    `label`) yet records **none** of it to bd's audit log (see Gap 3).

## 3. GAPS — what's missing, and how much it matters

> **Framing the headline question (boundary vs gap):** sequential-only is a
> **deliberate, load-bearing boundary**, not a defect. bead-chain's whole
> contract is the single-in_progress invariant (`lifecycle.py:121`) — steady,
> one-`/goal`-pass-at-a-time progress with one worker agent. True swarm
> parallelism (§ III waves, `execution_parallel_group`) requires *multiple
> concurrent worker agents*, which is a different architecture, not a missing
> feature here. The genuine gaps below are the ones that are **orthogonal to
> parallelism** — i.e. things a *serial* driver could and arguably should do.

| #   | Gap (one line)                                                                                                                                                                                                              | Severity | Recommended follow-up (one line)                                                                                                  |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `molecule` is not in `EXCLUDED_TYPES` (`beads.py:41` = `("epic",)`); a swarm/poured molecule (§ I, `issue_type=molecule`, `relates-to` epic, unblocked) is itself a ready leaf, so `next_ready()` can hand a workless orchestration handle to `/goal` — it has no code work and the close-guard blocks closing it, stalling the chain. | P1       | Add `"molecule"` to `EXCLUDED_TYPES` (one-line, mirrors the epic exclusion, server- + client-side). Same bug-class as gate Gap 2. |
| 2   | `execution_*` hints (§ VI) are dropped: the goal prompt surfaces only type/priority/parent (`prompt.py:289-293`) and never reads the bead's `metadata`, so `execution_model`/`execution_effort`/`execution_agent_type`/`execution_mode` can't shape even the **single** `/goal` pass it does run. | P2       | File a bead to map recognized `execution_*` keys onto the serial drive (effort→reasoning budget, model→model select, agent_type→agent). No parallelism required. |
| 3   | `bd audit record`/`label` (§ VII) is never called; bead-chain runs the richest `llm_call`/`tool_call` stream **plus** an LLM-judge verdict (an ideal `label`) but writes nothing to `.beads/interactions.jsonl` — the SFT/RL trail is empty. | P3       | File a bead to emit `bd audit record` for the `/goal` pass and `bd audit label` for the judge verdict (opt-in; host may log separately). |
| 4   | No `bd swarm validate`/`status` observability: bead-chain can't report waves, max-parallelism, or swarm progress for an epic it is draining; a human gets no "how swarmable / how far along" read-out. | P4       | Optional: surface `bd swarm status <epic>` in the drain summary when the active epic has a related swarm molecule.               |
| 5   | `## Required Skills` prose (§ V) reaches the LLM via description pass-through (`prompt.py:306`) but is never parsed/acted on; for a single-agent driver there is no routing to perform, and bd itself doesn't route either. | P4       | None needed — document as intentional pass-through; routing is meaningless for a one-worker serial driver.                       |

### Severity rubric

| Sev | Meaning                                                                       |
| --- | ---------------------------------------------------------------------------- |
| P0  | Correctness/data-loss hazard in the drain loop (e.g. closes wrong bead).      |
| P1  | Feature silently dropped where it changes which bead runs or how it's framed. |
| P2  | Feature unused where leveraging it would materially improve goal quality.     |
| P3  | Minor gap; workaround exists or impact is narrow.                            |
| P4  | Cosmetic / future-proofing only.                                            |

---

## Notes / open questions

- **Sequential-only is the boundary; parallelism is out of scope by design.**
  Waves (§ III) and `execution_parallel_group` (§ VI) presuppose *many worker
  agents*. bead-chain is the opposite of a swarm coordinator — it is the single
  worker the coordinator would dispatch *to*. Recommending it "parallelize
  parallel_group members" would mean abandoning the single-in_progress
  invariant the entire plugin is built on. That is **not** a recommended
  change; flagged here so the synthesis matrix records it as a conscious
  boundary, not an oversight.
- **Gap 1 is the headline and is cheap.** It is a one-line constant edit that
  closes a real *stall* hazard, and it is the exact sibling of gate Gap 2 in
  [`06-gates-coordination.md`](./06-gates-coordination.md) (a non-task,
  no-code-work bead leaking onto `bd ready` and being handed to `/goal`). It
  also subsumes part of the `mol-type` blindness noted in
  [`05-formulas-molecules.md`](./05-formulas-molecules.md): excluding the
  `molecule` type means poured/swarm molecules never get driven as if they were
  leaf work. **Recommend filing Gap 1 from the synthesis bead** (`bead_chain-hkb`),
  not here.
- **Gaps 2 + 3 are the two *serial-compatible* enrichments** — both improve a
  single `/goal` pass (better effort/model selection; a populated SFT/RL trail)
  without touching the parallelism boundary. They are the highest-value
  swarm-adjacent features bead-chain could adopt while staying a one-bead-at-a-
  time driver.
- **No bug filed.** Per the bug-discovery protocol: Gap 1 is a real defect but
  it does **not** block *this* bead's stated goal (authoring the coverage
  finding) — it is documented here and routed to synthesis as a follow-up
  recommendation, exactly as the gates section handled its P1 pair.
