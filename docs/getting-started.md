# Getting Started

This guide takes you from zero to your first completed bead with bead-chain.

---

## Prerequisites

bead-chain is a thin **queue driver** — it orchestrates tools it does not
replace. You need all three of these working before it can do anything:

1. **Code Puppy / wiggum** with `/goal` mode.
   bead-chain delegates the actual work-and-judge loop to wiggum's `/goal`
   engine. bead-chain never decides on its own whether a bead is "done" — the
   `/goal` LLM judges do.

2. **The `bd` (beads) CLI**, on your `PATH`.
   This is the issue tracker that holds your beads. Verify it:

   ```bash
   bd --version
   bd ready          # should list available work (or print nothing if the queue is empty)
   ```

   If your `bd` binary lives somewhere non-standard, point bead-chain at it with
   the `BEADS_BIN` environment variable (see
   [Configuration](#configuration) below).

3. **The bead-chain plugin installed** in your Code Puppy plugins directory.
   When it's loaded you'll have the `/bead-chain` slash command available.

---

## Your first chain

1. **Make sure there's work to do.** From the project you want to drive:

   ```bash
   bd ready
   ```

   If this is empty, create a bead first (`bd create --type=task --title='...'`)
   or there's nothing for the chain to pick up.

2. **Start the chain:**

   ```
   /bead-chain
   ```

   bead-chain will:
   - probe `bd ready` (or recover a stranded in-progress bead),
   - claim the top bead with `bd update <id> --claim`,
   - hand it to `/goal` as a goal prompt,
   - let the LLM judges decide when it's complete,
   - close it on success, and
   - grab the next bead — repeating until the queue is empty.

3. **Stop whenever you like** by pressing `Ctrl+C`. The bead you were on stays
   `in_progress`; the next `/bead-chain` run resumes it. See
   [Usage → Stopping and recovery](usage.md#stopping-and-recovery).

That's the whole loop. For a guided cap on how many beads to complete in one
run, use `/bead-chain --max=3`.

---

## Configuration

bead-chain is intentionally low-config.

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_BIN` | `bd` | Path to the `bd` executable, for non-standard installs. |

Timeouts and retries are hardcoded (not configurable): a 30-second `bd` command
timeout, with 3 retry attempts on timeout (0.5s / 1.0s backoff). These are
documented in the repo-root [README](../README.md#configuration).

---

## Next steps

- **[Usage](usage.md)** — flags, queue ordering, recovery, and the close guard.
- **[Troubleshooting](troubleshooting.md)** — when a bead won't run or a close gets blocked.
