# Gates & Coordination — Coverage Findings

| Field            | Value                                                              |
| ---------------- | ----------------------------------------------------------------- |
| Capability area  | `gates-coordination`                                              |
| Field-guide ref  | `field-guide-06-gates-and-coordination.html` (chapter 6)          |
| Bead-chain owner | `bead_chain-5cd`                                                  |
| Primary modules  | `lifecycle.py`, `beads.py`, `close_guard.py`                      |
| Status           | `done`                                                            |

---

## 1. AVAILABLE — what the field guide documents

Chapter 6 ("Gates & Async Coordination") is the home of bd's *waiting*
primitives. Citing `field-guide-06-gates-and-coordination.html`:

- **§ I — A gate is a bead.** `bd gate create` mints a real issue whose
  `issue_type` is literally `gate`, carrying `await_type` + `await_id` fields
  and **one `blocks` edge** to its target. That `blocks` edge is what removes
  the target from `bd ready`; closing the gate returns it. Lifecycle is one
  line: *create → blocks target → resolve → target ready again.*
- **§ II — Five `await_type`s.** `human` (manual approval, the default),
  `timer` (`--timeout`, auto-resolves on expiry), `gh:run` (clears on
  Actions success, escalates on failure), `gh:pr` (clears on MERGED,
  escalates on CLOSED), and `bead` (cross-rig `<rig>:<bead-id>`). Note: bd
  v1.0.4 **removed automatic cross-rig polling** — `bead` gates are stored
  and resolved manually only.
- **§ III — Seven verbs, one engine.** `gate create / list / show / resolve /
  check / add-waiter / discover`. `bd gate check` is the operational heart: it
  polls open gates, **closes** the resolved ones, and (only with
  `--escalate`) flags failed ones. It prints a parseable summary line
  `Checked N gates: R resolved, E escalated, X errors`, and takes a `--type`
  filter (`gh` / `gh:run` / `gh:pr` / `timer` / `bead` / `all`). `add-waiter`
  is a *wake registry* (registers a worker address), **not** a bead-parking
  mechanism — the blocking comes entirely from the `blocks` edge.
