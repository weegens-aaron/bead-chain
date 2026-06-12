"""State for the bead-chain plugin.

Mirrors wiggum's tiny-singleton pattern. Behavior lives in
``register_callbacks.py`` — this module is a dumb data box.

Thread-safety (known limitation)
--------------------------------
The singleton is **not** thread-safe: ``_STATE`` is a bare module-level
instance with no lock around its mutators. This is deliberate and safe in
practice — bead-chain's three coordinating hooks (command / turn-end /
turn-cancel) all fire on code_puppy's single interactive event loop, never
concurrently, so there is no contended writer. If bead-chain ever grows a
background/worker thread that mutates state, this box must gain a lock (or
move to per-run dependency injection). Until then, a lock would be pure
YAGNI ceremony.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "BeadChainState",
    "get_state",
    "is_active",
    "reset",
    "start",
    "stop",
]


@dataclass
class BeadChainState:
    """Whether the chain is engaged, and what bead it's currently chewing on.

    We hold the **full bead dict**, not just its id, so callers can peek
    at fields like the parent epic without having to round-trip through
    ``bd show``. Code that only needs the id can use the
    :pyattr:`current_bead_id` convenience property.
    """

    active: bool = False
    current_bead: dict[str, Any] | None = None
    completed_count: int = 0
    # Optional safety brake: stop the chain after this many beads have
    # been completed in the current run. None = no cap (run forever).
    # Set by /bead-chain --max=N; reset to None on stop().
    max_iterations: int | None = None

    @property
    def current_bead_id(self) -> str | None:
        """Convenience accessor for ``current_bead['id']`` (or ``None``).

        Pure read-only — to set the active bead, assign to
        :pyattr:`current_bead` directly with the bd-ready dict. This keeps
        the rename surgical: callers that only need the id stay unchanged.
        """
        if self.current_bead is None:
            return None
        bead_id = self.current_bead.get("id")
        return str(bead_id) if bead_id is not None else None

    def start(self) -> None:
        self.active = True
        self.current_bead = None
        # completed_count is reset on every fresh start() so each
        # /bead-chain run reports its own tally.
        self.completed_count = 0

    def stop(self) -> None:
        self.active = False
        self.current_bead = None
        # Always clear the cap so the next run starts at "no cap"
        # unless explicitly re-armed via --max=N.
        self.max_iterations = None

    def bump_completed(self) -> int:
        self.completed_count += 1
        return self.completed_count

    def reset(self) -> None:
        """Return this box to its just-constructed state (factory reset).

        This exists primarily for **test isolation**: because the module
        owns a single process-wide ``_STATE``, mutations leak between
        tests unless something puts it back to defaults. A teardown
        fixture calling ``get_state().reset()`` guarantees the next test
        starts pristine.

        Unlike :meth:`stop` (which disengages the chain but deliberately
        *preserves* ``completed_count`` so the end-of-run rollup can read
        the final tally), ``reset`` also zeroes the tally — it is a full
        factory reset, not a chain disengage. Keep the two distinct.
        """
        self.active = False
        self.current_bead = None
        self.completed_count = 0
        self.max_iterations = None


_STATE = BeadChainState()


def get_state() -> BeadChainState:
    return _STATE


def is_active() -> bool:
    return _STATE.active


def start() -> None:
    _STATE.start()


def stop() -> None:
    _STATE.stop()


def reset() -> None:
    """Factory-reset the singleton. Thin shortcut for test teardown."""
    _STATE.reset()
