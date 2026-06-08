#!/usr/bin/env python3
"""Build a Puppy Pages-compatible single HTML file from markdown.

Usage:
    python build_puppy_page.py <input> <output_file> [--title "Title"]

Input can be a single .md file or a directory of .md files.
Output is a single self-contained HTML file ready for share-puppy deployment.
All modes include sidebar navigation (heading-based for single files,
section-based for directories) with scroll-spy and jump-to-top.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_converter import MarkdownConverter, _escape  # noqa: E402
from build_single_page import (  # noqa: E402
    discover_pages,
    build_anchor_map,
    build_sidenav,
    load_css,
    LAYOUT_CSS,
    INTERACTIVE_JS,
    _guard_or_die,
)

SKILL_DIR = Path(__file__).resolve().parent.parent


def _extract_headings(md_text: str) -> list[dict]:
    """Extract headings from markdown text for TOC generation."""
    headings: list[dict] = []
    in_fence = False
    for line in md_text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            text = m.group(2).strip()
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            headings.append(
                {
                    "level": len(m.group(1)),
                    "text": text,
                    "slug": slug,
                }
            )
    return headings


def _build_heading_nav(headings: list[dict]) -> str:
    """Build sidebar nav HTML from extracted headings."""
    if not headings:
        return ""
    parts: list[str] = []
    current_group: str | None = None
    for h in headings:
        if h["level"] <= 2:
            # H1/H2 become section headers with their own nav groups
            if current_group is not None:
                parts.append("</ul></div>")
            current_group = h["text"]
            parts.append(
                f'<div class="nav-group">'
                f'<div class="nav-section open" data-section="{_escape(h["text"])}">'
                f"{_escape(h['text'])}</div>"
                f'<ul class="nav-items">'
            )
        else:
            # H3+ become nav links within the current group
            if current_group is None:
                # Edge case: H3 before any H1/H2
                current_group = "Contents"
                parts.append(
                    '<div class="nav-group">'
                    '<div class="nav-section open" data-section="Contents">Contents</div>'
                    '<ul class="nav-items">'
                )
            indent = "padding-left:" + str((h["level"] - 3) * 0.75) + "rem;"
            parts.append(
                f'<li><a href="#{h["slug"]}" class="nav-link" '
                f'data-target="{h["slug"]}" style="{indent}">'
                f"{_escape(h['text'])}</a></li>"
            )
    if current_group is not None:
        parts.append("</ul></div>")
    return "\n".join(parts)


def build_puppy_single_file(md_path: Path, output_file: Path, title: str):
    """Convert a single markdown file to a puppy-compatible HTML page."""
    md_text = md_path.read_text(encoding="utf-8")
    converter = MarkdownConverter()
    body_html, page_title = converter.convert(md_text)
    if not title:
        title = page_title or md_path.stem
    base_css = load_css()

    headings = _extract_headings(md_text)
    nav_html = _build_heading_nav(headings)

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<style>
{base_css}
{LAYOUT_CSS}
</style>
</head>
<body>
<aside class="sidebar">
  <div class="sidebar-header">{_escape(title)}</div>
  <div class="sidebar-nav">{nav_html}</div>
</aside>
<div class="content">
{body_html}
</div>
<button class="jump-top" id="jump-top" aria-label="Jump to top" title="Back to top">&uarr;</button>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: 'neutral'}});</script>
<script>{INTERACTIVE_JS}</script>
</body>
</html>"""

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(page_html, encoding="utf-8")
    _guard_or_die(page_html, output_file)
    print(f"Wrote {output_file} ({len(page_html) // 1024} KB) - ready for share-puppy!")


def build_puppy_directory(docs_dir: Path, output_file: Path, title: str):
    """Convert a directory of markdown files to a single puppy-compatible HTML page."""
    pages = discover_pages(docs_dir)
    if not pages:
        print(f"No .md files found in {docs_dir}")
        sys.exit(1)

    anchor_map = build_anchor_map(pages)
    converter = MarkdownConverter(anchor_map=anchor_map)
    sidenav_html = build_sidenav(pages)
    base_css = load_css()

    body_parts: list[str] = []
    for p in pages:
        md_text = p["src"].read_text(encoding="utf-8")
        html_body, _ = converter.convert(md_text)
        body_parts.append(
            f'<section id="{p["slug"]}">'
            f'<div class="section-badge">{p["section"]}</div>'
            f"{html_body}"
            f"</section><hr>"
        )

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<style>
{base_css}
{LAYOUT_CSS}
</style>
</head>
<body>
<aside class="sidebar">
  <div class="sidebar-header">{_escape(title)}</div>
  <div class="sidebar-nav">{sidenav_html}</div>
</aside>
<div class="content">
<h1 id="top">{_escape(title)}</h1>
<p>{len(pages)} pages combined into a single Puppy Page.</p>
<hr>
{chr(10).join(body_parts)}
</div>
<button class="jump-top" id="jump-top" aria-label="Jump to top" title="Back to top">&uarr;</button>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: 'neutral'}});</script>
<script>{INTERACTIVE_JS}</script>
</body>
</html>"""

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(page_html, encoding="utf-8")
    _guard_or_die(page_html, output_file)
    print(
        f"Wrote {output_file} ({len(page_html) // 1024} KB, {len(pages)} pages) - ready for share-puppy!"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build a Puppy Pages-compatible HTML file from markdown.",
    )
    parser.add_argument("input", help="Markdown file or directory")
    parser.add_argument("output_file", help="Output HTML file path")
    parser.add_argument(
        "--title", default="", help="Page title (auto-detected if omitted)"
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_file = Path(args.output_file).resolve()
    title = args.title or "Documentation"

    if input_path.is_file():
        build_puppy_single_file(input_path, output_file, args.title)
    elif input_path.is_dir():
        build_puppy_directory(input_path, output_file, title)
    else:
        print(f"Error: {input_path} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
