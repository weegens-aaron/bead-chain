#!/usr/bin/env python3
"""Build a searchable card-based index page from a manifest file.

Usage:
    python build_index.py <manifest.json> <output.html> [--title "Title"]

Supports two manifest formats:

1. Flat array (simple report index):
    [
      { "path": "report.html", "title": "My Report" },
      { "path": "PRB001/report.html", "title": "Analysis", "tags": ["PRB001"] }
    ]

2. Categorized object (knowledge-base / doc hub style):
    {
      "title": "My Hub",
      "subtitle": "Optional subtitle",
      "categories": [
        {
          "name": "Backend Services",
          "accent": "#0053e2",
          "entries": [
            {
              "slug": "my-service",
              "title": "My Service",
              "icon": "📡",
              "description": "What it does.",
              "tag": "Kafka",
              "tags": ["kafka", "backend"]
            }
          ]
        }
      ]
    }

    Categorized fields:
      slug        (required)  Directory name; links to <slug>/index.html.
      title       (required)  Display title.
      icon        (optional)  Emoji icon for the card.
      description (optional)  Short description.
      tag         (optional)  Primary badge label.
      tags        (optional)  Searchable keywords.
      categories[].name   (required)  Category heading.
      categories[].accent (optional)  Accent color (default: Walmart blue).
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

# ── Tag detection ────────────────────────────────────────────────────────────

TAG_PATTERNS = [
    (re.compile(r"(PRB\d{5,})", re.I), "badge-prb"),
    (re.compile(r"(INC\d{5,})", re.I), "badge-inc"),
    (re.compile(r"(SCOPING-\d+)", re.I), "badge-jira"),
    (re.compile(r"(REP-\d+)", re.I), "badge-jira"),
]


def _auto_tags(path: str) -> list[dict]:
    """Extract recognisable ticket IDs from a file path."""
    tags = []
    seen = set()
    for pattern, css_class in TAG_PATTERNS:
        for m in pattern.finditer(path):
            val = m.group(1).upper()
            if val not in seen:
                seen.add(val)
                tags.append({"label": val, "css": css_class})
    return tags


def _parse_tags(entry: dict) -> list[dict]:
    """Build tag list from explicit tags array or auto-detect from path."""
    if "tags" in entry and entry["tags"]:
        result = []
        for t in entry["tags"]:
            t_upper = t.upper()
            css = "badge-tag"
            for pattern, css_class in TAG_PATTERNS:
                if pattern.match(t):
                    css = css_class
                    break
            result.append({"label": t_upper, "css": css})
        return result
    return _auto_tags(entry.get("path", ""))


# ── HTML generation ──────────────────────────────────────────────────────────


def _load_base_css() -> str:
    css_path = SKILL_DIR / "assets" / "style.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return ""


INDEX_CSS = """
/* ── Index Page Layout ─────────────────────────────────────────── */
body {
  display: block;
  background: var(--c-bg-alt, #f6f8fa);
}

.index-header {
  background: var(--c-accent, #0969da);
  color: #fff;
  padding: 1.5rem 2rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: 0 2px 8px rgba(0,0,0,.2);
}

.index-header h1 {
  font-size: 1.4rem;
  font-weight: 700;
  margin: 0;
}

.index-header p {
  font-size: .85rem;
  opacity: .85;
  margin: .15rem 0 0;
}

.header-count {
  margin-left: auto;
  background: #ffc220;
  color: #1f2328;
  font-weight: 700;
  font-size: .8rem;
  padding: .35rem .75rem;
  border-radius: 999px;
  white-space: nowrap;
}

/* Search */
.search-bar {
  background: #fff;
  padding: 1rem 2rem;
  border-bottom: 1px solid var(--c-border, #d1d9e0);
  display: flex;
  align-items: center;
  gap: .75rem;
}

.search-bar input {
  flex: 1;
  max-width: 480px;
  padding: .55rem 1rem .55rem 2.4rem;
  border: 1.5px solid var(--c-border, #d1d9e0);
  border-radius: 6px;
  font-size: .95rem;
  outline: none;
  background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23767676' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E") no-repeat .7rem center;
  background-size: 1rem;
  transition: border-color .15s;
}

.search-bar input:focus {
  border-color: var(--c-accent, #0969da);
  box-shadow: 0 0 0 3px rgba(9,105,218,.15);
}

.search-info {
  font-size: .85rem;
  color: var(--c-text-muted, #59636e);
}

/* Grid */
.index-main {
  padding: 1.75rem 2rem 3rem;
  max-width: 1300px;
  margin: 0 auto;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.25rem;
}

/* Card */
.card {
  background: #fff;
  border: 1.5px solid var(--c-border, #d1d9e0);
  border-radius: 10px;
  padding: 1.25rem 1.4rem 1rem;
  display: flex;
  flex-direction: column;
  gap: .75rem;
  cursor: pointer;
  text-decoration: none;
  color: inherit;
  transition: box-shadow .18s, border-color .18s, transform .15s;
  position: relative;
  overflow: hidden;
}

.card::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 4px; height: 100%;
  background: var(--c-accent, #0969da);
  border-radius: 10px 0 0 10px;
  transition: background .18s;
}

.card:hover {
  box-shadow: 0 6px 24px rgba(9,105,218,.13);
  border-color: var(--c-accent, #0969da);
  transform: translateY(-2px);
}

.card:hover::before { background: #ffc220; }

.card:focus-visible {
  outline: 3px solid var(--c-accent, #0969da);
  outline-offset: 2px;
}

.card .badges {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
}

.card .badge {
  font-size: .72rem;
  font-weight: 700;
  padding: .2rem .55rem;
  border-radius: 4px;
  letter-spacing: .03em;
  text-transform: uppercase;
}

.badge-prb  { background: #e8f0fd; color: #002899; }
.badge-inc  { background: #fff8e5; color: #995213; }
.badge-jira { background: #e8daff; color: #581c87; }
.badge-tag  { background: #e2e8f0; color: #475569; }

.card-title {
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.4;
  flex: 1;
  margin: 0;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--c-bg-alt, #f6f8fa);
  padding-top: .65rem;
  font-size: .8rem;
  color: var(--c-text-muted, #59636e);
}

.card-open {
  color: var(--c-accent, #0969da);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: .25rem;
}

.card:hover .card-open { filter: brightness(.85); }

/* Empty state */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 4rem 2rem;
  color: var(--c-text-muted, #59636e);
}
.empty-state p { font-size: 1rem; margin-top: 1rem; }

/* Responsive */
@media (max-width: 600px) {
  .index-header { padding: 1rem; }
  .index-main   { padding: 1rem 1rem 2rem; }
  .search-bar   { padding: .75rem 1rem; }
}
"""


SEARCH_JS = """
(function() {
  const input = document.getElementById('search-input');
  const grid = document.getElementById('cards-grid');
  const cards = Array.from(grid.querySelectorAll('.card'));
  const countEl = document.getElementById('report-count');
  const infoEl = document.getElementById('search-info');
  const total = cards.length;

  function filter() {
    const q = (input.value || '').toLowerCase().trim();
    let visible = 0;
    cards.forEach(card => {
      const text = card.getAttribute('data-search').toLowerCase();
      const show = !q || text.includes(q);
      card.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    countEl.textContent = visible + ' Report' + (visible !== 1 ? 's' : '');
    infoEl.textContent = q ? 'Showing ' + visible + ' of ' + total + ' reports' : '';
    const empty = grid.querySelector('.empty-state');
    if (visible === 0) {
      if (!empty) {
        const div = document.createElement('div');
        div.className = 'empty-state';
        div.innerHTML = '<p>No reports match <strong>"' + q.replace(/</g,'&lt;') + '"</strong></p>';
        grid.appendChild(div);
      }
    } else if (empty) {
      empty.remove();
    }
  }

  input.addEventListener('input', filter);
})();
"""


def build_card_html(entry: dict, tags: list[dict]) -> str:
    title = html.escape(entry["title"])
    path = html.escape(entry["path"])
    search_text = html.escape(
        " ".join(
            [entry.get("title", ""), entry.get("path", "")] + [t["label"] for t in tags]
        )
    )

    badges_html = "".join(
        f'<span class="badge {t["css"]}">{html.escape(t["label"])}</span>' for t in tags
    )

    return f'''<a href="{path}" class="card" role="listitem" data-search="{search_text}">
  <div class="badges">{badges_html}</div>
  <p class="card-title">{title}</p>
  <div class="card-footer">
    <span>Report</span>
    <span class="card-open">Open
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
           stroke-linejoin="round" aria-hidden="true">
        <line x1="5" y1="12" x2="19" y2="12"/>
        <polyline points="12 5 19 12 12 19"/>
      </svg>
    </span>
  </div>
</a>'''


def build_index(manifest: list[dict], title: str) -> str:
    cards_html = "\n".join(
        build_card_html(entry, _parse_tags(entry)) for entry in manifest
    )
    count = len(manifest)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
{INDEX_CSS}
</style>
</head>
<body>

<header class="index-header" role="banner">
  <div>
    <h1>{html.escape(title)}</h1>
  </div>
  <span class="header-count" id="report-count" aria-live="polite">{count} Report{"s" if count != 1 else ""}</span>
</header>

<div class="search-bar" role="search">
  <input type="search" id="search-input" placeholder="Search by title, tag, or path\u2026"
         aria-label="Search reports"/>
  <span class="search-info" id="search-info" aria-live="polite"></span>
</div>

<main class="index-main">
  <div class="cards-grid" id="cards-grid" role="list" aria-label="Reports">
{cards_html}
  </div>
</main>

<script>{SEARCH_JS}</script>

</body>
</html>"""


# ── Categorized index (delegated to build_categorized_index.py) ──────────────

from build_categorized_index import build_categorized_index  # noqa: E402


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Build a searchable card-based index page from a manifest.",
    )
    parser.add_argument("manifest", help="Path to manifest.json")
    parser.add_argument("output_html", help="Output HTML file path")
    parser.add_argument("--title", default="Report Index", help="Page title")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output_html).resolve()

    if not manifest_path.is_file():
        print(f"Error: {manifest_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Detect format: categorized (object with 'categories') vs flat (array)
    if isinstance(manifest, dict) and "categories" in manifest:
        total = sum(len(cat.get("entries", [])) for cat in manifest["categories"])
        for ci, cat in enumerate(manifest["categories"]):
            if "name" not in cat:
                print(f"Error: category {ci} missing 'name'", file=sys.stderr)
                sys.exit(1)
            for ei, entry in enumerate(cat.get("entries", [])):
                if "slug" not in entry or "title" not in entry:
                    print(
                        f"Error: categories[{ci}].entries[{ei}] "
                        f"missing 'slug' or 'title'",
                        file=sys.stderr,
                    )
                    sys.exit(1)
        page_html = build_categorized_index(manifest, args.title)
        label = "categorized"
    elif isinstance(manifest, list):
        total = len(manifest)
        for i, entry in enumerate(manifest):
            if "path" not in entry or "title" not in entry:
                print(
                    f"Error: manifest entry {i} missing 'path' or 'title'",
                    file=sys.stderr,
                )
                sys.exit(1)
        page_html = build_index(manifest, args.title)
        label = "flat"
    else:
        print(
            "Error: manifest must be a JSON array or object with 'categories'",
            file=sys.stderr,
        )
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page_html, encoding="utf-8")
    print(f"✅ Index written to {output_path} ({total} entries, {label} format)")


if __name__ == "__main__":
    main()
