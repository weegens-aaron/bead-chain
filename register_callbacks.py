"""bead-chain slash commands + lazy interactive_turn_end hook.

bead-chain is a beads-driven /goal variant. It chains your ``bd ready``
queue into wiggum's /goal mode one bead at a time, closing each on
judge-approval and trotting on to the next until the queue is empty.

Flow when ``/bead-chain`` is invoked:

  1. Probe ``bd ready`` for the first ready bead. No beads → bail loud.
  2. Claim the bead with ``bd update <id> --claim``.
  3. Lazily register our ``interactive_turn_end`` hook *now*, not at
     module import time. This guarantees we get appended AFTER wiggum's
     hook (which loads at startup) so wiggum runs first each turn and
     we can observe ``wiggum_state.is_active()`` AFTER wiggum has
     decided its fate for this iteration.
  4. Activate wiggum goal mode with the bead's prompt.
  5. Return the prompt string — the CLI will execute it as the user's
     prompt, kicking off the first /goal iteration.

Subsequent turns:

  * Wiggum decides goal-incomplete → returns a continuation dict.
    We see ``wiggum_state.is_active() == True`` → return None,
    wiggum's continuation wins.
  * Wiggum decides goal-complete → stops itself, returns None.
    We see ``wiggum_state.is_active() == False`` AND we have a
    current bead → close it, grab next, repeat. If no next bead,
    we stop ourselves and the REPL hands back to the user.

Cancellation:

  * Ctrl+C / cancel → ``interactive_turn_cancel`` fires. We stop
    ourselves and leave the in-flight bead ``in_progress``. The next
    ``/bead-chain`` run will pick it up via the recovery tier and
    re-prompt the agent with the recovery preamble so it assesses the
    current state of the work before doing anything new.

This plugin is **not** a goal engine — it's a queue driver that
delegates the LLM-judged completion loop to wiggum's /goal mode.
Without wiggum loaded, /bead-chain has nothing to drive.

Module layout:

  * This file (``register_callbacks``) — wiring only: slash command,
    hook handlers, CLI flag parsing, callback registration.
  * :mod:`lifecycle` — state transitions: close, revert, invariant
    guard, next-bead waterfall, wiggum arming.
  * :mod:`beads` — thin subprocess wrapper around ``bd``.
  * :mod:`prompt` — bead-dict → goal-prompt formatting.
  * :mod:`close_guard` — shell-command hook that blocks premature
    agent-issued bead closes.
  * :mod:`state` — dumb singleton dataclass for chain state.
"""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import (
    emit_info,
    emit_success,
    emit_system_message,
    emit_warning,
)
from code_puppy.plugins.wiggum import state as wiggum_state

from . import state
from .beads import BeadsError, claim, is_excluded_type, next_ready
from .close_guard import on_run_shell_command as _on_run_shell_command
from .lifecycle import (
    activate_next_bead,
    close_current_bead_success,
    ensure_epic_in_progress,
    enforce_single_in_progress,
    is_recovery_bead,
    rollup_completed_epics,
)
from .prompt import format_bead_as_goal

# ---------------------------------------------------------------------------
# Lazy hook registration
# ---------------------------------------------------------------------------

_HOOKS_REGISTERED = False


def _ensure_hooks_registered() -> None:
    """Register our turn-end / cancel hooks exactly once, lazily.

    By deferring until the first /bead-chain invocation we guarantee
    wiggum (loaded at startup) is already in the callback list ahead
    of us — so wiggum's continuation-dict choice happens before we
    decide whether to grab the next bead.
    """
    global _HOOKS_REGISTERED
    if _HOOKS_REGISTERED:
        return
    register_callback("interactive_turn_end", _on_interactive_turn_end)
    register_callback("interactive_turn_cancel", _on_interactive_turn_cancel)
    _HOOKS_REGISTERED = True


# ---------------------------------------------------------------------------
# CLI flag parsing
# ---------------------------------------------------------------------------

# Sentinel returned by _parse_max_iterations to mean "the user passed an
# invalid --max value, refuse to start". We can't use None for this since
# None is a perfectly valid result (= no cap requested).
_PARSE_ERROR = object()


