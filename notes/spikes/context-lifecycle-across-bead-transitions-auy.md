# Context Lifecycle Across Bead Transitions

**Spike:** `bead_chain-auy`
**Date:** 2026-06-09
**Status:** Complete

## Executive Summary

When bead-chain transitions from bead N to bead N+1, the LLM gets a
**clean conversation history** but operates within an **unchanged runtime
environment**. The `clear_context: True` flag in the continuation dict
triggers two concrete host actions:

1. `current_agent.clear_message_history()` — wipes `_message_history` to `[]`
2. `finalize_autosave_session()` — persists the old session and rotates to a
   fresh autosave session ID

Everything else — system prompt, AGENTS.md, `load_prompt` plugin fragments,
tool registrations, kennel memories, bd memories, plugin singleton state,
wiggum config — **survives** across the transition because these are
reconstructed from disk/runtime sources each turn, not stored in
conversation history.

---

## Question-by-Question Analysis

### Q1: What does `clear_context: True` actually clear?

**Source:** `cli_runner.py:978–984` (host code)

```python
if continuation.get("clear_context", False):
    new_session_id = finalize_autosave_session()
    current_agent.clear_message_history()
    emit_system_message(
        f"Context cleared. Session rotated to: {new_session_id}"
    )
```

**What it clears:**

| Thing cleared | Mechanism | Evidence |
|---|---|---|
| Conversation history (all user/assistant/tool messages) | `clear_message_history()` sets `_message_history = []` and clears `_compacted_message_hashes` | `base_agent.py:189–191` |
| Autosave session | `finalize_autosave_session()` persists the current session, rotates to a new session ID | `config.py:2209` |

**What it does NOT clear:**

| Thing preserved | Why | Evidence |
|---|---|---|
| System prompt | Rebuilt fresh via `get_full_system_prompt()` on every agent `run()` call | `base_agent.py:162–180` |
| AGENTS.md / puppy rules | Loaded from disk by `load_puppy_rules()` → appended to system prompt | `_builder.py:38–83` |
| `load_prompt` plugin fragments | Collected fresh by `callbacks.on_load_prompt()` each turn | `base_agent.py:176–178` |
| Tool registrations | Statically defined in `get_available_tools()` | `agent_code_puppy.py:26–41` |
| MCP server connections | Held in `_mcp_servers` on the agent instance | `base_agent.py:79` |
| Agent identity | `self.id` is a `uuid4()` set at construction, never cleared | `base_agent.py:73` |

**The flag is authoritative, not advisory.** The host's continuation loop
in `cli_runner.py` checks `continuation.get("clear_context", False)` and
*acts on it* unconditionally. There is no "opt-out" path.

### Q2: What SURVIVES across bead transitions despite `clear_context`?

| Layer | Survives? | How it persists |
|---|---|---|
| **Conversation history** |  Wiped | `clear_message_history()` |
| **System prompt** (base) |  Yes | Rebuilt from `get_system_prompt()` each run; not stored in message history |
| **AGENTS.md** |  Yes | `load_puppy_rules()` reads from disk at prompt assembly time (`_builder.py:40–83`) |
| **`load_prompt` fragments** |  Yes | `on_load_prompt()` callback fires fresh each turn — includes Walmart rules, timestamp/CWD, file permissions, kennel recall, Tableau/Concord pointers |
| **Kennel memories** (host) |  Yes | `puppy_kennel` plugin's `_on_load_prompt()` calls `build_recall_block()` which queries the kennel SQLite DB fresh each turn (`puppy_kennel/register_callbacks.py:34–39`) |
| **bd memories** (project) |  Yes | `format_bead_as_goal()` calls `_fetch_memory_digest()` → `bd memories` subprocess each time a bead is armed; injected as `## Persistent Memories` block in the goal prompt (`prompt.py:117–150`) |
| **Plugin state (bead-chain)** |  Yes | `state.BeadChainState` is a module-level singleton (`_STATE`); `clear_context` never touches it. `active`, `current_bead`, `completed_count` persist across turns. |
| **Plugin state (wiggum)** |  Reset then re-armed | `wiggum_state.start(goal_prompt, mode="goal")` resets `loop_count=0`, `remediation_notes=None`, and sets the new prompt. So wiggum starts fresh for each bead but is re-armed in the same call. |
| **Execution hints** |  Reapplied | `apply_execution_hints(bead)` is called for each new bead in `activate_next_bead()` (`lifecycle.py:714–716`) |
| **bd prime context** |  Not injected | `bd prime` output is not part of the goal prompt. The agent gets bead-specific context via `format_bead_as_goal()`, not the full `bd prime` dump. |
| **Skills / activated skills** |  Persist | Skill activations modify the agent's system prompt state at the host level; not part of conversation history. However, skills activated by bead N are NOT automatically passed to bead N+1 — the system prompt is rebuilt clean. |
| **File system changes** |  Persist | Disk is disk. Commits, file edits, git state — all survive. |

