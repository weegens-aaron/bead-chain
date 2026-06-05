# Dead-Code Triage Report — bead_chain-mol-gf2

**Bead:** Dead-code triage — run `vulture` on the plugin modules
**Parent epic:** bead_chain-mol-iwr (code-health-audit)
**Tools:** `vulture 2.16` · `ruff 0.14.6` · **Date:** 2026-06-04

## TL;DR

- **`vulture . --min-confidence 80` reports 4 items — ZERO of them in the six
  core plugin modules.** All four are 100%-confidence hits in test stubs and a
  bundled skill, and all four are **false positives / keep** (see below).
- **At the bead's specified `--min-confidence 80` threshold, the core plugin
  modules (`beads.py`, `lifecycle.py`, `prompt.py`, `register_callbacks.py`,
  `close_guard.py`, `state.py`, `__init__.py`) are CLEAN.**
- **Ruff F401 cross-check (`ruff check . --select F401`) → `All checks passed!`**
  — zero unused imports repo-wide, matching the lint-triage sibling
  (LINT_TRIAGE_5TQ.md).
- **Net removal candidates: 0 confident deletions.** Two genuinely-uncalled
  public functions surface only at the **sub-80 (60%)** level and are flagged
  for a manual look — but both are already owned by `solid-review-mol-9o2`, are
  documented public API, and one is test-covered, so they are **NOT** safe blind
  deletes from this bead.

## Method

This repo has **no CI and no config**, so each child runs its tool locally.

```
$ vulture . --min-confidence 80          → 4 items (all FP, none in core)
$ vulture <6 core modules> --min-confidence 0
                                          → 3 items, all 60% confidence
$ vulture . --min-confidence 60          → 8 items total
$ ruff check . --select F401             → All checks passed!
$ ruff check .                           → All checks passed!
$ ruff format --check .                  → 28 files already formatted
$ python -m pytest -q                    → 63 passed
```

## Findings at `--min-confidence 80` (the bead's threshold)

| # | Location | Item | Conf | Verdict | Why |
|---|----------|------|------|---------|-----|
| 1 | `skills/md-to-html/scripts/md_lint.py:22` | param `filename` | 100% | **Keep (FP)** | Public-API keyword param `lint_markdown(text, filename="<stdin>")` in a **bundled skill** (out of the six-module core scope). Unused in the body today but part of the function's published signature. Cosmetic at most; prefix-`_` would break the named kwarg. |
| 2 | `tests/test_close_eligible_parsing.py:24` | var `k` | 100% | **Keep (FP)** | It's `lambda *a, **k: ...` — a `_run_bd` stub that deliberately swallows `*args/**kwargs` to mirror the real signature. Renaming buys nothing. |
| 3 | `tests/test_formula_epic_rollup.py:32` | var `k` | 100% | **Keep (FP)** | Same `lambda *a, **k:` stub pattern. |
| 4 | `tests/test_over_close_bug.py:48` | var `k` | 100% | **Keep (FP)** | Same `lambda *a, **k:` stub pattern. |

**Removal candidates at ≥80% confidence: NONE.**

## Sub-80-confidence items worth a manual look

Vulture's 60% tier surfaces functions it can't prove are unreferenced. These are
exactly the class the bead warned about (runtime-wired entrypoints) plus a couple
of genuinely-uncalled wrappers.

| # | Location | Item | Conf | Verdict | Why |
|---|----------|------|------|---------|-----|
| 5 | `register_callbacks.py:162` | `handle_bead_chain_command` | 60% | **Keep — FALSE POSITIVE** | Decorated with `@register_command(name="bead-chain", …)`. It's the `/bead-chain` slash-command entrypoint, **wired at runtime by code_puppy**, never called by name in-tree. This is the canonical callback/command false positive the bead flagged. **Do NOT remove.** |
| 6 | `beads.py:382` | `is_blocked` | 60% | **Manual look — keep for now** | Thin `bool(open_blocker_ids(...))` wrapper. **No production caller** (the `lifecycle.py:403` mention is prose in a docstring), BUT it has **live test coverage** (`test_blocker_gate.py`, `test_blocker_gate_e2e.py` assert on it). Deleting it would break 3+ tests. Already tracked by `solid-review-mol-9o2` (item #6). Not a clean dead-code delete from this bead. |
| 7 | `beads.py:258` | `next_in_progress` | 60% | **Removal candidate (low) — defer** | Genuinely uncalled: no production caller and no test. Head-of-`list_in_progress` convenience wrapper. **However** it is documented public API (diataxis `modules-and-functions` reference) and is already itemized by `solid-review-mol-9o2` (item #6). Removing it cleanly requires also pruning the diataxis docs — scope that belongs to that review/its doc bead, not a vulture-run triage. Recommend deletion be done there to avoid stepping on a sibling bead. |
| 8 | `skills/md-to-html/scripts/build_index.py:99` | `_load_base_css` | 60% | **Ignore (out of scope)** | Bundled skill, not a core plugin module. |
| 9 | `skills/md-to-html/scripts/md_converter.py:15` | `CALLOUT_TYPES` | 60% | **Ignore (out of scope)** | Bundled skill, not a core plugin module. |

## Cross-check with ruff F401

`ruff check . --select F401` → **`All checks passed!`** No unused imports
anywhere, in core modules or elsewhere. Vulture reported no unused-import items
either, so the two signals agree: **zero unused-import dead code.**

## Verdict

- **No confident (≥80%) dead code exists in the six core plugin modules.**
- **Nothing should be deleted by this bead.** The only 60% removal-candidate
  (`next_in_progress`) is documented public API already owned by
  `solid-review-mol-9o2`; deleting it here would (a) duplicate that bead's
  decision and (b) leave the diataxis reference dangling.
- All 80%/100% hits are textbook false positives: stub `**k` kwargs, a published
  skill param, and a `@register_command` runtime entrypoint.

## Bug-discovery protocol

No bugs discovered during this triage.

## Acceptance criteria — met

- [x] Ran `vulture . --min-confidence 80` locally and reviewed every item.
- [x] Cross-checked against ruff's F401 signal (clean, agrees with lint-triage).
- [x] Made a remove-vs-keep decision for each reported item with confidence notes.
- [x] Correctly identified the `@register_command` entrypoint as a false positive
      (the callback/command-handler trap the bead called out).
- [x] Listed sub-80-confidence items worth a manual look.
- [x] `ruff check .` + `ruff format .` clean; `pytest` green (63 passed).
