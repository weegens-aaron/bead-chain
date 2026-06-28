"""Tests for the single-source-of-truth plugin version (bead_chain-u2o).

``__init__.py`` is the *only* place the version is defined; the build script,
the git release tag, and runtime introspection all derive from it. These tests
lock that contract two ways:

  1. Runtime introspection: ``bead_chain.__version__`` (here imported directly
     as the top-level package ``__init__``) exposes a PEP 440-ish string. We
     assert its *shape*, never a hardcoded literal — a duplicated literal is a
     second source of truth that drifts (bead_chain-wn7).
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


def _load_init():
    """Import the package ``__init__.py`` in isolation.

    We load by file path rather than ``import bead_chain`` because the test
    suite runs with the repo root on ``sys.path`` (so sibling modules import
    bare), not the *parent* of the package — there is no ``bead_chain`` package
    name on the path in that layout.
    """
    spec = importlib.util.spec_from_file_location(
        "bead_chain_init", os.path.join(_ROOT, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


# PEP 440-ish: a dotted release segment (e.g. "0.2.1") optionally followed by
# pre/post/dev or local-version suffixes. We intentionally do NOT hardcode the
# concrete value here: __init__.py is the single source of truth, and a second
# literal in the test is just a duplicate that drifts (it did — see
# bead_chain-wn7). We lock the *contract* (defined + well-formed), not a copy.
_VERSION_RE = re.compile(
    r"^\d+(?:\.\d+)*(?:[._-]?(?:a|b|rc|alpha|beta|post|dev)\d*)*(?:\+[a-zA-Z0-9.]+)?$"
)


def test_version_is_defined_and_well_formed():
    """The single source of truth defines a PEP 440-ish ``__version__``.

    We assert the *shape* of the version rather than a hardcoded literal so the
    test never drifts from ``__init__.py`` on a release bump.
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
    with open(os.path.join(_ROOT, "__init__.py"), encoding="utf-8") as fh:
        source = fh.read()
    matches = re.findall(r'__version__ = "([^"]+)"', source)
    assert matches == [init.__version__], matches


if __name__ == "__main__":
    sys.path.insert(0, _ROOT)
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
