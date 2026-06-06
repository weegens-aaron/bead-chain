# Lint Triage Report — bead_chain-mol-xi5

**Bead:** Lint triage — run `ruff check` on the plugin modules
**Parent epic:** bead_chain-mol-4od (code-health-audit)
**Tool:** `ruff 0.14.6` · **Date:** 2026-06-06
**Prior pass:** supersedes/confirms `LINT_TRIAGE_5TQ.md` (re-run on a grown tree:
28 → 44 files, 63 → 245 tests).

## TL;DR

- **`ruff check .` (project-standard ruleset) → All checks passed. Zero diagnostics.**
- **`ruff format --check .` → 44 files already formatted; tree is clean.**
- **F401 (unused imports): ZERO** across the whole repo, incl. all core modules.
  The vulture/ruff CI signal the old formula cared about is clean.
- **No cleanup bead is warranted under the project's actual lint standard.**
- **`--fix` was deliberately NOT applied.**

## Method

This repo has **no `pyproject.toml`, no `ruff.toml`, and no CI**, so ruff runs
its **default ruleset** (`E` pycodestyle + `F` pyflakes — pyflakes *includes*
F401). That default set *is* the project standard per `prompt.py`
(`ruff check --fix`, `ruff format .`) and `AGENTS.md`.

```
$ ruff check .                          → All checks passed!
$ ruff check . --select F               → All checks passed!   (no F401/F811/F841/…)
$ ruff check <6 core modules> (default) → All checks passed!
$ ruff format --check .                 → 44 files already formatted
$ python -m pytest -q                   → 245 passed
```

Core epic modules (`beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`, `__init__.py`,
`execution_hints.py`) were also checked in isolation: **clean** on both the
default ruleset and `--select F`.

## Triage of the broader (`--select ALL`) sweep — informational only

To make a real fix-now / file-a-bead / ignore decision I ran the *entire* ruff
catalogue (1705 findings repo-wide; 97 on core modules ignoring 2 bogus E902
from non-existent file args). **None of these rules are enabled by the project
standard.** Listed only to justify the verdict.

### Ranked findings (none rise to a cleanup bead)

| # | Rank | Rule(s) | Count | Where | Verdict | Why |
|---|------|---------|-------|-------|---------|-----|
| 1 | — | `RUF100` unused-noqa | 19 | execution_hints.py:197, skills/md-to-html/scripts+tests | **Intentional / ignore. Do NOT `--fix`.** | `noqa` directives reference rules **non-enabled** under defaults: `BLE001` (a deliberate soft-fail `except Exception` that must never strand the chain) and `E402` (imports after `sys.path` manipulation in the bundled md-to-html scripts). They are defensive suppressions for a *stricter* config; they only read "unused" because the project runs defaults. Removing them re-breaks under any tightened ruleset. |
| 2 | Low | `C901`/`PLR0911`/`PLR0912`/`PLR0915` complexity | ~11 | beads.py, lifecycle.py | **Ignore (tracked elsewhere)** | Cyclomatic/branch/statement complexity on orchestration funcs. Judgment-call refactors already covered by the SOLID-review children (file-size/split beads, see `solid-review-mol-512`). Not lint debt, not the standard. |
| 3 | Low | `I001` unsorted-imports | 9 | mostly skills/md-to-html/scripts | **Ignore** | isort is opt-in; not enabled. Cosmetic; mostly bundled skill, not core. |
| 4 | Low | `PLW1510` subprocess-without-check | 5 | tests/*_e2e.py | **Ignore** | e2e harness asserts return codes manually. Not core; not the standard. |
| 5 | Noise | `S101`(429) `ANN*`(~440) `D*`(~180) `COM812`(126) `T201`(86) `SLF001`(79) `PTH*` `EM*` `TRY003` … | 100s | repo-wide | **Intentional / ignore** | `COM812` conflicts with ruff's own formatter (ruff disables it). `S101` asserts live in tests. `T201` prints are intentional user-facing CLI output for a code-puppy plugin. `ANN*`/`D*` are opt-in annotation/docstring style the project never adopted. |

### Verdict

The project's standardized lint signal is **100% clean** (E+F, incl. F401).
Every non-default finding is (a) an intentional defensive suppression, (b) a
formatter-conflicting rule ruff itself disables, (c) opt-in style never adopted,
or (d) complexity already tracked by other code-health-audit children. **Nothing
justifies a cleanup bead, and `--fix` was deliberately NOT blindly applied.**

## Bug-discovery protocol

No bugs discovered during this triage.

## Acceptance criteria — met

- [x] Ran `ruff check .` and reviewed every diagnostic (incl. F401 — zero).
- [x] Made a fix-now / file-a-bead / ignore decision per finding category.
- [x] Did NOT blindly `--fix`.
- [x] Produced a ranked list of findings worth a cleanup bead (verdict: none).
- [x] Confirmed `ruff format .` leaves the tree clean (44 files unchanged).
- [x] Tests green (245 passed).
