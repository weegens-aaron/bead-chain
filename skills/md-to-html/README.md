# md-to-html — Scenario Coverage

One skill, five modes, every markdown-to-HTML scenario you'll hit.

## Scenario Table

| # | Scenario | Mode | Input | Output | Navigation | Example |
|---|----------|------|-------|--------|------------|---------|
| 1 | **Single markdown file → shareable HTML** | `puppy-page` | One `.md` file | One `.html` file | Sidebar from headings | `convert.py puppy-page README.md readme.html` |
| 2 | **Docs directory → multi-page static site** | `multi-page` | Directory of `.md` files | Directory of `.html` files | Sidebar with page links | `convert.py multi-page docs/ _site --title "Docs"` |
| 3 | **Docs directory → single scrollable page** | `single-page` | Directory of `.md` files | One `.html` file | Scroll-spy sidebar | `convert.py single-page docs/ all.html --title "Docs"` |
| 4 | **Docs directory → Puppy Pages upload** | `puppy-page` | Directory of `.md` files | One `.html` file | Scroll-spy sidebar | `convert.py puppy-page docs/ page.html --title "Docs"` |
| 5 | **Collection of reports → searchable index** | `index` | `manifest.json` | Card-grid `.html` | Search bar + filter | `convert.py index manifest.json index.html --title "Reports"` |
| 6 | **Pre-flight lint check** | `lint` | `.md` files or dirs | Terminal output | — | `convert.py lint docs/` |
| 7 | **Discovery/research report** | `puppy-page` | Structured `.md` with front matter | One `.html` with rich components | Sidebar from headings | `convert.py puppy-page report.md report.html` |
| 8 | **Remediation plan** | `puppy-page` | Structured `.md` with fix boxes | One `.html` with rich components | Sidebar from headings | `convert.py puppy-page plan.md plan.html` |
| 9 | **Problem ticket index** | `index` | Manifest of ticket reports | Searchable card grid | Search by PRB/INC/title | `convert.py index manifest.json index.html` |

## When to Use Which Mode

```
                          ┌─────────────────────┐
                          │  What do you have?   │
                          └─────────┬───────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              One .md file    Directory of .md    manifest.json
                    │               │               │
                    ▼               │               ▼
              puppy-page            │             index
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
                  Need separate   One big     For Puppy
                  HTML per page?  scroll?     Pages?
                        │           │           │
                        ▼           ▼           ▼
                   multi-page   single-page  puppy-page
```

## Layout Components Available

All modes share the same CSS. These HTML components can be embedded directly
in any markdown file and will render correctly in every output mode.

| Component | Classes | Use Case |
|-----------|---------|----------|
| Summary Grid | `.exec-grid` + `.box-red`, `.box-spark`, `.box-green`, `.box-blue` | Executive summaries, at-a-glance panels |
| Badges | `.badge` + color/category/status variants | Status labels, ticket IDs, categories |
| Page References | `.page-ref`, `.page-ref-stale` | Linking to Confluence pages |
| File References | `.file-ref` | Referencing source code paths |
| Flow Steps | `.flow-step` + `.flow-num` + `.flow-content` | Architecture diagrams, numbered processes |
| Callouts (HTML) | `.callout` + `.callout-info`, `.callout-warn`, `.callout-stale`, `.callout-fix` | Warnings, notes, stale disclaimers |
| Callouts (MD) | `> [!NOTE]`, `> [!WARNING]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!CAUTION]` | Standard markdown callout syntax |
| Analysis Cards | `.hypo-card` + `.hypo-high`, `.hypo-med`, `.hypo-low` | Hypotheses, prioritized analysis |
| Accent Boxes | `.highlight-box`, `.bug-box`, `.fix-box` | Key insights, bugs, resolutions |
| Stale Banner | `.stale-banner` | Top-of-page staleness warning |
| Diff Lines | `.line-del`, `.line-add` | Code diff highlighting |

## Markdown Features

The shared converter (`md_converter.py`) handles:

| Feature | Syntax |
|---------|--------|
| Headings | `# H1` through `###### H6` |
| Bold / Italic | `**bold**`, `*italic*`, `***both***` |
| Inline code | `` `code` `` |
| Fenced code blocks | ` ```lang ... ``` ` |
| Mermaid diagrams | ` ```mermaid ... ``` ` |
| Tables | Pipe-delimited `\| col \| col \|` |
| Ordered lists | `1. item` |
| Unordered lists | `- item` |
| Blockquotes | `> text` |
| GitHub callouts | `> [!NOTE]`, `> [!WARNING]`, etc. |
| Links | `[text](url)` |
| Images | `![alt](src)` |
| Horizontal rules | `---` |
| YAML front matter | `---` delimited block (stripped) |
| Raw HTML passthrough | Block-level HTML elements pass through verbatim |
| Inline HTML | `<span>`, `<strong>`, etc. preserved in paragraphs |

## Manifest Format (Index Mode)

```json
[
  {
    "path": "relative/path/to/report.html",
    "title": "Human-Readable Report Title",
    "tags": ["PRB001", "INC123"]
  }
]
```

| Field | Required | Description |
|-------|----------|-------------|
| `path` | ✅ | Relative path from the index HTML to the report |
| `title` | ✅ | Display title shown on the card |
| `tags` | ❌ | Badge labels. Auto-detected from path if omitted (PRB/INC patterns) |

## YAML Front Matter

Supported in all markdown conversion modes. Stripped before conversion.

```yaml
---
title: Report Title
ticket: REP-1234
date: 2025-07-21
subtitle: REP · Discovery Report
source_count: 12
spaces: SCOPING, REGAT
stale_count: 2
---
```

Front matter is parsed and removed — it does not appear in the HTML body.
Agents or build scripts can read these fields for headers, banners, etc.

## File Structure

```
md-to-html/
├── SKILL.md                   # Skill definition (activated by agents)
├── README.md                  # This file — scenario coverage
├── assets/
│   └── style.css              # Shared theme + layout components
└── scripts/
    ├── convert.py             # Unified CLI (all modes)
    ├── md_converter.py        # Shared Markdown→HTML parser
    ├── md_lint.py             # Markdown linter
    ├── build_multi_page.py    # Mode: multi-page
    ├── build_single_page.py   # Mode: single-page
    ├── build_puppy_page.py    # Mode: puppy-page
    └── build_index.py         # Mode: index
```
