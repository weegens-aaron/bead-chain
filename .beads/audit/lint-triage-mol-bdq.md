# Lint triage — bead_chain plugin

**Bead:** bead_chain-mol-bdq (parent epic: bead_chain-mol-1vy, code-health-audit)
**Date:** 2026-05-29
**Tool:** `ruff 0.14.6`

## How this was run

No CI, no `pyproject.toml`/`ruff.toml`, no dependency manifest in this
repo — so ruff ran with its built-in defaults, locally, against the
whole tree.

```bash
ruff check .            # lint
ruff format --check .   # formatting drift
```

## Result

```
All checks passed!
11 files already formatted
```

**Zero lint findings. Zero formatting drift.** Every plugin module
(`beads.py`, `lifecycle.py`, `prompt.py`, `register_callbacks.py`,
`close_guard.py`, `state.py`) and the `tests/` suite pass clean under
ruff's default ruleset (E/F/W + the default-on subset).

## Notes / observations

- The test files carry intentional `# noqa: E402` markers on their
  `import beads` lines because they mutate `sys.path` before importing.
  ruff respects these — they are correct and required for the
  path-injection pattern these standalone tests use.
- `prompt.py` has one f-string with no placeholders
  (`f"BLOCKING bug — file..."`) that ruff's default config does **not**
  flag (F541 is in the default set but only fires on truly empty
  f-strings; this one is part of an adjacent-string concatenation block
  where neighbors *do* interpolate). Not a finding — left as-is for
  readability of the concatenated block.

## Recommendation

Nothing to fix. No cleanup beads filed. If the project later wants to
lock this in, a minimal `ruff.toml` pinning the ruleset would prevent
future drift — optional polish, not a bug.
