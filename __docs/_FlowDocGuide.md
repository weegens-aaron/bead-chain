# FlowDoc Authoring Guide (maintainer edition)

This is the **authoring contract** every bead-chain doc bead follows. It is the
sole carrier of template/section/naming fidelity — there is no external
"flowdoc" skill. Reproduce output identical in **shape** (section order, table
column headers, mermaid scaffolds, callout markers, naming) to these templates.
Do not paraphrase a template into a bare section list — carry the column layouts
and skeletons exactly.

**Audience for this set: maintainer.** Use the five maintainer templates below
(Feature / Flow / Endpoint / View / Concept). Fill EVERY section and table with
real values — no placeholders, real column values, real JSON field names, real
`file:symbol` impl-map rows. Include the mermaid diagram(s) each template calls
for. Link related docs bidirectionally.

---

## Core rules (encode these in every doc)

- **Features, not files** — document what the code *does*, not a file inventory.
- **Flows, not functions** — narrate processes end to end.
- **Why over what** — lead with the problem solved / behavior.
- **Behavior-first framing** — start from observable behavior.
- **Link every reference bidirectionally** — if A links B, B links A.
- **Mermaid for every flow/sequence** — diagrams are mandatory where the
  template shows them.
- **Callouts for gotchas** — use `> [!NOTE]`, `> [!WARNING]`, `> [!IMPORTANT]`,
  `> [!CAUTION]`.
- **READ-ONLY source** — never modify source while documenting.
- **Output only under `__docs/`** — never write elsewhere.

## Naming (N1)

Section directories AND item file names are BOTH PascalCase, e.g.
`Features/OrderSetManagement.md`. The manifest link target and the actual
filename must agree exactly.

---

## Template: Feature (maintainer)

```markdown
# <Name>

## What It Does
(1-2 sentences, behavior-first)

## Why It Exists
(the problem it solves)

## How It Works

### User Perspective
(what the user sees/does)

### System Perspective
(what the code does end to end)

```mermaid
sequenceDiagram
    (the request/interaction sequence)
```

## Key Data Shapes
(DTO / request / response JSON skeletons in fenced ```json blocks — real field names)

## API Surface
| Method | Path | Purpose | -> Endpoint doc |
|--------|------|---------|-----------------|

## Implementation Map
| Responsibility | File path | Symbol |
|----------------|-----------|--------|

## Configuration
| Key | Default | Effect |
|-----|---------|--------|

## Edge Cases
> [!WARNING]
> (one per edge case)

## Error Scenarios
| Trigger | Behavior | User sees |
|---------|----------|-----------|

## Testing
(how it's tested / how to test)

## Related
(bidirectional links to flows/endpoints/views)
```

---

## Template: Flow (maintainer)

```markdown
# <Name>

## What Happens
## Trigger
## Outcome

```mermaid
flowchart TD
    (the step graph)
```

## Step-by-Step
| # | What | Where (file:symbol) | Failure mode |
|---|------|---------------------|--------------|

## Data Transformations
(input -> output at each hop)

## Performance Characteristics
(latency/throughput/N+1 notes, sync vs async)

## Failure Handling
(retries, timeouts, compensation)

## Key Log Messages
| Log line | Where | Means |
|----------|-------|-------|

## Common Issues
| Symptom | Likely cause | Fix |
|---------|--------------|-----|

## Related
```

---

## Template: Endpoint (maintainer only)

> [!NOTE]
> bead-chain has no HTTP endpoints. This template is included for fidelity; this
> set's manifest contains no Endpoint items.

```markdown
# <METHOD> <path>

## Overview
| Method | Path | Auth | Purpose |
|--------|------|------|---------|

## Request

### Path/Query Params
| Name | In | Type | Required | Notes |
|------|----|------|----------|-------|

### Headers
| Header | Required | Notes |
|--------|----------|-------|

### Body
```json
(request skeleton)
```

### Validation Rules
| Field | Rule | Error |
|-------|------|-------|

### Rate Limit
| Limit | Window | Scope |
|-------|--------|-------|

## Response

### Success
(status + fenced ```json response skeleton)

### Errors
| Status | Code | When |
|--------|------|------|

## Implementation Map
| Responsibility | File path | Symbol |
|----------------|-----------|--------|

```mermaid
sequenceDiagram
    (client -> handler -> store)
```

## Example
(a real `curl` invocation with headers + body)

## Related
```

---

## Template: View (maintainer only)

> [!NOTE]
> bead-chain has no web views/pages. This template is included for fidelity;
> this set's manifest contains no View items.

```markdown
# <Name> (<route>)

## Overview
| Route | Auth | Purpose |
|-------|------|---------|

## URL Params
| Param | Type | Required | Notes |
|-------|------|----------|-------|

## What It Does
## User Actions

```mermaid
flowchart TD
    (page structure / component tree)
```

## Components
| Component | Responsibility | File |
|-----------|----------------|------|

## State Management
| State | Source | Updated by |
|-------|--------|------------|

## Data Flow
```mermaid
sequenceDiagram
    (view <-> API)
```

## API Dependencies
| Endpoint | Used for | -> Endpoint doc |
|----------|----------|-----------------|

## States
(Loading / Empty / Error states described)

## Accessibility
(keyboard, ARIA, focus, contrast notes)

## Responsive Behavior
(breakpoint behavior)

## Related
```

---

## Template: Concept (maintainer)

```markdown
# <Name>

## What Is It
## Why This Approach

## How It Works
(+ a concrete example)

## Where Used
(links to features/flows that rely on it)

## Conventions
> [!IMPORTANT]
> (the rules to follow)

## Anti-Patterns
> [!CAUTION]
> (what not to do)

## Related
```

---

## Per-bead acceptance checklist

A doc bead is done when:

1. The file exists at its PascalCase path (`<Section>/<PascalName>.md`).
2. Every template section and table is filled — no placeholders, real column
   values, real JSON field names, real `file:symbol` impl-map rows.
3. The mermaid diagram(s) the template calls for are present.
4. Related links are valid and bidirectional.
5. `_Manifest.md` has the item ticked `[x]` and the counters bumped.
