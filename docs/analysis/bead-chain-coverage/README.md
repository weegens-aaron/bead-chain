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
the matrix below — no new analysis, just consolidation. The prioritized,
deduped issues-and-gaps breakdown lives in **[`GAPS.md`](./GAPS.md)**.

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

## Capability matrix (filled by the synthesis bead `bead_chain-hkb`)

`Leveraged?` = Full / Partial / None. `Top gap sev` = highest P0–P4 in section.
`Gap count` = actionable gaps recorded in that section (cross-ref/disproven rows
noted in parentheses). The prioritized, deduped breakdown lives in
[`GAPS.md`](./GAPS.md).

| #   | Capability area      | Available? | Leveraged? | Top gap sev | Gap count | One-line headline |
| --- | -------------------- | ---------- | ---------- | ----------- | --------- | ----------------- |
| 1   | Anatomy of a bead    | Yes — ~35 fields, 9+1 types | **Partial** — 6 fields surfaced; `epic` excluded, `bug` escalated | **P1** | 7 | Free fields already on the `bd ready` dict (`acceptance_criteria`, `labels`) are dropped; `milestone` not excluded |
| 2   | Dependency graph     | Yes — 12 typed edges | **Partial** — `blocks` full + defence-in-depth; `waits-for` partial; `parent-child` structural | P2 | 5 (+1 cross-ref) | The 10 advisory edges are never surfaced as context; generic `waits-for` unhonored off `bd ready` |
| 3   | Status lifecycle     | Yes — 7 statuses, 10 idiomatic tx | **Partial** — 1 status read; 2 idiomatic + 1 freeform tx driven | P2 | 7 | Only `in_progress` is inspected; `pinned`/`hooked` mid-flight strands are invisible to recovery |
| 4   | Memories & recall    | Yes — 4 verbs + prime injection | **None** | P2 | 3 | Zero of bd's memory layer is bridged into the goal prompt; no `bd remember` nudge at done |
| 5   | Formulas & molecules | Yes — 13 mol verbs, cook, formula | **Partial** — `epic close-eligible` rollup only | P2 | 5 (1 disproven) | `mol-type` blindness (`patrol`/`swarm`/wisp driven as plain work); 3-segment id gap disproven |
| 6   | Gates & coordination | Yes — gate + merge-slot verb families | **Partial** — `blocks`-edge implicit + one fan-out workaround | **P1** | 6 | `gate` beads leak onto `bd ready` as drivable work; `bd gate check` never advances gates |
| 7   | Swarms               | Yes — swarm verbs, waves, audit log | **Partial** — atomic `--claim`; skills prose pass-through | **P1** | 5 | `molecule` beads leak onto `bd ready`; `execution_*` hints dropped (sequential-only is by-design) |
| 8   | Data layer (Dolt)    | Yes — `dolt push/pull/remote` | **Partial** — writes local DB; consumes no sync surface | **P1** | 5 | Nobody in the documented loop runs `bd dolt push` — cross-machine durability falls through a seam |
| 9   | Quality & hygiene    | Yes — lint, cycles, orphans, stale, … | **None** for graph hygiene (`close-eligible` ≠ ch09) | P2 | 6 | No `bd lint` gate — bead-chain drives beads missing their required `## Acceptance Criteria` |

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
