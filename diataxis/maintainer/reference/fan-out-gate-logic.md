# Reference: Fan-out gate logic

## The fan-out gate: overview

The fan-out gate prevents bead-chain from claiming or driving a bead that waits for spawned children to close. A fan-out gate is a `waits_for` field where:
- Field value is `"children-of(spawner_id)"` (exact format)
- The spawner is a bead that has spawned child beads (via molecule formulas)
- At least one spawned child is still `open` or `in_progress` (not `closed`)

**Current Status (bead_chain-9sc workaround):**

Due to a beads CLI upstream bug, beads with `waits_for: children-of(...)` gates are invisible to both `bd ready` and `bd blocked`. This implementation detects them at claim time in bead-chain and refuses to drive them.

**Enforcement point:**
- **At claim time** (`lifecycle.activate_next_bead()`) — If a bead has an unsatisfied fan-out gate, skip it and search for an alternative ready bead

---

## Background: What is a fan-out gate?

### Molecule workflow: spawning and synchronization

In bead-chain, a **molecule formula** can:
1. Contain a "discover" or other spawner bead that generates child beads
2. Contain a "finalize" or other consumer bead that must wait until all spawned children are done

**Example structure:**
```
- discover (spawner): runs once, spawns child-1..child-8
- process-child (template): instantiated 8 times as child-1..child-8
- finalize (consumer): waits for discover's children to all close
```

The finalize bead cannot run until all children are closed. This is expressed via the `waits_for` field:
```
waits_for: "children-of(discover)"
```

### Why gates exist (the problem they solve)

Without fan-out gates, you'd need:
- Manual dependency edges from finalize to each of the 8 children (brittle, hard to maintain)
- Or a custom script to detect spawned children (out of scope for beads)

The `children-of()` syntax allows formula authors to express "wait for all spawned children of this bead" without knowing in advance how many children exist.

### Why the gate is currently invisible

The beads CLI does not natively understand the `waits_for` field in the same way it understands `blocks` edges. The `bd ready` command doesn't know to exclude beads with unsatisfied `children-of()` gates, and `bd blocked` doesn't know to list them. This is a known upstream limitation.

**Bead-chain's workaround:** Detect these gates in Python at claim time and refuse to drive them. This is documented below.

---

## Gate logic: `_has_fan_out_gate_issue()`

**Location:** `lifecycle.py::_has_fan_out_gate_issue(bead_id)`

**Contract:**
```python
def _has_fan_out_gate_issue(bead_id: str) -> bool:
    """True if bead has an unsatisfied fan-out gate (waits_for: children-of(...)).
    
    False if:
    - No waits_for field
    - waits_for is not in children-of(...) format
    - All spawned children are closed
    - Bead or spawner don't exist (soft-fail)
    - Any error occurs (soft-fail)
    """
```

**Algorithm:**
1. Fetch the bead via `bd show <bead_id> --json`
2. Check if it has a `waits_for` field (string type)
3. Parse the field for `children-of(spawner_id)` format
4. Extract the `spawner_id`
5. Fetch all beads via `bd list --json`
6. Search for children where `parent == spawner_id` AND `status != "closed"`
7. Return `True` if any unclosed child exists, else `False`

**Example:**

If bead `mol-cw4` (finalize) has:
```json
{
  "id": "mol-cw4",
  "status": "open",
  "waits_for": "children-of(mol-0me)"
}
```

And `bd list --json` shows:
```json
[
  {"id": "mol-0me", "status": "closed"},
  {"id": "mol-0me.1", "parent": "mol-0me", "status": "open"},
  {"id": "mol-0me.2", "parent": "mol-0me", "status": "open"},
  ...
]
```

Then `_has_fan_out_gate_issue("mol-cw4")` returns `True` (finalize cannot run yet).

When all children close:
```json
[
  {"id": "mol-0me", "status": "closed"},
  {"id": "mol-0me.1", "parent": "mol-0me", "status": "closed"},
  {"id": "mol-0me.2", "parent": "mol-0me", "status": "closed"},
  ...
]
```

Then `_has_fan_out_gate_issue("mol-cw4")` returns `False` (finalize is now ready).

---

## Claim-time check: `activate_next_bead()`

**Location:** `lifecycle.py::activate_next_bead()`

**Pseudocode:**
```python
def activate_next_bead() -> bool:
    # ... existing code to pick a ready bead ...
    
    # NEW: Check for fan-out gates
    if _has_fan_out_gate_issue(bead["id"]):
        logger.warning(
            f"Bead {bead['id']} has unsatisfied fan-out gate: "
            f"waits_for=children-of(...) with unclosed spawned children. "
            f"Skipping; find other ready work."
        )
        return False  # Skip this bead, continue loop
    
    # Safe to claim
    beads.claim(bead["id"])
    state.active_bead = bead
    return True
```

**Result:** If a bead has an unsatisfied fan-out gate, bead-chain skips it and searches for alternative ready work. The gated bead re-enters the queue once all spawned children close.

---

## Soft-fail behavior

`_has_fan_out_gate_issue()` soft-fails to `False` (treat as unblocked) if:
- Bead ID is empty → Return `False`
- `bd show` raises an exception → Return `False`
- Bead record is `None` → Return `False`
- `waits_for` is not a string → Return `False`
- `children-of(...)` format is malformed → Return `False`
- Spawner bead can't be found → Return `False`
- `bd list --json` fails → Return `False`

