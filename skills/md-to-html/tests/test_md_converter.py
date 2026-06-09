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
    slugify,
    _normalize_fragment,
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


# -- Slugify and fragment normalization (bead_chain-2gm) ---------------------
# The heading-id slugifier and link-href slugifier must agree.  Two historical
# failure modes: (a) em-dash in heading becomes double-dash in href but
# single-dash in id; (b) HTML-entity emoji kept hex codes in id but stripped
# in href.


class TestSlugify:
    """Unit tests for the shared slugify() function."""

    def test_plain_heading(self):
        assert slugify("Hello World") == "hello-world"

    def test_em_dash_collapses(self):
        """An em-dash surrounded by spaces becomes a single dash."""
        assert slugify("Tier 0 \u2014 Recovery") == "tier-0-recovery"

    def test_html_entity_emoji_stripped(self):
        """HTML-entity emoji is decoded then stripped, leaving no hex leak."""
        assert (
            slugify("Chain Lifecycle Messages (&#x1F517;)")
            == "chain-lifecycle-messages"
        )

    def test_multiple_html_entity_emoji(self):
        assert (
            slugify("Recovery Messages (&#x1F516; / &#x26A0;&#xFE0F;)")
            == "recovery-messages"
        )

    def test_trailing_special_chars_stripped(self):
        assert slugify("Hello World!") == "hello-world"

    def test_already_slug(self):
        """Running a well-formed slug through slugify is idempotent."""
        assert slugify("tier-0-recovery") == "tier-0-recovery"


class TestNormalizeFragment:
    def test_hash_prefix_preserved(self):
        assert _normalize_fragment("#foo-bar") == "#foo-bar"

    def test_bare_slug_gets_hash(self):
        assert _normalize_fragment("foo-bar") == "#foo-bar"

    def test_double_dash_collapsed(self):
        assert _normalize_fragment("#tier-0--recovery") == "#tier-0-recovery"

    def test_trailing_dash_stripped(self):
        assert (
            _normalize_fragment("#chain-lifecycle-messages-")
            == "#chain-lifecycle-messages"
        )

    def test_empty_returns_empty(self):
        assert _normalize_fragment("") == ""
        assert _normalize_fragment("#") == ""


class TestHeadingFragmentConsistency:
    """End-to-end: heading id= must match normalised in-page #href."""

    def test_em_dash_heading_matches_fragment(self):
        md = (
            "| [Recovery](#tier-0--recovery) |\n"
            "|---|\n"
            "| x |\n"
            "\n"
            "## Tier 0 \u2014 Recovery\n"
            "\n"
            "Content here.\n"
        )
        body = _convert(md, known_pages=set())
        # The heading id and the link href must agree
        assert 'id="tier-0-recovery"' in body
        assert 'href="#tier-0-recovery"' in body

    def test_emoji_entity_heading_matches_fragment(self):
        md = (
            "| [Chain Lifecycle](#chain-lifecycle-messages-) |\n"
            "|---|\n"
            "| x |\n"
            "\n"
            "## Chain Lifecycle Messages (&#x1F517;)\n"
            "\n"
            "Content here.\n"
        )
        body = _convert(md, known_pages=set())
        assert 'id="chain-lifecycle-messages"' in body
        assert 'href="#chain-lifecycle-messages"' in body

    def test_cross_page_fragment_also_normalised(self):
        """Fragments appended to page links are normalised too."""
        md = "See [config](Configuration.md#excluded--container-types) here.\n"
        body = _convert(
            md,
            known_pages={"Reference/Configuration.html"},
            page_dir="Reference",
            page_html_rel="Reference/Other.html",
        )
        assert "#excluded-container-types" in body


# ── Bold adjacent to code spans (bead_chain-94u) ────────────────────────────
# When ** delimiters wrap inline <code>, the bold regex used to fail because
# the tokenizer split the text at code-span boundaries, leaving the **
# in separate fragments that couldn't match the bold pattern.


class TestBoldAdjacentToCode:
    """Regression tests for bold markdown (**) adjacent to <code> tags."""

    def test_bold_wrapping_code_span(self):
        md = "**`some_thing`**\n"
        body = _convert(md, known_pages=set())
        assert "<strong><code>some_thing</code></strong>" in body
        assert "**" not in body

    def test_bold_with_embedded_code_span(self):
        md = "**text with `inline` code**\n"
        body = _convert(md, known_pages=set())
        assert "<strong>text with <code>inline</code> code</strong>" in body
        assert "**" not in body

    def test_multiple_bold_code_combos(self):
        md = "**`code1`** and **`code2`**\n"
        body = _convert(md, known_pages=set())
        assert "<strong><code>code1</code></strong>" in body
        assert "<strong><code>code2</code></strong>" in body
        assert "**" not in body

    def test_bold_code_in_heading(self):
        md = "## Using **`my_func`** in code\n"
        body = _convert(md, known_pages=set())
        assert "<strong><code>my_func</code></strong>" in body
        assert "**" not in body

    def test_bold_code_in_list(self):
        md = "- Set **`enabled`** to true\n"
        body = _convert(md, known_pages=set())
        assert "<strong><code>enabled</code></strong>" in body
        assert "**" not in body

    def test_bold_code_in_table(self):
        md = "| **`key`** | value |\n|---|---|\n| a | b |\n"
        body = _convert(md, known_pages=set())
        assert "<strong><code>key</code></strong>" in body
        assert "**" not in body

    def test_italic_wrapping_code_span(self):
        md = "*`some_func`*\n"
        body = _convert(md, known_pages=set())
        assert "<em><code>some_func</code></em>" in body

    def test_bold_italic_wrapping_code_span(self):
        md = "***`critical`***\n"
        body = _convert(md, known_pages=set())
        assert "<strong><em><code>critical</code></em></strong>" in body

    def test_plain_bold_still_works(self):
        """Sanity: plain bold without code spans is unaffected."""
        md = "**bold text**\n"
        body = _convert(md, known_pages=set())
        assert "<strong>bold text</strong>" in body

    def test_bold_code_in_blockquote(self):
        md = "> Use **`flag`** to enable\n"
        body = _convert(md, known_pages=set())
        assert "<strong><code>flag</code></strong>" in body
        assert "**" not in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
