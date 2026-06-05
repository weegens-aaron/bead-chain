#!/usr/bin/env python3
"""Build a single-page HTML doc from a directory of Markdown files.

Usage:
    python build_single_page.py <docs_dir> <output_file> [--title "Site Title"]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_converter import MarkdownConverter, _escape, find_unconverted_links  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent

SECTION_PRIORITY = [
    "Overview",
    "Concepts",
    "Getting-Started",
    "Guides",
    "Reference",
    "Tutorials",
]


def _section_sort_key(section: str) -> tuple[int, str]:
    try:
        return (SECTION_PRIORITY.index(section), section)
    except ValueError:
        return (len(SECTION_PRIORITY), section)


def _guard_or_die(html_text: str, output_file: Path) -> None:
    """Fail the build if raw [text](path.md) links leaked into the HTML.

    Shared by the single-page and puppy-page builders. Catches the converter
    regression where multi-line markdown links survive as literal text.
    """
    found = find_unconverted_links(html_text)
    if not found:
        return
    print(f"\nUnconverted markdown links leaked into {output_file}:")
    for snippet in found:
        print(f"  {snippet}")
    print(
        "\nThese are raw [text](path.md) links the converter failed to "
        "rewrite. Fix the source markdown or the converter and rebuild."
    )
    sys.exit(1)


def _label(name: str) -> str:
    return (
        re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        .replace("-", " ")
        .replace("_", " ")
        .strip()
    )


def _slug(section: str, name: str) -> str:
    return f"{section}--{name}".lower().replace(" ", "-")


def discover_pages(docs_dir: Path) -> list[dict]:
    """Walk docs_dir and return ordered list of page dicts."""
    pages: list[dict] = []
    for md in sorted(docs_dir.rglob("*.md")):
        rel = md.relative_to(docs_dir)
        name = rel.stem
        # Skip underscore-prefixed working/authoring files (e.g. _Manifest,
        # _DiataxisGuide, _UpdateQueue, _AuditLog) so they never leak into
        # the published site.
        if name.startswith("_"):
            continue
        section = (
            str(rel.parent).replace("\\", "/")
            if rel.parent != Path(".")
            else "Overview"
        )
        pages.append(
            {
                "src": md,
                "rel": str(rel).replace("\\", "/"),
                "html_rel": str(rel.with_suffix(".html")).replace("\\", "/"),
                "section": section,
                "name": name,
                "label": _label(name) if name != "index" else "Index",
                "slug": _slug(section, name),
            }
        )
    pages.sort(
        key=lambda p: (
            _section_sort_key(p["section"]),
            0 if p["name"] == "index" else 1,
            p["name"],
        )
    )
    return pages


def build_anchor_map(pages: list[dict]) -> dict[str, str]:
    """Map relative path variants to #slug anchors."""
    mapping: dict[str, str] = {}
    for p in pages:
        anchor = "#" + p["slug"]
        for variant in [p["rel"], p["html_rel"], p["rel"].rsplit(".", 1)[0]]:
            mapping[variant] = anchor
            if "/" in variant:
                mapping[variant.split("/", 1)[1]] = anchor
    return mapping


def build_sidenav(pages: list[dict]) -> str:
    """Build collapsible sidebar nav grouped by section."""
    parts: list[str] = []
    current_section = None
    for p in pages:
        if p["section"] != current_section:
            if current_section is not None:
                parts.append("</ul></div>")
            current_section = p["section"]
            parts.append(
                f'<div class="nav-group">'
                f'<div class="nav-section" data-section="{current_section}">{current_section}</div>'
                f'<ul class="nav-items">'
            )
        parts.append(
            f'<li><a href="#{p["slug"]}" class="nav-link" '
            f'data-target="{p["slug"]}">{p["label"]}</a></li>'
        )
    if current_section is not None:
        parts.append("</ul></div>")
    return "\n".join(parts)


def load_css() -> str:
    css_path = SKILL_DIR / "assets" / "style.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return "body { font-family: system-ui, sans-serif; }"


