"""Tests for the single-source-of-truth plugin version (bead_chain-u2o).

``__init__.py`` is the *only* place the version is defined; the build script,
the git release tag, and runtime introspection all derive from it. These tests
lock that contract two ways:

  1. Runtime introspection: ``bead_chain.__version__`` (here imported directly
     as the top-level package ``__init__``) exposes a PEP 440-ish string.
  2. Greppability: the literal is readable by a non-Python build script via a
     simple ``grep`` over the file — the format is part of the contract.

Pure-stdlib, so they run standalone:
``python3 -m pytest tests/`` or ``python3 tests/test_version.py``.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The single-source __init__.py now lives in the bd/ plugin subdirectory.
_BD = os.path.join(_ROOT, "bd")


def _load_init():
    """Import the package ``__init__.py`` in isolation.

    We load by file path rather than ``import bead_chain`` because the test
    suite runs with the repo root on ``sys.path`` (so sibling modules import
    bare), not the *parent* of the package — there is no ``bead_chain`` package
    name on the path in that layout.
    """
    spec = importlib.util.spec_from_file_location(
        "bead_chain_init", os.path.join(_BD, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


# Strict MAJOR.MINOR.PATCH core with an optional PEP 440 / SemVer suffix
# (e.g. ``1.2.3``, ``1.2.3rc1``, ``1.2.3.post1``, ``1.2.3+local``). We assert
# the *shape* rather than a specific literal so a routine version bump never
# re-reds this test (bead_chain-dl3: the old hardcoded ``== "0.1.0"`` drifted
# from source and blocked the suite — see test_release_checksum.py for the
# same source-derived, never-hardcoded pattern).
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-.+]?[0-9A-Za-z][0-9A-Za-z.\-+]*)?$")


def test_version_is_defined_and_well_formed():
    """__version__ is defined and is a strict MAJOR.MINOR.PATCH version.

    Deliberately does NOT hardcode the value: a version bump must not have to
    touch this test. The runtime-vs-source consistency of the *literal* is
    locked separately by ``test_version_is_greppable_from_source``.
    """
    init = _load_init()
    assert hasattr(init, "__version__"), "__version__ missing from __init__.py"
    assert _VERSION_RE.match(init.__version__), init.__version__


def test_version_is_a_plain_string():
    """Runtime introspection gets a non-empty str (not a tuple/bytes)."""
    init = _load_init()
    assert isinstance(init.__version__, str)
    assert init.__version__.strip() == init.__version__
    assert init.__version__


def test_version_is_greppable_from_source():
    """A non-Python build script can extract the version with a simple grep.

    Mirrors the documented one-liner:
        grep -oE '__version__ = "[^"]+"' __init__.py | cut -d'"' -f2
    """
    init = _load_init()
    with open(os.path.join(_BD, "__init__.py"), encoding="utf-8") as fh:
        source = fh.read()
    matches = re.findall(r'__version__ = "([^"]+)"', source)
    assert matches == [init.__version__], matches


if __name__ == "__main__":
    sys.path.insert(0, _BD)
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
