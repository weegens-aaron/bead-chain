# Bead Selection Order Reference

## Overview

When bead-chain finishes one task and moves to the next, it doesn't just grab
whatever happens to be at the top of the queue. Instead, it follows a strict
four-tier priority waterfall — checking each tier in order and taking the first
match it finds. This ordering ensures that interrupted work is never forgotten,
urgent blockers are resolved before they snowball, related tasks stay together
for coherent output, and the general queue drains steadily when nothing else
takes priority.

Understanding this order helps you predict which task the chain will pick next,
and explains why a task you expected to see might not be the one that runs.

---

## The Priority Waterfall

Every time bead-chain needs a new task — at startup and after each successful
close — it walks the same four tiers, top to bottom, and takes the first task
it finds:

| Tier | Name | What it looks for | Why it goes first |
|------|------|-------------------|-------------------|
| **0** | [Recovery](#tier-0--recovery) | Any task left in-progress from a previous interrupted run | Unfinished work must be assessed before anything new begins — one task at a time, always |
| **1** | [Blocking Bug](#tier-1--blocking-bugs) | A ready bug that other tasks depend on | Fixing it unblocks downstream work, so it always cuts the line |
| **2** | [Epic Affinity](#tier-2--epic-affinity) | A ready sibling under the same parent epic as the just-completed task | Finishing related work together produces coherent commits and focused output |
| **3** | [Global Queue](#tier-3--global-ready-queue) | Whatever `bd ready` returns next | The general-purpose fallback when nothing higher-priority applies |

The waterfall is **strict** — tier 0 always beats tier 1, tier 1 always beats
tier 2, and so on. There are no exceptions and no overrides.

### Waterfall Flow

```mermaid
flowchart TD
    START([\"Task completed or\\nchain just started\"]) --> T0{\"Tier 0\\nAny stranded\\nin-progress tasks?\"}
    T0 -- Yes --> RECOVER[\"Recover that task\\n(resume with assessment)\"]
    T0 -- No --> T1{\"Tier 1\\nAny blocking\\nbugs ready?\"}
    T1 -- Yes --> BUG[\"Claim the blocking bug\"]
    T1 -- No --> T2{\"Tier 2\\nAny ready siblings\\nunder the same epic?\"}
    T2 -- Yes --> SIBLING[\"Claim the sibling task\"]
    T2 -- No --> T3{\"Tier 3\\nAnything in the\\nglobal ready queue?\"}
    T3 -- Yes --> NEXT[\"Claim the next ready task\"]
    T3 -- No --> GATES{\"Any gates\\njust resolved?\"}
    GATES -- Yes --> T0
    GATES -- No --> DONE([\"Queue empty —\\nchain stops\"])

    style START fill:#0071dc,color:#fff
    style RECOVER fill:#ffc220,color:#000
    style BUG fill:#e03131,color:#fff
    style SIBLING fill:#e6f2ff
    style NEXT fill:#e6f2ff
    style DONE fill:#2e7d32,color:#fff
```

> [!NOTE]
> When the queue appears empty, bead-chain probes for any gates that may have
> resolved (timers expired, external checks passed, dependency conditions
> satisfied). If any gate resolves, its gated tasks re-enter the ready queue
> and the waterfall runs again from the top.

---

## Tier 0 — Recovery

**What it looks for:** Any non-container task that is already marked as
in-progress (or hooked) when the chain needs its next task.

**When it fires:** At the very start of a chain run (when you type
`/bead-chain`) and between iterations if additional stranded tasks remain.

**What happens:**

1. The chain scans for tasks left in a recoverable state — in-progress or
   hooked — from a prior run that ended without finishing them (Ctrl+C, a
   crash, power loss, etc.).
2. Any stranded task that has open blockers is moved back to the open queue
   rather than being recovered. The chain never drives work that can't be
   completed.
3. The first unblocked stranded task is selected. It is **not** re-claimed
   (it's already in-progress), but the agent receives a special recovery prompt
   telling it to assess what's already been done before continuing.

If multiple tasks are stranded (which only happens after a hard crash that
bypassed all cleanup), they are recovered **one at a time**, each getting its
own full assessment.

> [!IMPORTANT]
> Recovery always wins. No blocking bug, no epic sibling, and no queue position
> can override recovery. Unfinished work is addressed before anything new
> begins — this is the chain's one-task-at-a-time discipline.

**You'll see:** A recovery message in your terminal identifying the stranded
task and noting that the agent will assess the current state.

For a deeper look at the recovery mechanism, see
[Recovery Mode](../Concepts/RecoveryMode.md).

---

## Tier 1 — Blocking Bugs

**What it looks for:** A ready bug that has at least one other task depending
on it (a dependent count greater than zero).

**When it fires:** After recovery is clear (no stranded tasks), before
considering epic siblings or the general queue.

**What happens:**

1. The chain checks the ready queue for bugs that other tasks are blocked by.
2. A bug must meet **both** criteria to qualify:
   - It is a bug-type issue (not a task, not an epic, not another container
     type).
   - At least one other task depends on it — meaning fixing it will unblock
     downstream work.
3. If a qualifying bug is found, it jumps to the front of the line and is
   claimed immediately.

> [!TIP]
> A bug with no dependents is **not** a blocking bug in this context. It's
> treated as ordinary work and will be picked up when its turn comes in the
> global queue at tier 3. "Blocking" means it's actively holding something
> else up.

**Why it matters:** A single unfixed blocking bug can stall an entire branch of
your task tree. By prioritising it above all regular work, the chain ensures
that downstream tasks are unblocked as quickly as possible — maximising the
amount of work available for subsequent iterations.

**You'll see:** An info message noting that a blocking bug was detected and
prioritised.

---

## Tier 2 — Epic Affinity

**What it looks for:** A ready task under the **same parent epic** as the task
the chain just completed.

**When it fires:** After confirming no recovery work and no blocking bugs, and
only if the just-closed task belonged to a parent epic.

**What happens:**

1. The chain looks at the task it just completed and checks whether it had a
   parent epic.
2. If it did, the chain asks for the next ready task under that same epic.
3. If a sibling is available, it is claimed next — even if the global queue has
   higher-priority unrelated tasks waiting.

> [!NOTE]
> Epic affinity only applies when the chain just completed a task with a parent
> epic. If the just-completed task was a top-level item (no parent), this tier
> is skipped entirely and the chain falls through to tier 3.

**Why it matters:** Finishing all children of an epic together produces
coherent, focused output. Commits stay related, context stays warm, and the
parent epic can roll up (auto-close) sooner. Jumping between unrelated epics
mid-stream creates scattered, context-switching work — epic affinity prevents
that by following the "finish what you start" principle.

**You'll see:** An info message noting that the chain is staying inside the
current epic.

---

## Tier 3 — Global Ready Queue

**What it looks for:** Whatever `bd ready` returns as the next available task.

**When it fires:** When all higher tiers come up empty — no stranded work, no
blocking bugs, and no epic siblings.

**What happens:**

1. The chain asks `bd` for the next ready task from the general queue.
2. `bd` applies its own priority and blocker resolution — the chain inherits
   that ordering without trying to second-guess it.
3. The first eligible task is claimed and driven.

This is the steady-state tier: most task picks during a chain run come from
here once recovery is clear, blocking bugs are resolved, and epic families are
finished.

**You'll see:** A standard "claimed" message identifying the task.

---

## What Gets Filtered Out

Regardless of tier, certain beads are **never** selected by the chain:

### Container and Handle Types

| Type | Why it's excluded |
|------|-------------------|
| **Epic** | A container that groups children — it's not doable work. The chain drives its children individually and rolls up the epic when they're all done. |
| **Milestone** | A scheduling or checkpoint container, not a unit of work. |
| **Gate** | A handle that blocks downstream work until a condition is met (a timer, an external check, etc.). Gates resolve themselves — they aren't worked by an agent. |
| **Molecule** | A swarm orchestrator that manages spawned sub-tasks. The sub-tasks are the actual work. |

These types are filtered out both when the chain queries for ready tasks **and**
when it double-checks any task it's about to claim — a two-layer safety net
that ensures containers never reach the work loop.

For more on excluded types, see the
[Configuration Reference](Configuration.md#excluded-container-types).

### Blocked Tasks

A task with open blockers — dependencies on other tasks that haven't been
completed yet — is never selected. This applies at every tier:

- **Tier 0 (recovery):** Stranded tasks with open blockers are moved back to
  the open queue rather than recovered.
- **Tiers 1–3:** Tasks sourced from the ready queue are rechecked for blockers
  before being claimed, as an extra safety layer.

### Pinned Tasks

Tasks that have been pinned (parked by a human or another tool to stay open
indefinitely) are excluded from the ready queue and from recovery. The chain
respects a deliberate pin.

---

## Tips

> [!TIP]
> **Predict the next pick.** If you want to know what the chain will grab next,
> check in this order: any in-progress tasks (`bd list --status=in_progress`),
> then bugs with dependents, then siblings of the just-closed task's epic, then
> `bd ready`. The first non-empty result is your answer.

> [!TIP]
> **Use epic affinity to your advantage.** If you want a set of related tasks
> completed together without interruption, group them under the same parent
> epic. Once the chain starts on one, it will finish the family before moving
> on — as long as no tier 0 or tier 1 work cuts in.

> [!TIP]
> **Blocking bugs are your fast lane.** If a task is stuck waiting on a bug,
> the chain will prioritise that bug automatically. You don't need to manually
> reorder your queue — just make sure the dependency relationship is recorded
> and the chain takes care of the rest.

> [!TIP]
> **Recovery is automatic.** You never need to manually trigger recovery or
> tell the chain about interrupted work. If a task is in-progress when the
> chain starts, it knows what to do. Don't manually reset the task's status —
> let the chain handle it. See [Recovery Mode](../Concepts/RecoveryMode.md).

---

## See Also

- [Commands](Commands.md) — the `/bead-chain` command and `--max` flag that
  start the chain whose task selection this document describes.
- [How Bead Chaining Works](../Concepts/HowBeadChainingWorks.md) — the
  claim→drive→judge→close loop that this selection order feeds into.
- [Tutorial: Automate a Sprint Backlog](../Tutorials/AutomateASprintBacklog.md)
  — see all four tiers in action during a real scenario, including recovery
  after a Ctrl+C interruption and epic-affinity picks.
- [Recovery Mode](../Concepts/RecoveryMode.md) — a deeper look at tier 0:
  how interrupted work is detected, assessed, and resumed.
- [The Close Guard](../Concepts/TheCloseGuard.md) — the safety mechanism
  that prevents AI agents from closing tasks themselves during the chain.
- [Configuration](Configuration.md) — environment variables, timeout/retry
  behavior, and the excluded container types list.
- [Status Messages](StatusMessages.md) — what every emoji-prefixed message
  means, including the selection-related info and warning messages.
- [How to Handle Bugs Discovered During Work](../Guides/HandleBugsDuringWork.md)
  — what happens when an agent finds an unrelated bug mid-task, including how
  filed bugs feed into tier 1 priority routing.
- [Overview](../Overview.md) — bead-chain at a glance, including the "smart
  task ordering" feature that this document details.
- [How to Run a Capped Session](../Guides/RunACappedSession.md) — using
  `--max=N` to cap the number of tasks the selection waterfall processes in one
  run.
- [How to Resume After an Interruption](../Guides/ResumeAfterInterruption.md)
  — what to do when a run is cut short; recovery (tier 0) picks up the
  stranded task first.

---

[← Back to Reference](index.md) · [← Back to User Docs](../index.md)
