# Explanation: Why epic rollup runs once per session

## About this topic

When the last child of an epic closes, the epic itself should close — it has
no more work to track. bead-chain does this rollup, but only **once per
session**, at the moment the ready queue drains, rather than after every
individual bead close. That timing choice is a deliberate response to a
data-safety bug. This piece explains the bug and the trade-off the fix
makes.

## Context and background

bd offers `bd epic close-eligible`, which closes every epic whose children
are all complete. Crucially, it runs a **server-side cascade**: closing
epic A's last child closes A, then checks whether A's parent epic B is now
eligible, closes B, checks B's parent C, and so on up the tree.

The original bead-chain called this after *every* bead close. That seemed
natural — close a bead, sweep up any epic it just completed. But the
cascade does not respect the boundary of "the epic I was working on." This
is the bug recorded as **bead_chain-tfn** (the over-close bug).

A concrete failure: closing bead N inside molecule-epic A triggers rollup,
which cascades to close A's parent (epic B), which happened to be the last
open child of an *unrelated* epic C. Closing C then closes all of C's
orphaned children — three tracking beads with no relationship to N or A at
all. One bead close silently swept up a chunk of unrelated state.

## How it fits together

The fix is small but pointed. The per-bead rollup call was removed from
`_on_interactive_turn_end` (the comment there preserves the full
explanation). Instead, `rollup_completed_epics()` is called from exactly one
place: the drain pass in `activate_next_bead`, when `pick_next_bead` returns
`None` because the queue is empty.

The cascade still exists inside bd — bead-chain cannot disable it. What
changed is *frequency*: calling close-eligible once, at session end, limits
the blast radius to whatever epics were eligible at that single moment. The
rollup is also soft-failing: a flaky or old `bd epic` logs a warning and
the chain keeps trotting, because rollup is courtesy cleanup, not the
mission.

## Why this approach

This is explicitly **mitigation, not prevention** — an important
distinction. The honest framing in the code is that the cascade bug lives
in bd; bead-chain just stops poking it so often. The alternatives
considered:

- **Disable rollup entirely.** Rejected: epics would linger as zombies
  after their work is done, which is exactly the state rollup exists to
  prevent.
- **Filter the cascade to only the current epic's ancestry.** Rejected as
  over-engineering against an output format bead-chain does not control;
  the once-per-session approach gets most of the benefit with a one-line
  change.
- **Keep per-bead rollup.** Rejected: that is the bug.

The accepted trade-off is latency: a parent epic whose final grandchild
closes mid-session may not roll up until the *next* session's drain pass.
That is a cosmetic delay in `bd status` displays. Weighed against silently
closing unrelated epics and their children, delayed-but-correct beats
prompt-but-destructive every time. Data safety wins over one-shot
cascading.

## Related

- [Modules and public functions](../reference/modules-and-functions.md) —
  `rollup_completed_epics`, `close_eligible_epics`.
- [Why bead-chain is a queue driver, not a goal engine](queue-driver-not-goal-engine.md)
  — the broader "prefer safety over cleverness" stance this fix embodies.
