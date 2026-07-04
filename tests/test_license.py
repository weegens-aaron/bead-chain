"""Tests for the MIT LICENSE file and its inclusion in the release zip.

This locks the acceptance criteria of ``bead_chain-aij``:

  1. A LICENSE file (MIT) exists at the repo root.
  2. The release ships it — i.e. ``LICENSE`` is named in the shared ship
     manifest (``scripts/ship-manifest.txt``), the ONE source of truth read
     by both ``build-release.sh`` and ``sync-plugin.py`` (ADR 0002).

Pure-stdlib, so they run standalone:
``python3 -m pytest tests/`` or ``python3 tests/test_license.py``.
"""

from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LICENSE = os.path.join(_ROOT, "LICENSE")
_SHIP_MANIFEST = os.path.join(_ROOT, "scripts", "ship-manifest.txt")


def test_license_file_exists_at_repo_root():
    """A LICENSE file lives at the repo root."""
    assert os.path.isfile(_LICENSE), "LICENSE missing from repo root"


def test_license_is_mit():
    """The LICENSE text is the MIT license (header + signature clause)."""
    with open(_LICENSE, encoding="utf-8") as fh:
        text = fh.read()
    assert "MIT License" in text, "LICENSE does not declare 'MIT License'"
    # The MIT permission grant and the all-caps warranty disclaimer are the
    # two fingerprints that distinguish MIT from other permissive licenses.
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text
    assert re.search(r"Copyright \(c\) \d{4}", text), "missing copyright line"


def test_ship_manifest_ships_license():
    """The ship manifest names LICENSE so it lands in the release zip."""
    with open(_SHIP_MANIFEST, encoding="utf-8") as fh:
        entries = [
            line.split("#", 1)[0].strip()
            for line in fh
        ]
    assert "LICENSE" in entries, "LICENSE not in scripts/ship-manifest.txt"


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
