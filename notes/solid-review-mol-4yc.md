# SOLID Review — Responsibility & Coupling (bead_chain-mol-4yc)

Judgment-only review of the six pure-Python modules in the `bead_chain`
code-puppy plugin: `beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`.

No mechanical tool exists for SRP / coupling — this is a careful read
focused on the three things the bead calls out:

1. SRP violations (modules approaching the 600-line guideline).
2. Leaky abstractions across the `beads` / `lifecycle` / `prompt` boundary.
3. Tight coupling to the code_puppy host callback API.

## Method

- Read every module end-to-end.
- Measured size: `wc -l *.py`.
- Mapped the host-coupling surface: `rg code_puppy`.
- Re-ran the test suite (`pytest -q` → 9 passed) so findings rest on a
  green baseline.

## Size snapshot (the SRP-by-line question)

| Module                  | Lines | % of 600 cap |
|-------------------------|-------|--------------|
| beads.py                | 504   | 84%          |
| lifecycle.py            | 481   | 80%          |
| register_callbacks.py   | 356   | 59%          |
| prompt.py               | 317   | 53%          |
| close_guard.py          | 150   | 25%          |
| state.py                | 79    | 13%          |

**Verdict on size:** nobody breaches 600. `beads.py` and `lifecycle.py`
are the two to watch, but **neither should be split for line count
alone** — that would hurt cohesion. The interesting SRP problems below
are about *what a module knows*, not how long it is.

---

## Findings — refactor candidates ranked by pain

### 1. (HIGHEST PAIN) `lifecycle.py` interleaves decisions with `emit_*` side effects → DIP violation, untestable brain

`lifecycle.py` is described as "the state-transition brain", and it is —
but almost every function in it reaches straight for the host's
`emit_info` / `emit_warning` / `emit_success`. That couples pure
decision logic to the code_puppy messaging system, so you can't unit-test
the *decisions* without the host present.

- `pick_next_bead` — the 4-tier waterfall, the single most logic-dense
  function in the plugin — emits inside every branch. Its routing
  decision (tier 0 stranded → tier 1 blocking bug → tier 2 epic affinity
  → tier 3 global) is exactly the thing you'd want a table-driven unit
  test over, and right now you can't write one without stubbing the host.
- `close_current_bead_success`, `enforce_single_in_progress`,
  `ensure_epic_in_progress`, `activate_next_bead`, `rollup_completed_epics`
  all mix "decide + mutate bd + mutate state + tell the user" in one body.

**Why it's #1:** it blocks testability of the highest-value logic *and*
it's the densest host coupling in the codebase (Dependency Inversion: the
brain depends directly on a concrete host messaging module instead of an
abstraction it owns).

**Recommended move (no split):** introduce a tiny `notify` seam — a
module-local indirection (e.g. `lifecycle.py` calls `from .reporting
import info, warn, success`, and `reporting.py` is the *only* place that
imports `code_puppy.messaging`). Tests can monkeypatch `reporting`. Bonus:
it collapses the emit-import duplication that currently exists in three
files. This is a ~30-line change, not a rewrite, and it does not increase
line count meaningfully.

### 2. (HIGH PAIN) `beads.py` is two modules in a trenchcoat: bd-transport vs bead-domain policy → SPLIT CANDIDATE

The docstring says "thin subprocess wrapper around the `bd` CLI." It is
not thin — it has accreted **bead-chain domain policy** that has nothing
to do with talking to a subprocess:

- *Transport concerns (genuinely "bd client"):* `_run_bd` + retry policy
  (`MAX_ATTEMPTS`, `_RETRY_BACKOFFS`), `_bd_bin`, `_parse_json_list`,
  `BeadsError`, and the query/mutation verbs (`next_ready`,
  `list_in_progress`, `claim`, `close`, `revert_to_open`, `show`,
  `close_eligible_epics`).
