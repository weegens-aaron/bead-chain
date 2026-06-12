# ADR 0003 — Concise inline "why" + cross-reference; deep design rationale lives in the existing `__docs/` FlowDocs

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| Status     | Accepted                                                              |
| Date       | 2026-06-12                                                            |
| Bead       | `bead_chain-vx1`, under epic `bead_chain-dyt` (Marketplace review remediation) |
| Source     | Marketplace code review finding (excessive inline documentation)       |
| Supersedes | —                                                                     |

## Context

The marketplace code review flagged **excessive inline documentation**: many
functions carry docstrings and comment blocks longer than the code they
explain. The canonical example is `beads.open_blocker_ids` — ~48 lines of
docstring for ~30 lines of logic — with a "Why this exists" narrative that
retells the `bdboard-oals` regression, the recovery-tier bypass, FB-10, and the
molecule fan-out-gate distinction.

The important observation: **that narrative is not unique to the code.** The
exact same rationale already lives, in fuller form, in the maintainer
documentation:

- `__docs/Flows/BeadClaimAndBlockerRecheck.md`
- `__docs/Flows/StrandedBeadRecovery.md`
- `__docs/Flows/NextBeadSelectionWaterfall.md`
- `__docs/Features/WorkTimeBlockerGate.md`
- plus the two existing ADRs in `notes/decisions/`.

So the inline mega-comments are, in large part, a **DRY violation** — a second
(and now divergent-risk) copy of design rationale that already has a documented
home. The volume also hurts navigation: you scroll past a page of history to
find fifteen lines of logic.

## Decision

**Adopt Alternative 1: keep concise docstrings inline (the essential *why* +
the non-obvious invariant), and remove the historical/narrative rationale from
the code, cross-referencing the existing `__docs/` FlowDocs / ADRs where the
deep story already lives.**

Concretely, for each over-documented runtime symbol:

1. Keep a docstring that states **what** it returns / does and the **one or two
   non-obvious invariants** a caller must know (e.g. "soft-fails to `[]` — never
   strand the chain; the close-guard is the backstop").
2. Keep the **"why" in a sentence**, not a section. If the *why* is a multi-step
   historical story (a past regression, a defence-in-depth argument, an audit
   finding), reduce it to one line and **link the FlowDoc / ADR** that owns it
   (e.g. `See __docs/Flows/StrandedBeadRecovery.md`).
3. Delete the retold-elsewhere narrative blocks (the `Why this exists` /
   numbered-history subsections, repeated FB-/bead-id war stories) from the
   code. The FlowDocs remain the single source of truth for the deep rationale.
4. Constant-definition comments shrink to the invariant + a pointer, not a
   paragraph (e.g. `BLOCKING_DEP_TYPES`, `RECOVERABLE_STATUSES`,
   `SATISFIED_BLOCKER_STATUSES`).

This ADR is the standing guidance for the rest of the marketplace-review pass
and for new code: **co-locate the *why*, externalise the *story*.**

## Rationale

- **DRY, honestly applied.** The deep rationale already has a home in
  `__docs/`. Duplicating it inline means two copies that drift — and the inline
  copy is the one most likely to go stale, because a maintainer updating a flow
  edits the FlowDoc, not a buried docstring. One source of truth, cross-linked.
- **Co-location is preserved where it earns its keep.** The essential *why* and
  the load-bearing invariants stay next to the code — that is exactly the value
  the original inline docs were reaching for. We keep the signal, drop the
  archive.
- **Navigation.** A 15-line function should read as ~15 lines, not 60. Trimming
  restores the signal-to-noise that the review correctly flagged.
- **The doc system already exists (anti-YAGNI for Alternative 3).** A new
  `DESIGN.md` would be a *fourth* home for rationale alongside `__docs/Flows`,
  `__docs/Features`, and `notes/decisions/`. Inventing it duplicates
  infrastructure we already maintain.

## Alternatives considered

1. **Keep inline, trim to essential context only (chosen).** Remove historical
   rationale, keep the *why* + invariants, cross-reference the FlowDocs.
2. **Move *all* ADR-style content to `notes/decisions/`, leave concise
   docstrings inline.** *Rejected.* Half-right (concise docstrings is exactly
   what we want) but the destination is wrong: most of this rationale is
   *flow/feature* narrative that already lives in `__docs/`, not *decision*
   records. Forcing it into `notes/decisions/` would itself create duplication
   with the FlowDocs and misuse the ADR log as a narrative dump.
3. **Hybrid: concise docstrings inline + a single `DESIGN.md` with code
   cross-references.** *Rejected.* The "single design doc" already exists —
   it's the `__docs/` FlowDoc set. Adding `DESIGN.md` creates a fourth
   competing home for the same content (DRY/YAGNI violation). We cross-reference
   the existing docs instead of minting a new one.
4. **No change — verbosity acceptable given plugin complexity.** *Rejected.*
   The review is right: the volume duplicates the FlowDocs and hurts
   navigation. Complexity justifies *good* docs, not *redundant* ones.

## Consequences

- **Positive:** code reads at its true size; one source of truth for deep
  rationale; less drift risk; the marketplace-review finding is resolved with a
  repeatable rule for the rest of the pass.
- **Negative / accepted:** a reader who wants the full history now follows a
  cross-reference instead of reading it in place — an acceptable trade, since
  the in-place copy was the stale-prone one. Cross-references must be kept valid
  (FlowDoc filenames are stable; ADR ids are immutable).

## Applied in this bead

As the reference application of this ADR, `beads.py` was trimmed:

- `open_blocker_ids` — the `Why this exists` numbered-history section and the
  retold `bdboard-oals` / FB-10 / fan-out-gate narrative were removed; the
  docstring now states the contract, the two blocking edge types, the optional
  pre-fetch arg, and the soft-fail invariant, and cross-references
  `__docs/Flows/StrandedBeadRecovery.md` and `BeadClaimAndBlockerRecheck.md`.
- `BLOCKING_DEP_TYPES`, `SATISFIED_BLOCKER_STATUSES`, `RECOVERABLE_STATUSES`
  constant comments were reduced to the invariant + a FlowDoc pointer.

Subsequent marketplace-review beads should apply the same rule to `lifecycle.py`,
`prompt.py`, and the remaining modules.
