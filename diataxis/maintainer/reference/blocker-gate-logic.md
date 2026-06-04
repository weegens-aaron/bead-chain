# Reference: Blocker gate and dependency logic

## The blocker gate: overview

The blocker gate prevents bead-chain from claiming or driving a bead that has an open work-time blocker. A blocker is a dependency edge where:
- `dependency_type == \"blocks\"` (case-insensitive)
- `status != \"closed\"` (the blocker is still open, in_progress, or blocked itself)

**Enforcement points:**
1. **At claim time** (`lifecycle.claim_next()`) — If a bead has open blockers, raise an error and skip it
2. **At recovery** (`lifecycle.handle_recovery()`) — If a stranded bead's blocker was reopened, revert the bead to `open`
3. **At close time** (via `bd close`) — The beads CLI itself refuses to close a bead with open blockers (safety net)

**Why three points?** Defence in depth. The close-time check is the final backstop, but catching blockers at claim time prevents wasted work.

---

## Dependency model

### Edge types (from beads spec)

A bead can have dependencies. Each dependency is a directed edge:

```json
{
  \"id\": \"other-bead-id\",
  \"dependency_type\": \"blocks\",  // or parent-child, discovered-from, related
  \"status\": \"closed\"             // or open, in_progress, blocked
}
```

**Edge types we care about:**

