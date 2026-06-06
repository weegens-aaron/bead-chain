# SOLID Review — Responsibility & Coupling (bead_chain-mol-512)

Judgment-only review of the pure-Python modules in the `bead_chain`
code-puppy plugin. There is no mechanical tool for SRP / coupling — this
is a careful read focused on the three things the bead calls out:

1. SRP violations (modules approaching/over the 600-line guideline).
2. Leaky abstractions across the `beads` / `lifecycle` / `prompt` boundary.
3. Tight coupling to the code_puppy host callback API.

> **This is the third pass.** Two prior reviews exist
> (`solid-review-mol-4yc.md`, then `solid-review-mol-9o2.md`). Read this
> one as the *current* state of the world: the codebase has grown
> **materially** again, a **new module landed** (`execution_hints.py`),
> and **two of mol-9o2's conclusions are now stale**. The
> "What changed since mol-9o2" section below saves the judges a diff.

## Method

- Read every module end-to-end.
- Measured size: `wc -l *.py`.
- Mapped the host-coupling surface: `rg code_puppy`, `rg emit_`.
- Traced cross-module reach-across (`rg "beads\._"`, `rg wiggum`) and
  hunted dead public API (`rg` for real call sites vs docstrings).
- Re-ran the suite (`pytest -q` → **245 passed**) and lint
  (`ruff check` + `ruff format --check` → clean) so every finding rests on
  a green baseline.

## Size snapshot (the SRP-by-line question)

| Module                  | Lines | % of 600 cap | vs mol-9o2 |
|-------------------------|-------|--------------|------------|
| **beads.py**            | **1082** | **180%**  | +471 (was 611) |
| **lifecycle.py**        | **795**  | **133%**  | +105 (was 690) |
| **prompt.py**           | **759**  | **127%**  | +442 (was 317) |
| register_callbacks.py   | 407   | 68%          | +9 (was 398)   |
| execution_hints.py      | 203   | 34%          | **new module** |
| close_guard.py          | 150   | 25%          | unchanged      |
| state.py                | 79    | 13%          | unchanged      |

**Verdict on size:** the situation has gone from bad to worse.
mol-9o2 reported **two** files over cap; we now have **three**, and the
breaches are severe rather than marginal:

- `beads.py` is **1082 lines — nearly double the 600 cap** and up 77%
  since the last review. It is no longer "two modules in a trenchcoat"; it
  is **four or five**.
- `prompt.py` **more than doubled** (317 → 759) and crossed from "fine on
  size, smelly on purity" to "cap-breaching, multi-concern."
- `lifecycle.py` (795) keeps climbing, driven by two monster functions.

The good news is unchanged from mol-9o2: **the correct cohesion splits
are exactly what gets these back under cap** — you do not need to slice
arbitrarily. The line cap just removed every remaining "leave it alone"
escape hatch.

---

## What changed since mol-9o2 (so judges don't have to diff)

1. **Three files now breach 600 (was two), and `beads.py` is ~2× cap.**
   The breaches are no longer marginal. See #1 and #2 below.
