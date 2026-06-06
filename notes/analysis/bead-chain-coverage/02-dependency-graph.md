# Dependency Graph — Coverage Findings

| Field            | Value                                                                       |
| ---------------- | --------------------------------------------------------------------------- |
| Capability area  | `dependency-graph`                                                          |
| Field-guide ref  | `field-guide-02-dependency-graph.html` (chapter 2)                          |
| Bead-chain owner | `bead_chain-xoq`                                                            |
| Primary modules  | `beads.py` (`open_blocker_ids`, `next_blocking_bug`), `lifecycle.py` (`pick_next_bead`, `_reject_if_blocked`, `_has_fan_out_gate_issue`) |
| Status           | `done`                                                                      |

---

## 1. AVAILABLE — what the field guide documents

Chapter 2 owns bd's **relationships**: "twelve typed relationships, and the
ready / blocked computation that walks them" (`field-guide-02-dependency-graph.html`,
deck). The thesis (§ II, "Blocking vs advisory: the bright line") is that only
**two** of the twelve edge types gate readiness; the other ten are advisory and
report `"no blocking dependencies"`. The guide verifies this empirically against
bd v1.0.4 by wiring eleven downstream beads to one open upstream — one per edge
type — and observing `bd ready --explain` / `bd blocked`.

### The complete edge taxonomy (§ I/II, `TAXONOMY_*` + `EDGE_COMMANDS`)

Source: `field-guide-02-dependency-graph.html` § I/II legend and § VIII command
reference. Grouped by gating behaviour exactly as the guide groups them.

| #   | Edge type             | Group          | Gates readiness? | Field-guide gloss                                                             | Creation command                              |
| --- | --------------------- | -------------- | ---------------- | ---------------------------------------------------------------------------- | --------------------------------------------- |
| 1   | `blocks`              | Blocking       | **YES**          | A must close before B is workable. "The spine of `bd ready` / `bd blocked`." | `bd dep add B A` (default)                     |
| 2   | `waits-for`           | Blocking       | **YES**          | Fanout aggregation gate; `all-children` or `any-children`.                    | `bd dep add B A --type=waits-for` / `--waits-for=A` |
| 3   | `parent-child`        | Structural     | no (structural)  | Hierarchy; children inherit the prefix (`bd-a3f8.1`) and roll up to epics.    | `bd dep add B A --type=parent-child` / `--parent=A` |
| 4   | `related`             | Informational  | no               | Bidirectional association. Context, not a gate.                              | `bd dep add B A --type=related` / `bd dep relate A B` |
| 5   | `relates-to`          | Informational  | no               | Formal bidirectional relation — a variant of `related`.                      | `bd dep add B A --type=relates-to`            |
| 6   | `tracks`              | Informational  | no               | A follows B's progress without blocking on it.                              | `bd dep add B A --type=tracks`                |
| 7   | `discovered-from`     | Informational  | no               | Provenance: A was found while working on B.                                 | `bd dep add B A --type=discovered-from`       |
| 8   | `caused-by`           | Informational  | no               | Causal: A (typically a bug) was caused by B.                                | `bd dep add B A --type=caused-by`             |
| 9   | `validates`           | Informational  | no               | A (test bead) validates B. Test → feature link.                            | `bd dep add B A --type=validates`             |
| 10  | `until`               | Informational  | no               | Temporal annotation. **Does NOT gate readiness** (Vol I correction, verified empirically). | `bd dep add B A --type=until`     |
| 11  | `supersedes`          | Informational  | no               | A replaces B. B may auto-close via `bd supersede`.                          | `bd dep add B A --type=supersedes` / `bd supersede B --with A` |
| 12  | `external:proj:cap`   | Cross-project  | gated at query time | Cross-project capability dep, resolved at query time (see Vol VIII).      | `bd dep add A external:proj:cap`              |

