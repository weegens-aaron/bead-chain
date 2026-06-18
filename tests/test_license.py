"""Tests for the MIT LICENSE file and its inclusion in the release zip.

This locks the acceptance criteria of ``bead_chain-aij``:

  1. A LICENSE file (MIT) exists at the repo root.
  2. The build script (``scripts/build-release.sh``) ships it in the release
     archive — i.e. ``LICENSE`` is named in the build allowlist.

Pure-stdlib, so they run standalone:
``python3 -m pytest tests/`` or ``python3 tests/test_license.py``.
"""

from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Runtime files (incl. LICENSE) live in the bd/ subdirectory; scripts/ stays
# at the repo root.
_BD = os.path.join(_ROOT, "bd")
_LICENSE = os.path.join(_BD, "LICENSE")
_BUILD_SCRIPT = os.path.join(_ROOT, "scripts", "build-release.sh")


def test_license_file_exists_in_bd_dir():
    """A LICENSE file lives in the bd/ plugin directory."""
    assert os.path.isfile(_LICENSE), "LICENSE missing from bd/"


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


def test_build_script_ships_license():
    """The build allowlist names LICENSE so it lands in the release zip."""
    with open(_BUILD_SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    # The allowlist entries are quoted bare filenames; LICENSE must be one.
    assert '"LICENSE"' in script, "LICENSE not in build-release.sh allowlist"


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
