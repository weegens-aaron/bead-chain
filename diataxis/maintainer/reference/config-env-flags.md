# Reference: Configuration, environment, and flags

## CLI flags

### `/bead-chain` — Main entry point

```bash
/bead-chain [OPTIONS]
```

#### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--max=N` | int | ∞ (unlimited) | Stop after closing N beads. Use for safety caps during testing. Example: `--max=3` closes 3 beads then stops. |
| `--help` | flag | — | Show usage and exit. |

#### Examples

```bash
# Run until queue empty
/bead-chain

# Safety cap: stop after 1 bead
/bead-chain --max=1

# Process 5 beads, then stop
/bead-chain --max=5

# Show help
/bead-chain --help
```

---

## Environment variables

### `BEADS_BIN` — Custom `bd` executable path

**Type:** string (path)

**Default:** `bd` (looks on `PATH`)

**When to use:**
- `bd` is not on your `PATH`
- You have multiple `bd` versions installed and need a specific one

**Example:**
```bash
export BEADS_BIN=/usr/local/bin/bd-1.0.5
/bead-chain
```

### Timeout and retry behavior (hardcoded, not configurable)

These are defined in `beads.py` as module constants:

| Constant | Value | Purpose |
|----------|-------|----------|
| `DEFAULT_TIMEOUT` | 30 seconds | Max time to wait for any `bd` command |
| `MAX_ATTEMPTS` | 3 | Retry count for transient timeouts (initial + 2 retries) |
| `_RETRY_BACKOFFS` | (0.5s, 1.0s) | Delays before retry attempts (exponential-ish) |

**Why hardcoded?** Per YAGNI: if someone needs env-var knobs, it's a 5-line follow-up. Doing both now overcommits.

**Behavior:**
- If `bd show` times out, retry after 0.5s
- If it times out again, retry after 1.0s
- If it times out a third time, give up and raise `BeadsError`
- Non-timeout failures (bd missing, non-zero exit) fail immediately (not retried)

---

## Configuration state (`state.py`)

No configuration file. Runtime state is held in memory:

```python
class ChainState:
    active_bead: dict | None          # Currently in_progress bead
    completed_count: int               # Beads closed in this session
    original_in_progress: dict | None  # Stranded bead from previous run
```

**Why?** bead-chain is a transient loop (runs 5 minutes, closes some work, exits). State persists across runs via the beads database (`bd list`, `bd show`), not via config files.

---

## Excluded types (hardcoded)

**Module:** `beads.py`

```python
EXCLUDED_TYPES = (\"epic\",)
```

**Effect:** bead-chain will never claim or drive an epic. Epics are containers; only leaf beads (tasks, bugs, docs) are work.

**Client-side filter:** Even if `bd ready --exclude-type=epic` leaks an epic (bd version drift), the client-side check catches it.

**To extend:** Edit `EXCLUDED_TYPES`, one-line change. DRY.

---

## Blocking dependency types (hardcoded)

**Module:** `beads.py`

```python
BLOCKING_DEP_TYPES = (\"blocks\",)
```

**Effect:** Only `blocks` edges gate work. Other edges (parent-child, discovered-from, related) do not.

**Case-insensitive:** Comparisons are lowercased for forward compatibility.

**To extend:** Add a new type string (e.g., `\"requires\"`) and edit `BLOCKING_DEP_TYPES`. One-line change. DRY.

---

## Satisfied blocker statuses (hardcoded)

**Module:** `beads.py`

```python
SATISFIED_BLOCKER_STATUSES = frozenset({\"closed\"})
```

**Effect:** A blocker only stops being a blocker once it is `closed`. A blocker in `open`, `in_progress`, or `blocked` state still gates work.

---

## Blocking bug types (hardcoded)

**Module:** `beads.py`

```python
BLOCKING_BUG_TYPES = (\"bug\",)
```

**Effect:** In `pick_next_bead()`, if a ready bug has `dependent_count > 0`, it jumps tier 1 ahead of epic affinity and global queue.

**To extend:** Add a new type (e.g., `\"regression\"`) and edit the tuple. One-line change. DRY.

---

## Close guard configuration

**Module:** `close_guard.py`

**Hardcoded behavior:**
- Intercepts `bd close` and `bd update --status=closed`
- If `state.active_bead` is set, blocks the command
- Prints a reminder message
- Idempotent (multiple registrations don't double-block)

**No configuration flags.** The guard is always on whenever bead-chain is active.

---

## Epic affinity configuration

**Module:** `lifecycle.py`

**Hardcoded behavior:**
- After closing a bead, prefer the next **sibling** (same parent epic) before falling back to global queue
- \"Sibling\" = same `parent` epic ID, status `open`, not blocked
- If no sibling is ready, fall back to global `bd ready`

**Why hardcoded?** Epic affinity is core to the design (coherent commits). Making it optional would create two code paths (complexity). If you don't want this behavior, override `pick_next_bead()` in your extension.

---

## Summary of what's configurable vs. hardcoded

| Item | Configurable? | Where |
|------|---------------|-------|
| `bd` executable path | Yes (env var) | `BEADS_BIN` |
| Max beads to process | Yes (CLI flag) | `--max=N` |
| Timeout duration | No (hardcoded) | `beads.py` line 19 |
| Retry attempts | No (hardcoded) | `beads.py` line 20 |
| Blocking edge types | No (hardcoded) | `beads.py` line 39 |
| Satisfied blocker status | No (hardcoded) | `beads.py` line 41 |
| Epic affinity behavior | No (hardcoded) | `lifecycle.py`, override in extension |
| Close guard activation | No (hardcoded) | Always on when bead-chain runs |
| Excluded bead types | No (hardcoded) | `beads.py` line 37 |

**Philosophy:** Most config is hardcoded per DRY and YAGNI. The two user-facing knobs (`BEADS_BIN`, `--max`) are the likely needs. If a new requirement emerges, it's a straightforward PR to add it.

---

## Related

- **What do the blocker logics actually check?** See [blocker-gate-logic.md](./blocker-gate-logic.md).
- **Understand the architecture?** Read [architecture.md](./architecture.md).
- **Want to extend bead-chain?** Check [../how-to/extend-with-custom-logic.md](../how-to/extend-with-custom-logic.md).
"