LAYOUT_CSS = """
/* ── Single-page layout overrides ── */
body { display: flex; min-height: 100vh; scroll-behavior: smooth; }

.sidebar {
    display: flex; flex-direction: column;
    width: 280px; min-width: 280px;
    background: var(--c-sidebar-bg, #f6f8fa);
    border-right: 1px solid var(--c-border, #d1d9e0);
    position: fixed; top: 0; left: 0; bottom: 0;
    overflow-y: auto; z-index: 10;
}
.sidebar-header {
    padding: 1rem 1.25rem 0.75rem; font-size: 0.95rem; font-weight: 700;
    border-bottom: 1px solid var(--c-border, #d1d9e0);
    position: sticky; top: 0; background: var(--c-sidebar-bg, #f6f8fa); z-index: 1;
}
.sidebar-nav { padding: 0.5rem 0.75rem 2rem; flex: 1; overflow-y: auto; }
.nav-group { margin-bottom: 0.25rem; }
.nav-section {
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--c-text-muted, #59636e);
    padding: 0.6rem 0.5rem 0.2rem; cursor: pointer; user-select: none;
}
.nav-section::before { content: '▸ '; font-size: 0.65rem; }
.nav-section.open::before { content: '▾ '; }
.nav-items { list-style: none; padding: 0 0 0 0.25rem; margin: 0; display: none; }
.nav-section.open + .nav-items { display: block; }
.nav-items li { margin: 0; }
.nav-link {
    display: block; padding: 0.2rem 0.75rem; font-size: 0.82rem;
    color: var(--c-text-muted, #59636e); text-decoration: none;
    border-radius: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.nav-link:hover { background: var(--c-border, #d1d9e0); color: var(--c-text, #1f2328); }
.nav-link.active { background: var(--c-sidebar-active, #0969da); color: #fff; font-weight: 600; }
.content { margin-left: 280px; flex: 1; min-width: 0; max-width: 60rem; padding: 2rem 2.5rem 4rem; }
section { scroll-margin-top: 1rem; }
.section-badge {
    display: inline-block; font-size: 0.7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--c-text-muted, #59636e); background: var(--c-bg-alt, #f6f8fa);
    border: 1px solid var(--c-border, #d1d9e0); border-radius: 4px;
    padding: 0.15rem 0.5rem; margin-bottom: 0.5rem;
}
.jump-top {
    position: fixed; bottom: 2rem; right: 2rem; width: 44px; height: 44px;
    border-radius: 50%; background: var(--c-accent, #0969da); color: #fff;
    border: none; font-size: 1.25rem; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2); opacity: 0; pointer-events: none;
    transition: opacity 0.25s, transform 0.25s; transform: translateY(10px); z-index: 100;
    display: flex; align-items: center; justify-content: center;
}
.jump-top:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
.jump-top.visible { opacity: 1; pointer-events: auto; transform: translateY(0); }
@media (max-width: 1100px) {
    .sidebar { width: 210px; min-width: 210px; }
    .sidebar-header { font-size: 0.85rem; padding: 0.75rem 0.75rem 0.5rem; }
    .nav-link { font-size: 0.78rem; padding: 0.2rem 0.5rem; }
    .nav-section { font-size: 0.68rem; }
    .content { margin-left: 210px; padding: 1.5rem 1.5rem 3rem; max-width: none; }
}
@media (max-width: 768px) { .sidebar { display: none; } .content { margin-left: 0; padding: 1rem; max-width: none; } }
@media print { .sidebar, .jump-top { display: none; } .content { margin-left: 0; max-width: 100%; } }
"""

INTERACTIVE_JS = """
(function() {
  const sections = document.querySelectorAll('.nav-section');
  if (sections.length) sections[0].classList.add('open');
  sections.forEach(s => s.addEventListener('click', () => s.classList.toggle('open')));
  const btn = document.getElementById('jump-top');
  window.addEventListener('scroll', () => {
    btn.classList.toggle('visible', window.scrollY > 400);
  }, {passive: true});
  btn.addEventListener('click', () => window.scrollTo({top: 0, behavior: 'smooth'}));
  const links = document.querySelectorAll('.nav-link');
  const targets = Array.from(links).map(l => ({
    link: l, el: document.getElementById(l.dataset.target)
  })).filter(t => t.el);
  let ticking = false;
  function updateActive() {
    const scrollY = window.scrollY + 100;
    let active = targets[0];
    for (const t of targets) { if (t.el.offsetTop <= scrollY) active = t; }
    links.forEach(l => l.classList.remove('active'));
    if (active) {
      active.link.classList.add('active');
      const group = active.link.closest('.nav-group');
      if (group) group.querySelector('.nav-section').classList.add('open');
      active.link.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    }
    ticking = false;
  }
  window.addEventListener('scroll', () => {
    if (!ticking) { requestAnimationFrame(updateActive); ticking = true; }
  }, {passive: true});
  updateActive();
})();
"""


def build_single_page(docs_dir: Path, output_file: Path, title: str):
    """Convert a docs directory into one self-contained HTML file."""
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
<p>Complete single-page reference &mdash; {len(pages)} pages combined.</p>
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
        f"Wrote {output_file} ({len(page_html) // 1024} KB, {len(pages)} pages combined)"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build single-page HTML from markdown docs."
    )
    parser.add_argument("docs_dir", help="Markdown source directory")
    parser.add_argument("output_file", help="Output HTML file path")
    parser.add_argument("--title", default="Documentation", help="Site title")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    output_file = Path(args.output_file).resolve()
    if not docs_dir.is_dir():
        print(f"Error: {docs_dir} is not a directory")
        sys.exit(1)
    build_single_page(docs_dir, output_file, args.title)


if __name__ == "__main__":
    main()
