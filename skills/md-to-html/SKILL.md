---
name: md-to-html
description: >
  Unified Markdown-to-HTML converter with three output modes: multi-page static
  site, single-page self-contained HTML, and Puppy Pages-compatible HTML for
  puppy.walmart.com. Includes a markdown linter to catch issues before conversion.
  Use when converting .md files or doc directories into HTML — whether for static
  sites, single-page docs, or Puppy Pages sharing. Replaces the separate
  docs-to-html and md-to-puppy skills with one unified tool and consistent styling.
---

# md-to-html

Unified Markdown-to-HTML converter. One shared parser, one shared theme, three
output modes, and a built-in linter.

## Quick Start

All commands use `convert.py` as the entrypoint:

```bash
python3 <skill_dir>/scripts/convert.py <mode> [args...]
```

## Modes

| Mode | Input | Output | Navigation |
|------|-------|--------|------------|
| `lint` | `.md` files/dirs | Terminal warnings/errors | — |
| `multi-page` | docs directory | Directory of `.html` files | Sidebar per page |
| `single-page` | docs directory | One `.html` file | Scroll-spy sidebar |
| `puppy-page` | `.md` file or dir | One `.html` file | Scroll-spy sidebar |
| `index` | `manifest.json` | Card-based index `.html` | Search bar |

## Step 1: Lint First

Always lint before converting to catch issues that produce broken HTML:

```bash
python3 <skill_dir>/scripts/convert.py lint <docs_dir>
```

Fix any errors before proceeding. Warnings are advisory.

## Step 2: Choose a Mode

### Multi-Page Site

Build a directory of HTML pages with sidebar navigation:

```bash
python3 <skill_dir>/scripts/convert.py multi-page <docs_dir> <output_dir> --title "Site Title"
```

- Produces `output_dir/` with one `.html` per `.md` file
- Sidebar navigation with active page highlighting
- highlight.js + Mermaid loaded from CDN at runtime

### Single Page

Combine all docs into one self-contained HTML file with scroll-spy sidebar:

```bash
python3 <skill_dir>/scripts/convert.py single-page <docs_dir> <output_file> --title "Site Title"
```

- All CSS inlined, JS via CDN
- Collapsible sidebar sections with scroll-spy
- Jump-to-top button
- Internal links rewritten to `#anchor` links

### Puppy Page

Build HTML compatible with puppy.walmart.com via `share-puppy`:

```bash
# Single file:
python3 <skill_dir>/scripts/convert.py puppy-page README.md output.html --title "My Doc"

# Directory:
python3 <skill_dir>/scripts/convert.py puppy-page docs/ output.html --title "My Docs"
```

- Single file input: sidebar nav from headings
- Directory input: sidebar with scroll-spy (same as single-page)
- Ready for `share-puppy` upload

After building, use the `share-puppy` sub-agent to deploy.

### Index Page

Build a searchable card-based index from a manifest:

```bash
python3 <skill_dir>/scripts/convert.py index manifest.json index.html --title "Report Index"
```

Supports two manifest formats:

#### Flat manifest (report index)

```json
[
  { "path": "reports/report-one.html", "title": "Report One" },
  { "path": "reports/report-two.html", "title": "Report Two", "tags": ["PRB001", "INC123"] }
]
```

Fields:
- `path` (required) — relative path from the index to the HTML file
- `title` (required) — display title for the card
- `tags` (optional) — badge strings (e.g. ticket IDs). Auto-detected from path if omitted (PRB/INC patterns)

#### Categorized manifest (knowledge base / doc hub)

```json
{
  "title": "My Knowledge Base",
  "subtitle": "Optional subtitle shown under the header",
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
```

Fields:
- `title` / `subtitle` (optional) — page header (overridden by `--title` flag)
- `categories[].name` (required) — section heading
- `categories[].accent` (optional) — accent color for card top bar (default: Walmart blue)
- `entries[].slug` (required) — directory name; links to `<slug>/index.html`
- `entries[].title` (required) — display title
- `entries[].icon` (optional) — emoji icon
- `entries[].description` (optional) — short description
- `entries[].tag` (optional) — primary badge label
- `entries[].tags` (optional) — searchable keywords

The format is auto-detected: objects with `categories` use categorized layout; arrays use flat layout.

## Features

| Feature | Multi-Page | Single Page | Puppy Page | Index |
|---|---|---|---|---|
| Sidebar navigation | ✅ | ✅ scroll-spy | ✅ | — |
| Search / filter | ❌ | ❌ | ❌ | ✅ |
| Code highlighting | CDN | CDN | CDN | — |
| Mermaid diagrams | CDN | CDN | CDN | — |
| Callout blocks | ✅ | ✅ | ✅ | — |
| Layout components | ✅ | ✅ | ✅ | ✅ badges |
| Tables | ✅ | ✅ | ✅ | — |
| Self-contained | ❌ (dir) | ✅ | ✅ | ✅ |
| Single .md input | ❌ | ❌ | ✅ | — |
| Manifest input | ❌ | ❌ | ❌ | ✅ |

