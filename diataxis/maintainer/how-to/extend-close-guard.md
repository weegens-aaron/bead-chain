# How-to: Extend the close-guard to block another bd command

Add a new forbidden `bd` invocation to the close-guard so that, while
bead-chain is driving a bead, agents cannot run it. Use this when you find
another command that bypasses the LLM-judge close contract (the guard
already blocks `bd close` and `bd update --status=closed`).

This guide assumes you can read regex and run the test suite. For the
rationale behind the guard, see [Why bead-chain is a queue driver, not a
goal engine](../explanation/queue-driver-not-goal-engine.md).

## When to use this

- You discover a `bd` command an agent can run that closes or otherwise
  short-circuits a bead without the judges' verdict.
- You want that command intercepted only while the chain is active.

## Steps

1. Open `close_guard.py`. Note the two existing building blocks you will
   reuse:

   - `_COMMAND_BOUNDARY` — anchors a match to a real command start
     (`^`, `&&`, `||`, `;`, `|`), so quoted text like
     `echo "run: bd close x"` does not trip the guard.
   - `_BD_INVOCATION` — matches `bd` with an optional path prefix.

2. Add a compiled regex for your new command, mirroring the existing ones:

   ```python
   _BD_DELETE_RE = re.compile(
       rf"{_COMMAND_BOUNDARY}{_BD_INVOCATION}\s+delete\b", re.MULTILINE
   )
   ```

3. Wire it into `detect_premature_close`, returning a `CloseGuardMatch`
   with a clear `pattern_name` and `description`:

   ```python
   if _BD_DELETE_RE.search(command):
       return CloseGuardMatch(
           pattern_name="bd delete",
           description="Direct `bd delete` removes a bead without a verdict.",
       )
   ```

4. The `run_shell_command` hook (`on_run_shell_command`) already consumes
   `detect_premature_close`, so no hook changes are needed — your new
   pattern is enforced automatically while `state.is_active()`.

5. Add a test covering both the positive case and a false-positive guard:

   ```python
   from close_guard import detect_premature_close
   assert detect_premature_close("bd delete cpp-1") is not None
   assert detect_premature_close('echo "bd delete cpp-1"') is None
   ```

6. Run the suite:

   ```bash
   python -m pytest -q
   ```

## Variations and options

- **Match flags or a gap before a flag** (like the existing
  `--status=closed` rule): restrict the gap to the same command with a
  `[^|;&]*?` segment so a later chained command is not blamed on the
  earlier one.
- **Keep the cheap pre-filter happy.** `detect_premature_close` early-exits
  when `"bd"` is not in the command; your pattern only runs past that gate,
  so no extra work is needed.

## Done — verify

- `python -m pytest -q` is green.
- A manual probe blocks the command while the chain is active and the agent
  sees the reminder emitted by `on_run_shell_command`.

## Related

- [Modules and public functions](../reference/modules-and-functions.md) —
  `detect_premature_close`, `CloseGuardMatch`, `on_run_shell_command`.
- [/bead-chain command and configuration](../reference/command-and-configuration.md)
  — when the guard is active.
