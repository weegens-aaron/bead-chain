"""Detect agent attempts to close a bead while bead-chain is in flight.

bead-chain delegates the close decision to wiggum's LLM judges: a bead
is only closed once the judges agree the goal is satisfied, via
:func:`bd close` invoked by the plugin itself (see ``beads.close``).

If an agent shells out to ``bd close`` (or ``bd update <id>
--status=closed``) mid-run, it short-circuits that contract and closes
the bead without any verdict. This module spots the bypass so the
``run_shell_command`` hook can block it with a reminder.

Pure functions, no side effects, trivially testable — kept in its own
module so :mod:`register_callbacks` doesn't grow regex baggage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from code_puppy.messaging import emit_warning

from . import state


@dataclass(frozen=True)
class CloseGuardMatch:
    """Result of a premature-close detection."""

    pattern_name: str
    description: str


# Tokens that legitimately precede a fresh command in a shell pipeline
# or chain. Anchoring to one of these (or start-of-string) prevents
# false positives like ``echo "run: bd close cpp-1"`` from triggering
# the guard — a plain space is **not** a command boundary, so a bd
# token inside a quoted string won't match. Same boundary set as
# ``force_push_guard.detector``, deliberately, for consistency. We do
# not try to support env-var prefixes (``FOO=bar bd close ...``) — they
# blur the line between quoted text and real invocations, and they
# aren't a pattern agents reach for in practice. YAGNI.
_COMMAND_BOUNDARY = r"(?:^|&&|\|\||;|\|)\s*"

# Optional path prefix (``/usr/local/bin/``, ``./``, ``$BEADS_BIN/``...).
# Anything non-whitespace ending in a slash is fine; the basename has to
# be exactly ``bd``.
_BD_INVOCATION = r"(?:\S*/)?bd"

# Match ``bd close [...]`` — any subcommand-style invocation of close
# regardless of trailing flags or bead id.
_BD_CLOSE_RE = re.compile(
    rf"{_COMMAND_BOUNDARY}{_BD_INVOCATION}\s+close\b", re.MULTILINE
)

# Match ``bd update <id> --status=closed`` or ``bd update <id> --status
# closed``. We restrict the gap between ``update`` and ``--status`` to
# the same command (no shell separators) so a later chained command
# doesn't get blamed on the earlier ``bd update --claim``.
_BD_UPDATE_STATUS_CLOSED_RE = re.compile(
    rf"{_COMMAND_BOUNDARY}{_BD_INVOCATION}\s+update\b[^|;&]*?"
    r"--status[=\s]+closed\b",
    re.MULTILINE,
)


def detect_premature_close(command: str) -> CloseGuardMatch | None:
    """Return a :class:`CloseGuardMatch` if ``command`` would close a bead.

    Returns ``None`` for unrelated commands and for legitimate
    ``bd update --claim`` / ``--status=in_progress`` calls. The check
    is intentionally lenient about *which* bead is being closed: while
    bead-chain is active, the agent has no business closing any bead
    — that's the chain's job.
    """
    # Cheap pre-filter: skip regex work entirely when the command can't
    # possibly invoke bd. ``"bd"`` appears in plenty of unrelated
    # strings, but it's a small enough set to be worth the savings.
    if "bd" not in command:
        return None

    if _BD_CLOSE_RE.search(command):
        return CloseGuardMatch(
            pattern_name="bd close",
            description="Direct `bd close` bypasses the LLM judges.",
        )
    if _BD_UPDATE_STATUS_CLOSED_RE.search(command):
        return CloseGuardMatch(
            pattern_name="bd update --status=closed",
            description=("Setting status=closed on a bead bypasses the LLM judges."),
        )
    return None


# ---------------------------------------------------------------------------
# run_shell_command hook
# ---------------------------------------------------------------------------
#
# Lives here (next to the detector) rather than in ``register_callbacks``
# because the two are one cohesive guard: change one and you'll almost
# certainly want to glance at the other. The hook is registered by
# ``register_callbacks`` at module scope — there's no ordering
# dependency on any other plugin, and the early ``state.is_active()``
# check makes it a cheap no-op when the chain isn't running.


async def on_run_shell_command(
    context: Any,
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
) -> dict[str, Any] | None:
    """Block premature `bd close` / `bd update --status=closed` calls.

    Returns ``None`` (allow) unless **both** conditions hold:

      * bead-chain is currently active, AND
      * the command would close a bead.

    In that case returns a ``{"blocked": True, ...}`` dict whose
    ``error_message`` is surfaced verbatim to the agent as the shell
    command's error output — a teachable moment reminding the agent
    the LLM judges are the only legitimate closer.
    """
    del context, cwd, timeout

    if not state.is_active():
        return None

    match = detect_premature_close(command)
    if match is None:
        return None

    current = state.get_state().current_bead_id or "the active bead"
    reminder = (
        f"🛑 bead-chain blocked `{match.pattern_name}`.\n"
        f"  {match.description}\n"
        f"  bead-chain is currently driving bead {current} through "
        f"wiggum's /goal mode. The bead will be closed automatically "
        f"once the LLM judges sign off — do NOT close it yourself.\n"
        f"  Keep working on the task. If you believe the bead is "
        f"complete, summarize what you did and let the judges decide."
    )
    emit_warning(reminder)
    return {
        "blocked": True,
        "reasoning": f"Premature close attempted ({match.pattern_name})",
        "error_message": reminder,
    }