### Q3: What does `format_bead_as_goal()` inject as the new context?

**Source:** `prompt.py:354–415`

The goal prompt is built from these components, in order:

1. **Preamble** (conditional, mutually exclusive):
   - `_RECOVERY_PREAMBLE` if `recovery=True`
   - `_TRIAGE_VERIFY_PREAMBLE` if the bead is a triaged bug
   - Otherwise: no preamble

2. **Title line:** `Complete beads issue {bead_id}: {title}`

3. **Description:** The bead's full description text

4. **Persistent Memories block** (`## Persistent Memories`): bd's memory
   layer, max 12 entries at 280 chars each. Fetched fresh from `bd memories`.

5. **Issue metadata:**
   - Type, Priority
   - Parent epic (with title + description excerpt, max 280 chars)
   - Labels

6. **Design block** (`## Design`): if the bead has a `design` field

7. **Acceptance Criteria block** (`## Acceptance Criteria`): if present

8. **Template Lint Warnings block** (`## Template Lint Warnings`): output
   of `bd lint <id>`, showing missing template sections

9. **Related Context block** (`## Related Context`): non-gating edges
   (discovered-from, caused-by, validates, related, relates-to, tracks)

10. **Done checklist:** Run linters, run tests, commit, `bd remember`

11. **Bug Discovery Protocol:** Always appended at the bottom

**How much of the previous bead's work is summarized?** None directly.
The new goal prompt contains zero explicit summary of bead N-1's work.
Cross-bead continuity comes from:
- **bd memories:** Insights the previous bead's agent recorded via
  `bd remember` appear in the Persistent Memories block of the next bead
- **AGENTS.md:** Project-level instructions persist
- **Disk state:** Files, commits, test results are all on disk
- **Epic context:** The parent epic's title/description excerpt gives
  the LLM a sense of the larger effort

### Q4: Recovery mode — what context does the recovered bead get?

**Source:** `prompt.py:49–65` (`_RECOVERY_PREAMBLE`)

A recovered bead gets:
1. The `_RECOVERY_PREAMBLE` prepended to the normal goal prompt
2. The same full goal prompt as a fresh bead (description, acceptance
   criteria, memories, etc.)
3. `clear_context: True` — so conversation history from the crashed
   session is wiped

The preamble instructs the agent to:
- Assess what changes have already been made
- Check if tests/linters pass
- Determine if work is effectively done
- If satisfied, summarize what's in place rather than redoing work

**There is NO crash-context injection.** The recovered bead does NOT
receive:
- What the previous agent was doing when it crashed
- Which files it had modified
- Any partial conversation transcript
- Error messages from the crash

The agent is expected to discover the current state by inspecting disk
(git log, file diffs, test output). This is a deliberate design choice:
the recovery preamble says "assess the current state of the repo" rather
than trying to reconstruct what happened.

### Q5: Is there a mechanism for carrying insights from bead N to bead N+1?

**Yes — two mechanisms exist:**