| Type | Direction | Blocks work? | Example |
|------|-----------|--------------|----------|
| `blocks` | Inbound (someone else blocks me) | **YES** | \"Bug X is blocking task Y\" |
| `parent-child` | Inbound (I'm a child epic) | **NO** | \"Task is under epic A\" |
| `discovered-from` | Inbound (spawned from a bead) | **NO** | \"Doc bead was spawned by discover bead\" |
| `related` | Inbound (cross-reference) | **NO** | \"Doc A is related to doc B\" |

**Canonical definition:** `beads.BLOCKING_DEP_TYPES = (\"blocks\",)`

### Blocker status lifecycle

A single blocker can have four states:

```
┌──────────┐
│ open     │  (task exists, not started)
└─────┬────┘
      │ claim → in_progress
      ▼
┌──────────┐
│ in_progress │  (task claimed, being worked)
└─────┬────┘
      │ (judges pass)
      ▼
┌──────────┐
│ closed   │  (work done, blocker satisfied)
└──────────┘

OR (if work is stranded/reverted):
┌──────────┐
│ blocked  │  (this blocker itself is blocked by something else)
└──────────┘
```

**For blocker gate purposes:**
- `open` → blocks work (not done)
- `in_progress` → blocks work (still being done)
- `blocked` → blocks work (itself is stuck)
- `closed` → does **NOT** block (work done)

---

## Gate logic: `open_blocker_ids()`

**Location:** `beads.py::open_blocker_ids(bead_id)`

**Contract:**
```python
def open_blocker_ids(bead_id: str) -> list[str]:
    \"\"\"Return list of open blocker ids; empty list means unblocked.\"\"\"
```

**Algorithm:**
1. Call `bd show <bead_id> --json` to fetch the bead's full record
2. Walk its `dependencies` array (each is a dict with `id`, `dependency_type`, `status`)
3. For each dependency:
   - Is `dependency_type` in `BLOCKING_DEP_TYPES`? (must be `\"blocks\"`)
   - Is `status` NOT in `SATISFIED_BLOCKER_STATUSES`? (must NOT be `\"closed\"`)
   - If both true, add the dep's `id` to the result
4. Return the list (empty = unblocked)

**Example:**

If task `task-123` has these dependencies:
```json
{
  \"dependencies\": [
    {\"id\": \"bug-456\", \"dependency_type\": \"blocks\", \"status\": \"open\"},     // BLOCKS
    {\"id\": \"bug-789\", \"dependency_type\": \"blocks\", \"status\": \"closed\"},   // does not block
    {\"id\": \"epic-xyz\", \"dependency_type\": \"parent-child\", \"status\": \"open\"} // does not block
  ]
}
```

Then `open_blocker_ids(\"task-123\")` returns `[\"bug-456\"]` (only the open blocks edge).

---

## Claim-time check: `claim_next()`

**Location:** `lifecycle.py::claim_next(bead)`

**Pseudocode:**
```python
def claim_next(bead: dict) -> None:
    blockers = beads.open_blocker_ids(bead[\"id\"])
    if blockers:
        # Don't claim; surface the blocker names
        blocker_str = \", \".join(blockers)
        raise RuntimeError(
            f\"Bead {bead['id']} is blocked by: {blocker_str}. \"
            f\"Fix the blockers first.\"
        )
    # No blockers; safe to claim
    beads.claim(bead[\"id\"])
    state.active_bead = bead
```

**Result:** If a bead has open blockers, it is never claimed. The chain loops to find the next ready bead.

---

## Recovery-time check: `handle_recovery()`

**Location:** `lifecycle.py::handle_recovery()`

**Scenario:** A previous run claimed a bead, then crashed. This run finds it `in_progress`. Check if blockers have changed; if not and the bead is unblocked, recover and resume it. If blocked, revert and skip.

**Pseudocode:**
```python
def handle_recovery() -> dict | None:
    workable = lifecycle._unblocked_in_progress()  # fetch list of unblocked in_progress bead(s)
    # (blocked beads are automatically reverted inside _unblocked_in_progress)
    if not workable:
        return None  # no recovery needed
    
    stranded = workable[0]  # pick the first (usually only) unblocked bead
    # Blockers already checked and unblocked; safe to resume
    return stranded
```

**Outcome:** If a stranded bead becomes blocked after it was claimed, `_unblocked_in_progress()` detects it and reverts it automatically. Only unblocked stranded beads are resumed.

---

## Close-time safety net: `bd close`

**Location:** Not in bead-chain; it's in the beads CLI itself.

**Behavior:** `bd close <id>` internally checks if the bead has open blockers. If it does, the close fails with:
```
Error: cannot close bead with open blockers: [bug-456, bug-789]
```

**Why it matters:** If somehow a blocker slipped past the claim-time check (version drift, human error), the close-time check catches it. Work is never considered \"done\" while blockers are open.

---

## The \"why three checks\" principle (defence in depth)

Each layer defends against a failure mode of the previous:

```
┌────────────────────────────────────────────────────────────┐
│ claim-time check (lifecycle.py)                            │
│   Purpose: prevent claiming a blocked bead                 │
│   Failure mode: bd version drift leaks a blocker            │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│ recovery-time check (lifecycle.py)                         │
│   Purpose: prevent resuming a bead whose blocker reopened  │
│   Failure mode: blocker closed, then reopened mid-run      │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│ close-time check (bd CLI)                                  │
│   Purpose: prevent closing if a blocker is now open        │
│   Failure mode: all previous checks somehow failed          │
└────────────────────────────────────────────────────────────┘
```

If all three fail to catch a blocker, the bead is closed with blockers open (very bad). This has not been observed in production, but the design assumes it won't happen.

---

## Blocker edge creation (who can wire them)

**Users can create blocker edges via:**
```bash
bd create --blocks=bug-456 --title=\"Task that depends on bug fix\"
```

Or by editing the bead:
```bash
bd update task-123 --blocks=bug-456
```

**bead-chain never creates blocker edges.** It only reads and respects them. The assumption is that domain experts (developers, managers) wire the dependencies; bead-chain just enforces them.

---

## Real-world scenarios

### Scenario 1: Task depends on open bug

```bash
bd create --type=bug --title=\"Fix X\" # → bug-abc (open)
bd create --type=task --blocks=bug-abc --title=\"Do Y\"
/bead-chain --max=1
```

**What happens:**
1. `bd ready` returns task (bug is open, so task is ready despite the blocks edge)
2. bead-chain tries to claim task
3. `open_blocker_ids(\"task\")` returns `[\"bug-abc\"]` (open blocker)
4. `claim_next()` raises and skips the task
5. `bd ready` next returns... nothing (bug is not ready, no other beads)
6. bead-chain says \"queue empty\" and stops

**Fix:** Fix the bug first.
```bash
bd close bug-abc
/bead-chain
# Now task is unblocked and claimed
```

### Scenario 2: Blocker reopened mid-session

```bash
# Session 1:
bd close bug-abc
/bead-chain  # claims task (no blockers)
# Agent is working, halfway through
# Ctrl+C → task stays in_progress

# Session 2:
bd update bug-abc --status=open  # someone reopened the bug
/bead-chain
# recovery mode: \"is task work done?\" → \"no\"
# check blockers → [\"bug-abc\"] (now open again!)
# revert task to open
# task re-enters queue behind bug-abc
```

**Outcome:** Work doesn't get wasted; the task is safely reverted and re-queued.

---

## Soft-fail behavior

`open_blocker_ids()` soft-fails to `[]` (treat as unblocked) if:
- `bd show` times out (after retries) → Assume no blockers; better to fail at close time
- `bd show` returns non-JSON or garbage → Assume no blockers
- Bead ID is empty or missing → Return `[]`

**Rationale:** A transient bd blip must not strand the chain. The close-time guard is the final safety net.

---

## Testing the gate

**Unit tests:** `tests/test_blocker_gate.py` — Mock blockers and verify the logic
**E2E test:** `tests/test_pick_respects_blocks.py` — Create real beads and verify bead-chain behavior

**Run them:**
```bash
python -m pytest tests/test_blocker_gate.py -v
python -m pytest tests/test_pick_respects_blocks.py -v
```

---

## Related

- **Understand the full architecture?** See [architecture.md](./architecture.md).
- **How are configurations set?** Check [config-env-flags.md](./config-env-flags.md).
- **Want to understand epic affinity?** Read [../explanation/epic-affinity-philosophy.md](../explanation/epic-affinity-philosophy.md).
"