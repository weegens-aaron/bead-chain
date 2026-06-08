# BugDiscoveryProtocol

## What It Does

Appends a fixed bug-handling rubric to **every** goal prompt bead-chain hands a
working agent: if you trip over a bug that's unrelated to the bead you're on,
*file* it as its own `bd` bug (one bug per bead) instead of silently fixing it
or abandoning your task — then, on a future iteration, the chain recognises the
filed bug and prompts a different agent to *verify* the fix rather than trust it
blind.

## Why It Exists

A disposable, stateless agent that stumbles on an unrelated bug has only bad
options without a protocol: fix it inline (scope-creeping the current bead and
muddying its commit/PR), ignore it (the bug evaporates with the agent's
context), or — worst — close its own bead to "move on" (the LLM judges are the
only legitimate closer). The bug-discovery protocol replaces all three with a
single, always-present instruction so bug handling is *identical on every
iteration of every bead* and never depends on an agent remembering the rules.

It also closes the loop on **blocking** bugs. When a bug genuinely stops the
current bead, the agent fixes it inline (scope expansion) **and** files it with
a `[bead-chain:triaged]` marker + a `--blocks` edge. That marker buys two
things: (1) tier-1 routing in `pick_next_bead` escalates the now-`dependent`
bug ahead of ordinary work via `next_blocking_bug`, and (2) when a later
iteration claims it, `is_triaged_bug` flips the prompt to a
triage-verification preamble so the inline patch gets a real test / proper fix
instead of being rubber-stamped. Filing-not-closing keeps the human-graded
close gate intact while still capturing every defect the swarm finds.

## How It Works

### User Perspective

The user never invokes this feature directly. They see its *effect*: every
spawned agent's goal prompt ends with a `BUG DISCOVERY PROTOCOL` block, so
when an agent hits an unrelated defect it emits a `bd create --type=bug ...`
call (visible in the run log) and keeps going, rather than derailing. Later in
the same `/bead-chain` session — or a future one — the user sees
`bead-chain: blocking bug detected -> prioritising <id>` as the chain jumps the
filed bug to the front, and that bug's agent receives a
`TRIAGE VERIFICATION` preamble telling it to confirm the earlier inline fix.

### System Perspective

