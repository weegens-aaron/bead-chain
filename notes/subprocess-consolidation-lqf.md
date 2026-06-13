# Subprocess consolidation per bead activation (bead_chain-lqf)

Marketplace review remediation (epic `bead_chain-dyt`). A single bead
activation used to fan out 10+ sequential `bd` subprocess spawns, each
with up to a 30s timeout × 3 retries. This bead cuts the redundant ones.

## What changed

### 1. `list_recoverable_strands` — N calls → 1 call

`bd list --status` accepts a **comma-separated** list
(`bd list --status open,in_progress`, verified via `bd list --help` on
bd 1.0.5). The recovery tier now issues **one** `bd list
--status=in_progress,hooked --exclude-type=epic --json` instead of one
spawn per status in `RECOVERABLE_STATUSES`.

- `beads._list_by_status(status)` → `beads._list_by_status(*statuses)`
  (variadic; joins with `,`). `list_in_progress` still passes a single
  status; `list_recoverable_strands` passes the whole tuple.
- Ordering contract preserved (`in_progress` before `hooked`) via a
  **stable client-side sort** keyed on each bead's index in
  `RECOVERABLE_STATUSES` — a single comma-status call returns beads in
  bd's own sort order, not grouped by our tuple, so we re-impose it.
- Dedup retained defensively (one call can't really echo a bead twice,
  but bd version drift could).

### 2. Activation reuses one `bd show` for two guards

`activate_next_bead` ran the work-time blocker guard
(`open_blocker_ids`) and the fan-out gate guard
(`_has_fan_out_gate_issue`) back-to-back; each independently spawned an
**identical** `bd show <bead_id> --json`. We now fetch that full record
**once** at the activation boundary and thread it into both:

- `beads.open_blocker_ids(bead_id, bead=None)` — optional pre-fetched
  record; falls back to its own fetch when omitted (preserves the
  single-arg contract every other caller uses).
- `lifecycle._has_fan_out_gate_issue(bead_id, bead=None)` — same.
- The spawner lookup inside the fan-out guard is a *different* bead, so
  it stays a separate `bd show`.

One fresh read at the activation boundary keeps the mid-flight-mutation
safety (pinned / re-blocked detection) the guards were written for, at
one subprocess instead of two.

## Before / after subprocess count

Common path: a global-ready bead with **no parent epic**, no stranded
work, not a blocking bug.

| Step                                   | Before | After |
|----------------------------------------|:------:|:-----:|
| `list_recoverable_strands` (2 statuses)|   2    |   1   |
| `next_blocking_bug`                    |   1    |   1   |
| `next_ready`                           |   1    |   1   |
| `_reject_if_blocked` → `show`          |   1    |   1   |
| activate: blocker-guard `show`         |   1    |   1*  |
| activate: fan-out-guard `show`         |   1    |   0*  |
| `claim`                                |   1    |   1   |
| **Total**                              | **8**  | **6** |

\* the two activation-time `show` calls collapse to a single reused one.

**Net: 8 → 6 spawns (-25%) on the common path.** With more recoverable
statuses configured the `list` saving grows 1:1 (N statuses: N → 1).

## Gotchas for the next bead

- `bd list --status a,b` is the wire format; the JSON each bead carries
  has both `status` and `issue_type` fields (used by the sort + the
  epic re-filter).
- Test stubs that monkeypatch `open_blocker_ids` /
  `_has_fan_out_gate_issue` must now accept the optional second arg
  (`lambda _bid, _bead=None: ...`).
- The per-status fan-out stub (`_patch_run_bd_by_status`) was rewritten
  to split the requested `--status=a,b` arg and concatenate the mapped
  lists, so the consolidated call is exercised end-to-end.
