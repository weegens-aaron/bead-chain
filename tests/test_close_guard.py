"""Tests for close_guard.detect_premature_close.

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

close_guard uses relative imports (``from . import state``), so we import
it via the package registered in conftest rather than flat.
"""

from __future__ import annotations

from code_puppy.plugins.bead_chain import close_guard  # noqa: E402


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