The protocol is a static constant, `_BUG_DISCOVERY_PROTOCOL`, that
`format_bead_as_goal` concatenates onto the tail of *every* prompt regardless
of which (mutually exclusive) preamble was selected. Filing is delegated
entirely to the agent via raw `bd create` — bead-chain writes no code to create
the bug; it only *instructs*. The downstream half is split across two modules:
`beads.next_blocking_bug()` (server-side `bd ready --type=bug` filtered to
`dependent_count > 0`) feeds tier 1 of `lifecycle.pick_next_bead`, and
`prompt.is_triaged_bug()` (a defensive substring check for `TRIAGE_MARKER` on a
`bug`-typed bead's description) makes `format_bead_as_goal` prepend
`_TRIAGE_VERIFY_PREAMBLE`. No source or bead is mutated by this feature — it is
pure prompt text plus a read-only selection query.

```mermaid
sequenceDiagram
    participant A1 as Working agent (bead N)
    participant Bd as bd CLI (bd create)
    participant Judges as LLM judges
    participant Pick as lifecycle.pick_next_bead
    participant NBB as beads.next_blocking_bug
    participant Fmt as prompt.format_bead_as_goal
    participant A2 as Verifying agent (future iteration)

    Note over A1: prompt ends with _BUG_DISCOVERY_PROTOCOL
    A1->>A1: discovers unrelated bug
    alt NON-BLOCKING
        A1->>Bd: bd create --type=bug --priority=2
        A1->>A1: continue original bead, then summarize
    else BLOCKING
        A1->>Bd: bd create --type=bug --priority=1<br/>--blocks=<bead N> (desc has TRIAGE_MARKER)
        A1->>A1: fix inline as scope expansion, finish bead N
    end
    A1->>Judges: present work (NEVER self-close)
    Judges->>Judges: close bead N
    Note over Pick,NBB: a later /bead-chain iteration
    Pick->>NBB: tier 1: any ready bug w/ dependent_count > 0?
    NBB-->>Pick: the triaged blocking bug
    Pick->>Fmt: format_bead_as_goal(bug)
    Fmt->>Fmt: is_triaged_bug(bug) == True
    Fmt-->>A2: _TRIAGE_VERIFY_PREAMBLE + body + protocol
    A2->>A2: verify/upgrade the inline fix, add tests
    A2->>Judges: present; judges close
```

## Key Data Shapes

This feature consumes/produces ordinary `bd` bug records — there is no bespoke
DTO. A **non-blocking** bug, as the protocol tells the agent to file it:

```json
{
  "id": "bead_chain-ab1",
  "issue_type": "bug",
  "priority": 2,
  "title": "<short title>",
  "description": "<what you saw, repro steps, suspected cause>",
  "status": "open",
  "dependent_count": 0,
  "dependencies": []
}
```

A **blocking** bug carries the triage marker in `description` and a `blocks`
edge back at the bead whose work it interrupted — that edge is what gives it
`dependent_count > 0` so tier-1 routing can escalate it:

```json
{
  "id": "bead_chain-ab2",
  "issue_type": "bug",
  "priority": 1,
  "title": "<short title>",
  "description": "[bead-chain:triaged] <what you saw, what you fixed inline, why it blocked>",
  "status": "open",
  "dependent_count": 1,
  "dependencies": [
    { "type": "blocks", "depends_on_id": "bead_chain-mol-bps.8" }
  ]
}
```

The only fields the *code* reads are `issue_type`, `description` (for
`is_triaged_bug`), and `dependent_count` (for `next_blocking_bug`). The output
of `format_bead_as_goal` is a single `str` — the protocol/preamble are plain
text spliced into it, not a structured object.

## API Surface

> [!NOTE]
> bead-chain is a terminal Code Puppy plugin with **no HTTP endpoints**. This
> feature's "surface" is in-process Python plus an instruction string the agent
> executes as a `bd` shell call, not a route — so the `-> Endpoint doc` column
> is N/A by design (see the Endpoints note in the
> [FlowDoc Manifest](../_Manifest.md)).

| Method | Path | Purpose | -> Endpoint doc |
|--------|------|---------|-----------------|
| `call` | `prompt.format_bead_as_goal(bead, *, recovery=False) -> str` | Append `_BUG_DISCOVERY_PROTOCOL` to every prompt; select `_TRIAGE_VERIFY_PREAMBLE` for triaged bugs | N/A — no HTTP surface |
| `call` | `prompt.is_triaged_bug(bead) -> bool` | Detect the `TRIAGE_MARKER` on a `bug`-typed bead to drive triage-verification | N/A — no HTTP surface |
| `call` | `beads.next_blocking_bug() -> dict \| None` | Tier-1 selection: top ready bug with `dependent_count > 0` | N/A — no HTTP surface |
| `shell` | `bd create --type=bug --title=... --description=... --priority=2` | Agent files a NON-BLOCKING discovered bug | N/A — `bd` subprocess |
| `shell` | `bd create --type=bug --title=... --description='[bead-chain:triaged] ...' --blocks=<id> --priority=1` | Agent files a BLOCKING discovered bug (then fixes inline) | N/A — `bd` subprocess |

## Implementation Map

| Responsibility | File path | Symbol |
|----------------|-----------|--------|
| The always-appended protocol text (file / fix-inline / don't-self-close rubric) | `prompt.py` | `_BUG_DISCOVERY_PROTOCOL` |
| Stable description sentinel marking a triaged blocking bug | `prompt.py` | `TRIAGE_MARKER` |
| Triage-verification preamble shown to the later verifying agent | `prompt.py` | `_TRIAGE_VERIFY_PREAMBLE` |
| Detect a triaged bug (`issue_type == 'bug'` + marker substring) | `prompt.py` | `is_triaged_bug` |
| Append protocol + select preamble (recovery > triage > none) | `prompt.py` | `format_bead_as_goal` |
| Which issue types count as "bug" for tier-1 escalation | `beads.py` | `BLOCKING_BUG_TYPES` |
| Tier-1 query: top ready bug with `dependent_count > 0` | `beads.py` | `next_blocking_bug` |
| Tier-1 wiring in the selection waterfall | `lifecycle.py` | `pick_next_bead` |
| Caller — first bead of the chain (prompt built here) | `register_callbacks.py:280` | `handle_bead_chain_command` |
| Caller — every later bead hand-off (prompt built here) | `lifecycle.py:718` | `activate_next_bead` |

## Configuration

| Key | Default | Effect |
|-----|---------|--------|
| `_BUG_DISCOVERY_PROTOCOL` | constant text (`prompt.py`) | Appended verbatim to the bottom of **every** goal prompt, regardless of preamble |
| `TRIAGE_MARKER` | `"[bead-chain:triaged]"` | Description sentinel that flips a claimed `bug` onto the triage-verification preamble; kept wire-stable so older filed bugs still resolve |
| `_TRIAGE_VERIFY_PREAMBLE` | constant text (`prompt.py`) | Prepended when a claimed bead is a triaged bug and `recovery=False` |
| `BLOCKING_BUG_TYPES` | `("bug",)` | Issue types eligible for tier-1 blocking-bug escalation; tuple so adding e.g. `"regression"` is a one-line edit |
| protocol non-blocking priority | `--priority=2` (baked into the rubric text) | NON-BLOCKING bugs are filed at P2 and left for natural queue order |
| protocol blocking priority | `--priority=1` + `--blocks=<id>` (baked into the rubric text) | BLOCKING bugs are filed at P1 with a `blocks` edge so they gain `dependent_count > 0` and jump the queue |

## Edge Cases

> [!WARNING]
> **The protocol is on EVERY prompt — including recovery and triage.** A
> recovering or triage-verifying agent still gets `_BUG_DISCOVERY_PROTOCOL`
> appended, because a bug can surface on any iteration. The preamble and the
> protocol are independent: preamble at the top, protocol at the bottom.

> [!WARNING]
> **`is_triaged_bug` fires only for `issue_type == 'bug'`.** A `task`/`docs`
> bead that merely *mentions* `[bead-chain:triaged]` in its description (e.g.
> this very doc) is **not** flipped into verification mode — the marker is
> meaningful only on bug beads filed via the protocol.

> [!WARNING]
> **Marker match is an un-anchored substring.** `TRIAGE_MARKER in description`
> deliberately doesn't require start-of-string, so a user may prepend their own
> formatting (a triage timestamp, a `[P1]` tag) without breaking detection.

> [!WARNING]
> **Recovery beats triage.** A bug that is *both* stranded `in_progress` *and*
> carries the marker gets the recovery preamble only — "assess current state"
> subsumes "verify a prior fix" (see the ordering in `format_bead_as_goal`).

> [!WARNING]
> **A blocking bug must carry `--blocks` to escalate.** Tier-1
> `next_blocking_bug` requires `dependent_count > 0`; a P1 bug filed *without* a
> `blocks` edge has no dependents and is treated as ordinary work, picked up by
> the global ready tier instead of jumping the queue.

> [!CAUTION]
> **Agents must never self-close.** The protocol explicitly forbids closing any
> bead — the LLM judges are the only legitimate closer. The triaged bug stays
> open *on purpose* so it can be claimed and verified in a later iteration;
> that's not a leak, it's the design.

## Error Scenarios

| Trigger | Behavior | User sees |
|---------|----------|-----------|
| Agent files a NON-BLOCKING bug, keeps working | Bug sits at P2 in the backlog; no escalation (no dependents) | New `bug` bead in `bd list`; original bead finishes normally |
| Agent files a BLOCKING bug with `--blocks` + marker, fixes inline | `next_blocking_bug` later returns it (`dependent_count > 0`); tier-1 escalation | `bead-chain: blocking bug detected -> prioritising <id>` |
| Triaged bug later claimed, `issue_type == 'bug'`, marker present, not recovering | `format_bead_as_goal` prepends `_TRIAGE_VERIFY_PREAMBLE` | A `TRIAGE VERIFICATION` prompt |
| Triaged bug claimed but `issue_type != 'bug'` (or marker absent) | `is_triaged_bug` returns `False`; ordinary prompt | No triage preamble |
| Triaged bug also stranded `in_progress` | Recovery preamble wins via ordering | Recovery prompt, not triage |
| `bead` is non-dict / missing `issue_type`/`description` | `is_triaged_bug` returns `False` (defensive, no raise) | Ordinary prompt; chain never stalls |
| Blocked candidate leaks into tier 1 (bd version drift) | `_reject_if_blocked` refuses to drive it; waterfall falls through | `bead-chain: blocking bug candidate <id> has open blocker(s)` |

## Testing

The protocol is exercised as part of `format_bead_as_goal`'s output: since
`_BUG_DISCOVERY_PROTOCOL` is appended on every call, the prompt-shape suites
(`tests/test_prompt_acceptance_criteria.py`,
`tests/test_prompt_memory_digest.py`,
`tests/test_prompt_lint_warnings.py`,
`tests/test_prompt_related_context.py`) all build full prompts and would catch
its accidental removal.

The tier-1 routing half has dedicated coverage:

- `tests/test_pick_respects_blocks.py` —
  `test_blocked_blocking_bug_is_skipped_falls_through` pins that a blocking-bug
  candidate flows through `pick_next_bead` tier 1 (and is refused only when
  itself blocked).
- `tests/test_wisp_exclusion.py` — asserts `next_blocking_bug()` actually
  queries `bd` with the container `--exclude-type` filter applied.

`is_triaged_bug` and preamble selection are pure functions: build a dict with
`issue_type="bug"` and a `[bead-chain:triaged]` description and call
`prompt.is_triaged_bug(bead)` / `prompt.format_bead_as_goal(bead)` in a REPL to
eyeball the triage preamble (and confirm a non-`bug` type does *not* flip).
Run the whole suite with `pytest -q` (245 tests).

## Related

- [BlockingBugPriority](BlockingBugPriority.md) — the *consumer* half: how the
  tier-1 waterfall escalates the blocking bug this protocol tells the agent to
  file (P1 + `--blocks`).
- [GoalPromptEnrichment](GoalPromptEnrichment.md) — the umbrella feature whose
  `format_bead_as_goal` appends this protocol and selects the preamble.
- [GoalPromptConstruction](../Flows/GoalPromptConstruction.md) — the flow that
  narrates, step by step, where the protocol and triage preamble are spliced in.
- [StrandedBeadRecovery](../Flows/StrandedBeadRecovery.md) — the recovery path
  whose preamble *wins* over the triage preamble when a bug is also stranded.
- [QueueDriverNotGoalEngine](../Concepts/QueueDriverNotGoalEngine.md) — the SRP
  boundary behind "file, don't close": bead-chain instructs, the judges close.
- [BdSubprocessTransport](../Concepts/BdSubprocessTransport.md) — the transport
  behind the agent's `bd create` filing and the `next_blocking_bug` query.
- [Features Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
