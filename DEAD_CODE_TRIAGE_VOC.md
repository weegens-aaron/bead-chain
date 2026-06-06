# Dead-Code Triage Report — bead_chain-mol-voc

**Bead:** Dead-code triage — run `vulture` on the plugin modules
**Parent epic:** bead_chain-mol-4od (code-health-audit)
**Tools:** `vulture 2.16` · `ruff 0.14.6` · **Date:** 2026-06-06

> Re-run of the same triage performed for the earlier epic (see
> `DEAD_CODE_TRIAGE_GF2.md`, epic mol-iwr). The tree has grown since then
> (245 tests now vs. 63), line numbers moved, and the test-stub `**k` hits that
> tripped vulture before are gone. Findings re-verified against the **current**
> source. Conclusion is unchanged: **zero confident dead code in the core
> modules.**

## TL;DR

- **`vulture . --min-confidence 80` reports exactly ONE item** —
  `skills/md-to-html/scripts/md_lint.py:22` (`filename`, 100%). It is in a
  **bundled skill**, not a core plugin module, and is a published-kwarg false
  positive. **No ≥80% hit lands in any of the six core modules.**
- **At the bead's `--min-confidence 80` threshold the core plugin modules are
  CLEAN** (`beads.py`, `lifecycle.py`, `prompt.py`, `register_callbacks.py`,
  `close_guard.py`, `state.py`, `__init__.py`, plus `execution_hints.py`).
- **Ruff F401 cross-check (`ruff check . --select F401`) → `All checks passed!`**
  — zero unused imports repo-wide. Matches the lint-triage sibling
  (`LINT_TRIAGE_5TQ.md`). The two signals agree: no unused-import dead code.
- **Net confident removal candidates: 0.** The only genuinely
  production-unused symbol (`next_in_progress`) surfaces only at the **60%**
  tier, is documented public API, and is already owned by `solid-review-mol-9o2`
  / `solid-review-mol-512` — deleting it from a vulture-run bead would step on a
  sibling and leave the diataxis reference dangling.

## Method

No CI, no config in this repo, so the tool runs locally (per the epic's design).

```
$ vulture . --min-confidence 80                     → 1 item (FP, not core)
$ vulture <core modules> --min-confidence 0         → 3 items, all 60%
$ vulture . --min-confidence 60                      → 7 items total
$ ruff check . --select F401                          → All checks passed!
$ ruff check .                                        → All checks passed!
$ ruff format --check .                               → 44 files already formatted
$ python -m pytest -q                                 → 245 passed
```

## Findings at `--min-confidence 80` (the bead's threshold)

| # | Location | Item | Conf | Verdict | Why |
|---|----------|------|------|---------|-----|
| 1 | `skills/md-to-html/scripts/md_lint.py:22` | param `filename` | 100% | **Keep (FP, out of core scope)** | Published keyword param of `lint_markdown(text, filename="<stdin>")` in a **bundled skill** — outside the six-module core. Unused in the body today but part of the function's public signature; prefixing `_` would break the named kwarg. Cosmetic at most. |

**Removal candidates at ≥80% confidence: NONE.**

## Sub-80-confidence items worth a manual look

Vulture's 60% tier surfaces symbols it can't prove are referenced — exactly the
runtime-wired-entrypoint class the bead warned about, plus convenience wrappers
and pytest fixtures.

### Core modules

| # | Location | Item | Conf | Verdict | Why |
|---|----------|------|------|---------|-----|
| 2 | `register_callbacks.py:163` | `handle_bead_chain_command` | 60% | **Keep — FALSE POSITIVE** | Decorated with `@register_command(name="bead-chain", …)`. It is the `/bead-chain` slash-command entrypoint, **wired at runtime by code_puppy**, never called by name in-tree. This is the canonical command-handler trap the bead flagged. **Do NOT remove.** |
| 3 | `beads.py:550` | `is_blocked` | 60%* | **Keep — test-covered API** | Thin `bool(open_blocker_ids(...))` wrapper. No production caller (the `lifecycle.py:484` mention is docstring prose), **but** it has live coverage in `test_blocker_gate.py`, `test_waits_for_blocker.py`, and `test_blocker_gate_e2e.py` (7+ assertions). \*Only shows at 60% in the core-only run because vulture couldn't see the tests; the full-repo run correctly suppresses it. **Not dead.** |
| 4 | `beads.py:423` | `next_in_progress` | 60% | **Removal candidate (low) — DEFER** | Genuinely production-unused: zero call sites in production **and** tests; only docstrings + diataxis reference it. Head-of-`list_in_progress` convenience wrapper. **However** it is documented public API and is already itemized by `solid-review-mol-9o2` (item 6) and `solid-review-mol-512`. A clean delete also requires pruning the diataxis `modules-and-functions` reference + HTML — scope that belongs to that SOLID/doc bead, not a vulture triage. Recommend the deletion happen there to avoid colliding with a sibling bead. |

### Out-of-core-scope (informational)

| # | Location | Item | Conf | Verdict | Why |
|---|----------|------|------|---------|-----|
| 5 | `tests/test_gate_check_empty_queue.py:35` | `_fresh_state` | 60% | **Keep (FP)** | `@pytest.fixture(autouse=True)` — invoked by pytest via injection, never by name. |
| 6 | `tests/test_hooked_pinned_strands.py:164` | `_restore_state` | 60% | **Keep (FP)** | Same autouse-fixture pattern. |
| 7 | `skills/md-to-html/scripts/build_index.py:99` | `_load_base_css` | 60% | **Ignore (out of scope)** | Bundled skill, not a core plugin module. |
| 8 | `skills/md-to-html/scripts/md_converter.py:15` | `CALLOUT_TYPES` | 60% | **Ignore (out of scope)** | Bundled skill, not a core plugin module. |

## Cross-check with ruff F401

`ruff check . --select F401` → **`All checks passed!`** No unused imports
anywhere — core or otherwise. Vulture reported no unused-import items either, so
both signals agree: **zero unused-import dead code.**

## Verdict

- **No confident (≥80%) dead code in the six core plugin modules.** The single
  100% hit is a published-kwarg FP in a bundled skill.
- **Nothing should be deleted by this bead.** The one real production-unused
  symbol, `next_in_progress` (60%), is documented public API already owned by
  the SOLID-review beads; deleting it here would duplicate that decision and
  orphan the diataxis reference.
- Every other hit is a textbook false positive: a `@register_command` runtime
  entrypoint, a test-covered boolean wrapper, and two `autouse` pytest fixtures.

## Bug-discovery protocol

No bugs discovered during this triage.

## Acceptance criteria — met

- [x] Ran `vulture . --min-confidence 80` locally and reviewed every item.
- [x] Cross-checked against ruff's F401 signal (clean; agrees with lint-triage).
- [x] Made a remove-vs-keep decision per reported item with confidence notes.
- [x] Correctly identified the `@register_command` entrypoint (and pytest
      autouse fixtures) as false positives — the callback/command-handler trap
      the bead called out.
- [x] Listed sub-80-confidence items worth a manual look.
- [x] `ruff check .` clean; `ruff format .` clean (44 files); `pytest` green
      (245 passed).
