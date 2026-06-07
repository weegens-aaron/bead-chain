# Troubleshooting

Common snags when running bead-chain, and how to clear them. For the normal
workflow, see **[Usage](usage.md)**.

---

## `/bead-chain` says there's nothing to do

bead-chain only drives the `bd ready` frontier. Check it directly:

```bash
bd ready
```

If that's empty, there genuinely is no available work. Possible reasons:

- **Everything is blocked.** Ready means *unblocked*. A bead with an open
  inbound `blocks` (`DEPENDS ON`) edge won't appear. Inspect with
  `bd show <id>` and clear or close its blockers first.
- **The work items are containers.** `epic`, `milestone`, `gate`, and
  `molecule` beads are intentionally filtered out — bead-chain only drives leaf
  work items. Make sure you actually have `task` / `bug` / etc. beads ready.
- **The queue really is empty.** Create a bead: `bd create --type=task
  --title='…'`.

---

## A bead I expected to run is being skipped

- **It's blocked.** See above — check `bd show <id>` for open `DEPENDS ON`
  edges.
- **It's a container type.** Epics/milestones/gates/molecules are never driven.
- **Epic affinity is in play.** After a close, bead-chain prefers ready siblings
  under the same parent epic before the global queue, so order may differ from a
  raw `bd ready`. This is expected — see
  [Usage → How the queue is ordered](usage.md#how-the-queue-is-ordered).

---

## "bd close blocked" — I tried to close a bead and got stopped

That's the **close guard** doing its job. While bead-chain is active, agents
can't close beads themselves:

> bead-chain blocked `bd close`. The bead will be closed automatically once
> the LLM judges sign off — do NOT close it yourself.

Let the chain run; the LLM judges close the bead on a passing verdict. This
exists so nobody short-circuits the quality gate. See
[Usage → The close guard](usage.md#the-close-guard).

---

## I pressed Ctrl+C — did I lose my work?

No. The bead you were on stays `in_progress`. The next `/bead-chain` run detects
it and resumes in **recovery mode**, assessing current state before doing new
work. See [Usage → Stopping and recovery](usage.md#stopping-and-recovery).

If a chain is cancelled before session-close ran, its bead mutations are
**local-only** until the next session-close runs `bd dolt push`. That's
documented, expected behavior — not data loss, just not-yet-synced.

---

## `bd` isn't found / wrong binary

If bead-chain can't find `bd`, or finds the wrong one:

```bash
which bd          # confirm what's on PATH
bd --version      # confirm it's the version you expect
```

Point bead-chain at a specific binary with the `BEADS_BIN` environment variable:

```bash
export BEADS_BIN=/path/to/bd
```

---

## `bd` commands are timing out

bead-chain uses a 30-second timeout per `bd` command and retries up to 3 times on
timeout (with 0.5s / 1.0s backoff). Retries cover *timeouts only* — not errors.
Persistent timeouts usually point at a slow or misconfigured `bd`/Dolt setup
rather than bead-chain. Try the same command by hand (`bd ready`, `bd show <id>`)
to confirm `bd` itself is healthy.

---

## My closed beads didn't show up on another machine

bead state travels on `refs/dolt/data`, which `git push` does **not** carry. Run
the session-close sync step:

```bash
git push
bd dolt push      # ships bead state to the remote
```

bead-chain never pushes for you — that's a deliberate session-close
responsibility. See [Usage → Syncing your work](usage.md#syncing-your-work) and
[ADR 0001](../notes/decisions/0001-dolt-push-lives-in-session-close.md).

---

## Still stuck?

- Read the **[Repo README](../README.md)** for the full feature/architecture
  tour.
- Run `bd prime` for the underlying issue tracker's complete command reference.
