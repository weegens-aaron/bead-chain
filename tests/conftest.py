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

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = "code_puppy.plugins.bead_chain"


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
