# ADR 0001 — `bd dolt push` (refs/dolt/data sync) lives in the session-close protocol, not in bead-chain

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| Status     | Accepted                                                              |
| Date       | 2026-06-06                                                            |
| Bead       | `bead_chain-uo4` (FB-4), under epic `bead_chain-2p3`                   |
| Source     | `notes/analysis/bead-chain-coverage/08-data-layer.md` (gaps #1, #2), `GAPS.md` row 4 |
| Supersedes | —                                                                     |

## Context

Issues live in a **local Dolt database** (`.beads/embeddeddolt/`, git-ignored).
Every `bd` mutation bead-chain makes — claim, close, revert-to-open, epic
rollup — writes only to that local DB. Cross-machine durability requires
`bd dolt push`, which ships bead state under `refs/dolt/data` on the git remote.
A plain `git push` carries `refs/heads/*` only; it does **not** carry
`refs/dolt/data`.

The coverage audit found that **nobody in the documented end-to-end loop runs
`bd dolt push`**:

- bead-chain's drain path (`lifecycle.py:517-524`) is `rollup → emit → stop` —
  no sync.
- The `AGENTS.md` "Session Completion" workflow runs `git pull --rebase` /
  `git push` / `git status` — none of which moves `refs/dolt/data`.

On a single persistent dev box this is harmless (the local Dolt DB is
authoritative). But on a **fresh clone, CI, a second machine, or a disposable
agent environment**, every claim/close/revert from a run is stranded locally and
invisible to other actors. This is a *seam* between two components, not a code
defect in either — which is exactly why it needs a recorded policy call rather
than a one-line patch. (Audit severity: 2× P1.)

## Decision

**Sync responsibility lives in the session-close protocol (option (b)).**
bead-chain remains 100% sync-agnostic.

Concretely:

1. The `AGENTS.md` "Session Completion" mandatory workflow gains an explicit
   `bd dolt push` step, **immediately after `git push`**, **gated on a
   configured Dolt remote** (`bd dolt remote list` non-empty) and **soft-failing**
   (warn, do not halt) when no remote is configured or the push errors.
2. bead-chain's drain path is **not** changed. It does not push, pull, export,
   or import. A drain is *not* a session boundary.
3. Any environment that does not run the `AGENTS.md` session-close (CI,
   disposable agents) is responsible for invoking `bd dolt push` as part of its
   own teardown — it is simply *another caller* of the same session-close
   responsibility, at the same layer.
4. Interrupted chains (Ctrl+C / cancel) remain **local-only** until the next
   session-close runs `bd dolt push`. This is documented, not silently relied
   upon.

## Rationale

- **Single Responsibility.** bead-chain is a *queue driver*, not a sync engine —
  a deliberate boundary codified in
  `maintainer/explanation/queue-driver-not-goal-engine.md`. Pushing on drain
  would force the driver to own sync *policy* it has no business owning: which
  remote, push cadence (every bead? once per drain?), and whether to
  `bd dolt pull` on start. Durability is a different axis than queue-draining.
- **The home already exists.** Durability and hand-off already live in the
  session-close protocol, right next to `git push`. Adding `bd dolt push` there
  puts a durability concern beside the other durability concern instead of
  scattering it. One place owns "make this run's work durable and visible to
  others."
- **A drain is not a session end.** You may run several chains in one session.
  Pushing on every drain is either premature or redundant; pushing once at
  session-close is the correct cadence and matches the `git push` cadence
  already in the protocol.
- **CI/disposable case is solved at the right layer.** Rather than special-casing
  the queue driver, we treat those environments as additional callers of
  session-close. The fix generalizes instead of accreting branches in
  `lifecycle.py`.

## Alternatives considered

- **(a) bead-chain pushes on successful drain** (soft-fail when a remote is
  configured). *Rejected as the primary mechanism.* The audit's gap table
  floated this, but the audit's own "Notes / open questions" flags that owning
  sync policy "would arguably violate" the queue-driver boundary. It also fires
  at the wrong cadence (per-drain, not per-session). It remains a *possible
  future safety net* if real-world CI usage shows session-close is too often
  skipped — but we do not adopt it now (YAGNI).
- **(c) Document local-only as intended** (no code change). *Rejected.* It
  leaves a known P1 cross-machine durability footgun unaddressed the moment a
  Dolt remote is configured; it only defers the decision.

## Consequences

- **Positive:** SRP boundary preserved; bead-chain stays simple and sync-free;
  one well-known place owns durability; cheap to implement (a documented step +
  small gate).
- **Negative / accepted risk:** durability depends on session-close actually
  running. An agent that exits without session-close strands state locally —
  mitigated by (3) extending the responsibility to CI/disposable teardown and by
  (4) documenting the interrupted-chain behavior.
- **Out of scope (future-proofing only):** `bd dolt pull` at `/bead-chain`
  startup once remotes are in active multi-machine use (audit gap #5, P4).

## Follow-up

Per the success criteria, because we chose an active option (b), a concrete
implementation task is filed: add the gated, soft-fail `bd dolt push` step to the
`AGENTS.md` session-close protocol and document the interrupted-chain /
CI-teardown local-only caveat. See the bead filed against epic `bead_chain-2p3`.