- **§ IV — Fanout aggregation.** A waiter created with
  `--waits-for <spawner>` gets a `waits-for` edge; `--waits-for-gate` picks
  the mode: **all-children** (default — unblock when *every* child closes) or
  **any-children** (unblock the instant the *first* child closes). A
  *childless* spawner is **vacuously satisfied** (waiter is READY); it only
  becomes blocked once the spawner fans out into open children. Crucially, the
  guide states the mode "is **not** surfaced in `bd show --json`, `bd dep
  list`, or the bead's metadata" — it is a behaviour applied at
  ready-computation time, not a stored field.
- **§ V — Merge-slots.** An advisory mutex made of a bead:
  `<prefix>-merge-slot`, label `gt:slot`, status `open ↔ in_progress`, with
  `metadata.holder` and `metadata.waiters`. Verbs `create / check / acquire /
  release`. The queue is **advisory**: `release` does *not* auto-promote the
  next waiter and `acquire` does *not* dequeue — fair hand-off is a convention,
  not a guarantee.
- **§ VI — Two births.** Gates arrive either ad-hoc (`gate create --blocks`)
  or **auto-created from a formula step** that declares a
  `"gate": {"type": "human"}` field when the molecule is poured;
  `bd mol ready --gated` rediscovers a parked molecule when its gate closes.

## 2. LEVERAGED — what bead-chain actually uses

bead-chain handles gates only **indirectly through the `blocks` edge**, plus
**one explicit special-case** for formula fan-out gates. There is **no use of
the `bd gate` / `bd merge-slot` verb families at all**.

- **Gate→target blocking is honoured for free, via the generic `blocks`
  path.** A §I gate's `blocks` edge to its target makes the target disappear
  from `bd ready`, and `next_ready()` shells out to
  `bd ready --exclude-type=epic --json` (`beads.py:222`), inheriting that
  server-side filtering. At claim time, `open_blocker_ids()` (`beads.py:311`)
  re-checks inbound edges whose `dependency_type` is in
  `BLOCKING_DEP_TYPES = ("blocks",)` (`beads.py:75`) and is rejected if open —
  invoked at `lifecycle.py:100`, `:452`, and `:557`. A gate blocking a target
  reads as exactly such a `blocks` edge, so a *gate-blocked target* is
  correctly never driven. **This is implicit, not gate-aware** — bead-chain
  has no concept of `await_type`, `await_id`, resolution, or escalation.
- **Fan-out (`waits-for`) gates: the one explicit handler.**
  `_has_fan_out_gate_issue()` (`lifecycle.py:628`) parses a bead's `waits_for`
  field, matches the `children-of(<spawner>)` form, then scans
  `bd list --json` for any child of the spawner that is not `closed`
  (`lifecycle.py:670-690`). If one exists it returns `True`; the activation
  path (`lifecycle.py:576`) then refuses to claim, reverts the bead to `open`,
  and stops the chain. This is a documented workaround (`SOLUTION_SUMMARY.md`)
  for the upstream bd bug where formula fan-out gates are invisible to both
  `bd ready` *and* `bd blocked` — which the field guide §IV independently
  confirms ("not surfaced in `bd show --json` / `bd dep list`").
- **NOT leveraged (explicitly stated):**
  - `bd gate check` — **never called anywhere** in the codebase. bead-chain
    never ticks the gate-resolution engine.
  - `bd gate create / resolve / list / show / discover / add-waiter` — none
    used. bead-chain neither creates nor resolves gates.
  - `--waits-for-gate` aggregation **mode** — never read; the fan-out handler
    hardcodes all-children semantics (any unclosed child = blocked).
  - `bd merge-slot *` (create/check/acquire/release) — no references at all.
  - cross-rig `bead` gates and federation wake registration — unhandled.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                           | Severity | Recommended follow-up (one line)                                                                      |
| --- | -------------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------- |
| 1   | `bd gate check` is never run, so timer/gh:run/gh:pr gates that are resolvable-but-unresolved keep their target out of `bd ready` → chain sees an empty queue and stops short of ready-pending-poll work. | P1       | File a bead to run `bd gate check` (opt-in `--escalate`) on the probe pass before declaring the queue empty. |
| 2   | `gate`-type beads are not in `EXCLUDED_TYPES` (`beads.py:41` = `("epic",)`); an unblocked gate is itself a leaf on `bd ready`, so `next_ready()` could hand a gate to `/goal` as workable — it has no code work and the close-guard blocks closing it, stalling the chain. | P1       | Add `"gate"` to `EXCLUDED_TYPES` (one-line, mirrors the existing epic exclusion, server- + client-side). |
| 3   | Fan-out aggregation mode is invisible (§IV) and `_has_fan_out_gate_issue` hardcodes **all-children**; an **any-children** waiter that should be READY after the first child closes is wrongly refused/reverted. | P2       | File a bead to honour any-children once bd surfaces the mode; until then skip the revert when mode is unknown. |
| 4   | No merge-slot acquire/release/check; bead-chain assumes it is the sole writer and would ignore a `<prefix>-merge-slot` mutex if run alongside other rigs/agents. | P3       | Document the sole-writer assumption; optionally `merge-slot acquire` before drive in multi-agent setups. |
| 5   | No cross-rig `bead` gate handling and no `gate add-waiter` registration — bead-chain can't participate in federation wake-ups. | P3       | Out of scope for single-rig drains; revisit only if federation is adopted.                            |
| 6   | The fan-out workaround does a full `bd list --json` scan per `waits_for` bead (`lifecycle.py:670`) to enumerate a spawner's children — O(all issues) and duplicating gate evaluation bd should own. | P3       | File a bead to narrow the query (e.g. `bd list --parent=<spawner>`) or retire the workaround once bd surfaces fan-out gates. |

### Severity rubric

| Sev | Meaning                                                                       |
| --- | ---------------------------------------------------------------------------- |
| P0  | Correctness/data-loss hazard in the drain loop (e.g. closes wrong bead).      |
| P1  | Feature silently dropped where it changes which bead runs or how it's framed. |
| P2  | Feature unused where leveraging it would materially improve goal quality.     |
| P3  | Minor gap; workaround exists or impact is narrow.                            |
| P4  | Cosmetic / future-proofing only.                                            |

---

## Notes / open questions

- **Gate-blocked targets are safe; the gate *machinery* is the gap.** Because a
  gate's `blocks` edge rides the generic blocker path, a gate-blocked **target**
  can't leak into the chain — that part is sound. The exposure is (a) the chain
  never *advances* gates (Gap 1), and (b) the gate bead *itself* may leak as
  drivable work (Gap 2).
- **Gaps 1 + 2 are the headline pair** and are cheap to close: Gap 2 is a
  one-line constant edit; Gap 1 is a single `bd gate check` shell-out on the
  probe pass. Recommend both as fast follow-up beads (filed by the synthesis
  bead `bead_chain-hkb`, not here).
- Gap 3's root cause is partly upstream (the mode isn't stored — field guide
  §IV "Accuracy · bd v1.0.4"), so the bead-chain fix is gated on bd surfacing
  it; flagged for the synthesis matrix.
