#!/usr/bin/env python3
"""Build a multi-page static HTML site from a directory of Markdown files.

Usage:
    python build_multi_page.py <docs_dir> <output_dir> [--title "Site Title"]
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_converter import (  # noqa: E402
    MarkdownConverter,
    _escape,
    _relative_link,
    find_unconverted_links,
)

SKILL_DIR = Path(__file__).resolve().parent.parent


def discover_pages(docs_dir: Path) -> list[dict]:
    """Walk docs_dir and return ordered list of page dicts."""
    pages = []
    for md in sorted(docs_dir.rglob("*.md")):
        rel = md.relative_to(docs_dir)
        name = rel.stem
        if name == "_Manifest":
            continue
        section = str(rel.parent).replace("\\", "/") if rel.parent != Path(".") else ""
        pages.append(
            {
                "src": md,
                "rel": rel,
                "section": section,
                "name": name,
                "html_rel": str(rel.with_suffix(".html")).replace("\\", "/"),
            }
        )
    pages.sort(
        key=lambda p: (
            p["section"] or "",
            0 if p["name"] == "index" else 1,
            p["name"],
        )
    )
    return pages


def build_sidebar(pages: list[dict], current_html_rel: str) -> str:
    """Generate sidebar HTML from pages list."""
    lines = ["<nav>"]
    current_section = object()
    for p in pages:
        section = p["section"]
        if section != current_section:
            current_section = section
            label = section.split("/")[-1] if section else "Overview"
            lines.append(f'<div class="nav-section">{_escape(label)}</div>')
        display = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p["name"].replace("_", " "))
        display = display[0].upper() + display[1:] if display else display
        active = ' class="active"' if p["html_rel"] == current_html_rel else ""
        href = _relative_link(current_html_rel, p["html_rel"])
        lines.append(f'<a href="{href}"{active}>{_escape(display)}</a>')
    lines.append("</nav>")
    return "\n".join(lines)


HLJS_CSS_CDN = (
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css"
)
HLJS_JS_CDN = (
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"
)
MERMAID_JS_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"


def render_page(
    body_html: str,
    title: str,
    sidebar_html: str,
    site_title: str,
    css_href: str,
) -> str:
    """Wrap body HTML in the full page template."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)} — {_escape(site_title)}</title>
<link rel="stylesheet" href="{css_href}">
<link rel="stylesheet" href="{HLJS_CSS_CDN}">
</head>
<body>
<aside class="sidebar">
<div class="sidebar-title">{_escape(site_title)}</div>
{sidebar_html}
</aside>
<main class="content">
{body_html}
</main>
<script src="{HLJS_JS_CDN}"></script>
<script>hljs.highlightAll();</script>
<script src="{MERMAID_JS_CDN}"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: 'neutral'}});</script>
</body>
</html>"""


def build_site(docs_dir: Path, output_dir: Path, site_title: str):
    """Convert docs_dir to a static HTML site in output_dir."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Copy CSS
    css_src = SKILL_DIR / "assets" / "style.css"
    if css_src.exists():
        shutil.copy2(css_src, output_dir / "style.css")

    pages = discover_pages(docs_dir)
    if not pages:
        print(f"No .md files found in {docs_dir}")
        sys.exit(1)

    known_pages = {p["html_rel"] for p in pages}
    converter = MarkdownConverter(known_pages=known_pages)

    leaks: dict[str, list[str]] = {}
    print(f"Building site: {len(pages)} pages from {docs_dir}")
    for page in pages:
        md_text = page["src"].read_text(encoding="utf-8")
        body_html, page_title = converter.convert(
            md_text,
            page["section"],
            page["html_rel"],
        )
        if not page_title:
            page_title = page["name"]

        sidebar_html = build_sidebar(pages, page["html_rel"])
        depth = page["html_rel"].count("/")
        root_prefix = "../" * depth
        full_html = render_page(
            body_html,
            page_title,
            sidebar_html,
            site_title,
            f"{root_prefix}style.css",
        )

        out_path = output_dir / page["html_rel"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(full_html, encoding="utf-8")
        found = find_unconverted_links(full_html)
        if found:
            leaks[page["html_rel"]] = found
        print(f"  {page['html_rel']}")

    if leaks:
        print("\n Unconverted markdown links leaked into the output:")
        for rel, found in leaks.items():
            for snippet in found:
                print(f"  {rel}: {snippet}")
        print(
            "\nThese are raw [text](path.md) links the converter failed to "
            "rewrite. Fix the source markdown or the converter and rebuild."
        )
        sys.exit(1)

    print(f"\n Site written to {output_dir} ({len(pages)} pages)")


def main():
    parser = argparse.ArgumentParser(
        description="Build multi-page HTML site from markdown docs."
    )
    parser.add_argument("docs_dir", help="Markdown source directory")
    parser.add_argument("output_dir", help="Output directory for HTML site")
    parser.add_argument("--title", default="Documentation", help="Site title")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not docs_dir.is_dir():
        print(f"Error: {docs_dir} is not a directory")
        sys.exit(1)
    build_site(docs_dir, output_dir, args.title)


if __name__ == "__main__":
    main()
