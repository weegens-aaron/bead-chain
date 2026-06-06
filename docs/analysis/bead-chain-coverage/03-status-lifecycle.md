# Status Lifecycle — Coverage Findings

| Field            | Value                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------- |
| Capability area  | `status-lifecycle`                                                                      |
| Field-guide ref  | `field-guide-03-status-lifecycle.html` (chapter 3)                                      |
| Bead-chain owner | `bead_chain-npn`                                                                        |
| Primary modules  | `lifecycle.py`, `beads.py`, `close_guard.py`, `register_callbacks.py`, `prompt.py`, `state.py` |
| Status           | `done`                                                                                  |

---

## 1. AVAILABLE — what the field guide documents

Chapter 3 ("Status, Lifecycle & Operational State") frames bd state as **two
axes**: *lifecycle status* ("where the work sits") and *operational state* ("what
the live system is doing"). This section owns the lifecycle-status axis; the
operational-state axis (`set-state` / `state`, event-as-truth) is a chapter-3
sub-topic that bead-chain touches nowhere and is recorded as a gap below.

### The seven built-in statuses (§ II.1, verbatim from `bd statuses`)

Source: `field-guide-03-status-lifecycle.html` § II.1, `STATUS_TABLE`. Custom
statuses go in `status.custom`. Each built-in rolls up into exactly one of **four
categories** (§ II.2, `CATEGORIES`).

| Status        | Category | Field-guide meaning                       | In `bd ready`?            |
| ------------- | -------- | ----------------------------------------- | ------------------------- |
| `open`        | active   | Available to work (default)               | yes, once unblocked       |
| `in_progress` | wip      | Actively being worked on                  | no (claimed/in flight)    |
| `blocked`     | wip      | Blocked by a dependency                   | no                        |
| `hooked`      | wip      | Attached to an agent's hook               | no                        |
| `deferred`    | frozen   | Deliberately put on ice for later         | no — "out of the queue"   |
| `pinned`      | frozen   | Persistent, stays open indefinitely       | no — "out of the queue"   |
| `closed`      | done     | Completed (terminal; `reopen` revives it) | no                        |

Category rollups (§ II.2): **active** = `open`; **wip** = `in_progress · blocked
· hooked`; **frozen** = `deferred · pinned` ("intentionally parked, out of the
ready queue"); **done** = `closed`.

### Idiomatic transitions (§ III.2, `TX_IDIOMATIC`)

The path teams *should* walk. Labels are the command that typically drives each
move; where no dedicated verb exists the guide writes the move as a `--status`
update so it never implies a CLI verb exists (§ III.3 — "there is no `bd block` /
`unblock` / `hook` / `pin`").

| From          | To            | Driven by              |
| ------------- | ------------- | ---------------------- |
| `open`        | `in_progress` | `--claim`              |
| `in_progress` | `closed`      | `close`                |
| `in_progress` | `blocked`     | `--status blocked`     |
| `blocked`     | `in_progress` | `--status in_progress` |
| `in_progress` | `hooked`      | `--status hooked`      |
| `hooked`      | `in_progress` | `--status in_progress` |
| `in_progress` | `pinned`      | `--status pinned`      |
| `open`        | `deferred`    | `defer`                |
| `deferred`    | `open`        | `undefer`              |
| `closed`      | `open`        | `reopen`               |

`TX_FREEFORM` (§ III.1) notes bd *also* permits non-idiomatic jumps with no
complaint (e.g. `closed → blocked`, `deferred → closed`) — the lifecycle is "a
convention, not an enforced cage."

### Verb reality (§ III.3, `VERB_REALITY`)

Only **four** lifecycle moves have dedicated convenience verbs — `close`
(alias `done`), `reopen`, `defer`, `undefer` — **plus** `--claim` on `update`.
Everything else (`blocked`, `hooked`, `pinned`) is reachable **only** via
`bd update <id> --status <x>`. `bd block` / `unblock` / `hook` / `pin` do not
exist.

### Lifecycle moves that emit events (§ IV, `MOVES`)

`close`, `reopen`, `supersede` (auto-closes the old bead), and `duplicate`
(close-as-dup pointer) each land an event on the bead's audit trail — more than
a bare status flip. `close` flags include `--reason`/`--reason-file`, `--force`
(**required to close `pinned` beads or unsatisfied gates**), `--suggest-next`,
`--claim-next`, `--continue`.

### Scheduling & staleness (§ VII)

Two **different** defer mechanisms: `bd defer <id> [--until <when>]` sets status
to **`deferred`** (frozen, hidden, returns via `bd undefer`); the `--defer
<when>` *flag* on create/update **keeps status `open`** but hides it from
`bd ready` until the date, then **self-clears** automatically. `stale` is
**computed, never stored** (`bd stale` surfaces beads untouched > 30 days; any
write resets `updated_at`).

---

## 2. LEVERAGED — what bead-chain actually uses

bead-chain is a serial drain loop, so it only ever needs a thin slice of the
lifecycle: claim a ready bead, recover a stranded one, revert when it can't
finish, and let the judges close. It implements exactly that slice — and reads
**`in_progress` as the only status it ever inspects**.

### Status reads

The single status value bead-chain reads is `in_progress`, pinned to a module
constant `_IN_PROGRESS_STATUS = "in_progress"` (`lifecycle.py:54`). It is
consumed in two ways:

- `is_recovery_bead()` (`lifecycle.py:57`) — `str(bead.get("status","")) ==
  _IN_PROGRESS_STATUS` (`lifecycle.py:68`) decides whether a picked bead is being
  *recovered* (already claimed) vs *freshly claimed*.
- `list_in_progress()` (`beads.py:230`) — shells out to `bd list
  --status=in_progress --exclude-type=epic --json` (`beads.py:251`) to enumerate
  stranded work. This is the only status-filtered `bd` query in the plugin.

No other status string (`open`, `blocked`, `deferred`, `closed`, `pinned`,
`hooked`) is ever read or compared anywhere in the codebase (verified by grep:
the only textual hits for `deferred`/`pinned`/`hooked`/`reopen`/`undefer`/
`supersede`/`--defer`/`bd stale` are incidental words inside doc-comments, not
handling — `beads.py:333` "blocker reopened", `prompt.py:21` "duplicate prose").

### Status writes (transitions bead-chain drives)

| bead-chain transition                | Implementation                                       | Maps to field-guide idiomatic edge        |
| ------------------------------------ | ---------------------------------------------------- | ----------------------------------------- |
| `open → in_progress`                 | `claim()` → `bd update <id> --claim` (`beads.py:471-473`) | `open → in_progress` (`--claim`)  idiomatic |
| `in_progress → open` (unwind)        | `revert_to_open()` → `bd update <id> --status=open` (`beads.py:476-494`) | **not** an idiomatic edge; closest verb is `reopen` (closed→open) — bead-chain uses a freeform `--status=open` jump from in_progress |
| `in_progress → closed`               | `close()` → `bd close <id> [--reason …]` (`beads.py:497-503`) | `in_progress → closed` (`close`)  idiomatic |

Claim, revert and close are wired into the drive loop as follows:

- **Claim (→ in_progress).** `pick_next_bead()`'s four-tier waterfall
  (`lifecycle.py:379`) selects a bead, then non-recovery picks are claimed via
  `claim(bead_id)` (`lifecycle.py:603`, and the command-handler path at
  `register_callbacks.py:261`). Recovery beads are *not* re-claimed — they are
  already `in_progress` (`lifecycle.py:608`, `register_callbacks.py:266`).
- **Recovery of stranded in_progress.** Tier 0 of the waterfall
  (`lifecycle.py:411-419`) returns the head stranded bead from
  `_unblocked_in_progress()` (`lifecycle.py:76`). `enforce_single_in_progress()`
  (`lifecycle.py:121`) enforces the one-at-a-time invariant at startup, returning
  the head and leaving extras `in_progress` to be drained one per iteration. A
  stranded bead is re-driven through `/goal` with the **`_RECOVERY_PREAMBLE`**
  (`prompt.py:24-46`, applied at `prompt.py:297`) so the agent assesses on-disk
  state before redoing work.
- **Revert-blocked-to-open.** `_unblocked_in_progress()` (`lifecycle.py:76`)
  refuses to recover a stranded bead that has open `blocks` edges: it calls
  `revert_to_open(bead_id)` (`lifecycle.py:109`) — the bdboard-oals fix, so
  work-time blocks are respected at claim time, not just at close. The same
  revert-on-can't-proceed pattern repeats at `register_callbacks.py:233`,
  `lifecycle.py:245` (stranded **epic** on close-failure),
  `lifecycle.py:566` and `lifecycle.py:585` (block / epic detected at activate).
- **Cancel leaves it in_progress (deliberate non-transition).**
  `_on_interactive_turn_cancel()` (`register_callbacks.py:351`) stops the chain
  on Ctrl+C and **leaves the in-flight bead `in_progress`** so the next run's
  tier-0 recovery resumes it — an intentional choice *not* to revert.
- **Close-guard (only the judges close).** `close_guard.py` blocks any agent
  shell-out to `bd close` (`_BD_CLOSE_RE`) **or** `bd update … --status=closed`
  (`_BD_UPDATE_STATUS_CLOSED_RE`) while the chain is active
  (`on_run_shell_command`, `close_guard.py`), reminding the agent the LLM judges
  are the only legitimate closer. Note the guard polices the *closed* status
  transition specifically — it does **not** police `defer`, `pinned`, `hooked`,
  or freeform `--status` jumps.

### What bead-chain leverages vs ignores, at a glance

- **Statuses inspected:** 1 of 7 (`in_progress`).
- **Transitions driven:** 3 (`→in_progress` via `--claim`, `→closed` via
  `close`, `→open` via raw `--status=open`). Of these, 2 are idiomatic edges and
  1 (`in_progress→open`) is a freeform jump bd permits but the guide doesn't list.
- **Verbs used:** `--claim`, `close`. **Verbs ignored:** `reopen`, `defer`,
  `undefer`, `supersede`, `duplicate`, `--force`.
- **Frozen axis (deferred/pinned):** untouched. bead-chain never parks a bead.
- **wip-but-not-in_progress (blocked/hooked):** never set, and only `blocked` is
  *indirectly* reasoned about — via the `blocks` **edge graph** (chapter 2's
  turf, `is_blocked()`/`open_blocker_ids()`, `beads.py:382`/`311`), **not** the
  `blocked` **status**. bead-chain treats "blocked" as a dependency fact, never
  flipping the status field to `blocked`; it reverts to `open` instead.
- **Operational-state axis (`set-state`/`state`/events):** untouched.

---

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                                                                                                                                   | Severity | Recommended follow-up (one line)                                                                                                       |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | A `pinned` bead that becomes ready/claimed can strand the chain: `close()` (`beads.py:497`) never passes `--force`, but the guide says closing a `pinned` bead **requires `--force`**, so `bd close` would fail and halt the loop (same family as the epic-close-fail hazard).                                                                                | P2       | File a bead to detect `status == "pinned"` on the picked bead and either skip it (treat as a frozen/excluded state) or close with `--force`. |
| 2   | Recovery only queries `bd list --status=in_progress` (`beads.py:251`); a bead transitioned to `hooked` or `pinned` mid-flight (by another agent/tool) is invisible to **both** `bd ready` and the recovery tier — stranded work that no run resumes.                                                                                                       | P2       | File a bead to widen the stranded-work query to the full `wip`/`frozen` rollup (e.g. also enumerate `--status=hooked`).                |
| 3   | `deferred` status + `defer`/`undefer` verbs are entirely unused. bead-chain has no way to *park* a bead it picks but legitimately can't finish yet — its only unwind is `revert_to_open` (`beads.py:476`), which drops the bead straight back onto the ready frontier, risking a re-pick loop on the next iteration.                                          | P3       | File a bead to consider `bd defer` (instead of revert-to-open) for "picked but not-now" beads, so they leave the ready queue cleanly. |
| 4   | `revert_to_open` drives `in_progress → open` via a **freeform** `--status=open` jump (`beads.py:494`) that is not in the guide's idiomatic edge set; the verb the guide blesses for re-opening is `reopen` (and that's `closed → open`). The unwind works (freeform jumps are permitted) but isn't the documented path and emits no Reopened event.            | P4       | Document the freeform unwind as intentional, or align naming so it doesn't read as a `reopen` it isn't.                                |
| 5   | The scheduled-snooze flag `--defer <when>` (status stays `open`, self-clears on date) is never used on `bd create` when bead-chain files bug beads (`bd create` calls in the bug-discovery protocol). Low impact for a serial driver, and `bd ready` already hides not-yet-due beads.                                                                        | P4       | No action unless deadline-aware scheduling is ever wanted; otherwise note as intentional (YAGNI for a serial loop).                   |
| 6   | The operational-state axis (`bd set-state`/`state`, event-as-truth) is untouched — bead-chain emits no operational events (e.g. "chain claimed/recovered bead X") into bd's audit trail; its signalling is `emit_info`/`emit_warning` to the console only.                                                                                                  | P4       | Consider emitting a bd `event` on claim/recover/revert for an auditable chain trail; cosmetic for now.                                |
| 7   | `close_guard` polices only the `closed` transition (`bd close`, `--status=closed`). An agent could still bypass intent by setting `--status deferred/pinned/blocked` mid-run, parking the active bead out of the judges' reach without "closing" it.                                                                                                          | P4       | If this is ever observed in the wild, extend the guard's pattern set to freeform `--status` mutations of the active bead.             |

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

- **Why nothing is rated P1/P0 here.** The lifecycle slice bead-chain actually
  needs — claim, recover-stranded, revert, judge-only close — is **covered and
  correct**, and the dangerous transitions are gated (close-guard) or
  defended-in-depth (epic/blocked reverts). The remaining gaps are *unused
  states* (`deferred`/`pinned`/`hooked`) that bd keeps **out of `bd ready` by
  design**, so they can't be selected on the happy path. They only bite when an
  external actor mutates a bead's status mid-flight — a real but narrow window,
  hence P2/P3. Gap #1 is the closest to a hazard (a strand) but is contingent on
  a `pinned` bead reaching `close()`, which the ready-queue exclusion normally
  prevents.
- **Transition-coverage scorecard.** Of the 10 idiomatic edges (§ III.2),
  bead-chain drives **2** (`open→in_progress`, `in_progress→closed`), drives a
  **3rd via a non-idiomatic freeform jump** (`in_progress→open`), and ignores the
  remaining 7 (`in_progress↔blocked`, `in_progress↔hooked`, `in_progress→pinned`,
  `open↔deferred`, `closed→open`). That's deliberate: a serial drain loop has no
  reason to park, hook, pin, or re-block work.
- **Cross-section seam — `blocked` is two things.** bead-chain handles
  *blockedness* via chapter 2's **`blocks` edge graph** (the bdboard-oals
  revert-on-block logic), never via the chapter-3 **`blocked` status**. The edge
  side is audited in `bead_chain-xoq` (dependency graph); this section counts
  only the *status* `blocked`, which bead-chain never sets, to avoid
  double-counting.
- **Cross-section seam — close mechanics.** The judge-only close *contract* and
  `close_guard` overlap chapter 6 (gates & coordination, `bead_chain-5cd`) and
  chapter 9 (quality & hygiene, `bead_chain-tl0`). Here it's counted only as the
  `in_progress → closed` lifecycle transition; the `--force`/gate-satisfaction
  angle of `close` lives in those sections.
- Gaps #1–#7 are recommendations for the synthesis bead (`bead_chain-hkb`); per
  the framework this section files no beads itself.