**Rationale:** A transient bd blip must not strand the chain. If we can't determine gate status, assume the gate is satisfied and let the bead proceed. If the gate was actually unsatisfied, the bead will fail at close time (the final safety net). This is defensive and matches the philosophy of `open_blocker_ids()`.

---

## Lifecycle of a fan-out-gated bead

### Phase 1: Spawned (children exist, not yet closed)

```
Spawner (discover) closes
↓
Spawned children (mol-0me.1..8) are open/in_progress
↓
finalize bead has waits_for: children-of(mol-0me)
↓
_has_fan_out_gate_issue(finalize) → True
↓
bead-chain skips finalize at claim time
↓
finalize remains open, invisible to bd ready
```

### Phase 2: Unblock transition (last child closes)

```
Child N closes
↓
All children now closed
↓
_has_fan_out_gate_issue(finalize) checks and finds all children closed
↓
Returns False
↓
finalize is no longer gated
↓
Next time bd ready is called, finalize appears as ready
↓
bead-chain can now claim and drive finalize
```

### Phase 3: Execution (consumer runs)

```
finalize is claimed and in_progress
↓
Agent executes finalize (e.g., aggregates child results)
↓
Agent runs bd close finalize
↓
finalize moves to closed
```

---

## Testing the gate

**Unit tests:** `tests/test_fan_out_gate.py` — Mock spawner/child relationships and verify gate detection logic

**Key test cases:**
- Bead with no `waits_for` field → unblocked
- Bead with non-`children-of(...)` format → unblocked
- Spawner with unclosed children → blocked
- All children closed → unblocked
- Soft-fails on error (missing spawner, etc.) → unblocked
- Unblock transition (last child closes) → gate transitions from blocked to unblocked

**Run them:**
```bash
python -m pytest tests/test_fan_out_gate.py -v
```

---

## Diagnosing a stalled fan-out gate

### Symptom: A bead seems to be ready but won't run

```bash
bd ready | grep finalize
# (no output — finalize not listed)

bd list | grep finalize
# finalize | open | (other fields)

bd dep tree finalize
# [READY] <— mislabeled! (beads CLI bug)
```

### Diagnosis: Check the waits_for field

```bash
bd show finalize --json | jq '.waits_for'
# "children-of(mol-0me)"

# Check spawner and its children
bd show mol-0me --json | jq '.status, .id'
bd list --json | jq '.[] | select(.parent == "mol-0me")'
```

### If children are still open/in_progress

The finalize bead has an unsatisfied fan-out gate. It will remain skipped by bead-chain until all children close. You can:

1. **Check child progress:** Are they still running? Are they stuck?
   ```bash
   bd list --json | jq '.[] | select(.parent == "mol-0me") | {id, status}'
   ```

2. **Wait for children to finish:** Let the work complete naturally.

3. **Manually close stuck children** (if stuck):
   ```bash
   bd update mol-0me.1 --status=closed
   bd update mol-0me.2 --status=closed
   # etc.
   ```

4. **Verify the gate is satisfied:**
   ```bash
   bd list --json | jq '.[] | select(.parent == "mol-0me") | .status' | grep -v closed
   # (no output means all are closed)
   ```

5. **Verify bead-chain detects the gate is satisfied:**
   - Run bead-chain again; finalize should now be claimable

---

## How formula authors express fan-out gates

In a molecule formula (e.g., `diataxis-generate.toml`):

```toml
[[bead]]
id = "discover"
type = "task"
description = "Discover docs to generate"
# ... bead config ...

[[bead]]
id = "process-child"
type = "task"
description = "Process one discovered doc"
parent = "discover"  # spawned from discover
# ... bead config ...

[[bead]]
id = "finalize"
type = "task"
description = "Aggregate results after all docs processed"
waits_for = "children-of(discover)"  # ← FAN-OUT GATE
# ... bead config ...
```

The `waits_for = "children-of(discover)"` line tells bead-chain: "don't run me until all children of `discover` are closed."

---

## Known limitations and future work

### Current limitations

1. **Invisible in `bd blocked`:** The gate is only visible at bead-chain claim time via a log warning. It doesn't appear in `bd blocked` (upstream beads CLI limitation).

2. **No gate object:** The gate is not materialized as a beads `gate` object. It's pure logic in bead-chain (Python).

3. **Not in `bd dep tree`:** The `bd dep tree` command doesn't understand `waits_for` fields and will mislabel a gated bead as `[READY]` even though it's blocked.

### Future work (pending upstream fixes)

- **File an issue in the beads project** to add native support for `waits_for: children-of(...)` gates
- **Add `bd gate list`** output for fan-out gates (matching blocker gates)
- **Fix `bd ready`** to exclude gated beads server-side
- **Fix `bd dep tree`** to understand `waits_for` format and show correct labels

Until then, bead-chain provides this workaround at claim time.

---

## Related

- **Understand the full architecture?** See [architecture.md](./architecture.md).
- **How blocker gates work?** Check [blocker-gate-logic.md](./blocker-gate-logic.md).
- **Diagnosing bead issues?** See [../how-to/debug-stuck-bead.md](../how-to/debug-stuck-bead.md).
