# _Manifest.md — bead-chain maintainer documentation

Tracks every item to document for the **maintainer** audience, grouped by its
Diátaxis type. Each item was classified with the compass (see
[`_DiataxisGuide.md`](_DiataxisGuide.md)) before being placed here.

> Type folders (`tutorials/`, `how-to/`, `reference/`, `explanation/`) are
> created **lazily** — a folder comes into existence only when its first doc
> lands in it. Do not pre-create empty buckets (the anti-pattern).

## Progress

- Total items: 10
- Completed: 0
- Remaining: 10

Per-type counts: Tutorials 1 · How-to 3 · Reference 2 · Explanation 4

## Tutorials

Compass: action + acquisition (a newcomer learning the codebase by doing).

- [ ] 001 | Tutorial: Run bead-chain locally and pass the test suite -> [Run bead-chain locally and pass the test suite](tutorials/run-locally-and-test.md)

## How-to

Compass: action + application (a competent contributor doing a real task,
including troubleshooting).

- [ ] 002 | How-to: Add a new excluded container bead type -> [Add a new excluded container bead type](how-to/add-excluded-bead-type.md)
- [ ] 003 | How-to: Diagnose and recover a stranded in_progress bead -> [Diagnose and recover a stranded in_progress bead](how-to/recover-stranded-bead.md)
- [ ] 004 | How-to: Extend the close-guard to block another bd command -> [Extend the close-guard to block another bd command](how-to/extend-close-guard.md)

## Reference

Compass: cognition + application (look up the precise machinery while working).

- [ ] 005 | Reference: /bead-chain command and configuration -> [/bead-chain command and configuration](reference/command-and-configuration.md)
- [ ] 006 | Reference: Modules and public functions -> [Modules and public functions](reference/modules-and-functions.md)

## Explanation

Compass: cognition + acquisition (understand the why behind the design).

- [ ] 007 | Explanation: Why bead-chain is a queue driver, not a goal engine -> [Why bead-chain is a queue driver, not a goal engine](explanation/queue-driver-not-goal-engine.md)
- [ ] 008 | Explanation: Why bead-chain respects blocks at claim time -> [Why bead-chain respects blocks at claim time](explanation/work-time-blocker-gate.md)
- [ ] 009 | Explanation: Why epic rollup runs once per session -> [Why epic rollup runs once per session](explanation/once-per-session-epic-rollup.md)
- [ ] 010 | Explanation: Why hooks register lazily so wiggum runs first -> [Why hooks register lazily so wiggum runs first](explanation/lazy-hook-registration-ordering.md)
