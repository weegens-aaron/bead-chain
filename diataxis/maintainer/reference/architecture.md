# Reference: Architecture and module layout

## Architecture overview

bead-chain is a beads-driven queue driver that plugs into Code Puppy's `/goal` mode. It orchestrates a simple state machine: **pick → claim → drive → judge → close → repeat**.

```
┌─────────────────────────────────────────────────┐
│  /bead-chain (entry point)                      │
│       │                                         │
│       ▼                                         │
│  ┌───────────────────────────────────────────┐ │
│  │ lifecycle.pick_next_bead()                │ │
│  │  - blocking bugs (tier 1)                 │ │
│  │  - epic siblings (affinity)               │ │
│  │  - global queue (fallback)                │ │
│  └───────────────────────────────────────────┘ │
│       │                                         │
│       ▼                                         │
│  ┌───────────────────────────────────────────┐ │
│  │ lifecycle.claim_next(bead)                │ │
│  │  - check blocker gate                     │ │
│  │  - bd update --claim                      │ │
│  │  - store in state.active_bead             │ │
│  └───────────────────────────────────────────┘ │
│       │                                         │
│       ▼                                         │
│  ┌───────────────────────────────────────────┐ │
│  │ prompt.format_goal_prompt(bead, ...)      │ │
│  │  - recovery preamble (if stranded)        │ │
│  │  - bug discovery protocol                 │ │
│  │  - bead description                       │ │
│  └───────────────────────────────────────────┘ │
│       │                                         │
│       ▼                                         │
│  ┌───────────────────────────────────────────┐ │
│  │ wiggum.invoke_goal(prompt) [external]     │ │
│  │  - LLM judges evaluate completion         │ │
│  │  - agent works on goal                    │ │
│  └───────────────────────────────────────────┘ │
│       │                                         │
│       ▼                                         │
│  ┌───────────────────────────────────────────┐ │
│  │ lifecycle.close_or_recover(bead, result)  │ │
│  │  - judges passed? → close                 │ │
│  │  - judges failed? → revert & loop         │ │
│  │  - can't close? → recovery mode next time │ │
│  └───────────────────────────────────────────┘ │
│       │                                         │
│       └──► (next bead) ───┐                    │
│                           ▼                    │
│                    (queue empty? stop)         │
└─────────────────────────────────────────────────┘
```

---

## Module responsibilities

### `register_callbacks.py` — Wiring and CLI integration

**Entry point:** Registers `/bead-chain` command with Code Puppy.

**Responsibilities:**
- Parse CLI flags (`--max`, `--help`)
- Register hook handlers into wiggum's lifecycle
- Validate environment and detect stranded beads
- Pretty-print summary at the end

**Does NOT:**
- Make `bd` calls (use `beads.py`)
- Manage state directly (use `state.py`)
- Format prompts (use `prompt.py`)

**Key exports:**
- `register()` — Called by Code Puppy at startup
- `cmd_bead_chain(args: List[str])` — Slash command handler

---

### `lifecycle.py` — State transitions and guards

**Core job:** Implement the state machine (pick → claim → drive → judge → close → repeat).

**Responsibilities:**
- `pick_next_bead()` — Apply the waterfall (blocking bugs → epic affinity → global)
- `claim_next(bead)` — Check blocker gate, call `bd update --claim`
- `close_or_recover(bead, result)` — Handle post-judgment: close or revert
- `handle_recovery()` — Detect stranded beads and resume
- `epic_affinity_siblings(bead)` — Find unblocked siblings under the same parent epic
- Guard invariants (one-bead-at-a-time, no premature closes)

**Does NOT:**
- Know about prompts or formatting
- Shell out directly (use `beads.py` for all bd calls)
- Hold mutable state (use `state.py` singleton)

**Key exports:**
- `pick_next_bead() -> dict | None`
- `claim_next(bead) -> None` (raises on blocker)
- `close_or_recover(bead, result) -> None`

---

### `beads.py` — Subprocess wrapper around `bd` CLI

**Core job:** Shell out to `bd` and parse JSON. No beads Python API; only CLI.

**Responsibilities:**
- `next_ready() -> dict | None` — `bd ready --json`
- `next_in_progress() -> dict | None` — `bd list --status=in_progress --json`
- `show(bead_id) -> dict | None` — `bd show <id> --json`
- `open_blocker_ids(bead_id) -> List[str]` — Fetch blocker dependencies
- `claim(bead_id)` — `bd update <id> --claim`
- `close(bead_id, reason)` — `bd close <id>`
- `revert_to_open(bead_id)` — `bd update <id> --status=open`
- Retry logic for transient timeouts (3 attempts, exponential backoff)

**Raises `BeadsError` on:**
- bd not found on PATH
- Timeout (after retries)
- Non-zero exit (bead not found, already closed, etc.)
- Non-JSON output

