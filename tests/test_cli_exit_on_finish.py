"""Tests for the ``--bead-chain`` exit-on-finish behaviour.

When the chain is launched via the ``--bead-chain`` CLI flag, code-puppy is
being used as a one-shot queue drainer: there is no human waiting at an
interactive REPL with follow-up tasks. Dropping back into an empty prompt
after the chain ends would just strand the process. The plumbing:

  * ``_handle_cli_args`` latches a module-level ``_EXIT_ON_CHAIN_FINISH``
    flag the moment it successfully starts a chain.
  * ``_exit_if_cli_launched`` reads that flag and raises ``SystemExit(0)``
    so the host's callback dispatcher (which catches ``Exception`` but NOT
    ``BaseException``) lets the exit propagate out of the continuation loop
    and back to the process boundary.
  * ``_on_interactive_turn_end`` calls it from every observed chain-stop
    branch (close failure + queue drained / cap / error).
  * ``_on_interactive_turn_cancel`` calls it after Ctrl+C halts the chain.

These tests cover the two halves: the latch only sets on a *successful*
start, and the hooks honour it at every stop point. The slash-command
launch path (``handle_bead_chain_command`` called directly) must NEVER
trigger an exit -- the user is interactively at a REPL with more work.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from code_puppy.plugins.bead_chain import register_callbacks, state


@pytest.fixture(autouse=True)
def _reset_exit_flag():
    """Snapshot + restore the module-level latch so tests don't leak it.

    Mirrors the spirit of conftest's beads-globals guard: any test that
    sets ``_EXIT_ON_CHAIN_FINISH`` must not poison the next one.
    """
    saved = register_callbacks._EXIT_ON_CHAIN_FINISH
    try:
        yield
    finally:
        register_callbacks._EXIT_ON_CHAIN_FINISH = saved
        state.reset()


# ---------------------------------------------------------------------------
# _handle_cli_args: when does the latch get set?
# ---------------------------------------------------------------------------


def _make_args(**overrides):
    """Build a fake argparse.Namespace-ish object for _handle_cli_args."""
    base = {"bead_chain": False, "bead_chain_max": None, "prompt": None}
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_handle_cli_args_noop_when_flag_absent(monkeypatch):
    """No flag, no behaviour -- latch stays False, handler isn't even called."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)

    def _boom(_command):
        raise AssertionError("handle_bead_chain_command must not run without flag")

    monkeypatch.setattr(register_callbacks, "handle_bead_chain_command", _boom)

    args = _make_args(bead_chain=False)
    assert register_callbacks._handle_cli_args(args) is None
    assert register_callbacks._EXIT_ON_CHAIN_FINISH is False


def test_handle_cli_args_sets_latch_on_successful_start(monkeypatch):
    """A goal-prompt string back from start => latch on, command injected."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)
    monkeypatch.setattr(register_callbacks, "_WIGGUM_AVAILABLE", True)
    monkeypatch.setattr(
        register_callbacks,
        "handle_bead_chain_command",
        lambda _cmd: "GOAL_PROMPT_TEXT",
    )

    args = _make_args(bead_chain=True)
    register_callbacks._handle_cli_args(args)

    assert register_callbacks._EXIT_ON_CHAIN_FINISH is True
    assert args.command == ["GOAL_PROMPT_TEXT"]


def test_handle_cli_args_does_not_set_latch_on_refused_start(monkeypatch):
    """If the chain refused to start (no beads / bad --max / etc.), no exit.

    ``handle_bead_chain_command`` returns ``True`` in every refuse-to-start
    branch (see the docstring on that function). We must fall through to a
    plain REPL in that case -- nothing for us to exit *from*.
    """
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)
    monkeypatch.setattr(register_callbacks, "_WIGGUM_AVAILABLE", True)
    monkeypatch.setattr(
        register_callbacks, "handle_bead_chain_command", lambda _cmd: True
    )

    args = _make_args(bead_chain=True)
    register_callbacks._handle_cli_args(args)

    assert register_callbacks._EXIT_ON_CHAIN_FINISH is False


def test_handle_cli_args_does_not_set_latch_when_wiggum_missing(monkeypatch):
    """Graceful degradation: no wiggum => warn + REPL, NEVER exit on finish."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)
    monkeypatch.setattr(register_callbacks, "_WIGGUM_AVAILABLE", False)

    def _boom(_command):
        raise AssertionError("handle_bead_chain_command must not run sans wiggum")

    monkeypatch.setattr(register_callbacks, "handle_bead_chain_command", _boom)

    args = _make_args(bead_chain=True)
    register_callbacks._handle_cli_args(args)

    assert register_callbacks._EXIT_ON_CHAIN_FINISH is False


def test_handle_cli_args_does_not_set_latch_when_start_raises(monkeypatch):
    """Startup hiccup must NOT leave a stale latch that poisons the REPL."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)
    monkeypatch.setattr(register_callbacks, "_WIGGUM_AVAILABLE", True)

    def _boom(_command):
        raise RuntimeError("bd fell over")

    monkeypatch.setattr(register_callbacks, "handle_bead_chain_command", _boom)

    args = _make_args(bead_chain=True)
    # Soft-fail contract: never propagates, just leaves us at the REPL.
    register_callbacks._handle_cli_args(args)
    assert register_callbacks._EXIT_ON_CHAIN_FINISH is False


# ---------------------------------------------------------------------------
# _exit_if_cli_launched: the actual exit lever
# ---------------------------------------------------------------------------


def test_exit_helper_is_noop_when_latch_unset(monkeypatch):
    """Slash-command path: latch False => no exit, no SystemExit."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)
    # Must not raise.
    register_callbacks._exit_if_cli_launched("queue drained")