2. **A new module landed — and it's the *good* kind.**
   `execution_hints.py` (FB-8) is genuinely well-factored: a pure core
   (`extract_execution_hints` / `_coerce_metadata`) and a soft-fail impure
   shell (`apply_execution_hints`). It is the SRP pattern the rest of the
   plugin should copy. **But** it adds a **fourth** host-coupling site
   (`code_puppy.config` setters + `code_puppy.messaging.emit_warning`),
   which *strengthens*, not weakens, the reporting-seam argument (#3).
3. **`prompt.py` graduated to a split candidate.** Prior reviews flagged
   it as a medium "impurity + epic-fetch dup" smell. At 759 lines it is
   now **three concerns in one file** — bd-fetch helpers, large static
   prose templates, and pure formatters. New #4 below.
4. **The "dead API" finding is partially stale.** `beads.is_blocked` is
   now exercised by tests (`test_blocker_gate*`, `test_waits_for_blocker`)
   — it's no longer *dead*, just *production-unused / test-only*.
   `beads.next_in_progress` is **still fully dead** (zero call sites, only
   a docstring mention). Re-scoped as #6.
5. **`beads.py` accreted whole new clusters** since mol-9o2: gate-check
   (`check_gates` + `_parse_gate_check_summary`), lint-warnings
   (`lint_warnings` + `_parse_lint_missing`), the memory layer
   (`memories`), and the recurring-epic policy (`is_recurring_epic`,
   `RECURRING_*`). This is *why* it doubled — and why the #1 split is now
   urgent, not optional.
6. **Everything else from mol-9o2 still holds**: `lifecycle` still
   reaches into `beads` privates (#3), still tangles decisions with
   `emit_*` (#1), and `wiggum_state` coupling is unchanged (#5).

---

## Findings — refactor candidates ranked by pain

### 1. (HIGHEST PAIN) `beads.py` is ~2× over cap = transport + 4 domain clusters in one file → SPLIT, urgently

The docstring still claims "thin subprocess wrapper around the `bd` CLI."
At **1082 lines it is the opposite of thin**, and it now bundles at least
five distinct responsibilities:

- **Transport (the genuine "bd client"):** `_run_bd` + retry policy
  (`MAX_ATTEMPTS`, `_RETRY_BACKOFFS`), `_bd_bin`, `_parse_json_list`,
  `BeadsError`, and the query/mutation verbs (`next_ready`,
  `list_in_progress`, `_list_by_status`, `list_recoverable_strands`,
  `next_ready_in_epic`, `open_blocker_ids`, `is_pinned`,
  `next_blocking_bug`, `show`, `claim`, `revert_to_open`, `close`,
  `has_epic_in_progress`).
- **Domain policy / predicates (bead-chain's own rules, not bd facts):**
  `EXCLUDED_TYPES` + `is_excluded_type`, the recurring-molecule cluster
  (`RECURRING_MOL_TYPES`, `_MOL_TYPE_KEYS`, `_mol_type_matches`,
  `is_recurring_epic`, `RECURRING_EPIC_LABELS`), the blocker vocabulary
  (`BLOCKING_DEP_TYPES`, `SATISFIED_BLOCKER_STATUSES`, status constants,
  `RECOVERABLE_STATUSES`, `BLOCKING_BUG_TYPES`), and parent-epic
  extraction (`PARENT_EPIC_KEY`, `_PARENT_EPIC_FALLBACK_KEYS`,
  `extract_parent_epic_id`).
- **Epic close/rollup machinery:** `close_eligible_epics`,
  `_preview_close_eligible`, `_bulk_close_eligible`, `_close_non_recurring`,
  `_parse_close_eligible_payload`, `_is_closed_epic`, `_normalise_closed_epic`.
- **Gate-check parsing:** `check_gates`, `_parse_gate_check_summary`,
  `_GATE_COUNT_KEYS`.
- **Lint-warning + memory parsing:** `lint_warnings`, `_parse_lint_missing`,
  `memories`, `_NON_MEMORY_KEYS`.

The tell that the domain bucket doesn't belong here: it's imported by
**both** `lifecycle.py` and `prompt.py`. Those predicates aren't
transport — they're the shared vocabulary of the whole plugin, currently
homed inside the "thin wrapper." That is the clearest *structural* leaky
abstraction in the tree, now amplified by sheer mass.

**Recommended split (cohesion-driven, and it relieves the worst breach):**
carve out, in order of payoff:
1. `domain.py` — the pure predicates + shape-normalisers + their constants
   (the bucket imported by `lifecycle`/`prompt`). Trivially unit-testable
   with no `bd`/host involvement.
2. `bd_parsers.py` (or fold into the relevant feature modules) — the three
   payload parsers (`_parse_close_eligible_payload`,
   `_parse_gate_check_summary`, `_parse_lint_missing`) are *shape* logic,
   not transport, and each pairs with a public verb.

After this, `beads.py` keeps only subprocess + JSON-list transport and the
verbs, dropping comfortably back under 600 and **finally earning its "thin
wrapper" docstring**. This is the single highest-value move in the
codebase.

### 2. (HIGH PAIN) `prompt.py` doubled to 759 and is three concerns in a trenchcoat → SPLIT

`prompt.py` was a medium smell in prior reviews; the size jump promotes
it. It now interleaves three cleanly separable concerns:

- **Impure bd-fetch helpers:** `_fetch_epic_context` (`bd show`),
  `_fetch_memory_digest` (`beads.memories`), `_fetch_lint_warnings`
  (`beads.lint_warnings`). The "prompt formatting" module carries a
  subprocess dependency — its own docstring confesses this.
- **Large static prose templates:** `_RECOVERY_PREAMBLE`,
  `_TRIAGE_VERIFY_PREAMBLE`, and especially `_BUG_DISCOVERY_PROTOCOL` are
  big multi-line string *assets*, not logic. They are a major chunk of the
  442-line growth and have no behavioural cohesion with the formatters.
- **Pure block formatters + orchestrator:** `_format_*_block`,
  `_format_*_lines`, `_first_paragraph_excerpt`, `_edge_type`,
  `_edge_target_id`, `is_triaged_bug`, and `format_bead_as_goal`.

**Recommended split:**
1. Lift the static prose constants into a `prompt_templates.py` (pure
   data). Sheds ~150 lines of asset text and lets the templates be edited
   without touching formatting logic.
2. Move the three `_fetch_*` helpers behind the same fetch boundary as #1
   / #3 (a `domain.py`/`epic.py` home), leaving `prompt.py` as
   pure-formatting-only at its seams.

This both relieves the cap breach and resolves the long-standing "prompt
isn't pure" complaint.

### 3. (HIGH PAIN) `lifecycle._has_fan_out_gate_issue` still reaches into `beads` **privates** + two monster functions → DIP / encapsulation / SRP

`lifecycle.py` (795) keeps two compounding problems:

- **Private reach-across (unchanged since mol-9o2):** the fan-out-gate
  workaround still does (lifecycle.py:784-785):

  ```python
  raw = beads._run_bd("list", "--json")
  all_issues = beads._parse_json_list(raw, "bd list --json")
  ```

  That is `lifecycle` punching past the public `beads` API into its
  private transport internals (`_run_bd`, `_parse_json_list` are
  underscore-prefixed by intent). It's the clearest encapsulation break in
  the tree: the whole point of `beads.py` is to own *all* `bd` subprocess
  traffic behind named verbs, and a raw "list every issue" query has no
  public home — so the caller punched through. If `beads` changes its
  retry/parse internals, `lifecycle` breaks silently.
- **Two over-large functions:** `activate_next_bead` (~190 lines) and
  `close_current_bead_success` (~120 lines) carry the bulk of the file.
  Each mixes "decide + mutate bd + mutate state + tell the user" in one
  body. `pick_next_bead` (the 4-tier waterfall: stranded → blocking bug →
  epic affinity → global) is exactly the table-driven-test target you
  can't unit-test today because every branch reaches for `emit_*` (see #4).

**Recommended moves:**
- Give `beads` a public verb for the query the gate needs
  (`list_all()` or `children_of(spawner_id)`), then lift the gate predicate
  into a cohesive `gates.py` (or the `domain.py` from #1). `lifecycle` then
  calls a *public* `gates.has_unsatisfied_fan_out(bead_id)`. Kills the
  private reach-across, shrinks `lifecycle`, makes the gate testable.
- Decompose `activate_next_bead` / `close_current_bead_success` into the
  decide-vs-effect halves the `reporting` seam (#4) unlocks.

> **Caveat (verified, do not "fix" here):** the fan-out gate is still
> WRITE-ONLY in bd — `bd show --json` does not surface `any-children` vs
> `all-children`, so the predicate can only do `all-children` semantics
> safely. This is tracked under FB-13 (`bead_chain-y0s`) behind gate
> `bead_chain-4b2`; it is **not** a finding of this review. The refactor
> above is purely about *where* the predicate lives, not *what* it decides.

### 4. (HIGH PAIN) `emit_*` host coupling now threads through **four** files → add a `reporting` seam (DIP)

The host-messaging dependency has spread, not shrunk (counts are real
`emit_*(` call sites, excluding the `from code_puppy.messaging import …`
lines and docstring mentions — verified via
`grep -cE "emit_[a-z_]+\("`):

| File | `emit_*` call sites |
|------|---------------|
| lifecycle.py | 39 |
| register_callbacks.py | 20 |
| execution_hints.py | 1 |
| close_guard.py | 1 |

That's **61 call sites across four files**, every one of them importing
`code_puppy.messaging` directly. Pure decision logic is welded to `code_puppy.messaging`, so you can't
unit-test the *decisions* (the 4-tier waterfall, the close/rollup
sequencing) without the host present. This was mol-9o2's #1 and it has
only gotten more diffuse.

**Recommended move (small, high-leverage):** introduce a tiny
`reporting.py` seam — everyone calls `from .reporting import info, warn,
success`, and `reporting.py` is the *only* place importing
`code_puppy.messaging`. Tests monkeypatch `reporting`. ~30 lines,
collapses the duplicate emit-imports now in **four** files, and finally
makes the waterfall testable. (`execution_hints.py` already proves the
pure-core/impure-shell pattern works here — this just gives the shell a
shared exit.)

### 5. (MEDIUM PAIN) Coupling to `wiggum_state` internals + now host `config` too → wrap behind one adapter

`bead-chain` depends directly on a *sibling plugin's internal state
module* across three production sites:

- `lifecycle.py:721` — `wiggum_state.start(goal_prompt, mode="goal")`
- `register_callbacks.py:281` — `wiggum_state.start(...)`
- `register_callbacks.py:321` — `wiggum_state.is_active()`

Plus the lazy-hook-ordering dance in `register_callbacks` is itself a
symptom of how tightly the two are coupled. And `execution_hints.py` now
adds direct coupling to `code_puppy.config` setters. If wiggum renames
`start`, changes the `mode` contract, or restructures its state,
bead-chain breaks in multiple spots with no single seam to fix.

**Recommended move:** a one-file `wiggum_adapter.py` exposing
`arm_goal(prompt)` and `is_goal_active()`. One import of
`code_puppy.plugins.wiggum.state` lives there; everyone else depends on
the adapter. Cheap insurance against a coupling you don't control, and it
gives the lazy-registration explanation one obvious home. (The
`config`-setter coupling in `execution_hints` is already isolated to that
module by design, so it's lower priority — but a future `host.py` could
absorb both it and the `reporting` seam.)

### 6. (LOW PAIN) Dead / production-unused public API: `next_in_progress` (and test-only `is_blocked`)

Re-scoped from mol-9o2's #6:

- `beads.next_in_progress` (beads.py:423) has **zero call sites** — only a
  docstring mention. Textbook YAGNI surface; **delete it**.
- `beads.is_blocked` (beads.py:550) is **no longer dead** — it's exercised
  by `test_blocker_gate*` and `test_waits_for_blocker`. But it has **no
  production call site**; callers use `open_blocker_ids(...)` directly.
  It's a thin `bool(open_blocker_ids(...))` convenience that exists only
  for its tests. Either promote it to a documented public predicate and
  *use* it where the prose comment at lifecycle.py:484 implies it should
  be, or inline it and delete the standalone tests. Don't leave a function
  whose only consumer is its own test.

### 7. (LOW PAIN) CLI flag parsing bolted into the wiring module

`register_callbacks._parse_max_iterations` (+ `_PARSE_ERROR` sentinel) is
argument-parsing — a distinct responsibility from hook wiring and command
registration. It's ~40 lines for a single `--max` flag, so this is
borderline YAGNI today. Flag it as: *if a second flag ever appears*,
extract a `cli.py`. Until then, leave it — splitting one flag's parser
into its own module would be ceremony, not cohesion.

### Non-issues (explicitly cleared)

- `execution_hints.py` (203 lines): **the model to copy.** Clean
  pure-core/impure-shell split, soft-fails per hint, well under cap.
  Its only blemish is the shared host coupling (#4/#5), not anything
  module-specific. Leave it.
- `close_guard.py` (150 lines): cohesive — detector + its one hook handler
  living together is correct SRP, as its docstring argues. Its `emit_*`
  usage is the shared #4 coupling, not a `close_guard`-specific flaw.
- `state.py` (79 lines): a deliberately dumb data box mirroring wiggum's
  pattern. No behaviour to leak. Leave it.
- `register_callbacks.py` (407 lines): the wiring/hooks/command split vs
  `lifecycle` is a clean, well-documented seam, comfortably under cap. Its
  blemishes are all shared (#4 emit, #5 wiggum, #7 flag parsing).

---

## Summary table — ranked

| # | Candidate | Pain | Type | Split? |
|---|-----------|------|------|--------|
| 1 | `beads` ~2× cap (1082) = transport + 4 domain clusters | **High** | SRP / leaky abstraction | **Yes — `domain.py` (+ parsers)** |
| 2 | `prompt` doubled (759) = fetch + prose + formatters | **High** | SRP / impurity | **Yes — `prompt_templates.py` + move fetch** |
| 3 | `lifecycle` reaches `beads` privates + 2 monster fns | **High** | DIP / encapsulation / SRP | **Yes — public verb + `gates.py`** |
| 4 | `emit_*` host coupling across 4 files | **High** | DIP / testability | No — add `reporting` seam |
| 5 | `wiggum_state` (+`config`) coupling | Med | Coupling to sibling/host | No — add adapter |
| 6 | `next_in_progress` dead; `is_blocked` test-only | Low | YAGNI / dead code | Delete / inline |
| 7 | `--max` parsing in wiring module | Low | SRP | Defer (YAGNI) |

## Bottom line

- **The project now violates its own 600-line guideline in three files,
  and `beads.py` is nearly double the cap.** What mol-4yc called "don't
  split for line count" and mol-9o2 softened to "two marginal breaches" is
  now a genuine structural problem in the two highest-traffic files.
- **Three true split candidates, all cohesion-driven** (each also relieves
  a real cap breach):
  1. `beads.py` → extract `domain.py` (shared predicates) and pull the
     payload parsers out. Fixes the worst leaky abstraction *and* the worst
     breach. **Highest value.**
  2. `prompt.py` → lift static prose into `prompt_templates.py` and move
     the `_fetch_*` helpers to the domain/epic home. Resolves the
     long-standing impurity complaint.
  3. `lifecycle.py` → give `beads` a public list/children verb, lift the
     fan-out gate into `gates.py`, and decompose the two monster functions.
     Kills the private reach-across.
- **The cheapest high-leverage win is still not a split** — it's the
  `reporting` seam (#4) that decouples decision logic from
  `code_puppy.messaging` across four files and unlocks unit-testing the
  4-tier waterfall.
- **`execution_hints.py` is the template for all of the above:** pure core,
  soft-fail shell, under cap. The refactors above are largely about
  retrofitting the rest of the plugin to that standard.
- **No new bugs filed.** Every finding here is a refactor candidate that is
  *in scope for this review bead* — it's what the bead asked us to surface
  — not an unrelated defect. The fan-out-gate write-only limitation noted
  in #3 is pre-existing, already tracked under FB-13/gate `bead_chain-4b2`,
  and explicitly out of scope.
