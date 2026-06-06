# SOLID Review — Responsibility & Coupling (bead_chain-mol-9o2)

Judgment-only review of the six pure-Python modules in the `bead_chain`
code-puppy plugin: `beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`.

There is no mechanical tool for SRP / coupling — this is a careful read
focused on the three things the bead calls out:

1. SRP violations (modules approaching/over the 600-line guideline).
2. Leaky abstractions across the `beads` / `lifecycle` / `prompt` boundary.
3. Tight coupling to the code_puppy host callback API.

> This is an **independent re-review** done against the *current* tree.
> A prior pass exists (`solid-review-mol-4yc.md`). Its findings still
> largely hold, but the codebase has **grown materially since then**, and
> two of its conclusions are now stale — see "What changed since
> mol-4yc" below. Read this doc as the current state of the world.

## Method

- Read every module end-to-end.
- Measured size: `wc -l *.py`.
- Mapped the host-coupling surface: `rg code_puppy`.
- Traced the cross-module call graph (`rg` for private-function reach-across,
  `wiggum_state.*`, dead public API).
- Re-ran the test suite (`pytest -q` → **63 passed**) so findings rest on a
  green baseline.

## Size snapshot (the SRP-by-line question)

| Module                  | Lines | % of 600 cap | vs mol-4yc |
|-------------------------|-------|--------------|------------|
| **lifecycle.py**        | **690** | **115%**  | +209 (was 481) |
| **beads.py**            | **611** | **102%**  | +107 (was 504) |
| register_callbacks.py   | 398   | 66%          | +42 (was 356)  |
| prompt.py               | 317   | 53%          | unchanged      |
| close_guard.py          | 150   | 25%          | unchanged      |
| state.py                | 79    | 13%          | unchanged      |

