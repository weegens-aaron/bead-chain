"""Tests for close_guard.detect_premature_close + on_run_shell_command.

Covers the core detector contract plus the regression for
``bead_chain-21d``: ``re.MULTILINE`` made ``_COMMAND_BOUNDARY``'s ``^``
match the start of *every embedded line*, so a ``bd close`` (or
``bd update ... --status=closed``) text living at the start of a line
*inside a quoted argument* — e.g. a multi-line git commit message body —
falsely tripped the guard and blocked the command.

The fix blanks out quoted string literals before the boundary scan, so:
  * text inside quotes can never satisfy the command boundary (no false
    positive), while
  * a genuine ``bd close`` on its own line *outside* quotes is still
    caught (no false negative) because real newlines remain separators.

The ``on_run_shell_command`` hook half exercises the active/idle gate,
the block payload shape, and the ``current_bead_id`` ``None`` fallback —
the two halves are one cohesive guard (they live in the same module) so
they share a test file.

close_guard uses relative imports (``from . import state``), so we import
it via the package registered in conftest rather than flat.
"""

from __future__ import annotations

import asyncio

import pytest  # noqa: E402

from code_puppy.plugins.bead_chain import close_guard, state  # noqa: E402


# ---------------------------------------------------------------------------
# Positive detections — real bypass attempts must still be caught.
# ---------------------------------------------------------------------------


def test_plain_bd_close_detected():
    match = close_guard.detect_premature_close("bd close cpp-1")
    assert match is not None
    assert match.pattern_name == "bd close"


def test_bd_close_after_chain_separator_detected():
    match = close_guard.detect_premature_close("git add . && bd close cpp-1")
    assert match is not None
    assert match.pattern_name == "bd close"


def test_bd_close_with_path_prefix_detected():
    match = close_guard.detect_premature_close("/usr/local/bin/bd close cpp-1")
    assert match is not None


def test_bd_update_status_closed_equals_detected():
    match = close_guard.detect_premature_close("bd update cpp-1 --status=closed")
    assert match is not None
    assert match.pattern_name == "bd update --status=closed"


def test_bd_update_status_closed_space_detected():
    match = close_guard.detect_premature_close("bd update cpp-1 --status closed")
    assert match is not None


def test_real_bd_close_on_own_line_outside_quotes_still_detected():
    """A genuine newline-separated bd close must NOT slip through the fix.

    In shell a bare newline is a command separator, so this is a real
    bypass attempt — the quote-blanking must leave it intact.
    """
    cmd = "git add .\nbd close cpp-1"
    match = close_guard.detect_premature_close(cmd)
    assert match is not None
    assert match.pattern_name == "bd close"


# ---------------------------------------------------------------------------
# Negative detections — legitimate / harmless commands must pass.
# ---------------------------------------------------------------------------


def test_unrelated_command_ignored():
    assert close_guard.detect_premature_close("git status") is None


def test_bd_update_claim_ignored():
    assert close_guard.detect_premature_close("bd update cpp-1 --claim") is None


def test_bd_update_status_in_progress_ignored():
    cmd = "bd update cpp-1 --status=in_progress"
    assert close_guard.detect_premature_close(cmd) is None


def test_bd_close_inside_single_line_quote_ignored():
    """A plain space is not a command boundary — already worked pre-fix."""
    cmd = 'echo "run: bd close cpp-1 when done"'
    assert close_guard.detect_premature_close(cmd) is None


def test_env_prefixed_bd_close_slips_through_documented_yagni():
    """``FOO=bar bd close`` is NOT caught — a deliberate YAGNI gap.

    The detector anchors on a real command boundary (start-of-line or a
    shell separator), and a space after an env-var assignment is not one.
    close_guard's module docstring documents this on purpose: env-var
    prefixes blur quoted-text vs. real invocations and aren't a pattern
    agents reach for, so we don't chase them. This test pins the
    behaviour so a future "fix" is a conscious decision, not an accident.
    """
    assert close_guard.detect_premature_close("FOO=bar bd close cpp-1") is None


# ---------------------------------------------------------------------------
# bead_chain-21d regression: bd-close text at a LINE START inside a quote.
# ---------------------------------------------------------------------------


def test_bd_close_at_line_start_in_double_quoted_arg_ignored():
    """The original repro: commit body whose line starts with 'bd close'."""
    cmd = 'git commit -m "Fix close_guard\n\nbd close was being parsed here"'
    assert close_guard.detect_premature_close(cmd) is None


def test_bd_close_at_line_start_in_single_quoted_arg_ignored():
    cmd = "git commit -m 'Refactor\nbd close mentioned in body'"
    assert close_guard.detect_premature_close(cmd) is None