| Mechanism | Scope | Injection point | Capacity |
|---|---|---|---|
| `bd remember <insight> --key=<slug>` | Project (travels with Dolt DB) | `## Persistent Memories` block in goal prompt | Max 12 entries × 280 chars each |
| Kennel memories (host) | Cross-repo (host agent's diary) | `load_prompt` fragment in system prompt | Host-managed capacity |

**bd memories** are the primary cross-bead channel. The done-checklist in
every goal prompt nudges agents to use it:
```
4. Record any durable, reusable insight you learned (a gotcha, a
   design decision, a non-obvious root cause) so the next bead
   starts warm: `bd remember <insight> --key=<short-slug>`.
```

**There is NO automatic note-passing.** bead-chain does not:
- Auto-append summaries of bead N's work to bead N+1's notes
- Copy completion notes between beads
- Inject `bd update --append-notes` on the next bead

The policy is explicit: bead-chain deliberately does NOT bridge bd's
project memories to the host Kennel (see `prompt.py:28–35`, the
`_MEMORY_DIGEST_MAX_ENTRIES` policy comment). The two are separate
layers by design.

### Q6: How does wiggum's `/goal` mode interact across bead-chain iterations?

**Source:** `wiggum/state.py:17–23`

Wiggum **fully resets** on each `wiggum_state.start()` call:

```python
def start(self, prompt: str, *, mode: str = "wiggum") -> None:
    self.active = True
    self.prompt = prompt
    self.loop_count = 0
    self.mode = mode
    self.remediation_notes = None
```

Every field is overwritten. There is no state that carries across
bead-chain iterations within wiggum. Specifically:
- `loop_count` resets to 0 (so each bead gets its own full iteration budget)
- `remediation_notes` is wiped (judge feedback from bead N doesn't leak)
- `prompt` is replaced with the new bead's goal prompt
- `mode` is reset to `"goal"` (bead-chain always sets this)

**The lifecycle:** For each bead:
1. `wiggum_state.start(goal_prompt, mode="goal")` — arms wiggum fresh
2. Wiggum drives `/goal` iterations (agent works, judges evaluate)
3. Within a single bead, wiggum may retry with `clear_context: True` +
   remediation notes appended
4. Judges pass → `wiggum_state.stop()` → wiggum goes inactive
5. bead-chain's `_on_interactive_turn_end` sees wiggum inactive →
   closes the bead → calls `activate_next_bead` → back to step 1

Note: within a single bead, if judges say INCOMPLETE, wiggum returns:
```python
{"prompt": f"{goal_prompt}\n\nJudge remediation notes:\n{notes}",
 "clear_context": True, ...}
```
So even within-bead retries clear conversation history. The only
cross-retry context is the remediation notes appended to the prompt.

### Q7: Scenarios where context should carry over but doesn't (or vice versa)?

**Context that SHOULD carry over but doesn't:**

| Gap | Impact | Severity |
|---|---|---|
| Related beads sharing domain knowledge get no explicit cross-bead summary | Agent N+1 may re-discover things agent N already figured out, wasting tokens | Low — mitigated by `bd remember` and disk state |
| If agent N discovers a non-obvious file layout or architecture pattern, it's lost unless explicitly `bd remember`'d | Agent N+1 starts cold on project topology | Low — AGENTS.md and bd memories partially cover this |
| Skills activated by bead N (e.g., a bead that activated `cp_walmart_colors`) don't auto-activate for bead N+1 | Next bead working on same UI area may forget the color rules | Medium — but skills are recorded in AGENTS.md if manually documented |

**Context that carries over and IS appropriate:**

| What carries | Why it's fine |
|---|---|
| bd memories | High-signal, curated, project-scoped. The right things to share. |
| AGENTS.md | Project rules should always apply. |
| Kennel memories | Cross-repo insights the host has learned. |
| Disk state | Obviously correct — work products persist. |

**Context that could inappropriately carry over (but doesn't, thanks to `clear_context`):**

| What's blocked | Why clearing is correct |
|---|---|
| Conversation history from bead N | Would confuse the LLM with irrelevant context from a different task |
| Tool call results from bead N | File contents may have changed; stale reads would be dangerous |
| Remediation notes from bead N's judges | Feedback on a different task is noise |

**Overall assessment:** The current design is well-calibrated. The clean
break is right for the common case (unrelated beads), and `bd remember`
provides the escape hatch for the uncommon case (related beads that need
to share domain knowledge). The main risk is agents forgetting to use
`bd remember` — but the done-checklist nudge mitigates this.

---

## Context Lifecycle Diagram

```
BEAD N LIFECYCLE                          BEAD N+1 LIFECYCLE
═══════════════                           ══════════════════

┌─────────────────────────┐
│  activate_next_bead()   │
│  ├─ claim(bead_id)      │
│  ├─ apply_exec_hints()  │
│  ├─ format_bead_as_goal │──── builds prompt from:
│  │   ├─ description     │    - bead dict fields
│  │   ├─ bd memories     │    - bd subprocess calls
│  │   ├─ epic context    │    - bd lint
│  │   ├─ acceptance_criteria
│  │   ├─ lint warnings   │
│  │   ├─ related context │
│  │   └─ bug protocol    │
│  ├─ wiggum_state.start()│──── resets loop_count=0,
│  │                      │     remediation_notes=None
│  └─ return {            │
│       prompt: "...",    │
│       clear_context:True│──┐
│     }                   │  │
└─────────────────────────┘  │
                              │
         HOST (cli_runner.py) │
         ═════════════════════╪═══════════
                              │
         ┌────────────────────▼───────┐
         │  clear_message_history()   │◄── conversation wiped
         │  finalize_autosave()       │◄── session rotated
         └────────────────────────────┘
                              │
         ┌────────────────────▼───────┐
         │  get_full_system_prompt()  │◄── rebuilt fresh:
         │  ├─ get_system_prompt()    │    - base agent prompt
         │  ├─ on_load_prompt()       │    - Walmart rules
         │  │   ├─ kennel recall      │    - kennel memories
         │  │   ├─ file permissions   │    - timestamps
         │  │   └─ plugin pointers    │    - skill refs
         │  └─ AGENTS.md (puppy rules)│
         └────────────────────────────┘
                              │
         ┌────────────────────▼───────┐
         │  run_prompt(next_prompt)   │◄── agent works on bead N
         │  ├─ tool calls (read/write)│
         │  ├─ shell commands         │
         │  └─ agent response         │
         └────────────────────────────┘
                              │
         ┌────────────────────▼───────┐
         │  _on_interactive_turn_end  │
         │  ├─ wiggum runs judges     │
         │  │   ├─ PASS → stop wiggum │
         │  │   └─ FAIL → retry with  │──→ clear_context: True
         │  │         remediation notes│    (within-bead retry)
         │  └─ bead-chain sees        │
         │      wiggum inactive       │
         └────────────────────────────┘
                              │
         ┌────────────────────▼───────┐
         │ close_current_bead_success │
         │  └─ bd close <id>          │
         └────────────────────────────┘
                              │
         ┌────────────────────▼───────┐
         │  activate_next_bead()      │──→ BEAD N+1 starts
         │  (same flow as above)      │    (exact same path)
         └────────────────────────────┘

  WHAT PERSISTS ACROSS THE BOUNDARY:
  ───────────────────────────────────
   System prompt (rebuilt from sources)
   AGENTS.md / puppy rules (from disk)
   load_prompt fragments (from plugins)
   Kennel memories (from SQLite)
   bd memories (from Dolt DB, via goal prompt)
   File system / git state
   bead-chain state singleton (active, count)
   Tool registrations
   MCP server connections
   Conversation history (wiped)
   Autosave session (rotated)
    Wiggum state (reset then re-armed)
    Activated skills (not auto-forwarded)
```

---

## Summary Table: Context Layers at Bead Close → Next Claim

| Context Layer | Stored In | Cleared by `clear_context`? | Available to next bead? | How? |
|---|---|---|---|---|
| Conversation messages | `_message_history` (in-memory) |  Yes |  No | Wiped by `clear_message_history()` |
| Compaction hashes | `_compacted_message_hashes` (in-memory) |  Yes |  No | Cleared alongside message history |
| Autosave session | File system + config |  Rotated |  No (new session) | `finalize_autosave_session()` |
| System prompt (base) | Agent class method |  No |  Yes | Rebuilt by `get_system_prompt()` each run |
| AGENTS.md | Disk file |  No |  Yes | `load_puppy_rules()` reads from disk |
| Walmart rules / timestamp | `load_prompt` hook |  No |  Yes | Rebuilt each turn by `on_load_prompt()` |
| Kennel memories | SQLite DB |  No |  Yes | `build_recall_block()` queries DB each turn |
| bd memories | Dolt DB (`bd memories`) |  No |  Yes | `_fetch_memory_digest()` in goal prompt |
| Tool registrations | Agent class |  No |  Yes | Static; defined in `get_available_tools()` |
| MCP servers | Agent instance |  No |  Yes | Held in `_mcp_servers`; not touched |
| bead-chain state | Module singleton |  No |  Yes | `_STATE.active`, `current_bead`, etc. |
| Wiggum state | Module singleton |  No (but re-armed) |  Re-armed | `start()` overwrites all fields |
| Execution hints | Applied per-bead | N/A |  Re-applied | `apply_execution_hints()` runs for each bead |
| Activated skills | Host-level |  No |  Depends | Skills that modify system prompt persist; but activation is not auto-forwarded |
| File system | Disk |  No |  Yes | Disk is disk |
| Git state | `.git/` |  No |  Yes | Commits, branches, etc. persist |
| Epic context | Goal prompt | N/A |  Yes | `_format_epic_metadata_lines()` fetches for each bead |

---

## Identified Gaps and Risks

### Low severity

1. **No automatic cross-bead work summary.** Bead N+1 relies entirely on
   disk state and `bd remember` entries for continuity. If bead N's agent
   doesn't `bd remember` a key insight, bead N+1 starts fully cold on that
   knowledge. The done-checklist nudge is the only mitigation.

2. **Skill activation doesn't auto-forward.** If bead N activates a skill
   (e.g., `cp_walmart_colors` for UI work), bead N+1 won't have it unless
   the bead description or AGENTS.md mentions it. For related beads in the
   same epic that need the same skill, this is a minor friction point.
   (Mitigation: bead authors can add `skills` metadata to beads via bd's
   skill field — but bead-chain's `apply_execution_hints()` only handles
   effort/model/agent_type today, not skills.)

### No action required

3. **Conversation wipe is correct.** The clean break prevents context
   confusion between unrelated tasks, keeps token budgets fresh, and avoids
   stale tool results. The cost (no implicit cross-bead context) is
   well-mitigated by the persistence mechanisms that DO survive.

4. **Recovery mode lacks crash context.** This is by design — reconstructing
   crash context from conversation history would be unreliable (the history
   was in-memory and lost with the crash). Having the agent assess disk state
   is more robust than trying to replay a corrupt/truncated transcript.
