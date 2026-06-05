# Reference: Modules and public functions

A structured map of the `bead_chain` package, mirroring its module layout.
Each module lists its public functions with signature and one-line
description. This page describes only; for tasks see the
[how-to guides](../how-to/), and for design rationale see the
[explanation](../explanation/) section.

## Package layout

```
bead_chain/
- __init__.py           # Package docstring
- register_callbacks.py # Wiring: /bead-chain command, hook handlers
- lifecycle.py          # State transitions: close, pick next, arm wiggum
- beads.py              # Subprocess wrapper around the bd CLI
- prompt.py             # Bead to goal prompt formatting
- close_guard.py        # Shell hook that blocks premature closes
- state.py              # Singleton dataclass for chain state
```

## `state.py`

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `BeadChainState` | dataclass | Holds `active`, `current_bead`, `completed_count`, `max_iterations` |
| `BeadChainState.current_bead_id` | property -> `str \| None` | Convenience accessor for `current_bead["id"]` |
| `BeadChainState.start` | `() -> None` | Set active, clear current bead, reset completed count |
| `BeadChainState.stop` | `() -> None` | Clear active, current bead, and the iteration cap |
| `BeadChainState.bump_completed` | `() -> int` | Increment and return the completed count |
| `get_state` | `() -> BeadChainState` | Return the module-level singleton |
| `is_active` | `() -> bool` | Whether the chain is engaged |
| `start` / `stop` | `() -> None` | Module-level wrappers over the singleton |

## `beads.py`

Thin subprocess wrapper. Raises `BeadsError` on infrastructure failure.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `BeadsError` | `RuntimeError` subclass | Raised when `bd` fails, is missing, or returns junk |
| `is_excluded_type` | `(bead) -> bool` | True for container types (case-insensitive) |
| `next_ready` | `() -> dict \| None` | Top ready non-epic bead |
| `list_in_progress` | `() -> list[dict]` | All in_progress non-epic beads |
| `next_in_progress` | `() -> dict \| None` | Head of `list_in_progress` |
| `next_ready_in_epic` | `(epic_id) -> dict \| None` | Top ready bead under an epic |
| `extract_parent_epic_id` | `(bead) -> str \| None` | Parent epic id via canonical + fallback keys |
| `open_blocker_ids` | `(bead_id) -> list[str]` | Ids of open `blocks` work-time blockers |
| `is_blocked` | `(bead_id) -> bool` | Whether any open work-time blocker exists |
| `next_blocking_bug` | `() -> dict \| None` | Top ready bug with `dependent_count > 0` |
| `show` | `(bead_id) -> dict \| None` | Full bead record via `bd show --json` |
| `claim` | `(bead_id) -> None` | `bd update <id> --claim` |
| `revert_to_open` | `(bead_id) -> None` | `bd update <id> --status=open` |
| `close` | `(bead_id, *, reason=None) -> None` | `bd close <id> [--reason ...]` |
| `has_epic_in_progress` | `() -> bool` | Whether any epic is in_progress |
| `close_eligible_epics` | `() -> list[dict]` | Roll up epics whose children are all closed |

## `prompt.py`

Bead-dict to goal-prompt formatting. Mostly pure.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `TRIAGE_MARKER` | `str` = `"[bead-chain:triaged]"` | Sentinel in a bug's description marking an inline-fixed triaged bug |
| `is_triaged_bug` | `(bead) -> bool` | True for a `bug` whose description carries the marker |
| `format_bead_as_goal` | `(bead, *, recovery=False) -> str` | Render the `/goal` prompt, with a recovery or triage preamble and the bug-discovery protocol appended |

Preamble precedence in `format_bead_as_goal`: `recovery` wins over a
triaged bug; otherwise no preamble. The bug-discovery protocol is appended
to every prompt.

## `close_guard.py`

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `CloseGuardMatch` | frozen dataclass | `pattern_name` and `description` of a detected close attempt |
| `detect_premature_close` | `(command) -> CloseGuardMatch \| None` | Detect `bd close` / `bd update --status=closed` at a command boundary |
| `on_run_shell_command` | `async (context, command, cwd=None, timeout=60) -> dict \| None` | Hook that blocks the command (returns a `blocked` dict) when the chain is active |

## `lifecycle.py`

State-transition logic. Functions mutate `state` and shell out via `beads`.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `is_recovery_bead` | `(bead) -> bool` | True if the bead was already in_progress when picked |
| `enforce_single_in_progress` | `() -> dict \| None` | Pick head in_progress bead for recovery; leave the rest |
| `close_current_bead_success` | `() -> dict \| None` | Close the current bead; halt + leave in_progress on failure |
| `rollup_completed_epics` | `() -> None` | Once-per-session epic rollup (soft-fail) |
| `ensure_epic_in_progress` | `(bead) -> None` | Claim the bead's parent epic if no epic is in_progress |
| `pick_next_bead` | `(just_closed) -> dict \| None` | Four-tier waterfall: recovery, blocking bug, epic affinity, global ready |
| `activate_next_bead` | `(just_closed=None) -> dict \| None` | Pick, claim, arm wiggum; honour the `--max` cap |

Private helpers worth knowing: `_unblocked_in_progress` (reverts blocked
stranded beads), `_reject_if_blocked` (defence-in-depth block recheck),
`_has_fan_out_gate_issue` (detects `waits_for: children-of(...)` gates).

## `register_callbacks.py`

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `handle_bead_chain_command` | `(command) -> str \| bool` | The `/bead-chain` slash command entry point |
| `_ensure_hooks_registered` | `() -> None` | Register turn hooks once, lazily (after wiggum) |
| `_parse_max_iterations` | `(command) -> int \| None \| object` | Parse `--max`; sentinel `_PARSE_ERROR` on bad input |
| `_on_interactive_turn_end` | `async (...) -> dict \| None` | Drive close to next-bead loop |
| `_on_interactive_turn_cancel` | `(prompt, *, reason="cancelled") -> None` | Halt on cancel; leave bead in_progress |

## Related

- [/bead-chain command and configuration](command-and-configuration.md) --
  flags, env vars, and constants.
- [Why bead-chain is a queue driver, not a goal engine](../explanation/queue-driver-not-goal-engine.md)
  -- how these modules divide responsibility.