def test_exit_helper_raises_system_exit_when_latch_set(monkeypatch):
    """CLI-launch path: SystemExit(0) -- BaseException so dispatcher won't eat it."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", True)
    with pytest.raises(SystemExit) as excinfo:
        register_callbacks._exit_if_cli_launched("queue drained")
    assert excinfo.value.code == 0


# ---------------------------------------------------------------------------
# Hook integration: turn-end + turn-cancel honour the latch
# ---------------------------------------------------------------------------


def _run_turn_end():
    return asyncio.run(
        register_callbacks._on_interactive_turn_end(
            agent=object(),
            prompt="p",
            result=None,
            success=True,
            error=None,
        )
    )


def test_turn_end_exits_when_queue_drains_and_latch_set(monkeypatch):
    """Empty-queue branch (activate returns None) triggers SystemExit."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", True)

    monkeypatch.setattr(
        register_callbacks, "close_current_bead_success", lambda: {"id": "x"}
    )

    def _drain(_just_closed):
        # Mirror the real activate_next_bead drain: it stops state itself.
        state.stop()
        return None

    monkeypatch.setattr(register_callbacks, "activate_next_bead", _drain)

    st = state.get_state()
    st.start()
    st.current_bead = {"id": "x", "title": "x"}

    with pytest.raises(SystemExit) as excinfo:
        _run_turn_end()
    assert excinfo.value.code == 0


def test_turn_end_exits_when_close_fails_and_latch_set(monkeypatch):
    """Close-failure branch (state stopped pre-activate) triggers SystemExit.

    Symmetric to the queue-drained case: any observable chain-stop while
    the CLI latch is on must terminate code-puppy, not silently fall through.
    """
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", True)

    def _close_then_halt():
        state.stop()
        return {"id": "x"}

    monkeypatch.setattr(
        register_callbacks, "close_current_bead_success", _close_then_halt
    )

    def _never_called(_just_closed):
        raise AssertionError("activate must be short-circuited on close failure")

    monkeypatch.setattr(register_callbacks, "activate_next_bead", _never_called)

    st = state.get_state()
    st.start()
    st.current_bead = {"id": "x", "title": "x"}

    with pytest.raises(SystemExit) as excinfo:
        _run_turn_end()
    assert excinfo.value.code == 0


def test_turn_end_does_not_exit_on_slash_command_launch(monkeypatch):
    """Slash-command launch: chain drains, REPL stays alive. The whole point."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)

    monkeypatch.setattr(
        register_callbacks, "close_current_bead_success", lambda: {"id": "x"}
    )

    def _drain(_just_closed):
        state.stop()
        return None

    monkeypatch.setattr(register_callbacks, "activate_next_bead", _drain)

    st = state.get_state()
    st.start()
    st.current_bead = {"id": "x", "title": "x"}

    # Must NOT raise -- the REPL stays alive for the human to keep working.
    assert _run_turn_end() is None


def test_turn_end_continuation_passes_through_when_chain_continues(monkeypatch):
    """Mid-chain (continuation dict returned) is unaffected by the latch.

    The latch only fires at chain *finish*. While there are still beads to
    drive, we hand back the continuation exactly like the pre-latch code did.
    """
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", True)

    monkeypatch.setattr(
        register_callbacks, "close_current_bead_success", lambda: {"id": "x"}
    )
    continuation = {"prompt": "next", "clear_context": True}
    monkeypatch.setattr(
        register_callbacks, "activate_next_bead", lambda _jc: continuation
    )

    st = state.get_state()
    st.start()
    st.current_bead = {"id": "x", "title": "x"}

    assert _run_turn_end() is continuation


def test_turn_cancel_exits_when_latch_set(monkeypatch):
    """Ctrl+C on a CLI-launched chain => exit, not awkward empty REPL."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", True)

    st = state.get_state()
    st.start()
    st.current_bead = {"id": "stranded-1", "title": "x"}

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(
            register_callbacks._on_interactive_turn_cancel("p", reason="Ctrl+C")
        )
    assert excinfo.value.code == 0


def test_turn_cancel_does_not_exit_on_slash_command_launch(monkeypatch):
    """Slash-command Ctrl+C: chain halts, user stays in REPL to inspect/recover."""
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", False)

    st = state.get_state()
    st.start()
    st.current_bead = {"id": "stranded-1", "title": "x"}

    # Must NOT raise.
    asyncio.run(
        register_callbacks._on_interactive_turn_cancel("p", reason="Ctrl+C")
    )


def test_turn_cancel_idle_is_noop_regardless_of_latch(monkeypatch):
    """No active chain => cancel is a no-op even if the latch happens to be set.

    Guards against the latch firing for a cancel that isn't *about* the chain
    (e.g. a stray cancel signal after the chain already exited cleanly).
    """
    monkeypatch.setattr(register_callbacks, "_EXIT_ON_CHAIN_FINISH", True)
    state.stop()

    # Must NOT raise -- early-return before reaching the exit helper.
    asyncio.run(
        register_callbacks._on_interactive_turn_cancel("p", reason="Ctrl+C")
    )
