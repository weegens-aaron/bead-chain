# Reference: /bead-chain command and configuration

Technical description of the `/bead-chain` slash command, its flag, its
environment configuration, and the hardcoded operational constants. This
page describes the machinery; it does not teach workflows (see the
[tutorials](../tutorials/) and [how-to guides](../how-to/) for those).

## Command

| Item | Value |
|------|-------|
| Name | `bead-chain` |
| Usage | `/bead-chain [--max=N]` |
| Category | `plugin` |
| Description | Chain `bd ready` beads through `/goal` until the queue is empty |
| Handler | `register_callbacks.handle_bead_chain_command` |
| Return | A goal-prompt string (first bead) on success; `True` (no-op) on early exit |

### Startup probe order

1. If the chain is already active, emit a notice and return `True`.
2. Parse `--max=N` (see below). On parse error, return `True` without
   touching `bd`.
3. `enforce_single_in_progress()` — recover a stranded bead if one exists.
4. If none, `next_ready()` — fetch the first ready non-epic bead.
5. Reject the candidate if it is an excluded type (`is_excluded_type`) or
   has open blockers (`open_blocker_ids`). Both are last-line-of-defence
   re-checks of filters `bd ready` already applies server-side.
6. Register hooks lazily, claim the bead (skipped for recovery beads),
   arm wiggum goal mode, and return the goal prompt.

The unsatisfied fan-out gate check (`waits_for: children-of(...)` with
unclosed children) is *not* applied on this startup path — it runs only
when picking each subsequent bead, in `lifecycle.activate_next_bead`. A
gated bead is rejected there, reverted to open, and the chain stops.

## Flag

| Flag | Forms | Type | Default | Effect |
|------|-------|------|---------|--------|
| `--max` | `--max=N`, `--max N` | positive integer | none (no cap) | Stop the chain after `N` beads are completed in the run |

Parsing (`_parse_max_iterations`) returns one of three outcomes:

| Outcome | Meaning |
|---------|---------|
| `None` | No `--max` flag present — run until the queue empties |
| positive `int` | Parsed cap value |
| `_PARSE_ERROR` sentinel | Flag present but value missing, non-integer, zero, or negative — a warning is emitted and the chain refuses to start |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_BIN` | `bd` | Path to the `bd` executable. Unset or empty falls back to `bd` on `PATH`. Read by `beads._bd_bin()`. |

## Operational constants

Defined in `beads.py`; not configurable at runtime (promoted to env vars
only if a concrete need arises).

| Constant | Value | Meaning |
|----------|-------|---------|
| `DEFAULT_TIMEOUT` | `30.0` | Per-`bd`-command timeout, in seconds |
| `MAX_ATTEMPTS` | `3` | Initial try plus up to two retries |
| `_RETRY_BACKOFFS` | `(0.5, 1.0)` | Delays (seconds) applied before each retry |
| `EXCLUDED_TYPES` | `("epic",)` | Container types never driven |
| `BLOCKING_DEP_TYPES` | `("blocks",)` | Dependency edge types that gate work |
| `SATISFIED_BLOCKER_STATUSES` | `frozenset({"closed"})` | Blocker statuses that no longer gate |
| `BLOCKING_BUG_TYPES` | `("bug",)` | Issue types eligible for blocking-bug priority |
| `PARENT_EPIC_KEY` | `"parent"` | Canonical bd field naming the parent epic |
| `_PARENT_EPIC_FALLBACK_KEYS` | `("parent_id", "epic_id")` | Legacy parent-id keys checked in order |

Retries apply to `subprocess.TimeoutExpired` only. `FileNotFoundError`
(bd missing) and non-zero exits (real bd errors such as "bead not found"
or "already closed") are permanent and surface on the first failure.

## Registered callbacks

| Hook | Handler | Registration | Purpose |
|------|---------|--------------|---------|
| `interactive_turn_end` | `_on_interactive_turn_end` | Lazy (first `/bead-chain`) | Drive close → pick-next → arm loop |
| `interactive_turn_cancel` | `_on_interactive_turn_cancel` | Lazy (first `/bead-chain`) | Halt on Ctrl+C; leave bead in_progress |
| `run_shell_command` | `close_guard.on_run_shell_command` | Eager (module import) | Block premature agent `bd close` |

The two turn hooks register lazily so they land *after* wiggum's
startup-registered hook; see
[Why hooks register lazily so wiggum runs first](../explanation/lazy-hook-registration-ordering.md).

## Close-guard patterns

While the chain is active, `close_guard.detect_premature_close` blocks:

| `pattern_name` | Matched form |
|----------------|--------------|
| `bd close` | `bd close [...]` at a command boundary |
| `bd update --status=closed` | `bd update <id> ... --status=closed` (or `--status closed`) in the same command |

Quoted or echoed text is not matched — the patterns anchor to a command
boundary (`^`, `&&`, `||`, `;`, `|`).

## Related

- [Modules and public functions](modules-and-functions.md) — the
  function-level map behind these knobs.
- [Run bead-chain locally and pass the test suite](../tutorials/run-locally-and-test.md)
  — a first hands-on run.
