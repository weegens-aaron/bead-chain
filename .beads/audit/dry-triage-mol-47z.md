# DRY triage — bead_chain plugin

**Bead:** bead_chain-mol-47z (parent epic: bead_chain-mol-1vy, code-health-audit)
**Date:** 2026-05-29
**Method:** Manual read-through of all six plugin modules, looking for
duplicated logic, copy-pasted blocks, and repeated literals that should
be centralized.

## How this was reviewed

There is no automated duplication tool wired into this repo. Reviewed
each module by hand for:
- repeated control-flow / parsing blocks,
- magic strings/literals appearing in >1 place,
- the same bd-arg construction repeated across query helpers.

## Findings

**No actionable duplication.** The codebase is already aggressively
DRY, and the authors left breadcrumbs documenting *why* each shared
helper exists. Concrete evidence the DRY work is already done:

| Concern | Centralized in | Notes |
|---|---|---|
| `--exclude-type=...` arg | `beads._exclude_type_arg()` | One source for the epic-exclusion flag; used by every `bd ready`/`bd list` call. |
| JSON-list parse + validate | `beads._parse_json_list()` | Single helper for the parse→validate→return pattern across all list queries. |
| Epic exclusion predicate | `beads.is_excluded_type()` | Reused server-side-filter companion in `beads`, `lifecycle` (3 call sites). |
| Excluded/blocking-bug types | `EXCLUDED_TYPES`, `BLOCKING_BUG_TYPES` tuples | One-line edits to extend; no scattered literals. |
| Parent-epic key lookup | `extract_parent_epic_id()` + key constants | Canonical key + fallbacks in one place. |
| Closed-epic shape coercion | `_normalise_closed_epic()` / `_is_closed_epic()` | bd version-shape handling centralized. |
| Recovery/triage preambles | module constants in `prompt.py` | Wording lives in one place each. |

## Borderline cases considered (and rejected)

1. **`ensure_epic_in_progress` + claim-then-set-current-bead block**
   appears in both `register_callbacks.handle_bead_chain_command`
   (startup) and `lifecycle.activate_next_bead` (mid-chain). The two
   blocks look similar (claim epic → claim bead → set current_bead →
   arm wiggum) but differ in their surrounding control flow (startup
   does flag-parsing + first-bead messaging; mid-chain does the
   --max cap check + waterfall pick). Extracting a shared helper would
   couple two genuinely different lifecycle phases and obscure the
   distinct messaging each emits. **Verdict: leave as-is** — this is
   cohesion-preserving repetition, not a DRY violation. Forcing it
   into one function would hurt readability (the Zen: "readability
   counts").

2. **The "last-line-of-defence epic assertion"** appears in three
   spots (startup, `activate_next_bead`, `close_current_bead_success`).
   Each emits a slightly different message and takes a different
   recovery action (return True / stop+return None / revert+stop).
   The shared *predicate* is already factored out (`is_excluded_type`);
   only the per-site reaction differs, which is exactly what should
   stay local. **Verdict: not duplication.**

## Recommendation

No cleanup beads filed. The module already honors DRY without
over-abstracting (no premature helper extraction that would violate
YAGNI). The borderline cases are correctly left un-merged for cohesion.