def _parse_max_iterations(command: str) -> int | None | object:
    """Parse ``--max=N`` or ``--max N`` from a slash-command string.

    Returns:
        * ``None`` — no ``--max`` flag present (no cap).
        * positive ``int`` — parsed cap value.
        * ``_PARSE_ERROR`` sentinel — the flag was present but the value
          was missing, non-integer, zero, or negative. A warning has
          already been emitted; caller should refuse to start.
    """
    tokens = command.split()
    raw: str | None = None
    for i, tok in enumerate(tokens):
        if tok.startswith("--max="):
            raw = tok[len("--max=") :]
            break
        if tok == "--max":
            raw = tokens[i + 1] if i + 1 < len(tokens) else ""
            break
    if raw is None:
        return None

    try:
        n = int(raw)
    except ValueError:
        emit_warning(
            f"🔗 bead-chain: --max requires a positive integer, got {raw!r}. "
            "Refusing to start."
        )
        return _PARSE_ERROR
    if n <= 0:
        emit_warning(f"🔗 bead-chain: --max must be > 0, got {n}. Refusing to start.")
        return _PARSE_ERROR
    return n


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


@register_command(
    name="bead-chain",
    description="Chain `bd ready` beads through /goal until the queue is empty 🔗",
    usage="/bead-chain [--max=N]",
    category="plugin",
)
def handle_bead_chain_command(command: str) -> str | bool:
    """Engage bead-chain: drive /goal across every ready bead in turn."""
    if state.is_active():
        emit_info("🔗 bead-chain is already running.")
        return True

    # Parse --max=N before touching bd: invalid flag → bail loud,
    # don't claim anything.
    max_iterations = _parse_max_iterations(command)
    if max_iterations is _PARSE_ERROR:
        return True

    # Probe first so /bead-chain fails loud on an empty queue or broken bd.
    # Recovery check beats the ready queue: if a prior run errored mid-bead,
    # we must finish (or formally close) that one before starting new work.
    # The startup guard enforces the single-in_progress invariant by
    # auto-reverting any extras to open before we proceed.
    try:
        bead = enforce_single_in_progress()
        if bead is None:
            bead = next_ready()
    except BeadsError as exc:
        emit_warning(f"🔗 bead-chain can't reach `bd`: {exc}")
        return True

    if bead is None:
        emit_info("🦴 No ready beads — bead-chain has nothing to fetch.")
        return True

    bead_id = str(bead.get("id", ""))

    # Last-line-of-defence assertion: matches the same check in
    # :func:`lifecycle.activate_next_bead`. An upstream filter leak
    # here would arm wiggum with an epic and produce the 'cannot
    # close epic' failure we hit in prod. Refuse early.
    if is_excluded_type(bead):
        emit_warning(
            f"🚫 bead-chain refused to start with {bead_id}: it's an excluded "
            f"container type ({bead.get('issue_type', '?')}). "
            "An upstream filter leaked an epic into the chain — this is a bug."
        )
        return True

    recovery = is_recovery_bead(bead)
    if recovery:
        emit_warning(
            f"⚠️ Recovering stranded in_progress bead {bead_id} — "
            "agent will assess current state before doing new work."
        )

    _ensure_hooks_registered()
    state.start()
    # mypy/pyright: max_iterations is int|None here (sentinel already handled).
    state.get_state().max_iterations = max_iterations  # type: ignore[assignment]

    # Walk the hierarchy top-down: claim the parent epic FIRST, then
    # the child bead. bd's UI caches per-parent children-by-status
    # views, so flipping a leaf to in_progress under a still-open
    # parent produces a stale tree until the user navigates back to
    # the parent. Going parent-first keeps the hierarchy consistent
    # at every observable moment. Soft-fails — never blocks the chain.
    ensure_epic_in_progress(bead)

    if not recovery:
        try:
            claim(bead_id)
        except BeadsError as exc:
            emit_warning(f"🔗 bead-chain couldn't claim {bead_id}: {exc}")
            state.stop()
            return True
    # Recovery beads are already in_progress — re-claiming is at best a
    # no-op and at worst a bd error, so we skip the call entirely.

    state.get_state().current_bead = bead

    goal_prompt = format_bead_as_goal(bead, recovery=recovery)
    wiggum_state.start(goal_prompt, mode="goal")

    emit_success("🔗 BEAD-CHAIN ENGAGED!")
    emit_info(f"First bead: {bead_id} — {bead.get('title', '')}")
    if max_iterations is not None:
        emit_info(f"Safety cap: stopping after {max_iterations} bead(s).")
    emit_info("Will claim → /goal → close → repeat until `bd ready` is empty.")
    emit_info("Press Ctrl+C to halt.")
    return goal_prompt


