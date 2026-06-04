# Spike — Recursive Formula Pours / Nested Epics vs. the Single-in_progress Invariant (bead_chain-t1z)

**Type:** spike · **Priority:** P1 · **Status:** investigation + plan (no
behaviour change shipped — see "Why no code change" below).

## The contract under examination

bead-chain holds exactly **ONE non-epic (doable) bead in_progress at a
time**. Epics are containers, never driven directly — they are filtered
out of every query (`--exclude-type=epic`) and re-filtered client-side
via `is_excluded_type`. An epic is flipped to `in_progress` only as a
*status signal* ("this is the effort bead-chain is working inside"),
managed by `ensure_epic_in_progress`.

A **formula pour** can spawn beads that are themselves epics, and those
epics can pour again. So the parent chain of the single active doable
bead can be:

```
epic L0  (in_progress)
└─ epic L1  (in_progress?)
   └─ epic L2  (in_progress?)
      └─ doable bead  (in_progress)   ← the ONE
```

N epics — one per level of the active branch — can *legitimately* be
`in_progress` at once, while the single-doable-bead contract still holds.

## Ground truth gathered this spike (not assumptions)

This was verified against the live bd in this repo, which **already
contains a nested epic** (`bead_chain-mol-syb` is an `epic` whose
`parent` is `bead_chain-mol-1vy`). Findings:

1. **`bd ready --json` exposes `parent`** as a top-level string field on
   each item, plus a `dependencies` array of `{type: "parent-child",
   depends_on_id: ...}` entries. `extract_parent_epic_id` reads the
   `parent` field — correct, but only gives the **direct** parent.
2. **`bd show <id> --json` DOES expose `parent`** when one exists
   (confirmed on `bead_chain-mol-syb` → `parent: bead_chain-mol-1vy`).
   A bead with no parent simply omits the key. This is the linchpin:
   **ancestor-walking is feasible today** by chaining `show` calls up
   the `parent` field, no new bd command needed.
3. **`bd list --type=epic --status=in_progress`** is what
   `has_epic_in_progress` uses — it returns a global boolean across the
   *entire* DB, with **no parent/branch scoping**.
4. **`bd epic close-eligible`** cascades natively (closing a leaf can
   roll an epic up, which can roll *its* parent up) and tolerates
   multi-segment formula ids — already regression-locked in
   `tests/test_formula_epic_rollup.py`. This part is recursion-safe.

## Per-function trace under recursive pours

### `enforce_single_in_progress()` (lifecycle) — startup guard

- Lists in_progress **non-epic** beads (`list_in_progress` passes
  `--exclude-type=epic`). Epics are invisible to it by design.
- Under deep nesting: still correct for *doable* beads (returns head,
  warns on extras). **It never sees the N in_progress epics**, so it
  neither validates nor corrupts them. Verdict: **safe, but blind** — it
  cannot detect a *stale* in_progress epic that belongs to a branch
  nobody is working anymore (see Gap C).

### `list_in_progress()` / `next_in_progress()` (beads)

- `--exclude-type=epic` means the N legitimately-in_progress epics are
  correctly excluded from "stranded doable work" recovery. Verdict:
  **correct under recursion** — the one place the multi-epic
  tolerance is *intentional and right*.

### `ensure_epic_in_progress(bead)` (lifecycle) — THE BUG SURFACE

```python
epic_id = extract_parent_epic_id(bead)   # DIRECT parent only
if not epic_id: return
if has_epic_in_progress(): return        # GLOBAL boolean, any epic anywhere
claim(epic_id)
```

Two independent defects compound under recursion:

- **Defect 1 — direct-parent-only.** It claims only `bead`'s immediate
  parent (L2 in the diagram). The ancestors L1 and L0 are **never
  walked**, so they stay `open` while their descendant epic and the leaf
  are `in_progress`. The "true what-is-bead-chain-working-on" signal the
  docstring promises is broken: a dashboard reading the top-level epics
  sees L0 as `open` even though work is live three levels down.
