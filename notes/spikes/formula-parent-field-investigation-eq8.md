# Spike: Formula `parent` field behavior on pour (bead_chain-eq8)

**Date:** 2026-06-09
**bd version:** 1.0.5 (6a3f515ce)
**Timeboxed:** 90 min

---

## TL;DR

The formula step `parent` field is **silently ignored** by `bd mol pour`. All
steps become flat children of the molecule root regardless of any `parent` value
in the formula JSON. This means formulas cannot create bd-level parent-child
hierarchies (epic > task nesting), which breaks `bd list --parent`,
`bd dep tree`, and `bd epic close-eligible` for formula-defined epics.

The `skills` field is also silently ignored. `labels`, `priority`, and
`depends_on` work correctly.

---

## Q1: Is `parent` a supported formula step field in bd 1.0.5?

**Answer: It is a supported `bd create` field but NOT a supported `pour` field.**

Evidence:
- `bd create --parent` exists and works (creates bd-level parent-child edge).
- `bd create --graph` node struct also accepts `parent` (per memory
  `bd-1-0-5-bd-create-graph-node`).
- Formula step JSON accepts `parent` syntactically (no schema validation error
  on cook or pour), but pour does not translate it to a `--parent` flag on the
  resulting `bd create` call.
- Training volume V (field-guide-05-formulas-and-molecules/OUTLINE.md) does NOT
  list `parent` as a supported formula step field.

## Q2: Does `parent` create bd-level parent-child edges on pour, or mol-internal only?

**Answer: Neither. It is completely ignored -- not even mol-internal hierarchy.**

Test: Poured a minimal formula with 3 steps (`root` epic, `child-a` task with
`parent: "root"`, `child-b` task with `parent: "root"` + `depends_on:
["child-a"]`).

Results:

| Query | Expected (if parent worked) | Actual |
|-------|----------------------------|--------|
| `bd show child-a` PARENT section | `root` epic ID | molecule root ID |
| `bd list --parent=<root-epic>` | child-a, child-b listed | "has no children" |
| `bd list --parent=<mol-root>` | root epic only | root epic + child-a + child-b (all flat) |
| `bd dep tree <root-epic>` | shows child-a, child-b as children | shows only the parent-child link to mol root |
| `bd mol show` tree | root > child-a, child-b | all three as flat siblings under mol root |
| `bd epic close-eligible` | root epic eligible when children close | "No epics eligible for closure" (epic has 0 children) |

**Consequence:** A formula that uses `parent` to create epic > task hierarchy
will produce a flat molecule where the epic sits as a childless sibling of its
intended children. The epic can never become close-eligible (it has no children
to complete), so it's stuck open forever unless manually closed.

## Q3: If parent doesn't wire bd-level edges, what's the correct formula pattern?

**Three options (in order of preference):**

### Option A: Post-pour fixup (works today)

After pour, manually re-parent the children:

```bash
# Pour the formula
bd mol pour my-formula --var name=foo

# Re-parent children to the formula's root epic
bd update <child-a-id> --parent <root-epic-id>
bd update <child-b-id> --parent <root-epic-id>
```

This is tedious for large formulas but works with current bd.

### Option B: File a bd enhancement / bug

Request that `bd mol pour` translate the formula step `parent` field into
`--parent` on the created bead, so parent-child edges are wired at pour time.
This is the natural expectation: `parent` is a real `bd create` field, and
formula steps already successfully translate `depends_on`, `labels`, and
`priority`. Treating `parent` the same way is consistent.

**Recommendation: File this as a bd bug.** The field is accepted without error,
has a clear semantic mapping to `bd create --parent`, and its silent-drop
behavior causes data-integrity issues (orphaned epics, broken close-eligible).

### Option C: Use `bd create --graph` instead of formulas

The `--graph` node struct supports `parent` and `edges` and does create bd-level
edges. However, this loses all formula features (variables, composition,
versioning, cook/pour/wisp lifecycle).

## Q4: Which extra step fields are recognized vs silently ignored?

| Step field | `bd create` flag | Recognized by pour? | Evidence |
|------------|-----------------|---------------------|----------|
| `type` | `--type` | YES | Steps created with correct issue_type |
| `title` | positional / `--title` | YES | Titles match formula |
| `description` | `--description` | YES | Descriptions match formula |
| `priority` | `--priority` | YES | P2/P3 correctly applied |
| `labels` | `--labels` | YES | `["delete-me", "spike-test"]` present |
| `depends_on` | `--deps` | YES | Blocks edges correctly wired between steps |
| `parent` | `--parent` | **NO -- silently ignored** | All steps parented to mol root |
| `skills` | `--skills` | **NO -- silently ignored** | Not present in `bd show --json` output |
| `waits_for` | `--waits-for` | **UNTESTED** (formula uses `children-of(X)` syntax, not a plain ID; needs separate investigation) | N/A |

---

## Recommended actions

1. **File a bd bug** for `parent` being silently ignored by pour. It should
   either be wired to `--parent` or rejected with an explicit error. Silent
   drop is the worst outcome.

2. **File a bd bug** for `skills` being silently ignored by pour. Same
   rationale -- the field exists on `bd create --skills`.

3. **Audit existing formulas** (flowdoc-generate, flowdoc-html,
   flowdoc-maintain, code-health-audit) that use `parent` and determine which
   ones are affected by orphaned epics / broken close-eligible.

4. **Investigate `waits_for`** separately -- the `children-of(X)` syntax is
   formula-level and may have different plumbing than the other fields.

---

## Test artifacts

- Test formula: `.beads/formulas/spike-parent-test.formula.json` (deleted)
- Test molecule: `bead_chain-mol-k2l` (burned via `bd mol burn`)
- No persistent artifacts remain.
