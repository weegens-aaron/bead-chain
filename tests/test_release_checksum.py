"""Tests for SHA256 checksum generation in the release build (bead_chain-ixc).

Locks the acceptance criteria:

  1. ``scripts/build-release.sh`` writes a SHA256 checksum file alongside the
     zip (``dist/bead-chain.zip.sha256``).
  2. The published checksum references the *bare* zip filename so that
     ``shasum -a 256 -c`` / ``sha256sum -c`` verify cleanly when the user has
     the zip and the ``.sha256`` side by side.

A fast static check always runs; a full integration run (actually invoking the
build) runs only when ``bash`` + a zip tool + a SHA256 tool are available, and
is skipped gracefully otherwise so the suite stays portable.

Pure-stdlib, so it runs standalone:
``python3 -m pytest tests/`` or ``python3 tests/test_release_checksum.py``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUILD_SCRIPT = os.path.join(_ROOT, "scripts", "build-release.sh")


def test_build_script_writes_checksum():
    """The build script emits a .sha256 next to the zip."""
    with open(_BUILD_SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    # The checksum helper writes "<file>.sha256"; the step calls it for the zip.
    assert ".sha256" in script, "build-release.sh never writes a .sha256 file"
    assert "sha256_in_dist" in script, "no sha256 helper invoked in build script"


def test_build_script_handles_both_sha_tools():
    """Cross-platform: the script tries both sha256sum and shasum."""
    with open(_BUILD_SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    assert "sha256sum" in script, "build script missing sha256sum (Linux) path"
    assert "shasum" in script, "build script missing shasum (macOS) path"


def _tools_available() -> bool:
    return all(shutil.which(t) for t in ("bash", "zip", "unzip")) and (
        shutil.which("shasum") or shutil.which("sha256sum")
    )


def test_build_produces_verifiable_checksum():
    """Integration: run the build, confirm the .sha256 matches the zip.

    Skipped when the required CLI tools aren't on PATH.
    """
    if not _tools_available():
        print("SKIP test_build_produces_verifiable_checksum (missing CLI tools)")
        return

    result = subprocess.run(
        ["bash", _BUILD_SCRIPT],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"build failed:\n{result.stderr}"

    dist = os.path.join(_ROOT, "dist")
    zip_path = os.path.join(dist, "bead-chain.zip")
    sha_path = os.path.join(dist, "bead-chain.zip.sha256")
    assert os.path.isfile(zip_path), "stable zip missing after build"
    assert os.path.isfile(sha_path), "stable zip .sha256 missing after build"

    with open(sha_path, encoding="utf-8") as fh:
        recorded = fh.read().strip()
    # Format is "<hex>  <bare-filename>"; the filename must be bare (no path)
    # so -c verification works from inside dist/.
    digest, _, name = recorded.partition(" ")
    assert name.strip() == "bead-chain.zip", (
        f"checksum names a path, not bare file: {name!r}"
    )

    actual = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
    assert actual == digest, "recorded SHA256 does not match the built zip"


if __name__ == "__main__":
    sys.path.insert(0, _ROOT)
    failures = 0
    for fn_name, fn in sorted(globals().items()):
        if fn_name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {fn_name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {fn_name}: {exc}")
    sys.exit(1 if failures else 0)
