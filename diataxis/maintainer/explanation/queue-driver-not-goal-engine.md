# Explanation: Why bead-chain is a queue driver, not a goal engine

## About this topic

bead-chain looks, at a glance, like an autonomous coding loop: it claims a
task, works it to completion, closes it, and moves on. But the most
important architectural decision in the whole plugin is what it deliberately
does *not* do — it never judges whether a task is finished. This piece
explains that division of labour and why it shapes everything else.

## Context and background

There are two distinct jobs bound up in "work a queue of tasks
autonomously":

1. **Deciding what to work on next** — reading `bd ready`, respecting
   blockers and priorities, recovering stranded work, claiming a bead.
2. **Deciding when a task is done** — running the agent turn after turn,
   evaluating output against acceptance criteria, and ruling pass/fail.

code-puppy already ships a component for the second job: **wiggum**, whose
`/goal` mode runs the agent in a loop and uses LLM judges to decide
completion. bead-chain was built to do only the first job and to hand the
second off wholesale.

## How it fits together

The flow is a clean delegation. `handle_bead_chain_command` picks a bead,
formats it into a goal prompt via `format_bead_as_goal`, and calls
`wiggum_state.start(goal_prompt, mode="goal")`. From there wiggum owns the
turn-by-turn loop. bead-chain re-enters only at `interactive_turn_end`: it
checks `wiggum_state.is_active()`, and *that boolean is the entire signal*.

- Wiggum still active → bead-chain returns `None` and lets wiggum's
  continuation win. The bead is not done.
- Wiggum stopped → the judges have ruled; bead-chain closes the bead and
  picks the next one.

bead-chain never inspects the agent's output, never scores it, never holds
an opinion on quality. It trusts the judges completely. The module
responsibilities reinforce this: `beads` knows nothing about chain state,
`prompt` only formats strings, `state` holds three fields and no behaviour,
and `lifecycle` performs state transitions but defers every completion
verdict to wiggum.

## Why this approach

The alternative — building completion judgement into bead-chain — was
rejected for several reasons:

- **Single responsibility.** Completion judgement is genuinely hard and
  already solved well in wiggum. Re-implementing it would duplicate a
  subtle, high-value component and guarantee the two copies drift.
- **Don't repeat yourself.** One judge implementation, one place to improve
  it. Every bead-chain run benefits from wiggum improvements for free.
- **You aren't gonna need it.** bead-chain's value is the *queue
  discipline* — recovery, blocker gating, epic affinity, the close guard.
  None of that requires owning the judging loop.

The trade-off is a hard dependency: without wiggum loaded, `/bead-chain`
has nothing to drive. That is an accepted cost, stated plainly in the
module docstring: "This plugin is not a goal engine — it's a queue driver."

A consequence worth internalising: because the judges are the only
legitimate closer, agents must never close their own beads. The
[close guard](../how-to/extend-close-guard.md) exists precisely to enforce
that contract, and the bug-discovery protocol repeats "do NOT close any
bead yourself" on every prompt. These are not arbitrary rules; they fall
directly out of the queue-driver-not-goal-engine stance.

## Related

- [Run bead-chain locally and pass the test suite](../tutorials/run-locally-and-test.md)
  — see the `format_bead_as_goal` prompt that gets handed to wiggum, the
  hand-off this whole decision turns on.
- [Modules and public functions](../reference/modules-and-functions.md) —
  the per-module responsibility split (`beads`/`prompt`/`state`/`lifecycle`)
  that encodes this decision in code.
- [Extend the close-guard to block another bd command](../how-to/extend-close-guard.md)
  — the operational guard that enforces "the judges are the only legitimate
  closer", a direct consequence of the queue-driver stance.
- [Why bead-chain respects blocks at claim time](work-time-blocker-gate.md)
  — a sibling consequence: trusting the bd queue (and its `blocks` edges)
  instead of reasoning about goals itself.