- *Domain-policy concerns (bead-chain's own rules, not bd facts):*
  `EXCLUDED_TYPES` + `is_excluded_type`, `BLOCKING_BUG_TYPES`,
  `PARENT_EPIC_KEY` + `_PARENT_EPIC_FALLBACK_KEYS` +
  `extract_parent_epic_id`, and the shape-normalisers `_is_closed_epic` /
  `_normalise_closed_epic`.

That second bucket is *policy* ("an epic is a container we never drive",
"a bug with dependents jumps the queue", "the parent key is `parent` with
two fallbacks"). It is imported by `lifecycle.py` **and** `prompt.py`,
which is the tell: the predicates aren't transport, they're the shared
vocabulary of the whole plugin, currently homed inside the transport
layer. This is the clearest **leaky abstraction** in the codebase — the
"thin wrapper" leaks domain knowledge upward.

**Recommended split:** carve a `domain.py` (or `beadshape.py`) holding the
pure predicates and shape-normalisers + their constants. `beads.py` keeps
only subprocess + JSON-list transport and imports the policy it needs (or
the query funcs accept it). Result: `beads.py` drops well under 400 lines
and finally earns its "thin" docstring; `lifecycle`/`prompt` import
domain semantics from a module that's *about* domain semantics. This is
the one genuine module-split recommendation, and it's driven by
**cohesion, not line count**.

### 3. (MEDIUM PAIN) Hard coupling to `wiggum_state` internals in two places → wrap behind one adapter

Both `lifecycle.activate_next_bead` and
`register_callbacks.handle_bead_chain_command` call
`wiggum_state.start(goal_prompt, mode="goal")`, and both hooks read
`wiggum_state.is_active()`. That's a direct dependency on a *sibling
plugin's internal state module* — not a published API — in (at least)
three call sites across two files. If wiggum renames `start`, changes the
`mode` contract, or restructures its state, bead-chain breaks in multiple
spots with no single seam to fix.

**Recommended move:** a one-file `wiggum_adapter.py` exposing
`arm_goal(prompt)` and `is_goal_active()`. One import of
`code_puppy.plugins.wiggum.state` lives there; everyone else depends on
the adapter. Cheap insurance against a coupling you don't control.

### 4. (MEDIUM PAIN) `prompt.py` isn't pure, and duplicates epic-fetch with `lifecycle`

`prompt.py`'s own docstring confesses the leak: `_fetch_epic_context`
shells out via `bd show`, so the "prompt formatting" module carries a
subprocess dependency. More importantly, it **duplicates** an epic
round-trip that already happens in `lifecycle.ensure_epic_in_progress`:

- `lifecycle.ensure_epic_in_progress` → `show(epic_id)` to grab the
  epic's `title` for a log line.
- `prompt._fetch_epic_context` → `show(epic_id)` to grab `title` +
  description excerpt for the prompt.

On every newly-activated bead with a parent epic, that's potentially two
`bd show` calls on the same epic in the same turn — wasteful, and the
"how do we read an epic" knowledge now lives in two modules (a soft DRY +
abstraction-boundary smell).

**Recommended move:** consolidate epic-context fetching into a single
helper (natural home: the `domain.py` from #2, or a small `epic.py`) that
returns `(title, excerpt)` once; let both callers consume it. Keeps
`prompt.py` formatting-only at the seams and removes the double fetch.

### 5. (LOW PAIN) CLI flag parsing bolted into the wiring module

`register_callbacks._parse_max_iterations` (+ `_PARSE_ERROR` sentinel) is
argument-parsing — a distinct responsibility from hook wiring and command
registration. It's only ~40 lines for a single `--max` flag, so this is
borderline YAGNI today. Flag it as: *if a second flag ever appears*,
extract a `cli.py`. Until then, leave it — splitting one flag's parser
into its own module would be ceremony, not cohesion.

### Non-issues (explicitly cleared)

- `close_guard.py` (150 lines): cohesive — detector + its one hook
  handler living together is correct SRP, as its docstring argues. The
  decision to register it in `register_callbacks` while implementing it
  here is sound. Leave it.
- `state.py` (79 lines): a deliberately dumb data box mirroring wiggum's
  pattern. No behaviour to leak. Leave it.
- `register_callbacks.py` overall: the wiring/hooks/command split vs
  `lifecycle` is a clean, well-documented seam. Its only blemishes are #1
  (emit coupling, shared) and #5 (flag parsing, minor).

---

## Summary table — ranked

| # | Candidate | Pain | Type | Split? |
|---|-----------|------|------|--------|
| 1 | `lifecycle` decisions tangled with `emit_*` | High | DIP / testability | No — add `reporting` seam |
| 2 | `beads` = transport + domain policy | High | SRP / leaky abstraction | **Yes — extract `domain.py`** |
| 3 | `wiggum_state` coupling in 2 files | Med | Coupling to sibling plugin | No — add adapter |
| 4 | `prompt` impurity + epic-fetch dup | Med | SRP / DRY | No — consolidate fetch |
| 5 | `--max` parsing in wiring module | Low | SRP | Defer (YAGNI) |

## Bottom line

- **Only one module is a true split candidate, and it's about cohesion,
  not size:** `beads.py` should shed its domain-policy half into a
  `domain.py`. That single move also fixes the worst leaky abstraction
  (predicates living in the "thin" transport wrapper) and shrinks both
  large files indirectly.
- **The highest-pain item is not a split at all** — it's the `emit_*`
  coupling threaded through `lifecycle`'s decision logic. A small
  `reporting` indirection unlocks unit-testing the 4-tier waterfall and
  centralises the host-messaging dependency.
- **No module breaches the 600-line guideline.** Resist splitting
  `beads`/`lifecycle` purely to chase line counts; do it for the
  responsibility boundaries above or not at all.
