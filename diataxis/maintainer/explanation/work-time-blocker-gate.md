# Explanation: Why bead-chain respects blocks at claim time

## About this topic

A blocked bead is one that depends on another, still-open issue via a
`blocks` edge. The obvious place to enforce that is at close time — and bd
does, refusing to close a bead with open blockers. bead-chain goes further:
it refuses to *start* a blocked bead at all. This piece explains why
prevention beats the close-time safety net, and the bug that taught us so.

## Context and background

`bd ready` already filters blocked beads server-side, so in the happy path
bead-chain never even sees one. The problem is the two paths that bypass
the ready frontier:

1. **The recovery tier.** Stranded-work recovery reads
   `bd list --status=in_progress`, which does *not* honour the ready
   frontier. A bead claimed while ready, then later re-blocked (its blocker
   reopened, or a new `blocks` edge wired after the claim), would reappear
   here and be re-driven to completion — only to fail at `bd close`.
2. **bd version drift.** A future `bd ready` could regress and leak a
   blocked bead. Same defence-in-depth rationale as the epic
   `--exclude-type` filter: never trust a single upstream guard.

This is the bug recorded as **bdboard-oals**: running blocked work to
completion, discovering the block only at the very end, having burned a
whole iteration of tokens on stale inputs.

## How it fits together

The fix is layered, with the same "respect blocks at claim time" check
applied at every site a bead could enter the chain:

- `open_blocker_ids(bead_id)` re-fetches the bead via `bd show` (the only
  query that carries each dependency's *status* and *type*) and returns the
  ids of open `blocks` blockers. It checks `blocks` edges only —
  `parent-child`, `discovered-from`, and `related` edges do not gate work.
- `_unblocked_in_progress` filters the recovery list: a blocked stranded
  bead is reverted to `open` (re-entering the queue behind its blockers)
  and dropped from the workable set.
- `_reject_if_blocked` guards the non-recovery waterfall tiers (blocking
  bug, epic affinity, global ready) — belt-and-suspenders against drift.
- `activate_next_bead` and `handle_bead_chain_command` both re-check at the
  activation boundary, in case a `blocks` edge was wired in the moment
  between picking and claiming.

`open_blocker_ids` soft-fails to "not blocked" on any bd error, on the
principle that a transient blip must not strand the chain — and the
close-time guard still backstops us if the soft-fail is wrong.

## Why this approach

One might argue the close-time guard is sufficient: bd will refuse the
close, so no corrupt state is committed. True, but it fails *late and
expensively*. By the time `bd close` rejects the bead, the agent has
already done a full pass of work against inputs that were never ready. The
work may be wrong (it built on an unfinished dependency) and it definitely
cost tokens and wall-clock time. Claim-time prevention turns a wasted
iteration into a no-op revert.

The trade-off is redundancy: the same blocker check runs at several sites,
which looks like repetition. It is deliberate defence in depth — each layer
guards a different bypass path, and the cost (a `bd show` per candidate) is
small against the cost of driving blocked work to a dead end. The redundant
final assertions in `activate_next_bead` would, in a perfectly correct
world, never fire; keeping them is the same insurance policy as the
client-side epic filter.

## Related

- [Diagnose and recover a stranded in_progress bead](../how-to/recover-stranded-bead.md)
  — the operational view of the recovery path.
- [Modules and public functions](../reference/modules-and-functions.md) —
  `open_blocker_ids`, `is_blocked`, `_unblocked_in_progress`.
