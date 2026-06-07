# DRY Triage Report — bead_chain-mol-ejq

Duplication pass across the six pure-Python modules of the `bead_chain`
code-puppy plugin: `beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`.

> Supersedes the line numbers in `notes/dry-triage-mol-47z.md`. The
> modules have shifted since that pass (every cited line moved, and a
> **new** internal self-clone has appeared in `lifecycle.py`). This
> report re-ran the tool against the *current* tree and re-verified
> every `file:line`. It is a **triage report only** — no refactors were
> performed.

## Method

There is no `.jscpd.json` in this repo, so the pass was run by hand.

- **Tool:** `jscpd` via `npx` (Node v18.20.8 available locally).
- **Run 1 — `--min-tokens 50` (jscpd default):** `0` clones. No literal
  copy-pasted blocks survive at the standard threshold; the prior split
  into six focused modules already paid off.
- **Run 2 — `--min-tokens 20` (aggressive):** `4` clones,
  `28` duplicated lines (1.25%), `177` duplicated tokens (1.89%).

```bash
npx jscpd --min-tokens 20 --format python \
  beads.py lifecycle.py prompt.py register_callbacks.py close_guard.py state.py
```

jscpd's token-stream detector only catches *literal* repetition. The
more valuable duplication here is **structural / semantic** (same shape,
slightly different identifiers and warning strings) which a token
detector under-reports. This report combines the jscpd hits with a
careful manual read focused on the three categories the bead calls out:
bd-subprocess invocation, JSON parsing, and status-handling blocks.

### Raw jscpd clones (min-tokens 20)

| # | Location A | Location B |
|---|------------|------------|
| C1 | `lifecycle.py:564-570` | `register_callbacks.py:231-237` |
| C2 | `lifecycle.py:582-592` | `lifecycle.py:563-573` (self-clone) |
| C3 | `lifecycle.py:599-605` | `register_callbacks.py:257-263` |
| C4 | `beads.py:289-295` | `beads.py:224-230` |

---

## Ranked duplication hotspots

### H1 — Epic-leak guard block (status-handling) — HIGH

The "an upstream filter leaked an epic, refuse + warn + stop" block is
copy-pasted **three times**, with near-identical warning strings. (Below
the jscpd threshold because the bodies diverge after the warning, but
the highest-value DRY target — the foot-gun text lives in triplicate.)

- `lifecycle.py:239-244` — `close_current_bead_success()` (refuse to close; also reverts + clears `current_bead`)
- `lifecycle.py:534-542` — `activate_next_bead()` (refuse to activate; `state.stop()`)
- `register_callbacks.py:208-214` — `handle_bead_chain_command()` (refuse to start; returns `True`)

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

**Refactor:** extract a helper, e.g.
`lifecycle._refuse_excluded(bead, *, verb: str) -> bool`, that emits the
canonical warning and returns whether the bead was refused. The
`close_current_bead_success` variant additionally reverts + clears
`current_bead`, so expose those as flags rather than forcing all three
call sites identical. Biggest DRY win: a wording/format change to the
foot-gun warning stops requiring a three-file sweep.

### H2 — `activate_next_bead` internal refuse-and-revert self-clone (status-handling) — HIGH

**New since mol-47z.** jscpd-confirmed self-clone within `lifecycle.py`
(C2: `582-592` ⇄ `563-573`). `activate_next_bead()` now contains two
near-identical guard blocks back to back — the open-blocker gate and the
fan-out gate — each ending in the same revert-and-stop tail:

- `lifecycle.py:558-570` — open work-time blocker gate
- `lifecycle.py:576-592` — fan-out gate (`waits_for: children-of(...)`)

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
tail is **verbatim** in both, and a third near-copy lives in the
`register_callbacks.py:225-238` blocker gate (see H3).

**Refactor:** extract a `lifecycle._revert_and_stop(bead_id, *, recovery: bool) -> None`
(or fold both gates through a single
`_refuse_activation(bead_id, reason, *, recovery)` helper). Collapses
two divergence-prone copies into one and makes the revert policy a
single source of truth.

### H3 — Claim-vs-recovery "arm wiggum" block (status-handling) — HIGH

jscpd-confirmed clones C1 (`lifecycle.py:564-570` ⇄
`register_callbacks.py:231-237`) and C3 (`lifecycle.py:599-605` ⇄
`register_callbacks.py:257-263`). The "walk the hierarchy top-down →
claim → assign state → arm wiggum" flow is duplicated between the
startup path and the per-iteration path:

- `register_callbacks.py:218-263` — `handle_bead_chain_command()`
- `lifecycle.py:593-619` — `activate_next_bead()`

