# Quality & Hygiene — Coverage Findings

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Capability area  | `quality-hygiene`                                                     |
| Field-guide ref  | `field-guide-09-quality-and-hygiene.html` (chapter 9)                 |
| Bead-chain owner | `bead_chain-tl0`                                                      |
| Primary modules  | `close_guard.py`, `lifecycle.py` (`rollup_completed_epics`), `beads.py` (`close_eligible_epics`), `prompt.py` (`format_bead_as_goal`) |
| Status           | `done`                                                                |

---

## 1. AVAILABLE — what the field guide documents

Chapter 9 is the **hygiene toolbox**: the small commands that turn a messy bead
graph into a shippable one. Its central thesis is that there are **two kinds of
"clean"** and conflating them is the #1 mistake (`field-guide-09-quality-and-hygiene.html`
§ I "The two kinds of clean"):

- **Graph hygiene** — *is the bead graph healthy?* Complete descriptions, acyclic
  DAG, no dangling refs, no stale/duplicate work. Any bd user, any project.
- **Contribution hygiene** — *is my code contribution ready to push?* (tests,
  gofmt, JSONL pollution, version sync). Exactly one command — `preflight` — and
  it is specific to contributing to the **beads codebase itself**.

The seven **graph-hygiene** surfaces (§ II "What each tool catches", § III–VIII):

- **`bd lint`** (§ III "lint: the template contract") — flags beads missing the
  **required template sections for their type**. The v1.0.4 contract is fixed:
  `bug` → `## Steps to Reproduce` + `## Acceptance Criteria`; `task`/`feature` →
  `## Acceptance Criteria`; `epic` → `## Success Criteria`; `chore` → none.
  Matches on literal markdown heading text. **Exits 1 on any warning, 0 when
  clean** — that non-zero exit is what makes it usable as a gate. Default scope =
  **open issues only** (`--status all`, `bd lint <id>`, `--type`, `--json`).
  Create-time sibling: `bd create --validate` / the `validation.on-create` config
  knob catches it *before* the bead enters the graph.
- **`bd dep cycles`** (§ IV "Cycles & graph integrity") — focused detector for
  circular `blocks` chains (strongly-connected components) that make `ready`
  uncomputable. Clean → `No dependency cycles detected`, exit 0. **Key nuance:
  cycles are prevented at write time** — `bd dep add` refuses an edge that would
  close a loop, so `dep cycles`/`graph check` are belt-and-suspenders for the
  bypass paths only (`--no-cycle-check`, bulk `create --graph`/`import`, branch
  merges).
- **`bd graph check`** — the superset: cycles + **structural** orphans (dangling
  edge targets, dup IDs) + integrity. Exit 0 clean / 1 dirty, CI-friendly.
- **`bd orphans`** (§ V) — issues **referenced in commit messages but still
  open/in_progress** (a git↔bd reconciliation, *not* a graph check). `--fix`
  auto-closes; `--details`/`--label` scope.  "orphan" is overloaded: `graph
  check` reports *structural* orphans (broken edges); `bd orphans` reports
  *committed-but-unclosed* work. Same word, two mechanisms.
- **`bd duplicates`** (§ V) — exact content-hash duplicates (title+desc+design+
  acceptance). Cheap, zero false positives.
- **`bd find-duplicates`** (§ V) — fuzzy: `--method mechanical` (Jaccard token
  overlap, **default**, `--threshold 0.5`) or `--method ai` (LLM judge, needs
  `ANTHROPIC_API_KEY`). There is **no `semantic`** method value.
- **`bd stale --days N`** (§ VI) — issues not updated recently (default 30, min
  1; `--limit`, `--status`). Surfaces abandoned/forgotten work.
- **`bd doctor`** (§ VII) — the installation/DB physical (`.beads/` existence, DB
  version/migrations, schema, IDs, hooks, `.gitignore` currency). Modes include
  `--check=conventions` (bundles lint+stale+orphans, advisory), `--deep`,
  `--fix`, `--agent --json`. **Load-bearing caveat: `bd doctor` is NOT supported
  in embedded Dolt mode — the default for `bd init`** — it returns `Note: 'bd
  doctor' is not yet supported in embedded mode`.

The one **contribution-hygiene** surface (§ VII, § VIII):

- **`bd preflight --check`** — a **pre-PR checklist for contributors to the beads
  codebase**, nothing to do with grooming a bead graph. Runs `go test`,
  `golangci-lint`, `gofmt`, JSONL-pollution, nix `vendorHash`, version sync,
  AGENTS.md/CLAUDE.md divergence. The guide explicitly **corrects a prior draft**:
  `preflight` runs **none** of lint/cycles/graph-check/stale/orphans (§ VII
  "Correction · preflight is NOT a graph gate").

