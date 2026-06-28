# ADR 0004 — A "blocked by open issues" close failure is recoverable, not a chain-halt

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| Status     | Accepted                                                              |
| Date       | 2026-06-09                                                            |
| Bead       | (filed alongside this ADR — see Follow-up)                            |
| Source     | Bug-discovery protocol deadlock; `lifecycle.close_current_bead_success` |
| Supersedes | —                                                                     |

## Context

When the LLM judges pass a bead, bead-chain auto-closes it in
`lifecycle.close_current_bead_success` via `close(bead_id, reason="bead-chain:
LLM judges passed")` (`lifecycle.py`). The current `except BeadsError` handler
treats **every** close failure as a fatal, infra-class problem:

> **Stop the chain.** A close failure means something is genuinely wrong (bd
> outage, permission issue, schema drift). Halt loudly rather than barreling on.

That assumption is too coarse. There is a second, *recoverable* class of close
failure that arises directly from the **Bug Discovery Protocol**
(`prompt._BUG_DISCOVERY_PROTOCOL`):

1. While working bead `X`, an agent discovers a blocking bug and, per protocol,
   files bug `Y` with `--blocks=<X>`.
2. The agent finishes (or partially finishes) and exits.
3. The judges run and **pass** `X`.
4. bead-chain calls `bd close X`, which bd **refuses** with `"blocked by open
   issue(s)"` because `Y` is open and blocks `X`.
5. The handler calls `state.stop()` — **the entire chain halts.**

This is a deadlock, not a fault: nothing is "genuinely wrong." A blocker was
filed *during* the bead's own run, which is exactly what the protocol told the
agent to do. The recovery path is already fully built — `lifecycle.pick_next_bead`
tier-0 (`_unblocked_strands`) reverts blocked beads to `open`, and tier-1 routes
to the blocking bug first (see
[WorkTimeBlockerGate](../../__docs/Features/WorkTimeBlockerGate.md)). The only
thing standing between the chain and self-healing is that the close-failure
handler kills the loop before that machinery ever runs.

The coarse handler conflates two distinct error classes:

| Error class                | Example                              | Correct response          |
| -------------------------- | ------------------------------------ | ------------------------- |
| Infra / config broken      | bd outage, permission, schema drift  | Halt loudly (keep)        |
| `"blocked by open issues"` | A blocker was filed during this run  | Revert to open + continue |

## Decision

**Split the `except BeadsError` handler in `close_current_bead_success` by error
class. A "blocked by open issues" close failure is recoverable: revert the bead
to `open` and continue the chain. Every other close failure keeps the existing
halt-loudly behavior.**

Concretely:

1. Add a narrow predicate (`_is_blocked_close_error`) that recognizes bd's
   "blocked by open issue(s)" close-refusal message.
2. On a recognized blocked-close error: emit an **info** (not warning) message,
   `revert_to_open(bead_id)`, clear `current_bead`, and **do not** call
   `state.stop()`. The next iteration's tier-0/tier-1 machinery routes to the
   blocker and re-drives the reverted bead once the blocker closes.
3. If the revert itself fails, fall back to halting (a failed revert *is* an
   infra-class problem).
4. All other `BeadsError`s retain today's behavior: warn, leave `in_progress`,
   `state.stop()`.

Independently, **reduce how often this path fires** by softening the Bug
Discovery Protocol so the common "I fixed it inline" case does **not** attach
`--blocks` to the current bead (the triage marker alone drives later
verification). `--blocks` is reserved for genuine dependency tracking. This is a
frequency reducer, not the correctness fix — the close-side recovery is what
makes the chain robust.

## Rationale

- **Distinguish faults from expected states.** A blocker filed during a run is a
  *documented, protocol-driven* outcome with a deterministic recovery path. The
  Zen of Python applies twice: *errors should never pass silently* (we still log
  it) but *in the face of ambiguity, refuse the temptation to guess* — and
  treating a recoverable state as a fatal fault is a guess that costs the whole
  chain.
- **The recovery machinery already exists.** `_unblocked_strands` +
  blocking-bug tier-1 routing were built precisely to respect work-time blocks.
  The close-failure halt short-circuits that investment for the one case it was
  designed to handle. Removing the halt lets the existing safety net do its job.
- **SRP / layering.** The close-side recovery lives where the close happens
  (`lifecycle`), not in the queue-selection layer and not in the prompt. The
  prompt change is a separate, lower-stakes concern (frequency), kept distinct.
- **Belt-and-suspenders, honestly.** bd's native close-time refusal remains the
  final net for genuinely blocked beads. We are not weakening that net — we are
  teaching the *driver* that tripping the net is sometimes routine.

## Alternatives considered

- **(a) Prompt-only fix: never file `--blocks` on the current bead.** *Rejected
  as the sole fix.* It narrows the window but cannot close it. A blocker can be
  wired after the claim (another agent/tool), or a genuine hard dependency may
  legitimately need `--blocks`. The chain must not halt when that happens. The
  prompt change is adopted as a *complement*, not a substitute.
- **(b) Three-branch protocol with an explicit "abandon" path.** *Rejected.* It
  assumed the agent could file `--blocks` and walk away cleanly, but the judges
  still run and the auto-close still fires and still fails — relocating the
  deadlock, not removing it. The close-side fix subsumes it.
- **(c) Pre-close blocker recheck that reverts before attempting `bd close`.**
  *Reasonable, deferred.* Could short-circuit the failing `bd close` entirely.
  But it duplicates the blocker-detection logic the close path already triggers
  via bd, and a pre-check has its own TOCTOU window. Handling the actual
  close-refusal is simpler and authoritative (bd is the source of truth on
  whether a close is allowed). Revisit if the failing `bd close` round-trip cost
  ever matters.

## Consequences

- **Positive:** the bug-discovery deadlock is gone; the chain self-heals via
  machinery that already exists; infra failures still halt loudly; the fix is
  small and local to `close_current_bead_success`.
- **Negative / accepted risk:**
  - **Token burn on re-drive.** A reverted bead is re-claimed in a later
    iteration after its blocker closes, re-loading context and possibly redoing
    work. Mitigated (optionally) by appending a judge-visible note on revert
    ("prior work may already satisfy criteria; verify before redoing"). The
    prompt softening reduces how often this happens.
  - **Brittle error-string match.** `_is_blocked_close_error` keys off bd's
    message wording, which can drift across bd versions. Mitigated by pinning it
    with a test against real bd output and keeping the match narrow; on a missed
    match we degrade to the *old* (halt) behavior, which is safe, not silent.

## Follow-up

Two beads are filed against this decision:

1. **Close-side fix (bug):** split the close-failure handler so a "blocked by
   open issues" refusal reverts to `open` and continues instead of halting. Add
   `_is_blocked_close_error` + regression tests (unit against the error string,
   e2e against a real bd `blocks` edge). Update the `close_current_bead_success`
   docstring and the affected docs (CloseGuard, WorkTimeBlockerGate narrative).
2. **Prompt enhancement (task, blocked by #1):** soften
   `_BUG_DISCOVERY_PROTOCOL` so the inline-fix case files the bug with the triage
   marker but **without** `--blocks` on the current bead; reserve `--blocks` for
   genuine dependency tracking. Update the design-decisions comment and the
   user-facing bug-handling guide/FAQ/README.
