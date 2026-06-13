"""Regression tests for bead_chain-c87: friendly error when wiggum is missing.

``register_callbacks.py`` and ``lifecycle.py`` both depend on
``code_puppy.plugins.wiggum.state``. Historically these were bare top-level
imports, so when wiggum wasn't loaded the whole bead-chain module failed to
import with a raw ``ImportError``. The plugin loader caught it and the app
survived, but the user saw a cryptic
``Failed to import callbacks from user plugin bead_chain: No module named
'code_puppy.plugins.wiggum'`` rather than an actionable message.

The fix imports wiggum defensively (keeping the module importable), records
absence in ``_WIGGUM_AVAILABLE``, logs one clear human-readable line at import
time, and makes ``/bead-chain`` degrade gracefully — emitting a friendly
"requires the wiggum plugin" warning instead of blowing up.

These tests verify:
  1. The friendly message names wiggum and is human-readable.
  2. When wiggum is unavailable, ``/bead-chain`` bails early with that
     message and never touches ``wiggum_state`` (no raw error).
  3. When wiggum IS available the prerequisite gate is transparent — the
     command proceeds past the gate (behaviour identical to before).
"""

from __future__ import annotations

import pytest
from code_puppy.plugins.bead_chain import register_callbacks, state


@pytest.fixture(autouse=True)
def _idle_chain():
    """Each test starts and ends with an idle chain."""
    state.reset()
    yield
    state.reset()


def test_message_is_human_readable_and_names_wiggum():
    """The friendly message must mention wiggum and /bead-chain, not a stacktrace."""
    msg = register_callbacks._WIGGUM_MISSING_MESSAGE
    assert "wiggum" in msg.lower()
    assert "bead-chain" in msg.lower()
    # No raw exception noise — it's a sentence, not a traceback fragment.
    assert "Traceback" not in msg
    assert "ModuleNotFoundError" not in msg


def test_command_degrades_gracefully_when_wiggum_missing(monkeypatch):
    """With wiggum absent, /bead-chain warns and returns True without crashing.

    Crucially it must bail BEFORE any ``bd`` probe or ``wiggum_state``
    dereference — so we make those explode and confirm they're never hit.
    """
    warnings: list[str] = []
    monkeypatch.setattr(register_callbacks, "_WIGGUM_AVAILABLE", False)
    monkeypatch.setattr(
        register_callbacks, "emit_warning", lambda m: warnings.append(m)
    )

    def _boom(*_a, **_k):  # pragma: no cover - asserts it's never called
        raise AssertionError("must not reach bd probe when wiggum is missing")

    monkeypatch.setattr(register_callbacks, "enforce_single_in_progress", _boom)
    monkeypatch.setattr(register_callbacks, "next_ready", _boom)

    result = register_callbacks.handle_bead_chain_command("/bead-chain")

    assert result is True, "degraded command consumes the slash command"
    assert warnings == [register_callbacks._WIGGUM_MISSING_MESSAGE]
    assert not state.is_active(), "no chain should have started"


def test_gate_is_transparent_when_wiggum_available(monkeypatch):
    """With wiggum present, the prerequisite gate doesn't short-circuit.

    We force the gate open then stop at the very next step (an empty queue),
    proving control flowed past the wiggum check exactly as it did before
    this fix — i.e. zero behavioural change on the happy path.
    """
    monkeypatch.setattr(register_callbacks, "_WIGGUM_AVAILABLE", True)
    infos: list[str] = []
    monkeypatch.setattr(register_callbacks, "emit_info", lambda m: infos.append(m))
    monkeypatch.setattr(register_callbacks, "emit_warning", lambda m: None)
    monkeypatch.setattr(register_callbacks, "enforce_single_in_progress", lambda: None)
    monkeypatch.setattr(register_callbacks, "next_ready", lambda: None)

    result = register_callbacks.handle_bead_chain_command("/bead-chain")

    assert result is True
    # The empty-queue message proves we sailed past the wiggum gate and the
    # "starting…" ack into the real probe path.
    assert any("No ready beads" in m for m in infos)
