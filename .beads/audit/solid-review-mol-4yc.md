# SOLID review — bead_chain plugin

**Bead:** bead_chain-mol-4yc (parent epic: bead_chain-mol-1vy, code-health-audit)
**Date:** 2026-05-29
**Method:** Manual responsibility/coupling review of all six modules
against the five SOLID principles (with a pragmatic lens — this is a
small pure-Python plugin, not an enterprise OO framework).

## Module responsibility map

| Module | Single responsibility | Verdict |
|---|---|---|
| `beads.py` | Thin subprocess wrapper around the `bd` CLI (I/O boundary). | ✅ SRP-clean. Only place that shells out to bd. |
| `state.py` | Dumb singleton dataclass for chain state. | ✅ Pure data box, no behavior leakage. |
| `prompt.py` | bead-dict → goal-prompt formatting (near-pure). | ✅ Formatting only; one soft-fail bd call clearly isolated. |
| `lifecycle.py` | State transitions (close, revert, pick-next, arm wiggum). | ✅ Owns transitions; explicitly forbids hook *registration*. |
| `register_callbacks.py` | Wiring: slash cmd, hook handlers, CLI parse, registration. | ✅ Wiring only; delegates logic to lifecycle/beads/prompt. |
| `close_guard.py` | Detect + block premature agent-issued bead closes. | ✅ Cohesive: detector regex + its one hook live together. |

The layering is clean and explicitly documented in the module
docstrings (`lifecycle` says "DO NOT add hook registration here";
`register_callbacks` says "wiring only"). Responsibilities do not bleed.

## SOLID principle-by-principle

- **S (Single Responsibility):** Each module has one reason to change.
  bd-output-shape changes → `beads.py`. Prompt wording → `prompt.py`.
  Waterfall priority → `lifecycle.py`. Slash-command surface →
  `register_callbacks.py`. No god-module.

- **O (Open/Closed):** Extension points are data-driven and additive:
  `EXCLUDED_TYPES`, `BLOCKING_BUG_TYPES`, `_PARENT_EPIC_FALLBACK_KEYS`
  are tuples you extend without touching logic. New excluded type =
  one-line edit. ✅

- **L (Liskov):** Minimal inheritance (`BeadsError(RuntimeError)`,
  frozen `CloseGuardMatch` dataclass). No subtype substitution hazards.
  N/A in practice. ✅

- **I (Interface Segregation):** `beads.py` exposes many small,
  single-purpose functions (`next_ready`, `claim`, `close`, …) rather
  than one fat client object. Callers import only what they use. ✅

- **D (Dependency Inversion):** Higher-level `lifecycle` depends on the
  `beads`/`prompt` function-level abstractions, not on subprocess
  details. The bd binary is overridable via `BEADS_BIN`. wiggum is
  reached through its published `state` module. Coupling flows toward
  stable abstractions. ✅

## Coupling observations

- The plugin depends on `code_puppy.plugins.wiggum.state` directly.
  This is intentional and documented ("bead-chain is **not** a goal
  engine — it delegates to wiggum"). It is a hard runtime dependency
  by design, not accidental coupling. Acceptable.
- `state.py`'s module-level singleton (`_STATE`) is shared global
  state. For a single-session interactive plugin this mirrors wiggum's
  own pattern and is the pragmatic choice; it is not a testability
  problem in practice (tests drive the public functions). No change
  recommended.

## Recommendation

No SRP/coupling violations found. No cleanup beads filed. The
separation of *wiring* (register_callbacks) from *transitions*
(lifecycle) from *I/O* (beads) from *formatting* (prompt) is a textbook
clean layering for a plugin of this size — and it is enforced by
explicit docstring contracts, not just convention.
