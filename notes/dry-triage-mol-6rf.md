# DRY Triage Report — bead_chain-mol-6rf

Duplication pass across the six pure-Python modules of the `bead_chain`
code-puppy plugin: `beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`.

> **Third pass.** Supersedes the `file:line` numbers in
> `notes/dry-triage-mol-47z.md` and `notes/dry-triage-mol-ejq.md` — every
> module has shifted again and **two new duplications have appeared**
> (see "What's new since mol-ejq" below). This report re-ran the tool
> against the *current* tree and re-verified every `file:line` by hand.
> It is a **triage report only** — no refactors were performed. Each
> hotspot is sized for its own follow-up refactor bead.

## Method

There is no `.jscpd.json` in this repo, so the pass was run by hand.

- **Tool:** `jscpd` via `npx` (Node v18.20.8 available locally).
- **Run 1 — `--min-tokens 50` (jscpd default):** `0` clones. No literal
  copy-pasted blocks survive at the standard threshold; the prior split
  into six focused modules continues to pay off.
- **Run 2 — `--min-tokens 20` (aggressive):** `5` clones,
  `36` duplicated lines (1.65%), `227` duplicated tokens (2.63%).
  *(Up from 4 clones / 28 lines in mol-ejq — the chain-drive path grew.)*

```bash
npx jscpd --min-tokens 20 --format python \
  beads.py lifecycle.py prompt.py register_callbacks.py close_guard.py state.py
```

jscpd's token-stream detector only catches *literal* repetition. The
higher-value duplication here is **structural / semantic** (same shape,
slightly different identifiers and warning strings) which a token
detector under-reports. This report combines the jscpd hits with a
careful manual read focused on the three categories the bead calls out:
**bd-subprocess invocation**, **JSON parsing**, and **status-handling**.

### Raw jscpd clones (min-tokens 20)

| # | Location A | Location B | Maps to |
|---|------------|------------|---------|
| C1 | `lifecycle.py:573-581` | `lifecycle.py:590-598` (self-clone) | H2 (NEW) |
| C2 | `lifecycle.py:661-671` | `lifecycle.py:680-690` (self-clone) | H3 |
| C3 | `lifecycle.py:662-668` | `register_callbacks.py:232-238` | H3 / H4 |
| C4 | `lifecycle.py:697-703` | `register_callbacks.py:258-264` | H4 |
| C5 | `lifecycle.py:714-720` | `register_callbacks.py:276-281` | H4 |

### What's new since mol-ejq

- **H2 is brand new** — the gate-probe re-pick (FB-3 / `x3g`) added a
  *second* verbatim `try: pick_next_bead() except BeadsError: warn +
  stop` block inside `activate_next_bead`, creating a self-clone.
- **H3 grew a third copy** — the fan-out-gate guard (FB-13 / `9sc`)
  added another `revert-and-stop` tail next to the blocker gate.
- **H6 is new** — the gate-check (`_parse_gate_check_summary`) and lint
  (`_parse_lint_missing`) parsers, both added after mol-ejq, each
  hand-roll the *same* "find the first `{...}` then `json.loads`"
  brace-extraction preamble.
- The single-object JSON hand-roll count grew **3 → 6** (H5).

---

## Ranked duplication hotspots

### H1 — Epic-leak guard block (status-handling) — HIGH

The "an upstream filter leaked an epic, refuse + warn + stop" block is
copy-pasted **three times** with near-identical warning strings:

- `lifecycle.py:255-272` — `close_current_bead_success()` (refuse to close; also reverts + clears `current_bead`)
- `lifecycle.py:632-640` — `activate_next_bead()` (refuse to activate; `state.stop()`)
- `register_callbacks.py:209-216` — `handle_bead_chain_command()` (refuse to start; `return True`)

All three share the shape:

```python
if is_excluded_type(bead):
    emit_warning(
        f" bead-chain refused to <verb> {bead_id}: it's an excluded "
        f"container type ({bead.get('issue_type', '?')}). "
        "An upstream filter leaked an epic into the chain — this is a bug."
    )
    ...stop / revert / return
```

**Refactor:** extract `lifecycle._refuse_excluded(bead, *, verb: str) -> bool`
that emits the canonical warning and returns whether the bead was
refused. The `close_current_bead_success` variant additionally
reverts + clears `current_bead`, so expose those as flags rather than
forcing all three call sites identical. Biggest DRY win: the foot-gun
warning text lives in one place; a wording change stops requiring a
three-site, two-file sweep.

### H2 — `pick_next_bead` try/except self-clone (status-handling) — HIGH *(NEW)*

jscpd-confirmed self-clone C1 (`lifecycle.py:573-581` ⇄ `590-598`).
`activate_next_bead()` now calls `pick_next_bead()` twice — once up
front, once after `probe_resolved_gates()` re-opens a gated bead — and
both calls carry the **verbatim** error tail:

