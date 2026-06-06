# Formulas & Molecules — Coverage Findings

| Field            | Value                                                              |
| ---------------- | ----------------------------------------------------------------- |
| Capability area  | `formulas-molecules`                                              |
| Field-guide ref  | `field-guide-05-formulas-and-molecules.html` (chapter 5)          |
| Bead-chain owner | `bead_chain-5xh`                                                  |
| Primary modules  | `lifecycle.py`, `beads.py`                                        |
| Status           | `done`                                                            |

---

## 1. AVAILABLE — what the field guide documents

Chapter 5 ("Formulas & Molecules — Rig → Cook → Run") owns bd's
**composition layer**: reusable plans (formulas), their compiled/instantiated
forms (proto / mol / wisp), and the verbs that move work between phases. Citing
`field-guide-05-formulas-and-molecules.html`:

- **§ I — Rig → Cook → Run.** A *formula* is a file (`.formula.json` /
  `.formula.toml`) with a `formula` id, a `type` enum
  (`workflow` | `expansion` | `aspect`), and a `steps` array — **each step
  becomes a child issue when cooked/poured**. `bd formula list` discovers them
  along a search-path (nearest wins); `bd formula convert` round-trips
  JSON ⇄ TOML. Steps may carry `depends_on`, `{{variable}}` placeholders, and
  **gate specs that are auto-created on pour** (→ ch06).
- **§ II — Five ways to compose.** `extends` (inherit parent steps),
  `compose.aspects` (cross-cutting concerns woven at join points),
  `compose.expansions` (macro-like step groups at splice points),
  **`bond`** (runtime polymorphic combine of formula×formula / proto×mol /
  mol×mol — `sequential` default, `parallel`, `conditional`), and **`distill`**
  (reverse: extract a formula from an existing ad-hoc epic).
- **§ III — Cook: compile-time vs runtime.** `bd cook` compiles a formula.
  Flags: `--var k=v` (substitution, auto-enables runtime), `--mode
  compile|runtime`, `--persist` (write a template-labelled proto epic+children),
  `--force`, `--dry-run`, `--prefix <str>`, `--search-path`. Compile mode keeps
  `{{vars}}` open for reuse; runtime fills them and pours concrete work.
- **§ IV — Phases (solid → liquid → vapor).** `proto` (solid, a
  template-labelled epic), `mol` (liquid — a poured molecule = **live epic +
  children DAG** you work), `wisp` (vapor — ephemeral, `dolt_ignored`,
  TTL-compacted). Transitions: **pour** (proto→mol, persistent + Dolt-versioned +
  git-synced + full audit trail), **wisp** (proto→ephemeral), **bond** (mol→mol),
  **squash** (mol→digest), **promote** (wisp→bead), **burn** (wisp→discarded,
  cascade-delete no trace).
- **§ V — Wisps, mol-types & promote.** *wisp-types*: `heartbeat`, `ping`,
  `patrol`, `gc_report`, `recovery`, `error`, `escalation`. **`mol-type`** is the
  companion axis: **`work`** (default — a DAG of tasks), **`swarm`** (multi-agent;
  skills routing + parallel groups, → ch07), and **`patrol`** (a *recurring
  operational molecule* — monitoring loops). `bd promote` condenses a wisp into a
  permanent bead (keeps id/links/events/comments); wisp GC is **time-based**
  (`--age`, `--closed`, `--exclude-type`), while `mol stale` is **graph-pressure**
  based.
- **§ VI — Thirteen verbs, one namespace** (`bd mol`, alias `bd protomolecule`):
  `show`, `pour`, `wisp`, `bond`, `squash`, `burn`, `distill`, `current`
  (step indicators: `[done] [current] [ready] [blocked] [pending]`), `progress`
  (completed/total, rate, ETA), `ready --gated` (gate-resume dispatch), `seed`
  (search-path health), `stale [--blocking]` (complete-but-unclosed mols), and
  `last-activity`.

## 2. LEVERAGED — what bead-chain actually uses

bead-chain consumes the molecule layer at exactly **one touch-point — epic
rollup** — and treats a poured molecule as nothing more than an ordinary
`epic + children` graph. It calls **none** of the `bd mol` / `bd cook` /
`bd formula` verb families.

- **Epic rollup via `bd epic close-eligible` (the one consumer).**
  `rollup_completed_epics()` (`lifecycle.py:282`) calls
  `close_eligible_epics()` (`beads.py:526`), which shells out to
  `bd epic close-eligible --json` (`beads.py:567`). It is invoked **once per
  session**, only on the empty-queue drain pass (`lifecycle.py:519`), as the
  documented mitigation for the over-close cascade bug (`bead_chain-tfn`). A
  poured molecule's live epic is rolled up by this path **identically to a
  hand-authored epic** — bd owns the cascade; bead-chain just triggers it.
- **Molecule id structure is opaque to bead-chain.** There is **zero**
  id-segment parsing anywhere in the plugin: a `grep` for
  `split`/`rsplit`/`partition`/regex on ids returns nothing, and
  `close_eligible_epics()` normalises whatever shape bd emits without inspecting
  the id (`beads.py:567-585`). Three-segment formula-epic ids
  (`<prefix>-mol-isk`) flow through untouched — locked in by
  `tests/test_formula_epic_rollup.py` (`test_multi_segment_ids_not_truncated`).