**Verdict on size:** `lifecycle.py` and `beads.py` now **both breach the
600-line guideline** (690 and 611). The prior review's headline — "nobody
breaches 600, don't split for line count" — is **no longer true**. The
guideline is now actively violated by the two most logic-dense files, and
both have grown ~20-40% since the last review. That tips the two largest
refactor candidates (#1 and #2 below) from "nice cohesion cleanup" to
"now also required to get back under the project's own cap." Crucially,
**the right splits are still cohesion-driven** — the line cap just removed
the "leave it alone" escape hatch.

---

## What changed since mol-4yc (so judges don't have to diff)

1. **Both big files now breach 600** (was: neither did). The "resist
   splitting purely to chase line counts" advice is obsolete — the splits
   below are now *both* cohesion-correct *and* cap-relieving.
2. **A new, worse leaky abstraction landed:** the `bead_chain-9sc`
   fan-out-gate workaround (`lifecycle._has_fan_out_gate_issue`) reaches
   into `beads`' **private** functions `_run_bd` / `_parse_json_list`
   (lifecycle.py:679-680). That is a harder boundary violation than the
   prompt-impurity smell that topped the old "medium" list. New #2 below.
3. **Two public functions are now dead:** `beads.is_blocked` and
   `beads.next_in_progress` have **zero real call sites** (only docstrings
   and docs reference them). New low-pain finding #6.

---

## Findings — refactor candidates ranked by pain

### 1. (HIGHEST PAIN) `lifecycle.py` is over-cap *and* tangles decisions with `emit_*` side effects → DIP violation, untestable brain

`lifecycle.py` is "the state-transition brain" — and at **690 lines it's
the single largest file, now 15% over the cap**. Two problems compound:

- **DIP / testability:** almost every function reaches straight for the
  host's `emit_info` / `emit_warning` / `emit_success`. That welds pure
  decision logic to the code_puppy messaging system, so you can't
  unit-test the *decisions* without the host present. `pick_next_bead`
  (the 4-tier waterfall: tier 0 stranded → tier 1 blocking bug → tier 2
  epic affinity → tier 3 global) is exactly the thing you'd want a
  table-driven test over, and right now you can't write one without
  stubbing the host. `close_current_bead_success`,
  `enforce_single_in_progress`, `ensure_epic_in_progress`,
  `activate_next_bead`, `rollup_completed_epics`, `_unblocked_in_progress`,
  `_reject_if_blocked` all mix "decide + mutate bd + mutate state + tell
  the user" in one body.
- **Size:** the file is doing startup-invariant guarding, close+rollup,
  epic claiming, the next-bead waterfall, activation, *and* the fan-out
  gate detector (#2). That's a lot of distinct responsibilities for one
  module — the line count is the symptom; the responsibility sprawl is the
  disease.

**Why it's #1:** highest-value logic, blocked from unit testing, densest
host coupling in the codebase, *and* it's the worst cap breach. The
`emit_*` indirection unlocks tests; pulling out the fan-out gate (#2)
plus the `beads` domain split (#3) is what actually gets it back under
600 without arbitrary slicing.

**Recommended moves (no arbitrary split):**
- Introduce a tiny `reporting.py` seam — `lifecycle` calls
  `from .reporting import info, warn, success`, and `reporting.py` is the
  *only* place importing `code_puppy.messaging`. Tests monkeypatch
  `reporting`. ~30 lines, collapses the duplicate emit-imports now in
  three files, and finally makes the waterfall testable.
- Extract the fan-out gate (#2) and lean on the `beads` domain split (#3)
  — those two moves shed the lines that pushed `lifecycle` over cap, for
  *cohesion* reasons, not to hit a number.

### 2. (HIGH PAIN — NEW) `lifecycle._has_fan_out_gate_issue` reaches into `beads` **private** functions → hard encapsulation break + misplaced responsibility

The `bead_chain-9sc` fan-out-gate workaround added
`_has_fan_out_gate_issue` to `lifecycle.py`, and it does this
(lifecycle.py:679-680):

```python
raw = beads._run_bd("list", "--json")
all_issues = beads._parse_json_list(raw, "bd list --json")
```

That is `lifecycle` reaching **past the public `beads` API into its
private transport internals** (`_run_bd`, `_parse_json_list` are
underscore-prefixed by intent). It's the clearest abstraction-boundary
violation in the tree right now:

- **Encapsulation break:** the whole point of `beads.py` is that it owns
  *all* `bd` subprocess traffic behind named verbs. A raw
  `bd list --json` "list every issue" query has no public home — so the
  caller punched through to the private layer instead. If `beads` changes
  its retry/parse internals, `lifecycle` breaks silently.
- **Misplaced responsibility:** parsing `waits_for: children-of(<id>)`,
  unpacking the spawner id, and scanning children is *gate-detection
  policy*, not state-transition brain. ~70 lines of it now live in the
  brain module, inflating it (#1) and mixing concerns.
- **Bonus smell (non-blocking, not filed):** that `bd list --json`
  full-table scan is unpaginated and loops in Python over *every* issue —
  fine today, O(N) foot-gun on a big repo. Note, don't fix here.

**Recommended move:** give `beads` a public verb for the query it needs
(e.g. `list_all()` or `children_of(spawner_id)`), then lift the gate
predicate into a small cohesive home — either the `domain.py` from #3 or
a dedicated `gates.py`. `lifecycle` then calls a *public* predicate
(`gates.has_unsatisfied_fan_out(bead_id)`) instead of hand-rolling
transport. Kills the private reach-across, shrinks `lifecycle`, and makes
the gate independently testable.

### 3. (HIGH PAIN) `beads.py` is two modules in a trenchcoat: bd-transport vs bead-domain policy → SPLIT CANDIDATE (now also over-cap)

The docstring says "thin subprocess wrapper around the `bd` CLI." At
**611 lines it is neither thin nor under cap**, because it has accreted
**bead-chain domain policy** that has nothing to do with talking to a
subprocess:

- *Transport concerns (genuinely "bd client"):* `_run_bd` + retry policy
  (`MAX_ATTEMPTS`, `_RETRY_BACKOFFS`), `_bd_bin`, `_parse_json_list`,
  `BeadsError`, and the query/mutation verbs (`next_ready`,
  `list_in_progress`, `next_ready_in_epic`, `next_blocking_bug`, `claim`,
  `close`, `revert_to_open`, `show`, `has_epic_in_progress`,
  `close_eligible_epics`, `open_blocker_ids`).
- *Domain-policy concerns (bead-chain's own rules, not bd facts):*
  `EXCLUDED_TYPES` + `is_excluded_type`, `BLOCKING_BUG_TYPES`,
  `BLOCKING_DEP_TYPES`, `SATISFIED_BLOCKER_STATUSES`, `PARENT_EPIC_KEY` +
  `_PARENT_EPIC_FALLBACK_KEYS` + `extract_parent_epic_id`, and the
  shape-normalisers `_is_closed_epic` / `_normalise_closed_epic`.

That second bucket is *policy* ("an epic is a container we never drive",
"a bug with dependents jumps the queue", "a `blocks` edge is the only
work-time blocker", "the parent key is `parent` with two fallbacks"). It
is imported by `lifecycle.py` **and** `prompt.py` — that's the tell: the
predicates aren't transport, they're the shared vocabulary of the whole
plugin, currently homed inside the transport layer. This is the clearest
*structural* leaky abstraction: the "thin wrapper" leaks domain knowledge
upward.

**Recommended split:** carve a `domain.py` (or `beadshape.py`) holding the
pure predicates + shape-normalisers + their constants. `beads.py` keeps
only subprocess + JSON-list transport. Result: `beads.py` drops well
under 400 lines (back under cap), finally earns its "thin" docstring; and
`lifecycle`/`prompt` import domain semantics from a module that's *about*
domain semantics. The pure predicates also become trivially unit-testable
without any `bd`/host involvement. **This is the one genuine module-split
recommendation — driven by cohesion, and now doubly justified because it
relieves a real cap breach.**

### 4. (MEDIUM PAIN) Hard coupling to `wiggum_state` internals across two files → wrap behind one adapter

`lifecycle.activate_next_bead` (lifecycle.py:616) and
`register_callbacks.handle_bead_chain_command` (register_callbacks.py:272)
both call `wiggum_state.start(goal_prompt, mode="goal")`, and the turn-end
hook reads `wiggum_state.is_active()` (register_callbacks.py:312). That's
a direct dependency on a *sibling plugin's internal state module* — not a
published API — across **3 call sites in 2 files**. If wiggum renames
`start`, changes the `mode` contract, or restructures its state,
bead-chain breaks in multiple spots with no single seam to fix. (The
lazy-hook-ordering dance documented in `register_callbacks` is itself a
symptom of how tightly the two are coupled.)

**Recommended move:** a one-file `wiggum_adapter.py` exposing
`arm_goal(prompt)` and `is_goal_active()`. One import of
`code_puppy.plugins.wiggum.state` lives there; everyone else depends on
the adapter. Cheap insurance against a coupling you don't control, and it
gives the lazy-registration explanation one obvious home.

### 5. (MEDIUM PAIN) `prompt.py` isn't pure, and duplicates epic-fetch with `lifecycle`

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
helper (natural home: the `domain.py` from #3, or a small `epic.py`) that
returns `(title, excerpt)` once; let both callers consume it. Keeps
`prompt.py` formatting-only at the seams and removes the double fetch.

### 6. (LOW PAIN — NEW) Dead public API: `beads.is_blocked` and `beads.next_in_progress`

`rg` shows both functions have **zero real call sites** — they appear only
in docstrings (`lifecycle.py:403` mentions `is_blocked` prose) and in the
generated docs. Callers use `open_blocker_ids(...)` and
`list_in_progress(...)[0]` directly instead.

- `is_blocked` is a thin `bool(open_blocker_ids(...))` wrapper nobody
  calls — textbook YAGNI surface.
- `next_in_progress` is a "head of `list_in_progress`" convenience nobody
  calls.

Not a bug, just unused API widening the module's surface (and its line
count, #3). **Recommended move:** delete both, or — if they're a
deliberate public convenience layer — add the missing test coverage and a
note saying "kept as public API." Don't leave them as untested orphans.

### 7. (LOW PAIN) CLI flag parsing bolted into the wiring module

`register_callbacks._parse_max_iterations` (+ `_PARSE_ERROR` sentinel) is
argument-parsing — a distinct responsibility from hook wiring and command
registration. It's only ~40 lines for a single `--max` flag, so this is
borderline YAGNI today. Flag it as: *if a second flag ever appears*,
extract a `cli.py`. Until then, leave it — splitting one flag's parser
into its own module would be ceremony, not cohesion.

### Non-issues (explicitly cleared)

- `close_guard.py` (150 lines): cohesive — detector + its one hook handler
  living together is correct SRP, as its docstring argues. Registering it
  in `register_callbacks` while implementing it here is a sound, documented
  call. Leave it. (Its `emit_warning` import is the same shared #1 coupling,
  not a `close_guard`-specific flaw.)
- `state.py` (79 lines): a deliberately dumb data box mirroring wiggum's
  pattern. No behaviour to leak. Leave it.
- `register_callbacks.py` (398 lines): the wiring/hooks/command split vs
  `lifecycle` is a clean, well-documented seam, comfortably under cap. Its
  only blemishes are #1 (emit coupling, shared), #4 (wiggum coupling,
  shared) and #7 (flag parsing, minor).

---

## Summary table — ranked

| # | Candidate | Pain | Type | Split? |
|---|-----------|------|------|--------|
| 1 | `lifecycle` over-cap (690) + decisions tangled with `emit_*` | **High** | DIP / testability / SRP | No — add `reporting` seam; shed #2/#3 |
| 2 | `lifecycle` fan-out gate reaches into `beads` privates | **High** | Leaky abstraction / encapsulation | Yes — public `beads` verb + `gates.py` |
| 3 | `beads` over-cap (611) = transport + domain policy | **High** | SRP / leaky abstraction | **Yes — extract `domain.py`** |
| 4 | `wiggum_state` coupling, 3 sites / 2 files | Med | Coupling to sibling plugin | No — add adapter |
| 5 | `prompt` impurity + epic-fetch dup | Med | SRP / DRY | No — consolidate fetch |
| 6 | Dead public API (`is_blocked`, `next_in_progress`) | Low | YAGNI / dead code | Delete or cover |
| 7 | `--max` parsing in wiring module | Low | SRP | Defer (YAGNI) |

## Bottom line

- **The project now violates its own 600-line guideline in two files**
  (`lifecycle.py` 690, `beads.py` 611). The prior review's "leave the big
  files alone" verdict is stale. The good news: the *correct* cohesion
  splits below are exactly what gets them back under cap — you don't have
  to slice arbitrarily.
- **Two true split candidates, both cohesion-driven:**
  1. Extract `beads`' domain-policy half into `domain.py` (#3) — fixes the
     structural leaky abstraction *and* relieves `beads`' cap breach.
  2. Lift the fan-out gate out of `lifecycle` into a `gates.py` behind a
     *public* `beads` query (#2) — kills the private-function reach-across
     *and* sheds the lines that pushed `lifecycle` over cap.
- **The highest-pain item is still not a split** — it's the `emit_*`
  coupling threaded through `lifecycle`'s decision logic (#1). A small
  `reporting` indirection unlocks unit-testing the 4-tier waterfall and
  centralises the host-messaging dependency that's currently duplicated
  across three files.
- **No new bugs filed.** Every finding here is a refactor candidate that
  is *in scope for this review bead* (it's what the bead asked us to
  surface), not an unrelated defect. The one runtime-adjacent smell (the
  unpaginated `bd list --json` full scan in the fan-out gate, #2) is noted
  as a future concern, not a current defect.