# ---------------------------------------------------------------------------
# interactive_turn_end / interactive_turn_cancel hooks
# (registered lazily by _ensure_hooks_registered)
# ---------------------------------------------------------------------------


async def _on_interactive_turn_end(
    agent: Any,
    prompt: str,
    result: Any = None,
    *,
    success: bool = True,
    error: BaseException | None = None,
) -> dict[str, Any] | None:
    """Drive the bead → /goal → close → next-bead loop.

    Returns None whenever wiggum should keep driving (i.e., goal mode
    still active for the current bead) or when we've run out of beads.
    Returns a continuation dict only when we're handing wiggum a NEW
    bead to chew on.
    """
    del agent, prompt, result, success, error

    if not state.is_active():
        return None

    # Wiggum is mid-goal — let it cook. We're guaranteed to run AFTER
    # wiggum on each turn because we registered later (see
    # _ensure_hooks_registered docstring).
    if wiggum_state.is_active():
        return None

    # Wiggum just stopped — that means the bead is either complete
    # (judges passed) or wiggum cancelled. We can't distinguish here,
    # but interactive_turn_cancel runs for cancellation and would have
    # already stopped us; so reaching this branch with state.active
    # still True implies success.
    just_closed = close_current_bead_success()
    # If close-failure stopped the chain, close_current_bead_success
    # already emitted the explanation and halted state. Bow out cleanly
    # rather than barreling into activate_next_bead and claiming a new
    # bead on top of the one we couldn't close.
    if not state.is_active():
        return None
    # Rollup runs *between* close and next-pick so logs read linearly:
    # closed bead → rolled-up epic(s) → started epic → picked next bead.
    # Only worth attempting when we actually closed something this turn.
    if just_closed is not None:
        rollup_completed_epics()
    # Note: starting the next bead's parent epic is handled inside
    # activate_next_bead, where we actually know which bead got
    # claimed. Doing it here would be premature.
    return activate_next_bead(just_closed)


def _on_interactive_turn_cancel(prompt: str, *, reason: str = "cancelled") -> None:
    """Bow out on Ctrl+C; leave the in-flight bead in_progress for recovery.

    Evolution of intent here matters — read this before "simplifying":

      * v1 left the bead claimed-but-open. Cancels accumulated stranded
        in_progress beads (5+ in ``bd status`` was routine).
      * v2 reverted to ``open``. Fixed the accumulation but introduced
        a worse failure mode: any partial work on disk got orphaned
        from its bead because the next ``bd ready`` could (and did)
        hand us a *different* bead, leaving the half-done changes
        silently attached to no tracked work.
      * v3 (this one): leave the bead **in_progress**. The next
        ``/bead-chain`` run hits the recovery tier first
        (:func:`pick_next_bead` tier 0) and re-prompts the agent with
        :data:`prompt._RECOVERY_PREAMBLE`, instructing it to assess
        what's already on disk before doing any new work. Partial
        work and its bead stay paired — no orphaning, no stranding-
        across-runs because the invariant guard finds it next time.

    The chain itself still stops cleanly here — we only halt the loop,
    not the bead's status. Recovery is a startup-time concern, handled
    by :func:`lifecycle.enforce_single_in_progress` /
    :func:`lifecycle.pick_next_bead` on the next run.
    """
    del prompt
    if not state.is_active():
        return
    bead_id = state.get_state().current_bead_id
    state.stop()
    emit_warning(f"🔗 bead-chain halted due to {reason}.")
    if not bead_id:
        return
    emit_system_message(
        f"🔖 Bead {bead_id} left in_progress — the next /bead-chain run "
        "will resume it with a recovery preamble so the agent assesses "
        "the current state before doing new work."
    )


# ---------------------------------------------------------------------------
# run_shell_command hook: block premature bead closes while chain is active
# ---------------------------------------------------------------------------
#
# The hook implementation lives in :mod:`.close_guard` alongside its
# regex detector — they're one cohesive feature ("what counts as a
# premature close" + "what to do when one is seen") and splitting them
# across files just to bow to layout convention would hurt SRP, not
# help it. We register it here, eagerly at module scope, because the
# hook is a one-line no-op when bead-chain is idle and has no ordering
# dependency on any other plugin.
#
# bead-chain's own ``bd close`` calls in :mod:`.beads` use
# ``subprocess.run`` directly and never traverse code_puppy's command
# runner, so this hook does NOT fire on them. Only agent-issued shell
# commands are intercepted. 🐶

register_callback("run_shell_command", _on_run_shell_command)
