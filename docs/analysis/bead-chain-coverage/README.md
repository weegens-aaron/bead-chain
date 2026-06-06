# bead-chain Capability Coverage Analysis

**Epic:** `bead_chain-10f` — Analyze bead-chain capability coverage vs the beads
feature surface.

**The question:** bead-chain is a queue driver that chains the `bd ready`
frontier into code-puppy/wiggum's `/goal` loop, one bead at a time. The beads
**field guide** (`../../../GOAT/training/beads/docs`, 9 chapters) documents the
full bd 1.0.4 feature surface. For each capability area we ask:

1. **AVAILABLE** — what does the field guide say bd offers? *(chapter ref)*
2. **LEVERAGED** — what does bead-chain actually use? *(source `file:line`)*
3. **GAPS** — what's missing, with a P0–P4 severity and a one-line follow-up.

Every section is filled from [`_template.md`](./_template.md). The final
synthesis (`bead_chain-hkb`) is a **mechanical merge** of the GAPS tables plus
the matrix below — no new analysis, just consolidation.

## Where findings live

```
docs/analysis/bead-chain-coverage/
├── README.md          ← you are here (index + matrix skeleton)
├── _template.md       ← the per-section shape (underscore = not a finding)
├── 01-anatomy.md
├── 02-dependency-graph.md
├── 03-status-lifecycle.md
├── 04-memories-recall.md
├── 05-formulas-molecules.md
├── 06-gates-coordination.md
├── 07-swarms.md
├── 08-data-layer.md
└── 09-quality-hygiene.md
```

## The 9 capability areas

| #   | Capability area      | Section file                                        | Field-guide chapter                              | Audit bead       |
| --- | -------------------- | --------------------------------------------------- | ------------------------------------------------ | ---------------- |
| 1   | Anatomy of a bead    | [`01-anatomy.md`](./01-anatomy.md)                  | `field-guide-01-anatomy-of-a-bead.html`          | `bead_chain-bn4` |
| 2   | Dependency graph     | [`02-dependency-graph.md`](./02-dependency-graph.md)| `field-guide-02-dependency-graph.html`           | `bead_chain-xoq` |
| 3   | Status lifecycle     | [`03-status-lifecycle.md`](./03-status-lifecycle.md)| `field-guide-03-status-lifecycle.html`           | `bead_chain-npn` |
| 4   | Memories & recall    | [`04-memories-recall.md`](./04-memories-recall.md)  | `field-guide-04-memories-and-recall.html`        | `bead_chain-a10` |
| 5   | Formulas & molecules | [`05-formulas-molecules.md`](./05-formulas-molecules.md) | `field-guide-05-formulas-and-molecules.html` | `bead_chain-5xh` |
| 6   | Gates & coordination | [`06-gates-coordination.md`](./06-gates-coordination.md) | `field-guide-06-gates-and-coordination.html` | `bead_chain-5cd` |
| 7   | Swarms               | [`07-swarms.md`](./07-swarms.md)                    | `field-guide-07-swarms.html`                     | `bead_chain-jmo` |
| 8   | Data layer (Dolt)    | [`08-data-layer.md`](./08-data-layer.md)            | `field-guide-08-data-layer.html`                 | `bead_chain-p6o` |
| 9   | Quality & hygiene    | [`09-quality-hygiene.md`](./09-quality-hygiene.md)  | `field-guide-09-quality-and-hygiene.html`        | `bead_chain-tl0` |

## Capability matrix (synthesis fills this in)

**Skeleton — `bead_chain-hkb` populates the cells from each section's findings.**
`Leveraged?` = Full / Partial / None. `Top gap sev` = highest P0–P4 in section.

| #   | Capability area      | Available? | Leveraged? | Top gap sev | Gap count | One-line headline |
| --- | -------------------- | ---------- | ---------- | ----------- | --------- | ----------------- |
| 1   | Anatomy of a bead    | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 2   | Dependency graph     | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 3   | Status lifecycle     | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 4   | Memories & recall    | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 5   | Formulas & molecules | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 6   | Gates & coordination | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 7   | Swarms               | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 8   | Data layer (Dolt)    | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |
| 9   | Quality & hygiene    | _TBD_      | _TBD_      | _TBD_       | _TBD_     | _TBD_             |

## How to fill a section (for audit beads)

1. Open the matching `NN-<area>.md` stub (already seeded from the template).
2. Read your field-guide chapter (the HTML files in the `docs/` dir above) for
   **AVAILABLE**.
3. Read the listed bead-chain modules for **LEVERAGED** — cite `file:line`.
4. Record every **GAP** with a P0–P4 severity and a one-line follow-up.
5. Flip the section's `Status` to `done`. Do **not** touch other sections.

## Source map (bead-chain modules per area)

These are starting points, not an exhaustive list — follow the code.

| Area                 | Primary bead-chain modules                                  |
| -------------------- | ---------------------------------------------------------- |
| Anatomy              | `prompt.py` (`format_bead_as_goal`, `prompt.py:258`)       |
| Dependency graph     | `lifecycle.py` (`pick_next_bead`, `_reject_if_blocked`)    |
| Status lifecycle     | `lifecycle.py`, `state.py`                                 |
| Memories & recall    | `prompt.py`                                                |
| Formulas & molecules | `lifecycle.py` (`rollup_completed_epics`, `_has_fan_out_gate_issue`) |
| Gates & coordination | `lifecycle.py`, `close_guard.py`                          |
| Swarms               | `lifecycle.py`, `register_callbacks.py`                   |
| Data layer (Dolt)    | `lifecycle.py`, `register_callbacks.py`, `state.py`       |
| Quality & hygiene    | `close_guard.py`, `lifecycle.py`                          |
