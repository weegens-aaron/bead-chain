# Usage

Day-to-day workflows for bead-chain. If you haven't run it yet, start with
**[Getting Started](getting-started.md)**.

---

## The command

```bash
/bead-chain           # Chain beads until the queue is empty
/bead-chain --max=3   # Stop after completing 3 beads (safety cap)
```

There is one command and one flag. Everything else is automatic.

---

## What happens each iteration

1. **Probe** — check `bd ready` for the next work item (or recover a stranded
   in-progress bead).
2. **Claim** — `bd update <id> --claim` atomically marks the bead `in_progress`.
3. **Drive** — the bead becomes a goal prompt handed to wiggum's `/goal` mode.
4. **Judge** — `/goal`'s LLM judges evaluate completion each turn.
5. **Close** — on a passing verdict, bead-chain runs `bd close <id>`.
6. **Repeat** — until the queue is empty, `--max` is hit, or you press `Ctrl+C`.

---

## How the queue is ordered

bead-chain doesn't blindly take `bd ready`'s first row. It applies a small
waterfall so the most valuable work goes first:

1. **Blocking bugs first.** A ready bug that other beads depend on
   (`dependent_count > 0`) jumps to the front — clearing it unblocks downstream
   work.
2. **Epic affinity.** After closing a bead, bead-chain prefers the next ready
   sibling **under the same parent epic** before falling back to the global
   queue. Finishing one epic's worth of work makes for coherent commits and PRs.
3. **Otherwise**, the normal `bd ready` frontier order.

Only **leaf work items** are ever driven. Container/handle types — `epic`,
`milestone`, `gate`, `molecule` — are filtered out (both server-side via
`--exclude-type` and client-side), so the chain never tries to "do" a container.

---

## Stopping and recovery

**To stop:** press `Ctrl+C`. The current bead stays `in_progress` — it is *not*
abandoned.

**Recovery mode:** the next `/bead-chain` run detects the stranded
`in_progress` bead at startup and resumes it with a recovery preamble that tells
the agent to assess current state before doing new work:

> RECOVERY MODE: Assess current state before doing new work. Is the work
> effectively done? If yes, summarize what's in place. Otherwise, continue from
> where the previous run left off.

This keeps partial work paired with its bead — no orphaning, no duplicate
effort.

**Re-blocked beads:** if a bead was claimed while ready but later picked up a new
blocker, recovery won't blindly re-run it. At every claim site bead-chain
rechecks blockers via `bd show`; a blocked stranded bead is reverted to `open`
(re-entering the queue behind its blockers) instead of being driven on stale
inputs.

---

## The close guard

While bead-chain is active, any attempt by the agent to run `bd close` or
`bd update --status=closed` **itself** is blocked:

> bead-chain blocked `bd close`. The bead will be closed automatically once
> the LLM judges sign off — do NOT close it yourself.

This is deliberate. **Only the LLM judges may close a bead.** An agent closing
its own work would short-circuit the quality gate. bead-chain does the closing
for you, after the judges pass.

---

## Epic rollup at session end

When the queue drains, bead-chain runs `bd epic close-eligible` **once** to
auto-close any epics whose children are all complete. This runs at the drain
pass, not after every close, to avoid bd's server-side cascade closing unrelated
epics.

**Recurring molecules are protected.** A poured `patrol` molecule is a recurring
monitor — auto-closing its epic would kill the recurrence. Rollup previews the
eligible set with `--dry-run` and skips any recurring epic, closing only the safe
ones.

---

## Bug discovery while you work

Every goal prompt carries a bug-discovery protocol. When the agent finds an
unrelated bug mid-task:

| Scenario | What happens |
|----------|--------------|
| **Non-blocking** (doesn't prevent the current goal) | Filed via `bd create --type=bug` and work continues. Priority-1 routing picks it up in a later iteration. |
| **Blocking** (can't finish the current bead without fixing it) | Filed with a `[bead-chain:triaged]` marker, fixed inline as scope expansion, and both are summarized for the judges. The bug stays open for proper verification later. |

Agents never close beads — including bug beads. The judges are the only
legitimate closer.

---

## Syncing your work

bead state lives in a local Dolt database and travels on `refs/dolt/data`, which
a plain `git push` does **not** carry. The session-close workflow adds a
`bd dolt push` step after `git push` to ship your bead mutations. bead-chain
itself never pushes — durability is a session-close responsibility, not a queue
driver's. See [AGENTS.md](../AGENTS.md) and
[ADR 0001](../notes/decisions/0001-dolt-push-lives-in-session-close.md) for the
full rationale.

---

## See also

- **[Troubleshooting](troubleshooting.md)** — common snags and fixes.
- **[Repo README](../README.md)** — feature tour, architecture, and module map.