**The readiness computation (§ III).** `bd ready` returns "the leaves of the
dependency forest: beads whose every *blocking* predecessor is already closed,"
priority-sorted. `bd blocked` is the mirror, citing the **direct** blocker (not
the transitive root). Useful surfaces: `bd ready --explain` (per-issue
reasoning), `bd ready --claim` (atomic claim), `bd dep tree <id>`, `bd dep
cycles` (integrity — Vol IX's turf, `bead_chain-tl0`).

**Two facts that matter for the audit below:**

- `until` *looks* blocking but is not — Vol I's first edition mis-classified it;
  ch02 explicitly corrects this ("Empirical testing in bd v1.0.4 proves it is
  not blocking — it is a temporal annotation … with zero effect on the readiness
  computation"). So "ignoring `until` for gating" is **correct**, not a gap.
- Known upstream bug **beads-88n** (§ VI): `bd graph` layering only considers
  `blocks` edges for its topological sort, so `waits-for`-gated issues render at
  Layer 0 in the visualisation but are correctly excluded from `bd ready`.
  "Treat `bd ready --explain` as the authoritative readout until this is patched."

## 2. LEVERAGED — what bead-chain actually uses

bead-chain consumes the dependency graph in exactly **three** ways, mapping onto
the two blocking edges plus the structural edge. All ten informational edges are
untouched.

### (a) `blocks` — fully honored, with defence-in-depth

`open_blocker_ids` (`beads.py:311`) is the canonical work-time blocker check. It
re-fetches the bead via `bd show <id> --json` (the `dependencies` array on `bd
ready`/`bd list` carries no per-edge *status*, so it can't tell open from closed
— `beads.py:339-344`), then walks `dependencies` and keeps an edge **only if**:

- `dependency_type` is in `BLOCKING_DEP_TYPES` — `("blocks",)` (`beads.py:75`),
  checked case-insensitively (`beads.py:369-370`); **and**
- `status` is *not* in `SATISFIED_BLOCKER_STATUSES` — `frozenset({"closed"})`
  (`beads.py:80`, `beads.py:373`). Open / in_progress / blocked all still gate.

`is_blocked` (`beads.py:382`) is the boolean wrapper. This is wired into every
non-`bd ready` path:

- **Recovery tier**: `_unblocked_in_progress` (`lifecycle.py:76`) calls
  `open_blocker_ids` on each stranded `in_progress` bead (`lifecycle.py:100`) and
  **reverts blocked ones to open** — the bdboard-oals fix, because `bd list
  --status=in_progress` bypasses the ready frontier.
- **Claim tiers 1–3**: `_reject_if_blocked` (`lifecycle.py:440`) re-checks
  `open_blocker_ids` (`lifecycle.py:452`) on blocking-bug / epic-affinity / global
  candidates as belt-and-suspenders against bd version drift
  (`pick_next_bead`, `lifecycle.py:421-436`).
- **Claim time**: `activate_next_bead` re-checks `open_blocker_ids`
  (`lifecycle.py:557`) before driving.

Verdict: `blocks` is honored **redundantly and correctly** — bd already filters
it server-side in `bd ready`, and bead-chain re-enforces it everywhere `bd ready`
is bypassed. This is the chapter's "spine" edge, and it's the one edge bead-chain
treats as load-bearing.

### (b) `waits-for` — partially honored (only the molecule `children-of(...)` form)

`_has_fan_out_gate_issue` (`lifecycle.py:628`) detects fan-out gates and skips the
bead at claim time (`lifecycle.py:576-580`). But it recognises **only one
representation** of `waits-for`: a `waits_for` field whose value is the literal
string `children-of(<spawner_id>)` (`lifecycle.py:652-662`). It then lists all
issues and checks whether the spawner has any unclosed child
(`lifecycle.py:678-686`). This is the `bead_chain-9sc` workaround for a beads CLI
bug where molecule fan-out gates are invisible to `bd blocked` (see
`SOLUTION_SUMMARY.md`).

What is **not** covered: the *generic* `waits-for` edge documented in § VIII
(`bd dep add B A --type=waits-for`). That form lands in the `dependencies` array
with `dependency_type == "waits-for"`, which `open_blocker_ids` ignores
(`BLOCKING_DEP_TYPES` is `("blocks",)` only, `beads.py:75`), and it is not in the
`children-of(...)` string form that `_has_fan_out_gate_issue` matches. So a
generic `waits-for` gate is honored *only* by bd's own server-side `bd ready`
filter — which is bypassed by the recovery tier, the exact gap class the `blocks`
defence-in-depth exists to close.

### (c) `parent-child` — honored structurally (epic affinity, rollup, exclusion)

bead-chain reads the parent via `extract_parent_epic_id` (`beads.py:295`,
canonical key `PARENT_EPIC_KEY = "parent"`, `beads.py:108`, plus `parent_id` /
`epic_id` fallbacks). It uses parent-child for three behaviours:

- **Epic affinity** (`pick_next_bead` tier 2, `lifecycle.py:427-431`): after a
  close, prefer a ready sibling under the same parent epic via
  `next_ready_in_epic` (`beads.py:276`, `bd ready --parent=<id>`). "Coherent
  commits and PRs beat queue-order optimality."
- **Epic rollup** (`rollup_completed_epics`, `lifecycle.py:282`): close epics
  whose children are all done.
- **Container exclusion**: epics are never driven as work (`EXCLUDED_TYPES`,
  `beads.py:41`) — covered in the anatomy section (`bead_chain-bn4`).

### (d) `dependent_count` — used as a proxy, edge-type composition unverified

`next_blocking_bug` (`beads.py:392`) escalates a ready bug ahead of the queue
when `dependent_count > 0` (`beads.py:430`), reasoning that "fixing it unblocks
downstream work" (`pick_next_bead`, `lifecycle.py:392`). `dependent_count` is a
bd-computed field, not an edge bead-chain inspects directly. **Whether bd counts
only `blocks` dependents or *all* edge types** (including soft `related` /
`tracks` / `discovered-from`) is not established here — if it includes soft
edges, a bug whose only dependents are non-gating would be falsely escalated as
"blocking." See GAP #4 and the open question.

### What is NOT leveraged (stated explicitly per the framework)

The ten advisory edges — `related`, `relates-to`, `tracks`, `discovered-from`,
`caused-by`, `validates`, `until`, `supersedes`, and `external:` — are **never
read** by any plugin module. Verified by grep across `beads.py`, `lifecycle.py`,
`prompt.py`, `close_guard.py`, `state.py`, `register_callbacks.py`: the only edge
strings that appear in code are `"blocks"` (`BLOCKING_DEP_TYPES`) and the
`children-of(...)` `waits_for` form. None of the soft edges is surfaced to the
agent in the goal prompt, nor used for selection or framing. For *gating* this is
**correct** (the guide says they don't gate); the gap is that bead-chain also
never uses them as **context**.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                                                                                                                 | Severity | Recommended follow-up (one line)                                                                                                          |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Generic `waits-for` edges (`bd dep add B A --type=waits-for`) are not honored outside `bd ready`: `open_blocker_ids` only checks `blocks` (`beads.py:75`) and `_has_fan_out_gate_issue` only matches the `children-of(...)` molecule string (`lifecycle.py:657`). A stranded `in_progress` bead re-gated by a generic `waits-for` would be re-driven — the bdboard-oals failure class for a second gating edge. | P2       | File a bead to add `"waits-for"` to `BLOCKING_DEP_TYPES` (one-line) so `open_blocker_ids` treats it as a work-time blocker in the recovery tier. |
| 2   | The six context-bearing soft edges (`related`, `relates-to`, `tracks`, `discovered-from`, `caused-by`, `validates`) are never surfaced in the goal prompt — the agent works a bead blind to its provenance, causal bug link, validating test, and related work. | P2       | File a bead to fold the bead's non-gating edges (esp. `discovered-from` / `caused-by` / `validates`) into the goal prompt as a "related context" block. |
| 3   | `supersedes` is ignored: if bead-chain surfaces a bead that has been superseded but not auto-closed, it drives redundant work. bd's `bd supersede` may auto-close the loser, but bead-chain has no awareness either way. | P3       | File a bead to skip / warn on beads with an inbound `supersedes` edge (treat like a soft exclusion).                                     |
| 4   | The blocking-bug escalation keys off bd's `dependent_count > 0` (`beads.py:430`) without knowing whether bd counts only `blocks` dependents or *all* edge types. If soft edges are counted, bugs with only advisory dependents jump the queue without actually unblocking anything. | P3       | File a bead to verify bd's `dependent_count` semantics empirically and, if it includes soft edges, switch escalation to a `blocks`-only dependent count. |
| 5   | Cross-project `external:proj:cap` deps are entirely unaddressed (Vol VIII territory). Low impact for a single-repo serial driver, but a future multi-repo chain would mis-read readiness. | P4       | No action unless bead-chain ever drives a cross-project queue; document as intentional scope.                                            |
| 6   | No graph-integrity awareness in the drain loop — `bd dep cycles` / orphan / tall-chain hazards (§ VI) are never checked. (Cross-section: this is ch09 / `bead_chain-tl0`'s turf; noted here only for completeness, not counted as a dependency-graph gap.) | —        | Tracked under quality & hygiene (`bead_chain-tl0`); no new bead from this section.                                                       |

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

- **Why no P0/P1 here.** For the *gating* edges the chapter actually cares about
  (`blocks`, `waits-for`), bead-chain's behaviour is correct on the hot path:
  `bd ready` filters both server-side, and `blocks` is re-enforced everywhere
  `bd ready` is bypassed. The `waits-for` gap (GAP #1) is real but narrow — it
  needs a *generic* `waits-for` edge **and** a stranded `in_progress` bead at the
  same time, so it's P2, not P1. Ignoring the ten advisory edges for gating is
  *correct per the guide* (§ II), so the only edge-gating risk is GAP #1.
- **`until` is correctly ignored.** ch02 explicitly corrects Vol I: `until` does
  not gate readiness. bead-chain treating it as a non-blocker (it isn't in
  `BLOCKING_DEP_TYPES`) is the right call — this is a non-gap and is called out
  here so the synthesis doesn't mistake it for a missed edge.
- **Open question — `dependent_count` composition (GAP #4).** Resolving this
  needs an empirical bd probe (wire a bug with only a `related` dependent, read
  `dependent_count`). Deliberately *not* run here to avoid mutating the live Dolt
  DB; filed as a verification follow-up instead.
- **Cross-section seams.** Fan-out *gate semantics* are owned here (chapter 2 owns
  the `waits-for` edge); the gate-type *catalogue* (`human`, `timer`, `gh:run`,
  `bead`, merge-slots) and coordination machinery live in chapter 6
  (`bead_chain-5cd`). Graph-integrity hygiene (`bd dep cycles`, orphans) is
  chapter 9 (`bead_chain-tl0`). Parent-child *as a field* is anatomy
  (`bead_chain-bn4`); parent-child *as selection behaviour* (epic affinity /
  rollup) is recorded here.
- Per the framework, this section files **no beads itself** — GAPs #1–#5 are
  candidates the synthesis bead (`bead_chain-hkb`) consolidates. None of these is
  an incidental bug discovered while working an unrelated goal (the bug-discovery
  protocol does not apply); they *are* this audit's deliverable.
