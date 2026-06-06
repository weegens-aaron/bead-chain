# DRY Triage Report — bead_chain-mol-47z

Duplication pass across the six pure-Python modules of the `bead_chain`
code-puppy plugin: `beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`.

## Method

There is no `.jscpd.json` in this repo, so a pass was run by hand.

- **Tool:** `jscpd` via `npx` (Node v18.20.8 available locally).
- **Run 1 — `--min-tokens 50` (jscpd default):** `0` clones. No
  large copy-pasted blocks exist; the prior split into `beads` /
  `lifecycle` / `prompt` / `register_callbacks` / `close_guard` /
  `state` already paid off.
- **Run 2 — `--min-tokens 20` (aggressive):** `3` clones,
  `18` duplicated lines (0.96%), `122` duplicated tokens (1.55%).

```
npx jscpd --min-tokens 20 --format python \
  beads.py lifecycle.py prompt.py register_callbacks.py close_guard.py state.py
```

jscpd's token-stream detector only catches *literal* repetition. The
more valuable duplication here is **structural / semantic** (same shape,
slightly different identifiers and strings) which a token detector
misses — so this report combines the jscpd hits with a careful manual
read focused on the three categories the bead calls out:
bd-subprocess invocation, JSON parsing, and status-handling blocks.

This is a **triage report only** — no refactors were performed. Each
hotspot below is sized for its own follow-up refactor bead.

---

## Ranked duplication hotspots

### 🥇 H1 — Epic-leak guard block (status-handling) — HIGH

The "an upstream filter leaked an epic, refuse + warn + stop" block is
copy-pasted **three times**, with near-identical warning strings:

- `lifecycle.py:188-205` — `close_current_bead_success()` (refuse to close)
- `lifecycle.py:437-446` — `activate_next_bead()` (refuse to activate)
- `register_callbacks.py:203-211` — `handle_bead_chain_command()` (refuse to start)

All three share the shape:

```python
if is_excluded_type(bead):
    emit_warning(
        f"🚫 bead-chain refused to <verb> {bead_id}: it's an excluded "
        f"container type ({bead.get('issue_type', '?')}). "
        "An upstream filter leaked an epic into the chain — this is a bug."
    )
    ...stop / return
```

**Refactor:** extract a helper, e.g.
`lifecycle._refuse_excluded(bead, *, verb: str) -> bool`, that emits the
canonical warning and returns whether the bead was refused. The
`close_current_bead_success` variant also reverts + clears
`current_bead`, so the helper should expose those as flags rather than
forcing all three call sites identical. Biggest DRY win in the repo:
the foot-gun warning text lives in one place, and a wording/format
change stops requiring a three-file sweep.

### 🥈 H2 — Claim-vs-recovery activation block (status-handling) — HIGH

jscpd-confirmed clone (`lifecycle.py:455-461` ⇄
`register_callbacks.py:228-234`). The "walk the hierarchy top-down"
flow is duplicated between the startup path and the per-iteration path:

- `register_callbacks.py:218-238` — `handle_bead_chain_command()`
- `lifecycle.py:449-468` — `activate_next_bead()`

Both contain the **verbatim** ~8-line "Walk the hierarchy top-down…"
comment, the `ensure_epic_in_progress(bead)` call, and the
`if not recovery: try: claim(bead_id) except BeadsError: ...stop` block,
then `state.get_state().current_bead = bead` +
`format_bead_as_goal(...)` + `wiggum_state.start(...)`.

**Refactor:** extract a shared
`lifecycle.claim_and_arm(bead, *, recovery: bool)` that does the
epic-first claim, the conditional `claim`, the state assignment, and the
wiggum arming. Both the startup command and `activate_next_bead` call it.
Kills the duplicated comment and the subtly-divergent error handling.

### 🥉 H3 — Client-side epic-filter loop (status-handling) — MEDIUM

jscpd-confirmed clone (`beads.py:208-214` ⇄ `beads.py:273-279`). The
"return first dict that isn't an excluded type" loop is repeated:

- `beads.py:210-215` — `next_ready()`
- `beads.py:275-280` — `next_ready_in_epic()`
- (variant) `beads.py:299-308` — `next_blocking_bug()` inner loop
- (variant) `beads.py:233-235` — `list_in_progress()` comprehension

```python
for item in items:
    if isinstance(item, dict) and not is_excluded_type(item):
        return item
return None
```

**Refactor:** a tiny `_first_drivable(items)` helper (and/or
`_drivable_only(items)` for the list case) centralises the
`isinstance(dict) and not is_excluded_type` predicate. Low risk, pure
function, trivially testable.

### H4 — Lenient single-object JSON parsing (JSON parsing) — MEDIUM

`_parse_json_list()` (`beads.py:114-135`) already centralises the
*list* case, but three functions hand-roll their own `json.loads` with
divergent error policies:

- `beads.py:330-339` — `show()` (raises on bad JSON, with the
  `snippet = raw[:200].replace("\n", " ")` pattern that is itself a copy
  of the snippet logic inside `_parse_json_list`)
- `beads.py:362-369` — `has_epic_in_progress()` (swallows on bad JSON)
- `beads.py:392-398` — `close_eligible_epics()` (swallows on bad JSON)

The `raw[:200]` snippet construction is duplicated between
`_parse_json_list` and `show`.

**Refactor:** add a `_parse_json(raw, context, *, strict: bool)` (or a
`_json_snippet(raw)` helper plus a single-object parse counterpart) so
the snippet formatting and decode-error handling live in one place.
Note the *intentional* policy split (raise vs. swallow) — the refactor
should preserve it via a flag, not flatten it.

### H5 — `str(bead.get("id", "<unknown>"))` + emit pattern — LOW

The "pull an id (defaulting to `<unknown>`/`?`) then emit a log line"
micro-pattern recurs throughout, e.g.:

- `lifecycle.py:382-386, 389-391` — `pick_next_bead()` (three tiers)
- `lifecycle.py:301-306` — `rollup_completed_epics()`
- `register_callbacks.py:382` etc.

**Refactor:** marginal. A `bead_id_of(bead)` helper would DRY the
`str(bead.get("id", "<unknown>"))` literal, but the surrounding emit
calls are genuinely different messages. Borderline YAGNI — fold into
H1/H2 if convenient, otherwise leave it. Listed for completeness.

### H6 — Duplicated import block — NOISE (do not refactor)

jscpd flagged `lifecycle.py:26-32` ⇄ `register_callbacks.py:64-70` as a
clone. This is just both modules importing `emit_*` from
`code_puppy.messaging` / names from `.beads`. **Not actionable** — it's
how Python imports work, and DRYing imports would be a YAGNI violation.

---

## Summary & recommendation

The codebase is in good DRY shape (0 clones at the standard 50-token
threshold). The duplication that exists is **semantic status-handling
repetition** that a token-based tool under-reports. Recommend filing
**one refactor bead covering H1–H3** (the high/medium status-handling
hotspots — they're closely related and touch the same "drive a bead"
flow) and optionally a **second, smaller bead for H4** (JSON parsing
consolidation, with care to preserve the raise-vs-swallow policy split).

H5 is borderline-YAGNI; H6 is noise. No refactor warranted for either.
