# bead-chain

## What Is It

bead-chain is a Code Puppy plugin that automates your issue queue. Instead of
manually picking up tasks, working them, and closing them one by one, bead-chain
drives the entire cycle for you — claiming a task, handing it to an AI-judged
work loop, waiting for the judges to sign off, closing it, and grabbing the
next one. You start it with a single command and walk away.

## Who Is It For

bead-chain is for any developer or team using Code Puppy with the beads (`bd`)
issue tracker who wants to automate steady, hands-off progress through their
task queue. Whether you're burning down a backlog, processing a batch of
generated tasks, or letting an AI agent chip away at work overnight, bead-chain
keeps the assembly line moving without manual intervention.

## Key Features

- **Automated chaining** — claim, work, judge, close, repeat until the queue is
  empty or you say stop.
- **Crash recovery** — if a run is interrupted (power loss, Ctrl+C, network
  blip), the next run picks up exactly where you left off. See
  [Recovery Mode](Concepts/RecoveryMode.md).
- **Smart task ordering** — related tasks under the same epic stay together;
  blocking bugs jump to the front of the line.
- **Safety guardrails** — AI agents cannot close tasks themselves; only the
  independent LLM judges can sign off on completed work. See
  [The Close Guard](Concepts/TheCloseGuard.md).
- **Automatic cleanup** — when all children of a parent epic finish, the epic
  closes itself at the end of the session.
- **Iteration cap** — limit how many tasks get processed in a single run for
  predictable, bounded sessions.

## Requirements

- **Code Puppy** (or wiggum) with `/goal` mode available.
- **beads (`bd`)** installed and on your PATH — the issue tracker that
  bead-chain drives.
- A repository with an active beads issue database containing ready work items.

## Getting Started

New to bead-chain? Start here:

- [Installation](GettingStarted/Installation.md) — download and set up the
  plugin.
- [Quick Start: Run Your First Chain](GettingStarted/RunYourFirstChain.md) —
  go from zero to watching tasks close themselves.

## Next Steps

Once you're up and running:

- [How to Run a Capped Session](Guides/RunACappedSession.md) — control how many
  tasks process in one run.
- [How to Resume After an Interruption](Guides/ResumeAfterInterruption.md) —
  what happens when things get cut short.
- [Commands Reference](Reference/Commands.md) — every command and option at a
  glance.
- [Status Messages](Reference/StatusMessages.md) — what every emoji-prefixed
  message means and what to do when you see it.
- [Configuration](Reference/Configuration.md) — environment variables and
  built-in defaults.
- [How Bead Chaining Works](Concepts/HowBeadChainingWorks.md) — understand the
  engine under the hood.
