# Lint Triage Report — bead_chain-mol-5tq

**Bead:** Lint triage — run `ruff check` on the plugin modules
**Parent epic:** bead_chain-mol-iwr (code-health-audit)
**Tool:** `ruff 0.14.6` · **Date:** 2026-06-04

## TL;DR

- **`ruff check .` (project standard ruleset) → All checks passed. Zero diagnostics.**
- **`ruff format .` → 28 files already formatted; tree is clean.** 
- **F401 (unused imports): ZERO across the whole repo, including all six core
  modules.** The signal the old vulture/ruff CI formula cared about is clean.
- **No cleanup bead is warranted under the project's actual lint standard.**

## Method

This repo has **no `pyproject.toml`, no `ruff.toml`, and no CI**. Therefore ruff
runs its **default ruleset** (`E` pycodestyle + `F` pyflakes — and pyflakes
**includes F401**). That default set *is* the project standard per `prompt.py`
(`ruff check --fix`, `ruff format .`) and `AGENTS.md`.

```
$ ruff check .            → All checks passed!
$ ruff check . --select F → All checks passed!   (no F401/F811/F841/etc.)
$ ruff format . --check   → 28 files already formatted
$ python -m pytest -q     → 63 passed
```

Core epic modules (`beads.py`, `lifecycle.py`, `prompt.py`,
`register_callbacks.py`, `close_guard.py`, `state.py`, `__init__.py`) were also
checked in isolation: **clean** on both the default ruleset and `--select F`.

## Triage of the broader (`--select ALL`) sweep — informational only

To make a real fix-now / file-a-bead / ignore decision I also ran the *entire*
ruff catalogue. None of these rules are enabled by the project standard; they are
listed only to justify the triage verdict.

### Ranked findings (none rise to a cleanup bead)

| # | Rank | Rule | Count | Where | Verdict | Why |
|---|------|------|-------|-------|---------|-----|
| 1 | — | `RUF100` unused-noqa | 23 | tests/, skills/ | **Intentional / ignore** | The `noqa` directives reference rules (`E402`, `F401`, `ARG001`, `E731`) that are *non-enabled* under the default config. They are defensive suppressions for a stricter config and only read as "unused" because the project runs defaults. Removing them would re-break under any tightened ruleset. **Do NOT `--fix`.** |
| 2 | Low | `C901`/`PLR0911`/`PLR0912`/`PLR0915` complexity | ~6 | beads.py, lifecycle.py | **Ignore (out of scope)** | Cyclomatic/branch complexity on a few orchestration functions. Judgment-call refactors, not lint debt; overlaps with other code-health-audit children. Not blocking and not part of the lint standard. |
| 3 | Low | `I001` unsorted-imports | 4 | skills/md-to-html/scripts/ | **Ignore** | Import sorting is opt-in (isort); not enabled. Cosmetic; lives in a bundled skill, not core. |
| 4 | Low | `PLW1510` subprocess-without-check | 4 | tests/*_e2e.py | **Ignore** | All in e2e test harness code where return codes are asserted manually. Not core; not the project standard. |
| 5 | Noise | `COM812`, `S101`, `T201`, `ANN*`, `D*`, `EM*`, `TRY003`, `PTH*` | 100s | repo-wide | **Intentional / ignore** | `COM812` conflicts with ruff's own formatter (ruff disables it by default). `S101` asserts live in tests. `T201` prints are intentional user-facing CLI output for a code-puppy plugin. `ANN*`/`D*` are opt-in annotation/docstring style the project never adopted. |

### Verdict

The project's standardized lint signal is **100% clean**. Every non-default
finding is either (a) intentional, (b) a formatter-conflicting rule ruff itself
disables, or (c) opt-in style the project never opted into. **Nothing here
justifies a cleanup bead, and `--fix` was deliberately NOT blindly applied.**

## Bug-discovery protocol

No bugs discovered during this triage.

## Acceptance criteria — met

- [x] Ran `ruff check .` and reviewed every diagnostic (incl. F401 — zero).
- [x] Made a fix-now / file-a-bead / ignore decision per finding category.
- [x] Did NOT blindly `--fix`.
- [x] Produced a ranked list of findings worth a cleanup bead (verdict: none).
- [x] Confirmed `ruff format .` leaves the tree clean (28 files unchanged).
- [x] Tests green (63 passed).