The recommended pre-PR loop (§ VIII) is a **hand-assembled script** — there is
**no single bd command that runs every graph check**: `lint` → `graph check` →
`orphans` → `stale` → `duplicates`/`find-duplicates` → (`doctor --deep`, server
mode only) → (`preflight`, beads-codebase only). The **two hard stops** are
`lint` and `graph check` (non-zero = not shippable); the rest are advisory.

> **Scope note — `bd epic close-eligible`.** The owning bead frames close-eligible
> rollup as a ch09 hygiene item. It is **not**: chapter 9's prose never mentions
> it (verified — zero occurrences in the chapter content). Epic close-eligible
> rollup is a formulas/lifecycle concern (chapters 5 & 3) and its data-layer
> consequences are audited in `08-data-layer.md`. It is covered here only as the
> *single* hygiene-adjacent automation bead-chain actually runs, so this section
> can state precisely what it is and is **not** (it is not lint/cycles/orphans).

## 2. LEVERAGED — what bead-chain actually uses

**bead-chain leverages ZERO of chapter 9's graph-hygiene tooling.** Verified
exhaustively: a search across the six core modules (`beads.py`, `lifecycle.py`,
`register_callbacks.py`, `close_guard.py`, `prompt.py`, `state.py`) for
`lint | graph check | dep cycles | orphan | stale | duplicat | doctor | preflight
| --validate | validation` returns **no** call site that shells out to any of
`bd lint`, `bd graph check`, `bd dep cycles`, `bd orphans`, `bd stale`,
`bd duplicates`, `bd find-duplicates`, `bd doctor`, `bd preflight`, or
`bd create --validate`. There is **no `bd ready`-frontier hygiene gate** anywhere
in the driver loop.

The only `lint`/`validation`-adjacent matches are **not** ch09 graph hygiene:

- `prompt.py:36` (`"- Are tests and linters passing?\n"`) and `prompt.py:311`
  (`"1. Run linters (\`ruff check --fix\`, \`ruff format .\`).\n"`) — the goal
  prompt **instructs the in-flight agent to run code linters** (`ruff`), i.e.
  *contribution* hygiene on the agent's own diff, not bd *graph* hygiene. This is
  a prompt-string nudge, not an enforced gate (cited in `04-memories-recall.md`).
- `skills/md-to-html/scripts/md_lint.py` — an unrelated bundled **markdown**
  linter, out of the six-module core scope.

**What bead-chain *does* run on the hygiene-adjacent axis — exactly one thing:
`bd epic close-eligible`, once per drain.** The end-of-session path is
`activate_next_bead` → the `bead is None` branch (`lifecycle.py:499-524`):

1. `rollup_completed_epics()` (`lifecycle.py:519`, def at `lifecycle.py:282`) —
   wraps `close_eligible_epics()` (`beads.py:526`), which is a single
   `_run_bd("epic", "close-eligible", "--json")` (`beads.py:572`).
2. `emit_success("bead-chain: no more ready beads…")` (`lifecycle.py:521`).
3. `state.stop()` (`lifecycle.py:524`).

This rollup is deliberately **once-per-session, not per-close** (`lifecycle.py:284-298`,
`beads.py:526-548`) as the `bead_chain-tfn` over-close mitigation, and it
**soft-fails** (`lifecycle.py:300-303`: warn + continue). It is a *rollup*
cascade, **not** a lint/cycles/orphans/stale sweep — none of the ch09 hard-stop
gates run before, during, or after it.

**The other hygiene-shaped thing bead-chain owns is `close_guard.py` — but it is
a self-close *blocker*, not a ch09 tool.** `detect_premature_close`
(`close_guard.py:68`) regex-matches an in-flight agent's attempt to
`bd close …` / `bd update … --status=closed`, and the `on_run_shell_command`
hook (`close_guard.py:108`) blocks it while the chain is active
(`close_guard.py:124-150`), reminding the agent that wiggum's LLM judges are the
only legitimate closer. This enforces the *close contract* (chapter 3 lifecycle
territory); it has **nothing to do with** the lint/cycles/orphans/preflight
hygiene surface of chapter 9.

