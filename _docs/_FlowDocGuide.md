# FlowDoc Authoring Guide — bead-chain (user edition)

> [!IMPORTANT]
> This guide is the **sole carrier** of template and naming fidelity for every
> doc bead in the user documentation set. Every doc bead reads this file and
> follows it exactly. If a template says a section exists, the doc includes it —
> no shortcuts, no paraphrasing the structure.

---

## Audience

**User.** These docs are for people who *use* bead-chain through Code Puppy,
not for people who maintain its source code. Maintainer docs live in `__docs/`.

## Classification

User docs follow the [Diataxis](https://diataxis.fr/) framework:

| Type | Purpose | Band |
|------|---------|------|
| Getting-Started | First steps to a concrete outcome | 001+ |
| Guide / How-To | Task-oriented instructions | 010+ |
| Tutorial | Narrative end-to-end walkthrough | 040+ |
| Reference | Lookup tables of commands, options, statuses | 060+ |
| Concept | Explanation of how and why things work | 090+ |

## Naming Convention (N1)

- Section **directories** are PascalCase: `GettingStarted/`, `Guides/`, etc.
- Item **filenames** are PascalCase with `.md` extension:
  `RunYourFirstChain.md`, not `run-your-first-chain.md`.
- The manifest link target and the actual filename must agree exactly.

## Output Rules

- **READ-ONLY source.** Doc beads never modify source code. Output goes only
  under `_docs/`.
- **Features, not files.** Describe what the product does, not how the code is
  structured.
- **Flows, not functions.** Describe user-visible sequences, not internal call
  chains.
- **Why over what.** Explain *why* a feature exists before describing *what* it
  does.
- **Behavior-first framing.** Lead with what the user experiences, not with
  implementation mechanics.
- **Bidirectional links.** Every reference to another doc is a working link, and
  the target links back.
- **Mermaid diagrams.** Every flow or sequence gets a mermaid diagram.
- **Callouts.** Use `> [!TIP]`, `> [!NOTE]`, `> [!WARNING]`, `> [!IMPORTANT]`,
  `> [!CAUTION]` for tips, context, gotchas, rules, and dangers.

## Leakage Rule (G7) — Enforced Inline

> [!CAUTION]
> Every user doc obeys ALL of these constraints at authoring time — this is not
> a finalize-only sweep:
>
> - **NO source paths** (`lifecycle.py`, `beads.py`, etc.)
> - **NO code or shell/install snippets** beyond the commands users actually type
>   (`/bead-chain`, `bd ready`)
> - **NO class or function names** (`BeadChainState`, `close_current_bead_success`)
> - **NO localhost, dev, or staging URLs**
>
> Describe the UI the user sees ("the chain picks up the next task", "you'll see
> a recovery warning"), never the implementation behind it.

## Writing Rules (encode all 7)

1. **Second person** — "you tap", "you'll see", never "the user".
2. **Active voice; imperative steps** — "Start the chain", not "The chain is
   started".
3. **Show, don't tell** — describe exactly what appears on screen.
4. **One idea per paragraph** — keep paragraphs short.
5. **Callouts for tips and gotchas** — use the `> [!TIP]` / `> [!WARNING]`
   family.
6. **Expected result after every step** — state what you should see after each
   action.
7. **Link generously and bidirectionally** — connect related pages in both
   directions.

---

## Section Templates

### Getting-Started page (user)

```markdown
# Quick Start: <achieve a first concrete outcome>

## What You'll Achieve
(the end result in one line)

## Prerequisites
(account / access / device — user-facing only)

## Step 1: <action>
(ONE user action plus the expected result the user should see;
use Option A / Option B sub-steps for branches)

## Step 2: <action>
...

## Step N: <action>
...

## Common Issues

| Symptom | What to do |
|---------|------------|
| ...     | ...        |

## What You Learned

## Next Steps
(links onward to Guides/Tutorials)
```

> [!NOTE]
> An **Installation** page exists under Getting-Started because bead-chain is
> an installed-locally product (downloaded and extracted into the plugins
> directory). If it were accessed via a hosted URL, this page would be replaced
> with an "Accessing bead-chain" page instead.

---

### Guide / How-To (user)

```markdown
# How to <task>

## What You'll Learn

## Prerequisites

## Overview
(1-2 sentences of context)

## Step 1: <sub-task>
(numbered actions, each with its expected result;
nest 1..n bullet sub-actions per step)

## Step 2: <sub-task>
...

## Step N: <sub-task>
...

## Troubleshooting

| Problem | Fix |
|---------|-----|
| ...     | ... |

## Related Guides
(bidirectional links)
```

---

### Tutorial (user)

```markdown
# Tutorial: <end-to-end scenario>

## What You'll Achieve

## Before You Begin

## The Scenario

## Step 1: <action>
(a narrative walkthrough showing expected output/screens;
cover Scenario A/B/C success + error branches a user may hit)

## Step 2: <action>
...

## Step N: <action>
...

## Final Result

## What You Learned

## Next Steps
```

---

### Reference (user)

```markdown
# <Subject> Reference

## Overview

## <grouped reference sections>
(screens, menus, buttons, fields, icons — as tables
| Item | What it does |, e.g. screen-by-screen)

## Tips

## See Also
```

---

### Concept (user)

```markdown
# <Concept in plain language>

## What Is It

## Why It Matters

## How It Works
(plain language, analogy-friendly, no code)

## Related
```

---

### FAQ (user; the finalize step writes/refreshes this)

```markdown
# Frequently Asked Questions

(grouped by theme: Getting Started / Troubleshooting / Common Tasks;
each entry a "### <question>" heading + a short answer)
```

---

## Checklist for Every Doc Bead

Before marking a manifest item done, verify:

- [ ] File exists at the exact PascalCase path listed in `_Manifest.md`.
- [ ] ALL template sections are present and filled (no placeholders, no "TBD").
- [ ] Mermaid diagram(s) present where the template calls for flow/sequence.
- [ ] All cross-references are working bidirectional links.
- [ ] Leakage rule satisfied — no source paths, no code, no class names, no
      internal URLs.
- [ ] Writing rules 1–7 applied throughout.
- [ ] Manifest item ticked `[x]` and counters bumped.
