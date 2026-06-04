# Dead-code triage — bead_chain plugin

**Bead:** bead_chain-mol-2gi (parent epic: bead_chain-mol-1vy, code-health-audit)
**Date:** 2026-05-29
**Tools:** `vulture 2.16` + `ruff 0.14.6` (F401/F811/F841)

## How this was run

```bash
vulture . --min-confidence 80 --exclude tests   # bead's required threshold
vulture . --min-confidence 60                    # sub-80 manual sweep
ruff check --select F401,F811,F841 .             # cross-check unused imports/vars
```

## Result at the required threshold (--min-confidence 80)

**Zero findings.** Vulture reports nothing in the plugin modules
(`beads.py`, `lifecycle.py`, `prompt.py`, `register_callbacks.py`,
`close_guard.py`, `state.py`) at 80% confidence. Ruff's F401/F811/F841
checks also pass clean — **no unused imports, redefinitions, or unused
local variables anywhere in the repo.**

> Conclusion: there are **no removal candidates**. No cleanup beads to file.

## Sub-80 sweep (manual look)

Lowering the threshold to 60% surfaced the following — all triaged as
**false positives, KEEP**:

| Location | Finding (conf) | Verdict | Why |
|---|---|---|---|
| `register_callbacks.py:156` `handle_bead_chain_command` | unused function (60%) | **KEEP** | Registered via `@register_command(name="bead-chain", ...)`. It is the `/bead-chain` slash-command entrypoint, wired into the code_puppy host at runtime — exactly the register_callback/register_command case the bead warns about. |
| `tests/test_close_eligible_parsing.py:24` `a`, `k` (100%) | unused vars | **KEEP** | `lambda *a, **k:` stub signature for `beads._run_bd`. The args must exist to accept any call shape even though the body ignores them. Idiomatic test double. |
| `tests/test_formula_epic_rollup.py:32` `a`, `k` (100%) | unused vars | **KEEP** | Same `lambda *a, **k:` monkeypatch stub. Intentional. |

None of these are dead code; all are runtime-wired or deliberate test
plumbing. No action required.

## Recommendation

The codebase is clean of dead code. If the project later adopts a
vulture run as part of `code-health-audit`, add a small whitelist /
`# noqa` for the `*a, **k` stub lambdas and decorate command handlers so
they don't keep surfacing as 60%-confidence noise — but that is optional
polish, not a bug.