## Section Ordering

Sections auto-detected from subdirectories. Priority order:
Overview → Concepts → Getting-Started → Guides → Reference → Tutorials.
Others sort alphabetically after. Root `.md` files → "Overview".
`index.md` sorts first within each section. `_Manifest.md` files skipped.

## Customizing the Theme

Edit `assets/style.css`. Uses `--c-*` CSS custom properties for easy theming.
Changes apply to all modes on next build.

## Reusable Layout Components

The shared CSS includes rich layout components you can embed as raw HTML in any
markdown file. They work in **all modes** (multi-page, single-page, puppy-page).

### Executive / Summary Grid

A responsive grid of colored summary boxes:

```html
<div class="exec-grid">
  <div class="box-red"><strong>🚨 Problem</strong><p>Description...</p></div>
  <div class="box-spark"><strong>⭐ Task</strong><p>Description...</p></div>
  <div class="box-green"><strong>✅ Goal</strong><p>Description...</p></div>
</div>
```

Variants: `.box-red`, `.box-spark`, `.box-green`, `.box-blue`

### Badges

Inline pill badges for status, categories, and labels:

```html
<span class="badge badge-green">✅ CURRENT</span>
<span class="badge badge-stale">⛔ STALE (2 yr)</span>
<span class="badge badge-technical">Technical</span>
<span class="badge badge-open">Open</span>
```

**Color badges:** `.badge-red`, `.badge-green`, `.badge-blue`, `.badge-yellow`,
`.badge-purple`, `.badge-orange`, `.badge-gray`, `.badge-stale`

**Category badges:** `.badge-technical`, `.badge-business`, `.badge-data`, `.badge-infra`

**Status badges:** `.badge-open`, `.badge-watch`, `.badge-resolved`

### Reference Tags

Inline tags for referencing pages and files:

```html
<span class="page-ref">Confluence Page Title</span>
<span class="page-ref-stale">Stale Page Title</span>
<span class="file-ref">src/main/java/com/example/Service.java</span>
```

### Flow Steps (Architecture Diagrams)

Numbered process steps with colored circles:

```html
<div class="flow-step">
  <div class="flow-num">1</div>
  <div class="flow-content"><strong>Step Title</strong><p>Details...</p></div>
</div>
<div class="flow-step">
  <div class="flow-num flow-num-red">2</div>
  <div class="flow-content"><strong>Error Path</strong><p>Details...</p></div>
</div>
```

Circle variants: `.flow-num` (blue), `.flow-num-red`, `.flow-num-yellow`, `.flow-num-green`

### Extended Callouts

Beyond the standard `> [!NOTE]` / `> [!WARNING]` markdown callouts, you can use
HTML callouts for more variants:

```html
<div class="callout callout-info">Info message</div>
<div class="callout callout-warn">Warning message</div>
<div class="callout callout-stale">⛔ Stale source disclaimer</div>
<div class="callout callout-fix">✅ Resolution details</div>
```

### Analysis Cards

```html
<div class="hypo-card hypo-high">High-priority hypothesis...</div>
<div class="hypo-card hypo-med">Medium-priority analysis...</div>
<div class="hypo-card hypo-low">Low-priority note...</div>
```

### Accent Boxes

```html
<div class="highlight-box">⚠️ Key insight or highlight</div>
<div class="bug-box">🐛 Bug or issue description</div>
<div class="fix-box">✅ Fix or resolution description</div>
```

### Stale Sources Banner

A top-of-page warning bar for reports with stale sources:

```html
<div class="stale-banner">
  <strong>⛔ Stale Sources Warning</strong>
  <span>3 sources are older than 12 months. Facts from those sources should be verified.</span>
</div>
```

### Diff Highlighting (in code blocks)

```html
<pre><code>
<span class="line-add">+ added line</span>
<span class="line-del">- removed line</span>
  unchanged line
</code></pre>
```

## File Structure

```
md-to-html/
├── SKILL.md
├── README.md                  # Scenario coverage guide
├── assets/
│   └── style.css              # Shared theme + layout components
└── scripts/
    ├── convert.py             # Unified CLI entrypoint
    ├── md_converter.py        # Shared Markdown→HTML converter
    ├── md_lint.py             # Markdown linter
    ├── build_multi_page.py    # Multi-page site builder
    ├── build_single_page.py   # Single-page builder
    ├── build_puppy_page.py    # Puppy Pages builder
    ├── build_index.py         # Flat card-based index builder
    └── build_categorized_index.py  # Categorized card-based index builder
```