```python
try:
    bead = pick_next_bead(just_closed)
except BeadsError as exc:
    emit_warning(f" bead-chain stopping — `bd ready` failed: {exc}")
    state.stop()
    return None
```

- `lifecycle.py:573-577` — initial pick
- `lifecycle.py:590-594` — post-gate-probe re-pick

**Refactor:** a tiny local `_pick_or_stop(just_closed)` (or inline
`_safe_pick`) that wraps the call + stop-on-`BeadsError` tail and
returns `bead | None`, with a sentinel for the stop case. Collapses two
divergence-prone copies into one. Low risk, fully covered by the
existing `activate_next_bead` tests.

### H3 — `activate_next_bead` revert-and-stop self-clone (status-handling) — HIGH

jscpd-confirmed self-clone C2 (`lifecycle.py:661-671` ⇄ `680-690`).
`activate_next_bead()` contains two back-to-back guard blocks — the
open-blocker gate and the fan-out gate (`waits_for: children-of(...)`)
— each ending in the same revert-and-stop tail:

- `lifecycle.py:656-668` — open work-time blocker gate
- `lifecycle.py:674-687` — fan-out gate (bead_chain-9sc workaround)

```python
if <gate fails>:
    emit_warning(f"bead-chain refused to activate {bead_id}: ...")
    if not recovery:
        try:
            revert_to_open(bead_id)
            emit_info(f"reverted {bead_id} to open")
        except BeadsError as exc:
            emit_warning(f"also couldn't revert {bead_id}: {exc}")
    state.stop()
    return None
```

The 6-line `if not recovery: try: revert_to_open(...) ... state.stop()`
tail is **verbatim** in both (and a third near-copy of just the revert
half lives in `register_callbacks.py:232-238`, see H4).

**Refactor:** extract `lifecycle._revert_and_stop(bead_id, *, recovery: bool) -> None`
(or fold both gates through one `_refuse_activation(bead_id, reason, *,
recovery)`). Single source of truth for the revert policy.

### H4 — Claim-and-arm cross-file block (status-handling) — HIGH

jscpd-confirmed clones C3/C4/C5. The "walk the hierarchy top-down →
claim → assign state → apply hints → arm wiggum" flow is duplicated
between the startup path and the per-iteration path:

- `register_callbacks.py:251-281` — `handle_bead_chain_command()`
- `lifecycle.py:689-721` — `activate_next_bead()`

Both contain the **verbatim** ~9-line "Walk the hierarchy top-down…"
comment, `ensure_epic_in_progress(bead)`, the
`if not recovery: try: claim(bead_id) except BeadsError: ...stop` block,
then `state.get_state().current_bead = bead` →
`apply_execution_hints(bead)` → `format_bead_as_goal(bead, recovery=...)`
→ `wiggum_state.start(goal_prompt, mode="goal")`. The two copies differ
only in their final `emit_*` lines and stop-return convention
(`return None` vs `return True`) — exactly the kind of near-twin that
silently drifts.

**Refactor:** extract `lifecycle.claim_and_arm(bead, *, recovery: bool) -> str`
returning the `goal_prompt`. Both the startup command and
`activate_next_bead` call it. Kills the duplicated comment and the
subtly-divergent error handling. (Closely related to H1–H3; all four
live on the same "drive a bead" path through `activate_next_bead` and
`handle_bead_chain_command`.)

### H5 — Lenient single-object JSON parsing (JSON parsing) — MEDIUM

`_parse_json_list()` (`beads.py:166-191`) already centralises the
*list* case, but **six** functions hand-roll their own single-object
`json.loads` with divergent error policies:

| Site | Function | Bad-JSON policy |
|------|----------|-----------------|
| `beads.py:657-659` | `show()` | **raises** |
| `beads.py:704-710` | `memories()` | **raises** |
| `beads.py:773-775` | `has_epic_in_progress()` | **swallows** |
| `beads.py:906-908` | `_parse_close_eligible_payload()` | **swallows** |
| `beads.py:997-999` | `_parse_gate_check_summary()` | **swallows** (+ brace-extract, H6) |
| `beads.py:1063-1065` | `_parse_lint_missing()` | **swallows** (+ brace-extract, H6) |

The `snippet = raw[:200].replace("\n", " ")` error-snippet construction
is *also* copy-pasted across `_parse_json_list` (`beads.py:185`),
`show()` and `memories()`.

**Refactor:** add a `_parse_json_object(raw, context, *, strict: bool)`
counterpart to `_parse_json_list`, plus a `_json_snippet(raw)` helper so
the snippet formatting + decode-error handling live in one place.
**Preserve the intentional raise-vs-swallow split** via the `strict`
flag — do not flatten it.

