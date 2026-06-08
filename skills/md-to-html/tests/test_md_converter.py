"""Tests for the zero-dependency markdown converter.

Focus: the multi-line-link-in-a-list regression (bead_chain-t2o), where a
markdown link whose [text] wraps across source lines leaked into the HTML as
literal ``[text](path.md)`` instead of an anchor.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from md_converter import (  # noqa: E402
    MarkdownConverter,
    find_unconverted_links,
)


def _convert(md: str, **kwargs) -> str:
    converter = MarkdownConverter(
        known_pages=kwargs.get("known_pages"),
        anchor_map=kwargs.get("anchor_map"),
    )
    body, _ = converter.convert(
        md,
        page_dir=kwargs.get("page_dir", ""),
        page_html_rel=kwargs.get("page_html_rel", ""),
    )
    return body


# ── The core regression ──────────────────────────────────────────────────────


def test_multiline_link_in_list_unindented_continuation():
    """Link text wrapping onto an *unindented* line still resolves."""
    md = (
        "- [Why bead-chain is a queue driver, not a goal\n"
        "engine](../explanation/queue-driver-not-goal-engine.md) — context\n"
    )
    body = _convert(
        md,
        known_pages={"maintainer/explanation/queue-driver-not-goal-engine.html"},
        page_dir="maintainer/how-to",
        page_html_rel="maintainer/how-to/add-excluded-bead-type.html",
    )
    assert "queue-driver-not-goal-engine.html" in body
    assert ">Why bead-chain is a queue driver, not a goal engine</a>" in body
    assert "[Why bead-chain" not in body  # no leaked raw syntax
    assert not find_unconverted_links(body)


def test_multiline_link_in_list_indented_continuation():
    """Link text wrapping onto an *indented* line also resolves."""
    md = (
        "- [Why bead-chain is a queue driver, not a goal\n"
        "  engine](../explanation/queue-driver-not-goal-engine.md)\n"
    )
    body = _convert(
        md,
        known_pages={"maintainer/explanation/queue-driver-not-goal-engine.html"},
        page_dir="maintainer/how-to",
        page_html_rel="maintainer/how-to/x.html",
    )
    assert ">Why bead-chain is a queue driver, not a goal engine</a>" in body
    assert not find_unconverted_links(body)


def test_single_line_link_in_list_still_works():
    md = "- A normal [link](other.md) in a list.\n"
    body = _convert(md, known_pages={"other.html"})
    assert '<a href="other.html">link</a>' in body


# ── Dangling-href guard (bead_chain-w8w) ─────────────────────────────────────
# When a .md link points at a target that is NOT a published page, the
# rewriter must NOT fabricate a .html href (which would 404). It keeps the
# visible label but drops the broken link.


def test_link_to_underscore_working_file_is_unlinked():
    """Class 1: links to underscore-prefixed files discover_pages() skips.

    e.g. every Related footer links back to ``_Manifest.md`` which is never
    a published page.
    """
    md = "See the [Manifest](../_Manifest.md) for the full list.\n"
    body = _convert(
        md,
        known_pages={"Architecture.html", "index.html"},
        page_dir="Concepts",
        page_html_rel="Concepts/Foo.html",
    )
    # Label preserved, but no anchor and no fabricated .html href.
    assert "Manifest" in body
    assert "_Manifest.html" not in body
    assert "<a " not in body
    assert not find_unconverted_links(body)


def test_link_to_out_of_site_file_is_unlinked():
    """Class 2: links to files OUTSIDE the doc set (README, AGENTS, ADRs)."""
    md = (
        "Read the [README](../README.md), the [agent guide](../AGENTS.md), "
        "and [ADR 0001](../../notes/decisions/0001-dolt.md).\n"
    )
    body = _convert(
        md,
        known_pages={"index.html", "Architecture.html"},
        page_dir="",
        page_html_rel="index.html",
    )
    assert "README" in body and "agent guide" in body and "ADR 0001" in body
    assert ".html" not in body  # no fabricated hrefs leaked
    assert "<a " not in body
    assert not find_unconverted_links(body)


def test_published_target_still_links_when_others_are_unlinked():
    """A real page link and a dangling link in the same prose: only the real
    one becomes an anchor; the dangling one degrades to plain text."""
    md = "[Real](Architecture.md) and [Missing](../_Manifest.md).\n"
    body = _convert(
        md,
        known_pages={"Architecture.html"},
        page_dir="",
        page_html_rel="index.html",
    )
    assert '<a href="Architecture.html">Real</a>' in body
    assert "Missing" in body
    assert "_Manifest" not in body
    assert not find_unconverted_links(body)


def test_no_known_pages_preserves_legacy_resolution():
    """When known_pages is None (standalone conversion), keep best-effort
    .html resolution rather than un-linking everything."""
    md = "A [link](other.md) here.\n"
    body = _convert(md, known_pages=None)
    assert '<a href="other.html">link</a>' in body


def test_trailing_paragraph_not_swallowed_into_list():
    """A blank-line-separated paragraph after a list stays its own block."""
    md = "- one\n- two\n\nTrailing paragraph.\n"
    body = _convert(md, known_pages=set())
    assert "<li>one</li>" in body
    assert "<li>two</li>" in body
    assert "<p>Trailing paragraph.</p>" in body
    # The paragraph must not be glued onto the last <li>.
    assert "<li>two</li>" in body and "two Trailing" not in body


# ── Callouts ─────────────────────────────────────────────────────────────────


def test_callout_renders_without_crashing():
    """Regression: dead code after a ``break`` left ``body`` undefined,
    crashing with UnboundLocalError on any document containing a callout.
    """
    md = "> [!WARNING]\n> This is a warning callout.\n"
    body = _convert(md, known_pages=set())
    assert 'class="callout callout-warning"' in body
    assert "WARNING" in body
    assert "This is a warning callout." in body


def test_callout_with_inline_first_line():
    md = "> [!NOTE] Heads up, this matters.\n"
    body = _convert(md, known_pages=set())
    assert 'class="callout callout-note"' in body
    assert "Heads up, this matters." in body


def test_callout_multiline_body_joins():
    md = "> [!TIP]\n> First line.\n> Second line.\n"
    body = _convert(md, known_pages=set())
    assert 'class="callout callout-tip"' in body
    assert "First line. Second line." in body


# ── Post-build guard ─────────────────────────────────────────────────────────


def test_find_unconverted_links_flags_leaked_md_link():
    html = "<p>See [the docs](../guide/intro.md) for details.</p>"
    found = find_unconverted_links(html)
    assert len(found) == 1
    assert "intro.md" in found[0]


def test_find_unconverted_links_ignores_code_blocks():
    """Markdown link syntax shown inside code samples must not trip the guard."""
    html = (
        "<pre><code>[text](path.md)</code></pre>\n"
        "<p>Use <code>[label](file.md)</code> like this.</p>"
    )
    assert find_unconverted_links(html) == []


def test_find_unconverted_links_clean_html():
    html = '<p>All good <a href="x.html">here</a>.</p>'
    assert find_unconverted_links(html) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
