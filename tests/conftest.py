"""Pytest fixtures for bead_chain tests.

The bead_chain plugin lives in ``~/.code_puppy/plugins/bead_chain`` and
uses relative imports (``from . import state``) plus
``from code_puppy.plugins.wiggum import ...``. At runtime code_puppy's
plugin loader registers it as a package; under bare pytest we have to do
that ourselves so the lifecycle/register modules import cleanly.

``beads.py`` is pure-stdlib and is still importable flat (the older
tests do ``import beads``), so this conftest is additive, not a
breaking change to those.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bd"
)
_PKG = "code_puppy.plugins.bead_chain"

# Make the flat ``beads`` module importable from any test (and from the
# autouse guard below) without each module re-inserting sys.path.
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)


def _register_package() -> None:
    """Make ``code_puppy.plugins.bead_chain`` importable as a real package."""
    if _PKG in sys.modules:
        return
    # Importing the parent guarantees code_puppy.plugins exists (it ships
    # in the venv alongside wiggum). If code_puppy isn't installed we just
    # let the ImportError surface — the lifecycle tests genuinely need it.
    import code_puppy.plugins  # noqa: F401

    spec = importlib.util.spec_from_file_location(
        _PKG,
        os.path.join(_PLUGIN_DIR, "__init__.py"),
        submodule_search_locations=[_PLUGIN_DIR],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PKG] = module
    spec.loader.exec_module(module)


_register_package()


@pytest.fixture(autouse=True)
def _restore_beads_module_globals():
    """Snapshot and restore the monkeypatchable ``beads`` module globals.

    Many test modules stub ``beads._run_bd`` / ``beads._parse_json_list`` /
    ``beads.show`` by direct attribute assignment (``beads.show = lambda
    ...``) and never restore the original. Without this guard a leftover stub
    from an alphabetically-earlier module leaks into later tests that call the
    real implementation — a test that passes in isolation then fails in the
    full suite (see bead_chain-221).

    Snapshotting before each test and restoring afterwards keeps that
    global module state per-test isolated, and protects future test
    modules automatically without hand-patching every stub helper.

    ``show`` is part of the snapshot set because of the bead_chain-7xv split:
    ``is_pinned`` / ``open_blocker_ids`` now live in ``beads_reads`` and
    resolve ``show`` through the live ``beads`` facade at call time, so the
    pinned-strand tests still stub ``beads.show`` — and that stub must be
    rolled back here. (Previously a stray ``importlib.reload(beads)`` in an
    e2e test happened to recreate the real ``show`` and masked the leak; the
    split made that reload unsafe, so the guard owns the cleanup outright.)
    """
    import beads

    saved_run_bd = beads._run_bd
    saved_parse_json_list = beads._parse_json_list
    saved_show = beads.show
    try:
        yield
    finally:
        beads._run_bd = saved_run_bd
        beads._parse_json_list = saved_parse_json_list
        beads.show = saved_show
