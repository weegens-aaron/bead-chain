# Frequently Asked Questions

Common questions about using bead-chain, grouped by theme. Each answer is short
and links to the relevant guide or reference for the full story.

---

## Getting Started

### What does bead-chain do?

bead-chain automates your task queue. Instead of manually picking up tasks,
working them, and closing them one by one, bead-chain drives the entire cycle
for you: claim a task, hand it to an AI-judged work loop, wait for independent
judges to sign off, close it, and grab the next one. You start it with a single
command and walk away.

See [Overview](Overview.md) for the full picture.

### What do I need before I can use bead-chain?

Two things:

1. **Code Puppy** (or wiggum) with `/goal` mode available.
2. **beads (`bd`)** installed and on your PATH.

Run `bd ready` in your terminal to confirm both are working. If the command
isn't found, install beads first. See
[Installation](GettingStarted/Installation.md) for detailed setup steps.

### How do I know bead-chain is installed correctly?

Type `/bead-chain` in Code Puppy. If the plugin is loaded, it either starts
processing tasks or reports that the queue is empty. Either way, the command is
recognised and running. If it isn't recognised, double-check that the
`bead_chain/` folder is directly inside your plugins directory and that you
restarted Code Puppy after extracting.

See [Installation](GettingStarted/Installation.md) for troubleshooting
specifics.

### Does bead-chain need internet access to work?

bead-chain itself runs locally. However, the AI agent and the LLM judges
require network connectivity to function. If you lose connectivity mid-task,
the chain stops and the current task stays in-progress for recovery on the next
run. See [Recovery Mode](Concepts/RecoveryMode.md).

---

## Common Tasks

### How do I start a chain?

Type `/bead-chain` in Code Puppy. The chain begins immediately and runs until
the queue is empty. See
[Run Your First Chain](GettingStarted/RunYourFirstChain.md).

### How do I stop a chain?

Three ways:

- **Ctrl+C** -- stops immediately. The current task stays in-progress for
  recovery.
- **`--max=N`** -- add the flag when starting (e.g. `/bead-chain --max=5`) and
  the chain stops automatically after closing N tasks.
- **Let it drain** -- do nothing, and the chain stops on its own when the queue
  is empty.

See [Commands](Reference/Commands.md) for the full reference.

### How do I limit how many tasks get processed?

Use the `--max` flag: `/bead-chain --max=3` processes at most three tasks, then
stops cleanly. Only successfully closed tasks (judge-approved) count toward the
cap. See [How to Run a Capped Session](Guides/RunACappedSession.md).

### Can I preview what the chain will do before starting it?

Yes. Run `bd ready` to see the task queue. That list is roughly what the chain
will draw from -- though bead-chain applies its own
[priority logic](Reference/BeadSelectionOrder.md) (recovery first, then
blocking bugs, then epic siblings, then the general queue).

For a more precise prediction, also check
`bd list --status=in_progress` -- any stranded tasks from a previous run will be
handled before anything from the ready queue.

### How do I upgrade bead-chain?

Re-run the same install command you used originally -- it always pulls the
latest release and overwrites the existing files. Then restart Code Puppy.
See [How to Upgrade or Uninstall bead-chain](Guides/UpgradeOrUninstall.md).

### How do I uninstall bead-chain?

Delete the plugin directory (`~/.code_puppy/plugins/bead_chain` on macOS/Linux
or `~\.code_puppy\plugins\bead_chain` on Windows) and restart Code Puppy. Your
task history and beads database are unaffected -- they live in the repository,
not in the plugin directory. See
[How to Upgrade or Uninstall bead-chain](Guides/UpgradeOrUninstall.md).

---

## The Chain Loop

### Who decides when a task is done?

Independent LLM judges -- never the agent that did the work. The agent submits
its work, and the judges evaluate the result against the task's acceptance
criteria. This separation of "doer" and "evaluator" is enforced by
[The Close Guard](Concepts/TheCloseGuard.md).

### What is the Close Guard?

A safety rail that blocks the AI agent from closing tasks itself during a chain
run. If the agent tries to run `bd close` while a chain is active, the command
is blocked and the agent receives a reminder to let the judges decide. See
[The Close Guard](Concepts/TheCloseGuard.md) for the full explanation.

### What types of beads does the chain skip?

bead-chain only drives leaf work items (tasks, bugs). It automatically skips
container and handle types:

- **Epics** -- groups of related child tasks.
- **Milestones** -- scheduling or checkpoint containers.
- **Gates** -- handles that block downstream work until a condition is met.
- **Molecules** -- swarm containers that orchestrate spawned sub-tasks.

These are filtered out before the chain even considers them. See
[Configuration](Reference/Configuration.md) for details.

### Does the chain close parent epics?

Yes -- automatically. At the end of a session, bead-chain checks whether any
parent epics now have all their children closed. If so, the epic is rolled up
(closed) without you having to do anything. See
[How Bead Chaining Works](Concepts/HowBeadChainingWorks.md).

