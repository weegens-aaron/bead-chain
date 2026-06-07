# Anatomy of a Bead — Coverage Findings

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Capability area  | `anatomy`                                                             |
| Field-guide ref  | `field-guide-01-anatomy-of-a-bead.html` (chapter 1)                   |
| Bead-chain owner | `bead_chain-bn4`                                                      |
| Primary modules  | `prompt.py` (`format_bead_as_goal`), `beads.py` (`is_excluded_type`) |
| Status           | `done`                                                                |

---

## 1. AVAILABLE — what the field guide documents

Chapter 1 frames the bead as "the smallest unit of memory in bd" and enumerates
the full data object: **9 built-in issue types + 1 pseudo-type**, **~35 fields**,
**12 edge kinds**, and **7 statuses** (Colophon: "9 types · 35 fields · 12 edge
kinds · 7 statuses"). Edges are chapter 2's turf (`bead_chain-xoq`); statuses are
chapter 3's (`bead_chain-npn`). This section owns **fields** and **types**.

### Type taxonomy (§ III "Nine types, one shape")

Every type carries the *same* fields and graph machinery; the type only signals
intent. Source: `field-guide-01-anatomy-of-a-bead.html` § III, `ALL_TYPES`.

| Type        | Field-guide gloss                                              |
| ----------- | ------------------------------------------------------------- |
| `task`      | The unit of work; claimed from `bd ready` when blockers close |
| `bug`       | A defect; carries reproduction notes                          |
| `feature`   | A new capability; often decomposed into child tasks           |
| `chore`     | Housekeeping (deps, docs, CI hygiene)                         |
| `epic`      | Hierarchical **container**; children inherit the prefix       |
| `decision`  | ADR-grade call; conventionally uses the `design` field        |
| `spike`     | Time-boxed research; produces knowledge, not code             |
| `story`     | User-facing narrative ("As a…, I want…, So that…")            |
| `milestone` | **Coordination container**; all children must close           |
| `event`     | Pseudo-type for operational state (Vol III)                   |

- **Aliases** (§ III): `enhancement`/`feat` → `feature`; `dec`/`adr` →
  `decision`. Custom types via `bd config set types.custom "…"`.
- **Lint contract** (§ III): `bd lint` / `--validate` enforce per-type sections —
  tasks & features require *Acceptance Criteria*; bugs additionally require
  *Steps to Reproduce*; epics require *Success Criteria*; `decision`
  conventionally uses `design`.

### The ~35-field set (§ IV "Thirty-five fields, one bead")

Source: `field-guide-01-anatomy-of-a-bead.html` § IV, `FIELD_GROUPS`.

| Group               | Fields                                                                              |
| ------------------- | ---------------------------------------------------------------------------------- |
| Identity            | `id`, `title`, `type`                                                               |
| Core metadata       | `status`, `priority`, `assignee`, `labels`, `due`, `defer`, `estimate`             |
| Content             | `description`, `acceptance`, `design`, `notes`, `context`, `body-file`/`stdin`      |
| Graph / structure   | `parent`, `deps`, `waits-for`, `external-ref`, `spec-id`                            |
| Composition / exec  | `ephemeral`, `mol-type`, `wisp-type`, `skills`, `metadata`                          |
| Event-only          | `event-actor`, `event-category`, `event-payload`, `event-target`                   |
| System / behavioral | `no-history`, `no-inherit-labels`, `validate`, `dry-run`, `graph`/`-f`, `silent`   |
| Timestamps (managed)| `created_at`, `updated_at`, `started_at`, `closed_at`, `close_reason`              |

The guide flags the **load-bearing** subset (§ II): "The metadata fields —
status, priority, assignee, updated — are the load-bearing columns. They are how
`bd ready` decides what an agent should do next." Composition/graph/event fields
are deferred to chapters 5, 7, 2, and Vol III respectively and are audited there.

---

## 2. LEVERAGED — what bead-chain actually uses

The goal prompt is assembled entirely by `format_bead_as_goal()`
(`prompt.py:258`). It is the **only** place a bead's anatomy is rendered for the
LLM. It reads exactly **six** fields off the bead dict:

| Field (bd JSON key) | Read at        | How it's surfaced in the prompt                          |
| ------------------- | -------------- | -------------------------------------------------------- |
| `id`                | `prompt.py:283`| `Complete beads issue {id}: …`                           |
| `title`             | `prompt.py:284`| prompt headline (defaults to `(no title)`)               |
| `description`       | `prompt.py:285`| prompt body (defaults to `(no description)`)             |
| `issue_type`        | `prompt.py:286`| `- Type: {issue_type}` metadata line                     |
| `priority`          | `prompt.py:287`| `- Priority: P{priority}` metadata line                  |
| `parent` (epic)     | `prompt.py:293`| `- Parent epic: …` via `_format_epic_metadata_lines`     |

The parent-epic line is enriched out-of-band: `_format_epic_metadata_lines`
(`prompt.py:87`) resolves the parent id with `extract_parent_epic_id`
(`beads.py:295`, canonical key `parent`, `beads.py:108`), then `_fetch_epic_context`
(`prompt.py:67`) shells out to `bd show` and pulls the epic's **`title`**
(`prompt.py:82`) plus a ≤280-char first-paragraph excerpt of its **`description`**.
So even the epic only contributes `id`/`title`/`description`.

**Type taxonomy — partially leveraged.** bead-chain reasons about types in three
narrow places, and treats every other type as generic work:

- **`epic` exclusion** (acceptance criterion for this bead): `EXCLUDED_TYPES =
  ("epic",)` (`beads.py:41`) drives both a server-side `--exclude-type=epic` arg
  (`_exclude_type_arg`, `beads.py:98`) on every `bd ready` / `bd list` query
  *and* a client-side re-filter via `is_excluded_type` (`beads.py:44`, case-
  insensitive on `issue_type`, `beads.py:64`). The double filter is deliberate
  defence-in-depth: the server-side flag "has been observed to leak epics
  through in the wild" (`beads.py:217-225`, `next_ready`). **Confirmed working
  as documented.**
- **`bug` escalation**: `BLOCKING_BUG_TYPES = ("bug",)` (`beads.py:88`) lets
  `next_blocking_bug` (`beads.py:392`) jump a ready bug ahead of the queue when
  `dependent_count > 0` (`beads.py:430`).
- **`bug` triage-verify**: `is_triaged_bug` (`prompt.py:230`) only flips a bead
  into the triage-verification preamble when `issue_type == "bug"`
  (`prompt.py:254` reads `description` for the `[bead-chain:triaged]` marker).

**Everything else is dropped.** Confirmed against this bd 1.0.4 build's actual
JSON contract: `bd ready --json` emits
`acceptance_criteria, comment_count, created_at, dependencies, dependency_count,
dependent_count, description, id, issue_type, labels, parent, priority, status,
title, updated_at`, and `bd show … --json` adds `assignee`, `started_at`. So the
dict already in `format_bead_as_goal`'s hand **carries `acceptance_criteria` and
`labels`** — and the formatter reads neither (no reference to either key exists
anywhere in `prompt.py`; verified by grep). `design`, `notes`, `estimate`,
`due`, `defer`, `context` were not present in the observed payloads (bd appears
to omit them when unset), and `assignee` is present only in `bd show` output;
none of them is referenced by any plugin module either way.

Net: of ~35 documented fields, bead-chain surfaces **6** (id, title,
description, type, priority, parent-epic), reasons about **1** type specially
for selection (`bug`) and **1** for exclusion (`epic`), and ignores the rest —
including fields it is *already holding in the ready-bead dict*.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                                      | Severity | Recommended follow-up (one line)                                                                                                  |
| --- | ----------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `acceptance_criteria` is present in the `bd ready --json` dict but never read into the goal prompt — the agent must re-derive "done" from the description, then LLM judges close against criteria the prompt never showed. | P1       | File a bead to render `bead["acceptance_criteria"]` as an `## Acceptance Criteria` block in `format_bead_as_goal` (`prompt.py:258`). |
| 2   | `design` (the ADR/design-rationale field, the conventional home for `decision`-type beads per ch01 lint contract) never reaches the prompt. | P2       | File a bead to surface `design` when populated, especially for `decision`/`spike` beads.                                         |
| 3   | `labels` are present in the ready dict yet ignored; bead-chain even hand-rolls a `[bead-chain:triaged]` *description* sentinel (`prompt.py` `TRIAGE_MARKER`) because labels were "a bd feature we haven't verified across versions" — now verified present. | P2       | File a bead to (a) surface labels in the prompt and (b) reconsider moving the triage marker onto a real bd label.               |
| 4   | `milestone` is a coordination **container** ("all children must close", ch01) but is **not** in `EXCLUDED_TYPES` (`beads.py:41`) — only `epic` is. A ready milestone could be driven as work and fail at `bd close` with open children, the same strand-the-chain hazard the epic filter exists to prevent (the `beads.py:40` comment literally anticipates `'milestone'`). | P1       | File a bead to add `milestone` to `EXCLUDED_TYPES` (one-line edit) plus a regression test.                                      |
| 5   | `notes` (the persistent scratchpad) and `context` (agent-injected situational context) are never surfaced — cross-iteration scratch state is invisible to the next run's agent. | P3       | File a bead to fold `notes`/`context` into the recovery preamble when present.                                                  |
| 6   | `estimate`, `due`, `defer` are ignored — no effort/deadline awareness in the drain loop (low impact for a serial one-at-a-time driver). | P3       | Consider surfacing `due`/`estimate` only if scheduling-aware ordering is ever wanted; otherwise document as intentional.        |
| 7   | `assignee` is dropped (present only in `bd show` output) — fine for a single-agent loop but blind to multi-agent ownership. | P4       | No action unless bead-chain ever drives a shared/multi-actor queue.                                                             |

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

- **Why gap #1 is P1, not P2.** The "When you believe this is done" checklist
  (`prompt.py:310`) tells the agent to run linters/tests/commit and notes "LLM
  judges will verify completion" — but the agent never sees the bead's own
  `acceptance_criteria`, so it is judged against a contract the prompt withheld.
  This changes *how the bead is framed*, which is the P1 line in the rubric.
  The data is free: it's already a key on the dict bead-chain passes in.
- **Why gap #4 is P1, not a filed bug.** It is a genuine strand-the-chain
  correctness hazard of the same family as the epic leak, but per the analysis
  framework this section *records gaps and recommends follow-up beads* rather
  than filing them itself (the synthesis bead `bead_chain-hkb` consolidates).
  It is not an incidental bug discovered while working an unrelated goal — it
  *is* this audit's deliverable — so the bug-discovery protocol doesn't apply.
- **Field-availability nuance.** `design`/`notes`/`estimate`/`due`/`defer` did
  not appear in the observed `bd ready` / `bd show` JSON (bd seems to omit
  unset fields), so for those, "dropped" means "the code reads no such key" —
  surfacing them is contingent on bd populating them. `acceptance_criteria` and
  `labels`, by contrast, are *demonstrably present and demonstrably ignored*.
- **Cross-section seam.** The note-vs-comment discussion (recording *what
  happened on this bead*) overlaps chapter 4 (`bead_chain-a10`), which already
  notes bead-chain prompts neither. This section counts only the static
  anatomy fields to avoid double-counting; the memory-injection angle lives
  there.
- Gaps #1–#7 are recommendations for the synthesis bead (`bead_chain-hkb`);
  per the framework this section files no beads itself.
