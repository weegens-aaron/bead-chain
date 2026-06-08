# Data Layer (Dolt) — Coverage Findings

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Capability area  | `data-layer`                                                          |
| Field-guide ref  | `field-guide-08-data-layer.html` (chapter 8)                          |
| Bead-chain owner | `bead_chain-p6o`                                                      |
| Primary modules  | `beads.py` (`_run_bd`, `close`/`claim`/`revert_to_open`), `lifecycle.py` (`activate_next_bead`, `rollup_completed_epics`), `register_callbacks.py` (`_on_interactive_turn_end`/`_on_interactive_turn_cancel`) |
| Status           | `done`                                                                |

---

## 1. AVAILABLE — what the field guide documents

Chapter 8 is the **data layer**: where a bead actually lives, and how bead state
travels between machines. Source: `field-guide-08-data-layer.html` (chapter 8),
restated verbatim in this repo's own architecture note (`AGENTS.md:5-14`) and the
canonical [SYNC_CONCEPTS.md] anti-pattern guide it links.

- **Storage engine — a local Dolt database.** Issues live in a local Dolt DB
  under `.beads/dolt/` (`AGENTS.md:6`, "Issues live in a local Dolt database").
  On this build the engine is **embedded / in-process** with data at
  `.beads/embeddeddolt/` (verified: `bd dolt status` → "Dolt engine: embedded
  (in-process, no server)"). Every `bd` mutation — claim, close, status change,
  epic rollup — writes here.
- **The wire protocol — `bd dolt push` / `bd dolt pull`.** Cross-machine sync
  uses a git-compatible Dolt protocol stored under **`refs/dolt/data`** on your
  git remote, *separate from* `refs/heads/*` where your code lives
  (`AGENTS.md:6-9`). A plain `git push` carries `refs/heads/*` only; it does
  **not** carry `refs/dolt/data`.
- **Remote management — `bd dolt remote add|list|remove`** (verified: `bd dolt
  remote` help). A Dolt remote must be configured before `bd dolt push` does
  anything; with none configured, `bd dolt push` prints the remote-URL help and
  no-ops.
- **`issues.jsonl` is a passive export, *not* the wire protocol** (`AGENTS.md:9`).
  Whether it is even written is gated by the `export.auto` config (verified:
  `bd config` → `export.auto = false` on this repo, and there is no
  `.beads/issues.jsonl` present at all).
- **Documented anti-patterns** (`AGENTS.md:12-14`, [SYNC_CONCEPTS.md]): don't
  treat the JSONL as the source of truth; don't `bd import` during normal
  operation; don't reach for third-party Dolt hosting before trying the default.

[SYNC_CONCEPTS.md]: https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md

## 2. LEVERAGED — what bead-chain actually uses

**bead-chain leverages the data layer transitively (it writes the local Dolt DB
on every transition) but consumes *none* of the sync surface — there is no
`bd dolt push`, `bd dolt pull`, `bd export`, or `bd import` anywhere in the
plugin.** This was verified exhaustively: a case-insensitive search for
`dolt|push|pull|jsonl|sync|import|export` across the six core modules
(`beads.py`, `lifecycle.py`, `register_callbacks.py`, `close_guard.py`,
`prompt.py`, `state.py`) returns **zero** sync-related call sites. The only
matches are unrelated: `close_guard.py:40` mentions a *git* "force_push_guard"
(it guards `git push --force`, not Dolt), and `beads.py:536` uses the English
word "pull" in an epic-filtering comment.

**Writes to the local Dolt DB — every `bd` op funnels through one subprocess
shim.** All bead state changes are `subprocess.run([bd, *args])` in
`_run_bd` (`beads.py:182`), which talks to the embedded Dolt DB:

| Operation         | Call site                              | bd command            |
| ----------------- | -------------------------------------- | --------------------- |
| Claim a bead      | `claim` (`beads.py:473`)               | `bd update --claim`   |
| Close a bead      | `close` (`beads.py:502`)               | `bd close [--reason]` |
| Revert to open    | `revert_to_open` (`beads.py:494`)      | `bd update --status=open` |
| Epic rollup       | `close_eligible_epics` (`beads.py:567`)| `bd epic close-eligible --json` |

So a single chain run can mutate the local Dolt DB dozens of times. None of those
mutations is ever pushed by bead-chain.

**Session end — what bead-chain does when the queue drains.** The end-of-session
path is `activate_next_bead` → the `bead is None` branch (`lifecycle.py:517-524`):

1. `rollup_completed_epics()` (`lifecycle.py:519` → `lifecycle.py:282`) — a
   *local* `bd epic close-eligible` cascade (another local-DB write).
2. `emit_success("bead-chain: no more ready beads…")` (`lifecycle.py:521`).
3. `state.stop()` (`lifecycle.py:524`).

There is **no `bd dolt push`, no `git push`, no `bd export`** in this path. The
chain simply stops with all its mutations sitting in the local DB. **bead-chain
delegates 100% of sync responsibility to the human / `/goal` session-close git
protocol** documented in `AGENTS.md` ("Session Completion", `AGENTS.md:72-95`).

**The Ctrl+C path is the same — sync-free by design.**
`_on_interactive_turn_cancel` (`register_callbacks.py:351`) calls `state.stop()`
and *intentionally leaves the in-flight bead `in_progress`* for the next run's
recovery tier (`register_callbacks.py:351-378`). No sync is attempted; recovery
is framed purely as a **local** startup concern (the docstring: "Recovery is a
startup-time concern, handled by `lifecycle.enforce_single_in_progress` /
`lifecycle.pick_next_bead` on the next run").

**The drive loop itself** (`_on_interactive_turn_end`,
`register_callbacks.py:289`) only ever calls `close_current_bead_success()` and
`activate_next_bead()` — neither touches the sync surface.

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line)                                                                                                                                                                                                                                                                                              | Severity | Recommended follow-up (one line)                                                                                                                |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | The delegation **target is incomplete**: the `AGENTS.md` "Session Completion" mandatory workflow (`AGENTS.md:79-86`) runs only `git pull --rebase` / `git push` / `git status` — and `git push` carries `refs/heads/*`, *not* `refs/dolt/data`. The embedded Dolt DB is even git-ignored (`.beads/.gitignore:3`, `embeddeddolt/`), so **no** bead-state mutation ever leaves the machine via the documented loop. | P1       | File a bead to add an explicit `bd dolt push` (gated on a configured remote) to the session-close protocol — and decide whether bead-chain should trigger it on drain or stay sync-agnostic. |
| 2   | bead-chain runs no `bd dolt push` at chain end (`lifecycle.py:517-524` = rollup + emit + stop). On a single persistent dev box this is harmless (local Dolt is authoritative), but on a fresh clone / CI / second machine / disposable agent env, **every** claim/close/revert from the run is stranded and invisible to other actors. | P1       | File a bead: opt-in `bd dolt push` on successful drain when `bd dolt remote list` is non-empty; soft-fail (warn, don't halt) if it errors — mirror the `rollup_completed_epics` soft-fail pattern. |
| 3   | Ctrl+C / cancel (`register_callbacks.py:351`) stops the chain leaving the bead `in_progress` with no sync. Recovery is documented as local-only, so a mid-chain interrupt on machine A is invisible to machine B even though the bead is "claimed."                                                            | P3       | File a bead to (at minimum) document that interrupted chains are local-only until a manual `bd dolt push`; optionally push on cancel.            |
| 4   | No reliance on `issues.jsonl` either way — bead-chain neither reads nor writes it (correct per ch08), but on this repo `export.auto = false` and no JSONL exists, so there is *also* no passive git-tracked snapshot of bead state as a fallback. The local Dolt DB is the only copy.                          | P3       | No code change — document that JSONL is not a sync fallback here; if a git-visible audit trail is wanted, enable `export.auto` deliberately (not as a sync mechanism). |
| 5   | bead-chain never runs `bd dolt pull` at startup, so a chain can begin against a stale local DB if another machine pushed newer state. Low impact today (no remote configured) but a correctness footgun once multi-machine sync is turned on.                                                                   | P4       | Future-proofing only: consider a `bd dolt pull` at `/bead-chain` startup once remotes are in use; document as out-of-scope for now.             |

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

- **Is this a bead-chain bug, or correct SRP?** Mostly the latter. bead-chain is
  a *queue driver*, not a sync engine, and the sibling explanation
  [QueueDriverNotGoalEngine](../../../__docs/Concepts/QueueDriverNotGoalEngine.md) makes "we don't own
  X" a deliberate stance. Owning sync policy (which remote? push every bead or
  once per drain? pull on start?) would arguably violate that boundary. The real
  finding is therefore a **seam**, not a code defect: *nobody* in the documented
  end-to-end loop (`AGENTS.md` session-close included) actually runs
  `bd dolt push`, so bead-state durability beyond the local machine falls through
  the crack between "bead-chain delegates it" and "the git protocol doesn't do
  it." That's why gaps #1 and #2 are P1 rather than a filed code bug — they need
  a human decision about *where* sync should live.
- **Why not P0.** The drain loop is correct on a single machine: the local Dolt
  DB persists, and interrupted/failed beads stay `in_progress` for the tier-0
  recovery path (`close_current_bead_success` docstring, `lifecycle.py:184`).
  There is no wrong-bead-closed or in-loop data corruption — the hazard is
  cross-machine durability, which only bites under multi-machine / ephemeral use.
  Hence P1 (silently-dropped capability with real consequence) over P0.
- **Grounding for "git push can't carry it."** Verified on this repo:
  `embeddeddolt/` is git-ignored (`git check-ignore` → `.beads/.gitignore:3`),
  `git for-each-ref refs/dolt` is **empty** (nothing has ever been dolt-pushed
  here), and `bd dolt remote` reports no configured remote (matches the project
  memory: "`bd dolt push` printed the remote-URL help, meaning no Dolt remote is
  configured"). So today the data is *local-only by construction*, not by
  accident.
- **Cross-section seam.** Status transitions (claim/close/revert) are chapter 3's
  turf (`bead_chain-npn`); this section counts only *where those transitions are
  persisted and whether they sync*, to avoid double-counting the lifecycle
  mechanics themselves.
- Gaps #1–#5 are recommendations for the synthesis bead (`bead_chain-hkb`); per
  the analysis framework this section files no beads itself.