- **Defect 2 — global `has_epic_in_progress()` short-circuit.** Even if
  we *wanted* to walk ancestors, the very first `has_epic_in_progress()`
  check returns `True` the moment **any** epic anywhere in the DB is
  in_progress — including an epic on a *different, abandoned* branch.
  Result: when bead-chain moves from branch A's leaf to branch B's leaf,
  it sees "an epic is already in_progress" (A's) and **declines to start
  B's parent epic at all**. The status signal points at the wrong branch.

  This already bites in the **flat (non-recursive)** case too: any
  lingering in_progress epic suppresses activation of the correct one.
  Recursion just makes it the *normal* state rather than an edge case.

### `pick_next_bead()` / epic-affinity (lifecycle)

- Tier 2 affinity uses `extract_parent_epic_id(just_closed)` →
  `next_ready_in_epic(direct_parent)`. Under recursion, "finish what you
  start" only looks one level up. When the **last** ready child of L2 is
  closed, affinity finds no sibling in L2 and falls through to the global
  `next_ready()` — it does **not** try L1's other children (L2's
  siblings) next. So the chain can ping-pong across branches instead of
  draining one sub-epic before moving to its aunt. Not *incorrect*
  (global queue is a valid fallback), but it defeats the coherent-commit
  intent for nested structures. Verdict: **suboptimal, non-breaking.**

### `rollup_completed_epics()` / `close_eligible_epics()` (lifecycle/beads)

- Fully delegated to `bd epic close-eligible`, which cascades up the
  ancestor chain server-side. When L2's last child closes, bd rolls up
  L2 → then L1 → then L0 in one call. Verdict: **recursion-safe today.**
  *Caveat:* it closes epics regardless of their `in_progress`/`open`
  status, so even the orphaned-direct-parent epics from Defect 1
  eventually get cleaned up — which is *why this latent bug has stayed
  invisible*. The rollup masks the activation bug.

### Status displays / recovery

- Recovery (`next_in_progress`, tier-0) only ever resurfaces the single
  doable bead — correct. But a **stranded in_progress epic** on a dead
  branch is invisible to recovery (epics excluded) AND invisible to the
  startup guard (epics excluded), so it sits `in_progress` forever until
  a rollup happens to close it. With recursion there are N such epics per
  branch, multiplying the stranding surface. Verdict: **latent leak,
  pre-existing, amplified by recursion.**

## Gap summary

| # | Gap | Severity | Recursion-specific? |
|---|-----|----------|---------------------|
| A | `ensure_epic_in_progress` claims direct parent only — ancestors L1..L0 stay `open` | High (wrong status) | Yes |
| B | Global `has_epic_in_progress()` short-circuits activation across branches | High (wrong-branch signal) | Amplified (exists flat) |
| C | Stranded in_progress epics on dead branches invisible to guard+recovery | Medium (leak) | Amplified |
| D | Epic affinity walks one level, ping-pongs across branches | Low (suboptimal) | Yes |
| E | Rollup masks A/B/C, so bugs stay invisible until exhaustion | — (diagnostic note) | — |

## Recommended plan

Sequenced so each step is independently shippable and testable. The
**core invariant does not change** — still exactly one doable bead in
flight; we are fixing the *epic status signal* to be branch-accurate.

### Step 1 — Walk the ancestor chain in `ensure_epic_in_progress` (fixes A)

Add a `beads.ancestor_epic_ids(bead) -> list[str]` that starts from the
direct `parent` and repeatedly `show`s upward, collecting each ancestor
whose `issue_type == "epic"`, stopping when `parent` is absent. Then
`ensure_epic_in_progress` claims **every ancestor epic not already
in_progress**, bottom-up or top-up (top-up keeps bd's per-parent UI
cache consistent — claim L0, L1, L2 in that order). Guard against cycles
with a `seen` set (bd shouldn't allow them, but `dep cycles` exists for a
reason — cheap insurance). Soft-fail per the existing contract.

### Step 2 — Make the in_progress check branch-scoped, not global (fixes B)

