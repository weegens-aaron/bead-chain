# ExecutionHints

## What Is It

A thin adapter that lets a bead **author** shape the single `/goal` pass
bead-chain runs for that bead, by reading a small, *unenforced* `execution_*`
vocabulary out of the bead's free-form `metadata` JSON and mapping the
serial-compatible subset onto code-puppy's own runtime knobs (reasoning effort,
model select, agent select). `bd` itself does nothing special with these keys —
they are a shared contract between bead authors and orchestrators, and
bead-chain is one such orchestrator that *opts in* to the three keys that have a
sensible one-worker meaning.

## Why This Approach

Coverage-audit gap **FB-8** (`bead_chain-9n3`, swarms#2) found that `bd` carries
five canonical execution keys in each bead's `metadata` —
`execution_parallel_group`, `execution_agent_type`, `execution_model`,
`execution_effort`, `execution_mode` (settable via
`bd update --set-metadata k=v`) — but bead-chain historically read **none** of
them. An author therefore had no lever to influence even the lone `/goal` pass
the chain runs per bead.

bead-chain is a **one-bead-at-a-time serial driver** (single-`in_progress`
invariant — see [Queue Driver, Not Goal Engine](QueueDriverNotGoalEngine.md)),
so only three of the five keys have a coherent single-worker meaning. The design
deliberately maps *only those three* and lets everything else fall through the
"unknown keys ignored" path rather than inventing fake semantics:

| `execution_*` key | Serial meaning? | bead-chain behavior |
|-------------------|-----------------|---------------------|
| `execution_effort` | yes — reasoning budget for one worker | mapped → `config.set_openai_reasoning_effort` |
| `execution_model` | yes — which model the one worker uses | mapped → `config.set_model_name` |
| `execution_agent_type` | yes — which agent persona drives | mapped → `config.set_default_agent` |
| `execution_parallel_group` | no — there is no parallelism | ignored (falls through) |
| `execution_mode` | no — run mode is always `goal` | ignored (falls through) |

The whole thing is built as a **pure core + soft-fail shell** so one
fat-fingered hint can never strand the chain, and it does **no auto-restore**
(YAGNI): a hint persists exactly like a user typing `/model` or `/agent`
mid-session, and a bead with no hints leaves the prior selection untouched.

## How It Works

Two functions, split for testability:

1. **`extract_execution_hints(metadata)`** — the *pure* dict→dict core. It
   coerces `metadata` to a dict (accepting both a parsed object and a
   stringified `"{}"`, collapsing absent/`None`/garbage to `{}`), then keeps
   only keys present in `_RECOGNIZED_HINTS`, stringifies+strips each value, and
   drops empty/whitespace-only values (a blank `execution_model=` means "no
   preference", not "the empty model").
2. **`apply_execution_hints(bead)`** — the *impure* orchestrator. It resolves
   the bead's `metadata` (using the cached dict's `metadata` if present, else
   re-fetching via `beads.show` — because `bd ready --json` omits `metadata`
   while `bd show <id> --json` carries it), extracts the hints, and calls each
   recognized setter. It **soft-fails per hint**: an invalid value is logged via
   `emit_warning` and skipped; other valid hints in the same bead still apply.
   It returns a list of `"label → value"` strings for the caller to log.

```mermaid
flowchart TD
    Start([activate_next_bead /<br/>handle_bead_chain_command<br/>after claim, before /goal arm]) --> Apply[apply_execution_hints bead]
    Apply --> IsDict{bead is a dict?}
    IsDict -->|no| Empty[return []]
    IsDict -->|yes| Resolve[_resolve_metadata<br/>cached metadata? else beads.show id]
    Resolve --> Extract[extract_execution_hints<br/>pure filter]
    Extract --> Coerce[_coerce_metadata<br/>dict / JSON-string / garbage to dict]
    Coerce --> Keep{recognized, non-empty<br/>execution_* keys?}
    Keep -->|none| Empty
    Keep -->|some| Loop[for each hint:<br/>resolve setter via getattr config]
    Loop --> Callable{setter callable<br/>on this build?}
    Callable -->|no| Skip[skip silently<br/>version drift]
    Callable -->|yes| Try[setter value]
    Try -->|raises| Warn[emit_warning,<br/>skip this hint]
    Try -->|ok| Add[append 'label -> value']
    Add --> More{more hints?}
    Skip --> More
    Warn --> More
    More -->|yes| Loop
    More -->|no| Return[return applied list]
    Return --> Log[caller emits<br/>' execution hints: ...']
    Log --> Goal([format_bead_as_goal -><br/>wiggum /goal])
```

### Concrete example

An author files a bead and pins its execution shape:

```bash
bd update bead_chain-abc \
  --set-metadata execution_effort=high \
  --set-metadata execution_model=gpt-5 \
  --set-metadata execution_parallel_group=alpha
```

`bd show bead_chain-abc --json` then carries (trimmed):

```json
{
  "id": "bead_chain-abc",
  "title": "Tricky refactor",
  "status": "in_progress",
  "metadata": {
    "execution_effort": "high",
    "execution_model": "gpt-5",
    "execution_parallel_group": "alpha"
  }
}
```

When the chain activates this bead, `apply_execution_hints(bead)`:

- runs `extract_execution_hints` → `{"execution_effort": "high", "execution_model": "gpt-5"}`
  (`execution_parallel_group` is dropped — not recognized);
- calls `config.set_openai_reasoning_effort("high")` and
  `config.set_model_name("gpt-5")`;
- returns `["reasoning effort → high", "model → gpt-5"]`, which the caller logs
  as ` execution hints: reasoning effort → high; model → gpt-5`.

The `/goal` pass for this bead then runs at high reasoning effort on `gpt-5`.
If the author had instead written `execution_effort=ludicrous` (an invalid
budget), `set_openai_reasoning_effort` would raise, the warning
`bead-chain: ignoring execution_effort='ludicrous' — couldn't set reasoning effort: ...`
is emitted, and the chain proceeds with `model → gpt-5` still applied.

### Implementation references

| Responsibility | File:Symbol |
|----------------|-------------|
| Recognized key → (setter name, label) table | `execution_hints.py:_RECOGNIZED_HINTS` |
| Metadata coercion (dict / JSON-string / garbage → dict) | `execution_hints.py:_coerce_metadata` |
| Pure recognized-hint filter | `execution_hints.py:extract_execution_hints` |
| Metadata resolution (cached vs `bd show` re-fetch) | `execution_hints.py:_resolve_metadata` |
| Impure soft-fail orchestrator | `execution_hints.py:apply_execution_hints` |
| Re-fetch transport | `beads.py:show` (via `execution_hints.py` import) |
| Per-hint failure log | `code_puppy.messaging.emit_warning` (imported in `execution_hints.py`) |
| Apply site — first bead on engage | `register_callbacks.py:handle_bead_chain_command` (line ~276) |
| Apply site — every subsequent bead | `lifecycle.py:activate_next_bead` (line ~714) |

## Where Used

- [BeadChaining](../Features/BeadChaining.md) — the core feature whose per-bead
  `/goal` pass these hints shape, applied right after claim and before the goal
  prompt is built.
- [BeadClaimAndBlockerRecheck](../Flows/BeadClaimAndBlockerRecheck.md) — the
  flow (`lifecycle.activate_next_bead`) that calls `apply_execution_hints`
  immediately after claiming each subsequent bead.
- [GoalPromptConstruction](../Flows/GoalPromptConstruction.md) — hints are
  applied in the same step, just before `format_bead_as_goal` arms wiggum's
  `/goal` loop.
- [BdSubprocessTransport](BdSubprocessTransport.md) — `_resolve_metadata`
  re-fetches missing `metadata` via `beads.show`, riding the same subprocess
  transport.
- [QueueDriverNotGoalEngine](QueueDriverNotGoalEngine.md) — the serial,
  single-`in_progress` invariant is exactly why `execution_parallel_group` and
  `execution_mode` are deliberately ignored.

## Conventions

> [!IMPORTANT]
> - **Adding a recognized key is a one-line edit.** Extend
>   `_RECOGNIZED_HINTS` with `"<key>": ("<config_setter_name>", "<label>")` —
>   only do this for keys with a coherent *single-worker* meaning, mirroring how
>   `EXCLUDED_TYPES` / `RECOVERABLE_STATUSES` are extended. DRY.
> - **Store setters by name, resolve at apply time.** Setters are looked up via
>   `getattr(config, name)` at apply time, never bound at import — so tests can
>   monkeypatch `code_puppy.config` cleanly and a setter that vanishes under
>   code-puppy version drift degrades to a silent no-op instead of an import
>   error that breaks the whole plugin.
> - **Keep the core pure.** `extract_execution_hints` and `_coerce_metadata`
>   must stay side-effect-free dict→dict functions; all I/O and config mutation
>   lives in `apply_execution_hints`.
> - **Soft-fail per hint, always.** A bad value is logged and skipped; one
>   fat-fingered hint must never raise or strand the chain.

## Anti-Patterns

> [!CAUTION]
> - **Don't act on `execution_parallel_group` or `execution_mode`.** bead-chain
>   is serial (single `in_progress`) and always runs `mode="goal"`; honoring
>   parallel grouping or alternate run modes would violate the queue-driver
>   contract.
> - **Don't snapshot/restore config around each bead.** There is intentionally
>   no auto-restore — a hint persists like a user-typed `/model` or `/agent`.
>   Re-introducing per-bead isolation here is a separate, larger feature, not a
>   quiet addition.
> - **Don't assume `bd ready --json` carries `metadata`.** It doesn't on this
>   build; rely on `_resolve_metadata` to re-fetch via `beads.show` rather than
>   reading a `metadata` key that may be absent.
> - **Don't bind config setters at import time.** That re-breaks both the test
>   monkeypatch story and version-drift resilience.
> - **Don't raise on a bad hint value.** Treat invalid values as "ignore and
>   warn", never as a fatal error.

## Related

- [BeadChaining](../Features/BeadChaining.md)
- [BeadClaimAndBlockerRecheck](../Flows/BeadClaimAndBlockerRecheck.md)
- [GoalPromptConstruction](../Flows/GoalPromptConstruction.md)
- [BdSubprocessTransport](BdSubprocessTransport.md)
- [QueueDriverNotGoalEngine](QueueDriverNotGoalEngine.md)
- [ChainStateSingleton](ChainStateSingleton.md)
- [GoalPromptEnrichment](../Features/GoalPromptEnrichment.md) — sibling per-bead
  enrichment applied around the same point, just before the prompt is built.
- [ChainIterationLoop](../Flows/ChainIterationLoop.md) — the loop applies these
  `execution_*` hints to each bead before arming wiggum.
- [Concepts Index](index.md)
- [Architecture](../Architecture.md)
- [FlowDoc Manifest](../_Manifest.md)
