# bead-chain documentation 

User-facing documentation for **bead-chain** — a beads-driven `/goal` variant
that chains your `bd ready` queue into wiggum's goal loop, one bead at a time.

New here? Start with **[Getting Started](getting-started.md)**.

---

## Guides

| Guide | Read it when you want to… |
|-------|---------------------------|
| **[Getting Started](getting-started.md)** | Install the prerequisites and run your first chain. |
| **[Usage](usage.md)** | Learn the day-to-day workflow: flags, stopping, recovery, and how the queue is ordered. |
| **[Troubleshooting](troubleshooting.md)** | Figure out why a bead isn't being picked up, why a close was blocked, or why your work didn't sync. |

---

## What is bead-chain, in one breath?

```
bd ready ─▶ claim ─▶ /goal ─▶ LLM judges ─▶ bd close ─▶ (next bead)
```

You run `/bead-chain` once. It pulls the next ready bead, claims it, hands it to
wiggum's `/goal` mode, lets the LLM judges decide when it's done, closes it, and
moves on — until the queue is empty or you press `Ctrl+C`. No manual bead
juggling, no lost context between tasks.

---

## Where things live

| Location | Purpose | Audience |
|----------|---------|----------|
| **[`README.md`](../README.md)** (repo root) | Project front page: feature tour, architecture, module map, configuration reference. | Everyone — start here for the big picture. |
| **`docs/`** (you are here) | Task-oriented how-to guides. | Users running bead-chain. |
| **`notes/`** | Working artifacts: ADRs (`decisions/`), deep analysis (`analysis/`), and triage/spike write-ups. | Maintainers and the curious. |

> **Rule of thumb:** if it helps you *use* bead-chain, it belongs in `docs/`.
> If it records *why a decision was made* or captures investigation work, it
> belongs in `notes/`.

---

## See also

- **[AGENTS.md](../AGENTS.md)** — instructions for agents using the `bd` issue tracker in this repo.
- **wiggum** — the `/goal` engine bead-chain delegates LLM-judged completion to.
- **beads / `bd`** — the underlying issue tracker CLI. Run `bd prime` for its full workflow reference.