### H6 — Brace-extraction JSON preamble (JSON parsing) — MEDIUM *(NEW)*

`_parse_gate_check_summary()` and `_parse_lint_missing()` both deal with
`bd` commands that wrap their JSON in human-readable noise, so each
hand-rolls the **same** "carve out the first `{...}`" preamble:

- `beads.py:993-998` — `_parse_gate_check_summary()`
- `beads.py:1059-1064` — `_parse_lint_missing()`

```python
start = raw.find("{")
end = raw.rfind("}")
if start == -1 or end == -1 or end < start:
    ...
payload = json.loads(raw[start : end + 1])
```

**Refactor:** a small `_extract_json_object(raw)` helper (returns the
`{...}` substring or `None`) that both parsers share. Pure function,
trivially unit-tested. Naturally folds into the H5 `_parse_json_object`
work (the brace-extract is just a pre-step before the shared decode).

### H7 — Client-side epic-filter loop (status-handling) — MEDIUM

The "return first dict that isn't an excluded type" predicate is
repeated across the ready/list helpers:

- `beads.py:342-344` — `next_ready()` (loop, returns first)
- `beads.py:454-456` — `next_ready_in_epic()` (loop, returns first)
- `beads.py:384` — `_list_by_status()` (comprehension, returns all)
- `beads.py:593+` — `next_blocking_bug()` (variant inner loop)

```python
for item in items:
    if isinstance(item, dict) and not is_excluded_type(item):
        return item
return None
```

**Refactor:** `_first_drivable(items)` (loop case) and/or
`_drivable_only(items)` (list case) centralise the
`isinstance(dict) and not is_excluded_type` predicate. Low risk, pure
function, trivially tested.

### H8 — `str(bead.get("id", "<unknown>"))` + emit micro-pattern — LOW

The "pull an id (defaulting to `<unknown>`/`""`) then emit a log line"
micro-pattern recurs throughout `lifecycle.py` and
`register_callbacks.py`. A `bead_id_of(bead)` helper would DRY the
literal, but the surrounding messages are genuinely different.
Borderline YAGNI — fold into H1/H3 if convenient, otherwise leave it.
Listed for completeness.

### H9 — Duplicated import block — NOISE (do not refactor)

jscpd at very low thresholds flags both `lifecycle.py` and
`register_callbacks.py` importing `emit_*` from `code_puppy.messaging`
and names from `.beads`. **Not actionable** — that's how Python imports
work; DRYing imports would be a YAGNI violation.

---

## Note on bd-subprocess invocation (the bead's first category)

Good news: **there is no duplication here.** Every `bd` call funnels
through the single `_run_bd()` transport (`beads.py:283`), the
`--exclude-type` arg is centralised in `_exclude_type_arg()`
(`beads.py:212`), and the binary lookup lives in `_bd_bin()`
(`beads.py:233`). This category was a hotspot in earlier eras of the
codebase but has been fully consolidated. Nothing to file.

---

## Summary & recommendation

The codebase remains in good DRY shape (**0 clones at the standard
50-token threshold**). The duplication that exists is **semantic
status-handling repetition** on the "drive a bead" path that a
token-based tool under-reports — and the chain-drive path has grown two
*new* duplications (H2, H6) since mol-ejq.

**Recommended refactor beads:**

1. **One bead covering H1–H4** (the high-priority chain-drive cleanup —
   `_refuse_excluded`, `_pick_or_stop`, `_revert_and_stop`,
   `claim_and_arm`). They all live on the same two functions
   (`activate_next_bead` / `handle_bead_chain_command`) and share
   state-management concerns, so doing them together avoids
   half-refactoring the flow.
2. **One smaller bead for H5 + H6 + H7** (the `beads.py` purity pass —
   `_parse_json_object` + `_json_snippet` + `_extract_json_object` +
   `_first_drivable`, preserving the raise-vs-swallow policy split).

H8 is borderline-YAGNI; H9 is noise; bd-subprocess invocation is
already clean. No refactor warranted for those.

## Bug-discovery protocol

No bugs discovered during this triage.

## Acceptance criteria — met

- [x] Ran a duplication pass locally (`jscpd` via `npx`, Node available)
      at both the default (50) and aggressive (20) min-token thresholds.
- [x] Combined the token-detector hits with a careful manual read of the
      three named categories (bd-subprocess, JSON parsing, status-handling).
- [x] Produced a **ranked** list of duplication hotspots with verified
      `file:line` and a sized refactor recommendation for each.
- [x] Re-verified every `file:line` against the *current* tree and noted
      drift vs. the prior `mol-47z` / `mol-ejq` passes.
- [x] `ruff check .` + `ruff format .` clean; `pytest` green (report-only
      bead — no code changed).