- **Formula fan-out gates: a gate-shaped workaround, not mol awareness.**
  `_has_fan_out_gate_issue()` (`lifecycle.py:628`) parses a bead's
  `waits_for: children-of(<spawner>)` field — a marker that originates from
  formula fan-out — and refuses to drive the bead while the spawner has unclosed
  children (`lifecycle.py:576`). This is the `blocks`/gate path (analysed in
  detail in [`06-gates-coordination.md`](./06-gates-coordination.md)), **not**
  molecule-phase logic; it never reads `mol-type`, phase, or step state.
- **NOT leveraged (explicit).** A repo-wide grep for the molecule verbs
  (`mol pour|mol wisp|mol squash|mol burn|mol distill|mol current|mol progress|mol stale|mol ready|bd cook|formula|wisp|patrol|protomolecule`)
  returns **no matches** in any source module:
  - `bd cook` / `bd formula list|convert` — bead-chain never compiles or
    discovers formulas (it consumes their *poured output* as plain beads).
  - `bd mol pour | wisp | bond | squash | burn | distill | promote` — none used.
  - `mol-type` (`work` / `swarm` / `patrol`) — never read; **every molecule is
    driven as if it were `work`**, one bead at a time.
  - wisp-types and the ephemeral `dolt_ignored` lifecycle — unhandled; no
    `promote`/`burn`/`squash`.
  - `mol current` / `mol progress` / `mol stale` / `mol last-activity` — never
    called; bead-chain has no molecule-workflow position or staleness probe.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                                                                                              | Severity | Recommended follow-up (one line)                                                                                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------- |
| 1   | **3-segment formula-epic id rollup** — the originally-suspected gap: `<prefix>-mol-isk` epics fail to roll up. **Investigated & disproven** (`bead_chain-0kx`): no id parsing exists; bd 1.0.4 rolls up 2- and 3-segment ids identically. | P4       | None — regression-locked by `tests/test_formula_epic_rollup.py`; keep the test, do not reintroduce id parsing.    |
| 2   | **`patrol` mol-type blindness (recurring ops).** A poured `patrol` molecule (recurring monitoring loop) is driven as plain `work`; once its children close, `close_eligible_epics()` (`beads.py:526`) closes the epic — defeating its recurring nature. | P2       | File a bead to detect `mol-type=patrol` (or template label) and exclude such epics from `bd epic close-eligible`. |
| 3   | **`swarm` mol-type blindness.** A `swarm` molecule (multi-agent, skills routing + parallel groups) is drained sequentially one bead at a time; parallel-group / skills execution metadata is ignored. | P2       | Defer to swarms audit (`bead_chain-jmo` / [`07-swarms.md`](./07-swarms.md)); cross-referenced here, not re-filed. |
| 4   | **wisp ephemerality blindness.** bead-chain has no wisp concept; if any wisp-type bead (heartbeat/ping/patrol/recovery) leaks onto `bd ready` it is neither excluded (`EXCLUDED_TYPES`, `beads.py:41`) nor promotable/burnable — it could be handed to `/goal` as if it were real code work. | P2       | File a bead to confirm whether wisps surface on `bd ready`; if so, add wisp issue-types to the exclusion filter.  |
| 5   | **No `mol stale --blocking` probe.** A complete-but-unclosed molecule can wedge the `bd ready` frontier; bead-chain only ever sweeps via the once-per-session `close-eligible`, never runs `bd mol stale`. | P3       | File a bead to run `bd mol stale --blocking` on the drain/probe pass before declaring the queue empty.            |
| 6   | **Once-per-session, cascade-disabled rollup** (`lifecycle.py:502-519`) means a formula-molecule's *parent* epic may stay open one session longer than bd's native cascade would close it. | P3       | Accepted tradeoff for the over-close fix (`bead_chain-tfn`); monitor only — re-file only if stale parents bite.   |

### Severity rubric

| Sev | Meaning                                                                       |
| --- | ---------------------------------------------------------------------------- |
| P0  | Correctness/data-loss hazard in the drain loop (e.g. closes wrong bead).      |
| P1  | Feature silently dropped where it changes which bead runs or how it's framed. |
| P2  | Feature unused where leveraging it would materially improve goal quality.     |
| P3  | Minor gap; workaround exists or impact is narrow.                            |
| P4  | Cosmetic / future-proofing only.                                            |

---

## Notes / open questions

- **The headline 3-segment id gap is a non-issue.** The task brief and
  `bead_chain-0kx` both flagged formula-epic ids (`<prefix>-mol-isk`) as the
  suspected rollup failure. The grounded finding is the opposite: bead-chain does
  **no** id parsing, so id segment-count is irrelevant, and bd 1.0.4 rolls up
  both shapes the same. It is recorded here as **P4 (disproven / regression-locked)**
  so the synthesis matrix carries the verdict rather than re-litigating it.
- **The real molecule gap is mol-type blindness, not ids.** bead-chain flattens
  the §V `mol-type` axis: `work` / `swarm` / `patrol` are all driven as `work`.
  The `patrol` (Gap 2) and `swarm` (Gap 3) cases are where leveraging mol-type
  would change behaviour — `patrol` because rollup actively *closes* something
  meant to recur, `swarm` because sequential draining throws away parallelism.
- **Gate-shaped, not mol-shaped.** The only formula-adjacent runtime handling
  (`_has_fan_out_gate_issue`, `lifecycle.py:628`) is really a *gate* workaround;
  its full analysis lives in the gates section. It is noted here only so the
  synthesis doesn't double-count it as molecule coverage.
- Gaps 2–5 are the candidate follow-up beads; per the epic plan they are filed by
  the synthesis bead (`bead_chain-hkb`), not here.