Replace the global `has_epic_in_progress()` short-circuit with a
per-epic-id check: "is *this specific* ancestor already in_progress?"
The data is already in hand from Step 1's `show` walk (each ancestor
dict carries `status`), so this needs **no extra bd calls** — check
`ancestor["status"] != "in_progress"` before claiming. `has_epic_in_progress`
can stay for other callers but must no longer gate per-branch activation.

### Step 3 — Branch-aware affinity (fixes D, optional / lower priority)

Extend `pick_next_bead` tier 2: when `next_ready_in_epic(direct_parent)`
is empty, walk up to the grandparent and try its ready descendants
before falling to the global queue. Keep it bounded (don't re-walk to
root every pick — one level up is the 80/20). Defer if Steps 1–2 land
the status correctness; this is polish, not correctness.

### Step 4 — Stranded-epic sweep (fixes C)

The rollup already closes *completed* epics. The remaining leak is an
in_progress epic on a branch with no in_progress descendant. Cheapest
fix: after Step 2, an epic only becomes in_progress when it's a true
ancestor of the active bead, so when the active bead changes branch the
*old* ancestors should be reverted to `open` (they're not done, just no
longer active). Add a `revert_inactive_ancestor_epics(active_bead)` pass
in `activate_next_bead` that reverts in_progress epics that are NOT
ancestors of the newly-activated bead AND are not eligible for rollup.
This is the one genuinely new bit of bookkeeping; gate it behind tests.

### Step 5 — Tests (gates all of the above)

`beads.py` is pure-stdlib and stubbable via `_patch_run_bd`, mirroring
`tests/test_formula_epic_rollup.py`. Add:

- `test_ancestor_walk_collects_all_epic_levels` — stub `show` to return
  a 3-level chain; assert all 3 ids returned, leaf's non-epic ancestor
  (if any) excluded, cycle-safe.
- `test_ensure_epic_skips_already_in_progress_ancestor` — one ancestor
  already in_progress, others open → only the open ones claimed.
- `test_activation_not_suppressed_by_foreign_branch_epic` — a
  *different-branch* epic in_progress must NOT block claiming the active
  branch's ancestors (the Defect-2 regression).
- `test_revert_inactive_ancestors_on_branch_switch` (Step 4).

Lifecycle decision logic is currently tangled with `emit_*` (see
`docs/solid-review-mol-4yc.md` finding #1); these tests will be easier
after the `reporting` seam lands, but the `beads.py` helpers (ancestor
walk) are testable **now** without it. Land Step 1's helper + its test
first to get value without waiting on the refactor.

## Why no code change shipped in this spike

This bead is a **spike** (investigate + produce a plan). The acceptance
criteria ask to *document current behaviour* and *produce a plan* — not
to implement the fix. The implementation is non-trivial (new ancestor
walk, branch-scoped checks, a revert pass, four new tests) and each step
above is a clean candidate for its own P1 doable bead under this epic.
Shipping a half-implementation under a spike would violate the
one-coherent-change-per-bead discipline the chain itself enforces.

**Suggested follow-up beads (to be filed/poured):**

1. `beads.ancestor_epic_ids` helper + ancestor-walk test (Step 1+5a).
2. Branch-scoped activation in `ensure_epic_in_progress` (Step 2+5b/c).
3. `revert_inactive_ancestor_epics` stranded-epic sweep (Step 4+5d).
4. Branch-aware affinity (Step 3) — lowest priority / optional.

## Bottom line

- The **rollup path is already recursion-safe** (bd cascades natively).
- The **doable-bead invariant is never threatened** by nesting — the
  `--exclude-type=epic` filters keep recovery and the single-in_progress
  guard correct.
- The real breakage is the **epic status signal**: `ensure_epic_in_progress`
  only claims the direct parent (A) and a global in_progress check
  suppresses cross-branch activation (B). Both exist in the flat case but
  become the *default* state under recursive pours. The native rollup
  has been quietly masking them (E), which is why they've gone unnoticed.
- Fix is feasible **without new bd commands** — `bd show` exposes
  `parent`, enabling a pure ancestor walk. Plan is four sequenced,
  independently-shippable steps, tests-first where the code is pure.