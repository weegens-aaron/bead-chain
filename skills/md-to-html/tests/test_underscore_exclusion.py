"""Regression tests for bead_chain-7rq.

Underscore-prefixed authoring/working files (e.g. ``_Manifest.md``,
``_DiataxisGuide.md``, ``_UpdateQueue.md``, ``_AuditLog.md``) must be skipped
by page discovery (both multi- and single-page builders) and by the linter so
they never leak into the published HTML site. Previously only the exact name
``_Manifest`` was excluded.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_multi_page  # noqa: E402
import build_single_page  # noqa: E402
import md_lint  # noqa: E402

UNDERSCORE_FILES = [
    "_Manifest.md",
    "_DiataxisGuide.md",
    "_UpdateQueue.md",
    "_AuditLog.md",
]


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    """A docs tree with one real page plus several underscore working files."""
    (tmp_path / "index.md").write_text("# Real Page\n\nhello\n", encoding="utf-8")
    for name in UNDERSCORE_FILES:
        (tmp_path / name).write_text(f"# {name}\n\nworking notes\n", encoding="utf-8")
    return tmp_path


def test_multi_page_discover_skips_underscore_files(docs_dir: Path):
    pages = build_multi_page.discover_pages(docs_dir)
    names = {p["name"] for p in pages}
    assert names == {"index"}
    assert not any(p["name"].startswith("_") for p in pages)


def test_single_page_discover_skips_underscore_files(docs_dir: Path):
    pages = build_single_page.discover_pages(docs_dir)
    names = {p["name"] for p in pages}
    assert names == {"index"}
    assert not any(p["name"].startswith("_") for p in pages)


def test_lint_directory_skips_underscore_files(docs_dir: Path):
    # Give every underscore file a guaranteed lint error; a real page stays clean.
    for name in UNDERSCORE_FILES:
        (docs_dir / name).write_text("##NoSpaceHeading\n", encoding="utf-8")
    results = md_lint.lint_directory(docs_dir)
    # No underscore file should appear in the results, so there are no errors.
    assert all(not Path(rel).name.startswith("_") for rel in results)
    assert results == {}


def test_multi_page_build_omits_underscore_html(docs_dir: Path, tmp_path: Path):
    out = tmp_path / "out"
    build_multi_page.build_site(docs_dir, out, "Test Site")
    html_files = {p.name for p in out.rglob("*.html")}
    assert html_files == {"index.html"}
    assert not any(name.startswith("_") for name in html_files)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
