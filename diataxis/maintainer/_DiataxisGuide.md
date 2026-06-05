# _DiataxisGuide.md — authoring contract (maintainer edition)

## The compass — classify EVERY item before you write it
Ask two questions, in order:
  Q1. Does the reader need to DO (action) or to KNOW (cognition)?
  Q2. Are they STUDYING (acquisition) or WORKING (application)?
The pair selects the type:
  action  + acquisition  -> tutorial
  action  + application  -> how-to guide
  cognition + application -> reference
  cognition + acquisition -> explanation
The compass is a SHOULD/diagnostic, not a MUST: never reject a doc merely
for 'mixing modalities', but each doc has ONE primary type that decides
its section folder. (research §'The Compass: Two Axes')

## tutorials/ — learning-oriented  (https://diataxis.fr/tutorials/)
  * A lesson under the guidance of a tutor; serves STUDY, learning by doing.
  * RUTHLESSLY MINIMISE EXPLANATION — link out to explanation instead.
  * ASPIRE TO PERFECT RELIABILITY: every step works, every time. The
    author carries nearly all the responsibility.
  * One concrete, achievable, happy-path end-goal. No decision points,
    no 'if you want, you can…'.
  Template: Title / What you'll build / Prerequisites / numbered steps,
  each with the exact result the reader should see / 'You did it' close /
  'Where next' links to how-to + explanation. NO digressions.

## how-to/ — goal/task-oriented  (https://diataxis.fr/how-to-guides/)
  * Directions that guide an ALREADY-COMPETENT reader through a REAL task.
  * Recipe-style: a series of steps toward a result, correctly and safely.
  * About GOALS, PROJECTS and PROBLEMS — NOT about tools (tools are
    reference). Assume competence; omit teaching.
  * Troubleshooting/'fix X' content lives here (it is a task).
  Template: How to <goal> / when to use this / numbered recipe steps /
  variations & options / 'Done — verify' / Related (link reference +
  other how-tos). No conceptual lecturing.

## reference/ — information-oriented  (https://diataxis.fr/reference/)
  * Technical DESCRIPTION of the machinery and how to operate it (a MAP).
  * DESCRIBE AND ONLY DESCRIBE. No tutorials, no how-to steps, no opinion.
  * PRODUCT-LED, not user-led: structure MIRRORS the product. Style is
    AUSTERE, neutral, objective, factual, consistent.
  Template: subject overview line / structured description — tables for
  commands/variables/parameters/fields/return values, ordered to mirror
  the product / examples ONLY as illustration / Related. No 'why', no
  walkthrough. (maintainer may add source-path / mermaid / API tables;
  user describes only what users operate: CLI, variables, output layout.)

## explanation/ — understanding-oriented  (https://diataxis.fr/explanation/)
  * Discursive treatment that permits reflection; answers 'Can you tell me
    about…?'. Serves STUDY — the WHY. The 'read in the bath' kind of doc.
  * MUST provide context and background; MAY and SHOULD consider
    ALTERNATIVES and counter-examples; MAY admit OPINION and perspective.
  * Not tied to a single task; no step-by-step.
  Template: About <topic> / context & background / how it fits together /
  why this approach (tradeoffs, alternatives considered, opinion allowed) /
  Related (link tutorial + reference). Conceptual overviews live here.

## Audience overlay (maintainer) — surface-detail constraint, layered on top
  * maintainer: implementation detail, source paths, code, mermaid,
    API/View tables, internal/build commands ALL allowed.
  * user: NO source paths, NO code, NO internal/localhost/staging URLs,
    NO dev-setup/build/test instructions. Product-expert-to-customer voice.
  (The 'maintain' formula's leakage grep — src/ | npm | localhost — is the
  audit gate; do not trip it.)
  The overlay limits allowed detail only; it NEVER overrides a type's
  orientation above.

## Anti-pattern (DO NOT) — the documented Diátaxis misuse
Do NOT pre-create empty tutorials/ how-to/ reference/ explanation/ folders
'just in case'. From the official guidance: "It certainly does not mean
that you should create empty structures … with nothing in them. Don't do
that. It's horrible." A section folder exists ONLY once it holds at least
one real document. Structure EMERGES per item.

READ-ONLY source. Output only under DOCS_DIR.