def test_bd_update_status_closed_at_line_start_in_quote_ignored():
    cmd = 'git commit -m "Notes\nbd update cpp-1 --status=closed (example)"'
    assert close_guard.detect_premature_close(cmd) is None


def test_real_close_after_quoted_multiline_body_still_detected():
    """Quote-blanking must not swallow a real bd close that follows.

    A multi-line commit message (quoted, harmless) chained via && to a
    genuine bd close should still trip the guard on the real invocation.
    """
    cmd = 'git commit -m "line one\nline two" && bd close cpp-1'
    match = close_guard.detect_premature_close(cmd)
    assert match is not None
    assert match.pattern_name == "bd close"


# ---------------------------------------------------------------------------
# _blank_quoted helper unit checks.
# ---------------------------------------------------------------------------


def test_blank_quoted_preserves_length():
    cmd = 'echo "hello world"'
    assert len(close_guard._blank_quoted(cmd)) == len(cmd)


def test_blank_quoted_removes_inner_content():
    cmd = 'echo "bd close x"'
    blanked = close_guard._blank_quoted(cmd)
    assert "bd close" not in blanked
    assert blanked.startswith("echo ")


# ===========================================================================
# on_run_shell_command hook — the active/idle gate + block payload.
# ===========================================================================
#
# The hook is async, but the repo has no pytest-asyncio, so we drive the
# coroutine with asyncio.run(). It reads the shared chain singleton, so an
# autouse fixture leaves that singleton pristine for the next module.


@pytest.fixture(autouse=True)
def _restore_state():
    """Leave the shared chain singleton pristine for the next module."""
    yield
    s = state.get_state()
    s.active = False
    s.current_bead = None
    s.completed_count = 0
    s.max_iterations = None


@pytest.fixture
def captured_warnings(monkeypatch):
    """Capture emit_warning calls so the hook stays side-effect-free here."""
    warnings: list[str] = []
    monkeypatch.setattr(close_guard, "emit_warning", warnings.append)
    return warnings


def _engage(bead: dict | None) -> None:
    """Mark the chain active with ``bead`` as the in-flight current bead."""
    s = state.get_state()
    s.active = True
    s.current_bead = bead


def _run_hook(command: str):
    return asyncio.run(close_guard.on_run_shell_command(None, command))


def test_hook_noop_when_chain_idle(captured_warnings):
    """Idle chain → even a blatant `bd close` is allowed (returns None).

    The guard is the chain's bouncer; when the chain isn't running there's
    no in-flight bead to protect, so the hook must get out of the way.
    """
    # state defaults to inactive; assert that precondition explicitly.
    assert state.is_active() is False
    assert _run_hook("bd close cpp-1") is None
    assert captured_warnings == []


def test_hook_blocks_close_when_active(captured_warnings):
    """Active chain + `bd close` → blocked dict + a teachable warning."""
    _engage({"id": "cpp-42", "title": "t"})
    result = _run_hook("bd close cpp-42")
    assert result is not None
    assert result["blocked"] is True
    assert "bd close" in result["reasoning"]
    # The reminder names the in-flight bead so the agent knows what's pending.
    assert "cpp-42" in result["error_message"]
    # Surfaced verbatim to the agent AND emitted as a warning.
    assert captured_warnings == [result["error_message"]]


def test_hook_blocks_update_status_closed_when_active(captured_warnings):
    """The second pattern is gated the same way as `bd close`."""
    _engage({"id": "cpp-7", "title": "t"})
    result = _run_hook("bd update cpp-7 --status=closed")
    assert result is not None
    assert result["blocked"] is True
    assert "bd update --status=closed" in result["reasoning"]


def test_hook_allows_benign_command_when_active(captured_warnings):
    """Active chain + harmless command → None, no warning."""
    _engage({"id": "cpp-1", "title": "t"})
    assert _run_hook("git status") is None
    assert captured_warnings == []


def test_hook_allows_claim_when_active(captured_warnings):
    """`bd update --claim` is legitimate even mid-chain → None."""
    _engage({"id": "cpp-1", "title": "t"})
    assert _run_hook("bd update cpp-1 --claim") is None
    assert captured_warnings == []


def test_hook_current_bead_id_none_fallback(captured_warnings):
    """Active but no current bead → reminder uses the 'the active bead' text.

    state.start() flips active True while leaving current_bead None (the
    window between engaging the chain and picking the first bead). The
    hook must still block and degrade gracefully to a generic label
    rather than printing 'None'.
    """
    _engage(None)
    assert state.get_state().current_bead_id is None
    result = _run_hook("bd close cpp-1")
    assert result is not None
    assert result["blocked"] is True
    assert "the active bead" in result["error_message"]
    assert "None" not in result["error_message"]
