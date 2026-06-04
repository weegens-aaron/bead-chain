# _DiataxisGuide.md — authoring contract (maintainer edition)

## The compass — classify EVERY item before you write it

Ask two questions, in order:

**Q1. Does the reader need to DO (action) or to KNOW (cognition)?**
**Q2. Are they STUDYING (acquisition) or WORKING (application)?**

The pair selects the type:

- **action + acquisition** → **tutorial**
- **action + application** → **how-to guide**
- **cognition + application** → **reference**
- **cognition + acquisition** → **explanation**

The compass is a SHOULD/diagnostic, not a MUST: never reject a doc merely for mixing modalities, but each doc has ONE primary type that decides its section folder.

*(research §The Compass: Two Axes)*

---

## tutorials/ — learning-oriented
https://diataxis.fr/tutorials/

* A lesson under the guidance of a tutor; serves STUDY, learning by doing.
* RUTHLESSLY MINIMISE EXPLANATION — link out to explanation instead.
* ASPIRE TO PERFECT RELIABILITY: every step works, every time. The author carries nearly all the responsibility.
* One concrete, achievable, happy-path end-goal. No decision points, no if you want, you can….

**Template:**
1. Title
2. What you'll build
3. Prerequisites
4. Numbered steps, each with the exact result the reader should see
5. "You did it" close
6. "Where next" — links to how-to + explanation
7. NO digressions.

---

## how-to/ — goal/task-oriented
https://diataxis.fr/how-to-guides/

* Directions that guide an ALREADY-COMPETENT reader through a REAL task.
* Recipe-style: a series of steps toward a result, correctly and safely.
* About GOALS, PROJECTS and PROBLEMS — NOT about tools (tools are reference). Assume competence; omit teaching.
* Troubleshooting/fix-X content lives here (it is a task).

**Template:**
1. How to \<goal\>
2. When to use this
3. Numbered recipe steps
4. Variations & options
5. "Done — verify" (how to confirm it worked)
6. "Related" — links to reference + other how-tos
7. No conceptual lecturing.

---

## reference/ — information-oriented
https://diataxis.fr/reference/

* Technical DESCRIPTION of the machinery and how to operate it (a MAP).
* DESCRIBE AND ONLY DESCRIBE. No tutorials, no how-to steps, no opinion.
* PRODUCT-LED, not user-led: structure MIRRORS the product. Style is AUSTERE, neutral, objective, factual, consistent.

**Template:**
1. Subject overview line
2. Structured description — tables for commands/variables/parameters/fields/return values, ordered to mirror the product
3. Examples ONLY as illustration
4. "Related" — links to how-to + other reference
5. No why, no walkthrough.
6. *(maintainer layer: source paths, code structure, Mermaid diagrams, internal API tables allowed)*

---

## explanation/ — understanding-oriented
https://diataxis.fr/explanation/

* Discursive treatment that permits reflection; answers "Can you tell me about…?". Serves STUDY — the WHY. The read-in-the-bath kind of doc.
* MUST provide context and background; MAY and SHOULD consider ALTERNATIVES and counter-examples; MAY admit OPINION and perspective.
* Not tied to a single task; no step-by-step.

**Template:**
1. About \<topic\>
2. Context & background
3. How it fits together
4. Why this approach (tradeoffs, alternatives considered, opinion allowed)
5. "Related" — links to tutorial + reference
6. Conceptual overviews live here.

---

## Audience overlay (maintainer) — surface-detail constraint, layered on top

**Maintainer layer allowed:**
* Implementation detail, source paths, code snippets
* Mermaid diagrams and internal architecture
* API/View tables, internal/build commands
* Staging/localhost URLs

**Applies to all four types** — the overlay limits allowed detail only; it NEVER overrides a type's orientation above.

The maintain-formulas leakage grep — `src/ | npm | localhost` — is the audit gate. If you trip it when writing user docs, fix it. For maintainer docs, it's expected and fine.

---

## Anti-pattern (DO NOT)

**Do NOT pre-create empty tutorials/ how-to/ reference/ explanation/ folders just in case.**

From the official guidance: "It certainly does not mean that you should create empty structures … with nothing in them. Dont do that. Its horrible."

A section folder exists ONLY once it holds at least one real document. Structure EMERGES per item.

**READ-ONLY source.** Output only under DOCS_DIR.

---

## Per-type checklist

Use this to verify your draft before filing:

### Tutorial
- [ ] One happy-path goal, achievable in one sitting
- [ ] Every step has a visible outcome
- [ ] No "if you want…" branching
- [ ] Assumes zero prior knowledge
- [ ] External explanation linked, not inlined

### How-to
- [ ] Assumes reader is already competent
- [ ] Steps are a recipe, not teaching
- [ ] Covers the real, complete task
- [ ] Includes variations as options, not decisions
- [ ] Ends with "done — verify" 

### Reference
- [ ] Mirrors product structure, not user goals
- [ ] Neutral, austere, no opinion
- [ ] Tables for parameters/fields/commands
- [ ] Examples are illustration only
- [ ] No "why" or walkthrough

### Explanation
- [ ] Background and context first
- [ ] Considers alternatives
- [ ] Allows opinion and perspective
- [ ] Not tied to a single task
- [ ] Permits reflection, not just action