---

## Recovery and Interruptions

### I pressed Ctrl+C -- is my work lost?

No. Pressing Ctrl+C is the designed way to stop a chain early. The current task
stays in-progress on purpose, and any changes the agent already made remain in
the repository exactly as they were. The next `/bead-chain` run detects the
stranded task and resumes it automatically. See
[How to Resume After an Interruption](Guides/ResumeAfterInterruption.md).

### What happens if my machine crashes or loses power?

Same as Ctrl+C, but without the goodbye message. The in-progress task's status
was already saved when it was claimed, so it survives the crash. The next
`/bead-chain` run finds it and enters Recovery Mode. See
[Recovery Mode](Concepts/RecoveryMode.md).

### I manually reset a stranded task to open -- now what?

The recovery signal was erased. The chain will treat the task as brand-new work
and the agent won't know to check what was already done -- risking duplicated
or conflicting changes. In the future, leave stranded tasks in-progress and let
Recovery Mode handle them.

### Can I upgrade bead-chain while a task is in-progress?

Yes, but stop the chain first (Ctrl+C). After upgrading and restarting Code
Puppy, the next `/bead-chain` run enters Recovery Mode and resumes the stranded
task using the new version. See
[How to Upgrade or Uninstall bead-chain](Guides/UpgradeOrUninstall.md).

---

## Bugs and Unexpected Issues

### What happens when the agent finds an unrelated bug mid-task?

The agent follows a built-in protocol: file the bug as a new bead, then decide
whether it blocks the current task's acceptance criteria.

- **Non-blocking:** the bug is filed at priority 2 and the agent continues the
  original task without interruption. The bug waits its turn in the queue.
- **Blocking:** the bug is filed at priority 1 with a triage marker, fixed
  inline as scope expansion, and both pieces of work are presented to the
  judges.

See [How to Handle Bugs Discovered During Work](Guides/HandleBugsDuringWork.md).

### A bug was filed and inline-fixed, but the bug bead is still open -- is that right?

Yes, intentionally. The inline fix was done under time pressure as scope
expansion. The open bug bead ensures a future chain iteration will claim it and
verify the fix properly with a dedicated triage-verification prompt. See
[How to Handle Bugs Discovered During Work](Guides/HandleBugsDuringWork.md).

---

## Troubleshooting

### `/bead-chain` isn't recognised

Restart Code Puppy. It loads plugins at startup, so it won't see new files until
restarted. If the problem persists, make sure the `bead_chain/` folder is
directly inside `~/.code_puppy/plugins/` (not nested in a subfolder). See
[Installation](GettingStarted/Installation.md).

### "No ready beads" when I expected tasks

Run `bd ready` to check your queue. If it's empty, create tasks with
`bd create`. If tasks exist but don't appear, they may be blocked by
unresolved dependencies. Resolve the blockers and the tasks will re-enter the
ready queue.

### The chain keeps rejecting my work

The judges found gaps against the task's acceptance criteria and the agent keeps
iterating. If you think the criteria are unreasonable, press Ctrl+C, revise the
task's description or acceptance criteria with `bd update`, and re-run.

### The chain seems stuck on a task

Give it time -- complex tasks can take several minutes. If it genuinely stalls,
press Ctrl+C and re-run `/bead-chain` to trigger recovery. The agent will
assess what's already done and continue.

### `bd ready` returns "command not found"

beads (`bd`) isn't installed or isn't on your PATH. Install beads first, then
return to use bead-chain. If `bd` is installed but in a non-standard location,
set `BEADS_BIN` to point to it. See
[Configuration](Reference/Configuration.md).

### "bead-chain can't reach `bd`"

The `bd` command failed or isn't available. Check that `bd` is installed and on
your PATH, or that `BEADS_BIN` points to the correct location. Try running
`bd ready` manually to diagnose.

### The agent tried to close a task and was blocked

This is the [Close Guard](Concepts/TheCloseGuard.md) doing its job. The agent
was reminded to let the judges decide. No action needed -- the agent will
continue working and the judges will close the task when it meets the acceptance
criteria.

### I see "found N in_progress beads" at startup

Multiple tasks were left stranded, likely from a hard crash. bead-chain handles
this automatically, recovering each task one at a time. No action needed unless
you see it repeatedly, which could indicate an underlying stability issue.

---

## Further Reading

- [Overview](Overview.md) -- what bead-chain is and who it's for.
- [Commands](Reference/Commands.md) -- every command and option at a glance.
- [Status Messages](Reference/StatusMessages.md) -- what every message means.
- [Configuration](Reference/Configuration.md) -- environment variables and
  built-in defaults.
- [How Bead Chaining Works](Concepts/HowBeadChainingWorks.md) -- the engine
  under the hood.

---

[← Back to User Docs](index.md)
