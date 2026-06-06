# Memories & Recall — Coverage Findings

| Field            | Value                                                       |
| ---------------- | ----------------------------------------------------------- |
| Capability area  | `memories-recall`                                           |
| Field-guide ref  | `field-guide-04-memories-and-recall.html` (chapter 4)       |
| Bead-chain owner | `bead_chain-a10`                                            |
| Primary modules  | `prompt.py`, `register_callbacks.py`, `beads.py`            |
| Status           | `done`                                                      |

---

## 1. AVAILABLE — what the field guide documents

bd 1.0.4 ships a complete, durable, cross-session **knowledge layer** exposed
through four verbs over a keyed kv store. Source: `field-guide-04-memories-and-recall.html`.

- **The four verbs** (§ II "Four verbs, one keyed store"):
  - `bd remember "<text>" [--key K]` — write a memory. With `--key` it's an
    upsert by that exact key; without, the content is slugified into an
    auto-key (still an upsert). Output prefix `Remembered` = insert,
    `Updated` = in-place overwrite.
  - `bd recall <key>` — read one memory back **verbatim** by exact key.
    Missing key → stderr + `exit 1`.
  - `bd memories [<substr>]` — list all memories alphabetically by key, or
    filter by case-insensitive substring of key **or** value. `bd memories
    --json` dumps `{ key: value, …, schema_version: 1 }`. No-match search is
    `exit 0` (the asymmetry-with-`recall` gotcha).
  - `bd forget <key>` — permanently retire one memory. No undo / soft-delete.
- **Always keyed, upsert semantics** (§ III "The key is the contract"):
  there is no append-only mode. Explicit keys are stored verbatim; auto-slugs
  can silently collide and overwrite.
- **Prime-time injection** (§ IV "Prime-time injection") — the load-bearing
  mechanism: `bd prime` is a fast (~600 ms), read-only command that assembles
  a markdown doc containing a `## Persistent Memories` block (all memories,
  sorted lex-by-key, each a level-3 heading). It's wired to fire automatically
  via **`SessionStart`** and **`PreCompact`** hooks that `bd init` writes into
  `.claude/settings.json`. The guide explicitly notes the CLAUDE.md / AGENTS.md
  fallback: agents are told to run `bd prime` manually at the top of every
  session when no host hook exists.
- **Memory vs note vs comment vs kv** (§ V): only **memory** is injected at
  prime and aimed at "future agents"; notes/comments are bead-scoped and die
  with the bead; kv is for machines. "If a human would want to read it next
  week, it's a memory."
- **Persistence across boundaries** (§ VI): memories survive context reset,
  account rotation, and machine boundaries because they round-trip through
  `bd dolt push/pull` over `refs/dolt/data` (cross-links chapter 8, data layer).
- **Hygiene** (§ VII): keep the set small + curated — prime injects *all*
  memories with no recency weighting, truncation cap, or relevance filter.

The premise the guide hammers (§ I "The forgetting problem"): the agent should
**not have to remember to look** — memory must be *injected* into the next
session automatically, because the `MEMORY.md` / discovery-burden approach rots.

## 2. LEVERAGED — what bead-chain actually uses

**Nothing. bead-chain consumes none of bd's memory surface.** This is a verified
negative, not an omission in the audit:

- A full-tree grep for `prime`, `remember`, `recall`, `memories`, and `forget`
  across all plugin `*.py` returns **zero** call sites. The bd subprocess
  wrapper `beads.py` shells out only to `ready`, `list`, `show`, `update`
  (`--claim` / `--status`), `close`, and `epic` subcommands
  (`beads.py:211`–`beads.py:567`) — `bd remember` / `bd recall` / `bd memories`
  / `bd prime` are never invoked.
- The goal prompt is assembled entirely by
  `format_bead_as_goal()` (`prompt.py:258`) from the bead's own
  `title` / `description` / `issue_type` / `priority`, an optional parent-epic
  title+excerpt (`prompt.py:_format_epic_metadata_lines`), one of three mutually
  exclusive preambles (recovery / triage-verify / none), and the appended bug
  protocol (`prompt.py:191`). **No `## Persistent Memories` block, no `bd
  recall` digest, and no `bd memories` output is ever read into the prompt.**
- That prompt is handed straight to `wiggum_state.start(goal_prompt,
  mode="goal")` (`register_callbacks.py:270`–`271`) with no memory-enrichment
  step before or after.
- The "When you believe this is done" checklist (`prompt.py:310`–`312`)
  instructs the agent to (1) run linters, (2) run tests, (3) commit — but
  **never to `bd remember` a durable insight**. The only knowledge-capture
  behavior bead-chain prompts is filing **bugs as beads** via the bug-discovery
  protocol (`prompt.py:191`); general cross-session learnings have no home and
  die with the context window.

Net: bead-chain treats every `/goal` iteration as a context-free unit of work.
Whatever the host (code-puppy/wiggum) injects on its own (e.g. its separate
Kennel memory) is outside bead-chain's control — bead-chain itself bridges
**zero** of bd's documented memory layer into the bead it's about to run.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                  | Severity | Recommended follow-up (one line)                                                                                  |
| --- | ---------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------- |
| 1   | Goal prompt injects no memories — agents start every bead cold and must self-discover repo context. | P2       | File a bead to prepend a `bd memories` / `bd prime` digest into `format_bead_as_goal` so each bead inherits durable project context. |
| 2   | Done-checklist never prompts `bd remember`; cross-session insights learned mid-bead are lost.   | P2       | File a bead to add a "record durable insights via `bd remember --key=…`" step to the `prompt.py` completion checklist. |
| 3   | bd's memory layer and the host (code-puppy) Kennel are two unbridged parallel memory stores.    | P3       | File a bead to decide policy: bridge `bd memories` ↔ Kennel, or document the split so insights aren't recorded twice / lost. |

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

- **Whose job is injection?** The field guide frames prime injection as the
  *host's* responsibility (`SessionStart` / `PreCompact` hooks), not a
  per-task driver's. A defensible reading is that bead-chain *shouldn't* inject
  memories because the host already does at session start. The counter-argument
  — and why these stay P2, not P4 — is that bead-chain re-frames the agent's
  task on *every* bead via a fresh `/goal` prompt; if the host's prime context
  has been compacted away by bead N, the relevant facts are gone and bead-chain
  has the cheapest hook to re-surface them. A human should pick the policy.
- **Cross-section dependency:** the note-vs-comment side of chapter 4 (recording
  *what happened on this bead* as a `bd comment`/`bd note`) overlaps anatomy
  (ch01, `bead_chain-bn4`). bead-chain prompts neither; left to that section to
  avoid double-counting. Gaps #1–#3 here are memory-specific.
- Gaps #1–#3 are recommendations for the synthesis bead (`bead_chain-hkb`) to
  consolidate; per the framework, this section files no beads itself.