**Does NOT:**
- Know about chain state or logic
- Parse bead semantics (just passes through bd's JSON)
- Make decisions (it's a thin wrapper)

**Key exports:**
- `next_ready(), next_in_progress(), show(), claim(), close(), revert_to_open()`, etc.

---

### `prompt.py` — Goal prompt formatting

**Core job:** Build the goal prompt passed to `/goal`.

**Responsibilities:**
- Format recovery preamble (if stranded)
- Include bug discovery protocol
- Format bead description (title, parent epic context, labels)
- Template the complete prompt

**Does NOT:**
- Invoke `/goal` (that's wiggum's job)
- Make bd calls
- Manage state

**Key exports:**
- `format_goal_prompt(bead: dict, is_recovery: bool = False) -> str`

---

### `state.py` — Singleton chain state

**Core job:** Hold the mutable state (what bead is active, how many closed, etc.).

**Data:**
- `active_bead` — Current `in_progress` bead dict
- `completed_count` — Number of beads closed in this session
- `original_in_progress` — Stranded bead from previous run (for recovery)

**Why not global variables?** Easier to test (inject a fresh state), easier to debug (single object to inspect).

**Key exports:**
- `ChainState` — Dataclass with mutable fields

---

### `close_guard.py` — Shell hook that blocks premature closes

**Core job:** If a bead is under bead-chain's watch, prevent agents from closing it manually.

**Mechanism:** Registers a shell hook that intercepts `bd close` and `bd update --status=closed`.

**Behavior:**
- If `state.active_bead` is set, block the close with a reminder
- If no active bead, allow the close (outside bead-chain)
- Always idempotent (multiple blocks are fine)

**Key exports:**
- `register_shell_hook()` — Called by `register_callbacks` at startup

---

## Data flow: Pick to close

### Incoming data

`bd ready --json` returns a list of bead dicts. Each dict has:
```json
{
  \"id\": \"proj-1abc\",
  \"title\": \"Fix X\",
  \"issue_type\": \"task\",
  \"priority\": 2,
  \"status\": \"open\",
  \"parent\": \"proj-epic-xyz\",
  \"dependencies\": [
    {\"id\": \"proj-bug-456\", \"dependency_type\": \"blocks\", \"status\": \"open\"}
  ],
  \"dependent_count\": 0,
  \"labels\": [\"bug-discovery\", \"diataxis\"],
  \"...\": \"...\"
}
```

### Processing

1. **pick_next_bead()** — Applies waterfall, returns top ready bead
2. **claim_next(bead)** — Checks `open_blocker_ids()`, calls `claim(bead.id)`
3. **format_goal_prompt(bead)** — Extracts title, labels, parent context
4. **wiggum.invoke_goal(prompt)** — External; returns judges' decision
5. **close_or_recover()** — If judges pass, calls `close(bead.id, reason)`

### Outgoing state

- Bead moves from `open` → `in_progress` → `closed`
- Parent epic can auto-close via `bd epic close-eligible` if all children done
- Session state (`completed_count`, `original_in_progress`) updates

---

## Key invariants

**One bead at a time (enforced):**
- Only one bead in `in_progress` (list_in_progress() checks this)
- Stranded beads from previous runs are resumed, not duplicated

**Blocker gate (enforced at claim time):**
- No bead with open `blocks` dependencies is claimed
- If a blocker is reopened after claim, recovery mode detects and reverts

**No premature closes (enforced via close_guard.py):**
- Agents cannot call `bd close` while a bead is active
- Only the LLM judges (via bead-chain) can close

**Epic affinity (applied in pick_next_bead):**
- Prefer unblocked siblings under the current epic before global queue
- Improves commit coherence

---

## File structure

```
bead_chain/
├── __init__.py                # Package docstring
├── register_callbacks.py      # 200 lines: wiring, CLI, summary
├── lifecycle.py               # 450 lines: pick/claim/close/recover
├── beads.py                   # 550 lines: bd CLI wrapper + retry logic
├── prompt.py                  # 150 lines: prompt formatting
├── close_guard.py             # 200 lines: shell hook to block closes
├── state.py                   # 50 lines: chain state dataclass
├── README.md                  # Usage and feature overview
├── AGENTS.md                  # beads usage for contributors
│
└── tests/
    ├── conftest.py            # Pytest fixtures
    ├── test_blocker_gate.py    # Blocker logic unit tests
    ├── test_pick_respects_blocks.py  # Pick + blocker integration
    ├── test_formula_epic_rollup.py   # Epic auto-close
    └── test_rollup_e2e.py      # End-to-end epic closure
```

---

## Dependency graph (imports)

```
register_callbacks
    ├─ lifecycle
    │   ├─ beads
    │   ├─ prompt
    │   └─ state
    ├─ state
    ├─ close_guard
    └─ (wiggum) [external]

lifecycle
    ├─ beads
    ├─ prompt
    └─ state

close_guard
    └─ state

prompt
    └─ (state) [optional, for recovery context]

beads
    └─ (none — pure subprocess wrapper)
```

**Circular imports:** None. Data flows from `register_callbacks` → `lifecycle` → `beads`, with `state` as a side channel for shared state.

---

## Related

- **How does the blocker gate work?** See [blocker-gate-logic.md](./blocker-gate-logic.md).
- **What configuration is available?** Check [config-env-flags.md](./config-env-flags.md).
- **Understand the epic affinity philosophy?** Read [../explanation/epic-affinity-philosophy.md](../explanation/epic-affinity-philosophy.md).
"