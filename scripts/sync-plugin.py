#!/usr/bin/env python3
"""sync-plugin.py — sync dev bead-chain code into a local plugin dir.

The shippable file set is read from ``scripts/ship-manifest.txt`` — the
SAME single source of truth the release build (``build-release.sh``) uses,
so the plugin install can never drift from what actually ships.

Default destination is the code_puppy plugin dir::

    ~/.code_puppy/plugins/bead-chain

Usage::

    python scripts/sync-plugin.py                 # sync to the default dir
    python scripts/sync-plugin.py --dry-run        # show what WOULD change
    python scripts/sync-plugin.py --dest <path>    # sync somewhere else
    python scripts/sync-plugin.py --prune          # also delete dest files
                                                   #   not in the manifest

Idempotent: files already byte-for-byte identical are skipped. Exit code
is 0 on success (or a clean dry-run), non-zero if a manifest path is
missing from the repo or post-sync verification fails.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

# This file lives in <repo>/scripts/, so the repo root is its parent's parent.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
MANIFEST_FILE = SCRIPT_DIR / "ship-manifest.txt"
DEFAULT_DEST = Path.home() / ".code_puppy" / "plugins" / "bead-chain"


def read_manifest(manifest: Path) -> list[str]:
    """Return the ordered list of repo-relative ship paths.

    Mirrors the bash parser in build-release.sh: blank lines are ignored
    and everything from a ``#`` to end-of-line is a comment.
    """
    if not manifest.is_file():
        raise FileNotFoundError(f"ship manifest not found: {manifest}")
    paths: list[str] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            paths.append(line)
    if not paths:
        raise ValueError(f"ship manifest is empty after parsing: {manifest}")
    return paths


def plan_sync(
    paths: list[str], src_root: Path, dst_root: Path
) -> list[tuple[str, str]]:
    """Classify each manifest path as new / changed / unchanged.

    Returns a list of (status, relpath). Raises if a manifest path is
    missing from the repo — fail-closed, exactly like the release build.
    """
    plan: list[tuple[str, str]] = []
    for rel in paths:
        src = src_root / rel
        if not src.is_file():
            raise FileNotFoundError(f"manifest path is missing from the repo: {rel}")
        dst = dst_root / rel
        if not dst.exists():
            plan.append(("new", rel))
        elif filecmp.cmp(src, dst, shallow=False):
            plan.append(("unchanged", rel))
        else:
            plan.append(("changed", rel))
    return plan


def find_strays(paths: list[str], dst_root: Path) -> list[str]:
    """Return files under dst_root NOT named in the manifest (--prune fodder)."""
    if not dst_root.is_dir():
        return []
    wanted = {(dst_root / rel).resolve() for rel in paths}
    return sorted(
        str(p.relative_to(dst_root))
        for p in dst_root.rglob("*")
        if p.is_file() and p.resolve() not in wanted
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help=f"destination plugin dir (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change without writing anything",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete files in --dest that are not in the manifest",
    )
    args = parser.parse_args(argv)

    dst_root: Path = args.dest.expanduser()

    try:
        paths = read_manifest(MANIFEST_FILE)
        plan = plan_sync(paths, REPO_ROOT, dst_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    verb = "Would sync" if args.dry_run else "Syncing"
    print(f"==> {verb} {len(paths)} file(s)")
    print(f"    from: {REPO_ROOT}")
    print(f"    to:   {dst_root}")

    to_write = [rel for status, rel in plan if status in ("new", "changed")]
    for status, rel in plan:
        mark = {"new": "+", "changed": "~", "unchanged": "="}[status]
        print(f"    {mark} {rel}  ({status})")

    strays = find_strays(paths, dst_root) if args.prune else []
    for rel in strays:
        print(f"    - {rel}  (stray -> prune)")

    if args.dry_run:
        print(f"==> Dry run: {len(to_write)} would change, {len(strays)} would prune")
        return 0

    dst_root.mkdir(parents=True, exist_ok=True)
    for rel in to_write:
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, dst)
    for rel in strays:
        (dst_root / rel).unlink()

    # Verify: every manifest file must now be byte-for-byte identical.
    mismatches = [
        rel
        for rel in paths
        if not filecmp.cmp(REPO_ROOT / rel, dst_root / rel, shallow=False)
    ]
    if mismatches:
        print(
            f"ERROR: post-sync verification failed for: {mismatches}", file=sys.stderr
        )
        return 1

    print(
        f"==> Done. {len(to_write)} written, "
        f"{len(paths) - len(to_write)} already in sync, "
        f"{len(strays)} pruned. All {len(paths)} files verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