**Net:** the bead's two named bead-chain behaviors — `bd epic close-eligible` at
drain and `close_guard`'s self-close block — are real and correctly scoped, but
**neither is a chapter-9 graph-hygiene tool**, and bead-chain **does not run, nor
surface, any of lint / cycles / graph check / orphans / stale / duplicates /
doctor / preflight** into the `/goal` loop.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                                                                                                                                                                                                          | Severity | Recommended follow-up (one line)                                                                                                                              |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | bead-chain never runs `bd lint` (or honors its exit-1 gate), so it will happily claim and drive a bead **missing its required template sections** (e.g. a `task` with no `## Acceptance Criteria`) — exactly the case the project memory records hitting after a `--graph` import.        | P2       | File a bead: run `bd lint <id>` on each bead at claim time and inject the warnings into the goal prompt (or skip + warn), so the agent is told what's missing. |
| 2   | bead-chain never runs `bd dep cycles` / `bd graph check`. Cycles are prevented at write time, **but the documented bypasses (`--no-cycle-check`, bulk `create --graph`, branch merges)** can introduce one — and a cycle silently freezes a whole component so `bd ready` never offers it. | P3       | File a bead: a one-shot `bd graph check` at chain **startup** (exit-1 → warn loudly, don't drain a graph that can't compute `ready` correctly).                |
| 3   | bead-chain never runs `bd orphans`. In an agent workflow a `/goal` run can land a commit ("fixes bead_chain-xxx") yet the bead stays open if judges/close path are bypassed — precisely the commit↔bd drift `bd orphans` reconciles, here invisible.                                      | P3       | File a bead: optional `bd orphans` (report-only) at drain alongside the existing rollup; surface counts, do not auto-`--fix`.                                  |
| 4   | bead-chain never runs `bd stale`. A bead stranded `in_progress` by a crashed/Ctrl-C'd run (left in_progress by design) is recovered next start, but **forgotten open work elsewhere in the graph is never surfaced** by the driver.                                                       | P4       | Future-proofing: optionally emit `bd stale --days N` summary at drain; document as advisory-only.                                                              |
| 5   | `bd preflight` is correctly **not** used (it is a beads-codebase contributor checklist, not a graph gate). The only risk is conceptual: the bead's framing implies preflight is graph hygiene. No bead-chain code should ever call it.                                                     | P4       | No code change — record the "preflight is not a graph gate" correction so no future bead wires it into the drive loop.                                          |
| 6   | The goal prompt's "definition of done" (`prompt.py:308-315`) tells the agent to run **code** linters/tests but never tells it to leave the **bead graph** clean (no `bd lint`/`graph check` in the close-out checklist). Contribution hygiene is nudged; graph hygiene is absent.        | P3       | File a bead: extend the prompt close-out (or a drain-time emit) to remind that graph hygiene (`bd lint`, `bd graph check`) is part of a clean session.         |

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

- **Is this a bead-chain defect, or correct SRP?** Mostly the latter, with one
  real seam. bead-chain is a *queue driver*, not a graph groomer — owning the
  full ch09 hygiene loop would arguably overreach the
  `queue-driver-not-goal-engine` boundary (sibling explanation). That justifies
  why `dep cycles`/`orphans`/`stale`/`doctor`/`preflight` being unused is at most
  P3–P4. **The one finding that bites is gap #1 (lint, P2):** the driver picks
  beads off the `bd ready` frontier and frames them as goals *without ever
  checking they satisfy the template contract*, and the project memory already
  records `bd lint` flagging every task "Missing: ## Acceptance Criteria" after a
  `--graph` import. A bead with no acceptance criteria "cannot be judged done"
  (ch09 deck) — and bead-chain's whole close decision is the LLM judges. Feeding
  judges an un-lintable bead is the highest-leverage hygiene gap.
- **Why no P0/P1.** Nothing here is a correctness/data-loss hazard in the drain
  loop and nothing changes *which* bead runs — the gaps are unused-tooling, not
  wrong behavior. The cycle case (gap #2) is the closest to "changes what runs"
  (a cycle hides a component from `ready`), but cycles are write-time-prevented,
  so it stays P3.
- **`close_guard` ≠ ch09 hygiene.** `close_guard.py` is genuinely good hygiene
  *in spirit* (it protects the close contract) but it is a lifecycle/coordination
  control (chapters 3 & 6), not a chapter-9 graph-cleanliness tool. Counted here
  only to state explicitly that bead-chain's "blocks self-close" behavior does
  **not** substitute for lint/cycles/orphans.
- **Cross-section seams.** Epic close-eligible rollup's *data-layer* behavior is
  owned by `08-data-layer.md` (`bead_chain-p6o`); its *formula/rollup* semantics
  by `05-formulas-molecules.md` (`bead_chain-5xh`). The `ruff`-linter prompt nudge
  is also noted in `04-memories-recall.md`. This section counts only the **ch09
  graph-hygiene tooling** to avoid double-counting.
- Gaps #1–#6 are recommendations for the synthesis bead (`bead_chain-hkb`); per
  the analysis framework this section files no beads itself.