Both contain the **verbatim** ~9-line "Walk the hierarchy top-down…"
comment, the `ensure_epic_in_progress(bead)` call, the
`if not recovery: try: claim(bead_id) except BeadsError: ...stop` block,
then `state.get_state().current_bead = bead` +
`format_bead_as_goal(...)` + `wiggum_state.start(goal_prompt, mode="goal")`.

**Refactor:** extract a shared
`lifecycle.claim_and_arm(bead, *, recovery: bool)` that does the
epic-first claim, the conditional `claim`, the state assignment, and the
wiggum arming. Both the startup command and `activate_next_bead` call it.
Kills the duplicated comment and the subtly-divergent error handling
(note the two call sites currently differ only in the final
`emit_*` line — easy to let them drift further).

> H1–H3 are closely related (they all live on the "drive a bead" path
> through `activate_next_bead` and `handle_bead_chain_command`) and are
> best addressed in **one refactor bead** that introduces the
> `_refuse_excluded` / `_revert_and_stop` / `claim_and_arm` trio.

### H4 — Client-side epic-filter loop (status-handling) — MEDIUM

jscpd-confirmed clone C4 (`beads.py:289-295` ⇄ `beads.py:224-230`). The
"return first dict that isn't an excluded type" loop is repeated:

- `beads.py:224-227` — `next_ready()`
- `beads.py:290-293` — `next_ready_in_epic()`
- (variant, comprehension) `beads.py:253-255` — `list_in_progress()`

```python
for item in items:
    if isinstance(item, dict) and not is_excluded_type(item):
        return item
return None
```

**Refactor:** a tiny `_first_drivable(items)` helper (and/or
`_drivable_only(items)` for the list case) centralises the
`isinstance(dict) and not is_excluded_type` predicate. Low risk, pure
function, trivially unit-tested.

### H5 — Lenient single-object JSON parsing (JSON parsing) — MEDIUM

`_parse_json_list()` (`beads.py:133-159`) already centralises the *list*
case, but three functions still hand-roll their own `json.loads` with
divergent error policies:

- `beads.py:456-462` — `show()` — **raises** on bad JSON, and re-uses the
  `snippet = raw[:200].replace("\n", " ")` construction that is itself a
  copy of the snippet logic inside `_parse_json_list` (`beads.py:152`)
- `beads.py:513-521` — `has_epic_in_progress()` — **swallows** on bad JSON
- `beads.py:571-...` — `close_eligible_epics()` — **swallows** on bad JSON

The `raw[:200].replace("\n", " ")` snippet construction is duplicated
between `_parse_json_list` and `show`.

**Refactor:** add a `_parse_json(raw, context, *, strict: bool)` (or a
`_json_snippet(raw)` helper plus a single-object parse counterpart) so
the snippet formatting and decode-error handling live in one place.
**Preserve the intentional policy split** (raise vs. swallow) via a
flag — do not flatten it.

### H6 — `str(bead.get("id", "<unknown>"))` + emit micro-pattern — LOW

The "pull an id (defaulting to `<unknown>`/`?`) then emit a log line"
micro-pattern recurs throughout (e.g. `lifecycle.py:535`, scattered
`pick_next_bead` / `rollup_completed_epics` emits). A `bead_id_of(bead)`
helper would DRY the literal, but the surrounding messages are genuinely
different. Borderline YAGNI — fold into H1/H2 if convenient, otherwise
leave it. Listed for completeness.

### H7 — Duplicated import block — NOISE (do not refactor)

jscpd at very low thresholds flags both modules importing `emit_*` from
`code_puppy.messaging` and names from `.beads`. **Not actionable** —
that's how Python imports work; DRYing imports would be a YAGNI
violation.

---

## Summary & recommendation

The codebase remains in good DRY shape (**0 clones at the standard
50-token threshold**). The duplication that exists is **semantic
status-handling repetition** on the "drive a bead" path that a
token-based tool under-reports — and one block (H2) has regressed into a
literal self-clone since mol-47z.

**Recommended refactor beads:**

1. **One bead covering H1–H3** (the high-priority status-handling trio —
   `_refuse_excluded`, `_revert_and_stop`, `claim_and_arm`). They touch
   the same two functions and share state-management concerns, so doing
   them together avoids half-refactoring the flow.
2. **One smaller bead for H4 + H5** (the `beads.py` purity pass —
   `_first_drivable` predicate helper and `_parse_json` consolidation,
   preserving the raise-vs-swallow split).

H6 is borderline-YAGNI; H7 is noise. No refactor warranted for either.
