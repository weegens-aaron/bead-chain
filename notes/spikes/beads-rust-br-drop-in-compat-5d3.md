# Spike: is `beads_rust` (`br`) a drop-in replacement for `bd`?

- **Bead:** `bead_chain-5d3` (spike, P2)
- **Question:** Can a bead-chain user set `BEADS_BIN=br`
  ([beads_rust](https://github.com/Dicklesworthstone/beads_rust)) instead of
  `bd` (Go beads CLI) and have the chain work?
- **Method:** Audited the real `bd` command surface from bead-chain's source
  (every `_run_bd(...)` call site), then installed `br` and ran each exact
  invocation against a scratch workspace.
- **`br` version tested:** `br 0.2.15` (darwin_arm64, official install.sh).
- **Verdict: NOT a drop-in. INCOMPATIBLE as-is.** The chain stops cleanly at
  the *first* bead-selection read and can never pick a single bead. Supporting
  `br` is possible but requires a backend-adapter layer (est. below), not a
  flag flip.

---

## TL;DR

`br` is a faithful clone of "classic beads" for the **mutation + introspection**
paths (`update --claim`, `update --status=open`, `close --reason`, `show --json`,
`lint`, `epic close-eligible`) — those are byte-for-byte compatible with what
bead-chain expects. But the **queue/read** paths bead-chain leans on hardest
are broken by three independent issues, any one of which is chain-fatal:

1. `--exclude-type` flag does not exist on `br ready` / `br list` (exit 2).
2. `br list --json` returns an **object** `{issues:[...],total,...}`, not the
   top-level **array** bead-chain's `_parse_json_list` requires.
3. `br list --parent=<id>` does not exist (only `br ready --parent` does).

Plus two soft (non-fatal) feature losses: `br` has no `memories` subcommand and
no `gate` subcommand.

Failure mode is **graceful, not a crash**: `pick_next_bead` → `_unblocked_strands`
→ `list_recoverable_strands` → `bd list --status=… --exclude-type=… --json`
errors (exit 2) → `BeadsError` → caught in `activate_next_bead` →
`state.stop()` with `"bead-chain stopping — bd ready failed: …unexpected
argument '--exclude-type'"`. The chain dies on its first move, every run.

---

## Actual `bd` surface bead-chain depends on

> NB: the bead description listed an *aspirational* surface (`bd search`,
> `bd dep tree`, `bd dep cycles`, `bd blocked`, `update --append-notes/
> --description/--design/--notes`). Grepping every `_run_bd(...)` call site
> shows the **real** surface is narrower — bead-chain never calls those. The
> matrix below covers what the code actually invokes.

| # | bead-chain call (exact) | call site |
|---|---|---|
| 1 | `ready --exclude-type=… --json` | `beads_reads.next_ready` |
| 2 | `ready --parent=<id> --exclude-type=… --json` | `beads_reads.next_ready_in_epic` |
| 3 | `ready --type=<bug> --exclude-type=… --json` | `beads_reads.next_blocking_bug` |
| 4 | `list --status=<a,b> --exclude-type=… --json` | `beads_reads._list_by_status` (→ `list_in_progress`, `list_recoverable_strands`) |
| 5 | `list --parent=<id> --json` | `beads_reads.has_open_children` |
| 6 | `list --type=epic --status=in_progress --json` | `beads_writes.has_epic_in_progress` |
| 7 | `show <id> --json` | `beads_reads.show` |
| 8 | `memories --json` | `beads_reads.memories` |
| 9 | `update <id> --claim` | `beads_writes.claim` |
| 10 | `update <id> --status=open` | `beads_writes.revert_to_open` |
| 11 | `close <id> [--reason <txt>]` | `beads_writes.close` |
| 12 | `epic close-eligible [--dry-run] --json` | `beads_writes._preview_close_eligible` / `_bulk_close_eligible` |
| 13 | `gate check --json` | `beads_writes.check_gates` |
| 14 | `lint <id> --status all --json` | `beads_writes.lint_warnings` |

---

## Compatibility matrix (verified against `br 0.2.15`)

| # | Command | `br` result | Status |
|---|---|---|---|
| 1 | `ready --exclude-type=… --json` | `error: unexpected argument '--exclude-type'` (exit 2) | **BREAK** |
| 2 | `ready --parent --exclude-type … --json` | `--parent` OK, `--exclude-type` rejected -> exit 2 | **BREAK** (via exclude-type) |
| 3 | `ready --type=bug --exclude-type … --json` | `--type` OK, `--exclude-type` rejected -> exit 2 | **BREAK** (via exclude-type) |
| 4 | `list --status=a,b --exclude-type … --json` | `--exclude-type` rejected exit 2; also `list --json` is an **object** | **BREAK x2** |
| 5 | `list --parent=<id> --json` | `error: unexpected argument '--parent'` (exit 2) | **BREAK** |
| 6 | `list --type=epic --status=in_progress --json` | flags OK but returns `{"issues":[],"total":…}` (object) | **BREAK** (shape) |
| 7 | `show <id> --json` | array `[{…}]`; has `id,title,status,priority,issue_type,assignee,created_at,updated_at,dependencies[]` | OK |
| 8 | `memories --json` | `error: unrecognized subcommand 'memories'` (exit 2) | soft-fail (feature loss) |
| 9 | `update <id> --claim` | `open -> in_progress`, sets assignee | OK |
| 10 | `update <id> --status=open` | `in_progress -> open` | OK |
| 11 | `close <id> --reason "…"` | `Closed …` | OK |
| 12 | `epic close-eligible [--dry-run] --json` | dry-run -> `[]`; live -> `{"closed":[],"count":0}` (matches bd 1.0.4!) | OK |
| 13 | `gate check --json` | `error: unrecognized subcommand 'gate'` (exit 2) | soft-fail (feature loss) |
| 14 | `lint <id> --status all --json` | `{"total":1,"issues":1,"results":[{"id","title","type","missing":[…],"warnings"}]}` — identical to bd | OK |

### JSON schema notes
- **Issue fields:** `id`, `title`, `status`, `priority`, `issue_type`,
  `assignee`, `labels`, `created_at`, `updated_at` all present and named
  identically. `issue_type` (not `type`) matches bead-chain's
  `is_excluded_type`. [OK]
- **`priority` is an integer** (`1`), not `"P1"`. bead-chain only renders it
  (`prompt.py:702` -> `f"- Priority: P{priority}"` -> "P1"); no parsing/compare,
  so cosmetically fine. [OK]
- **`show` dependency edges:** `dependencies: [{id,title,status,priority,
  dependency_type}]` — `dependency_type` + `status` + `id` are exactly what
  `open_blocker_ids` reads. [OK] (work-time blocker gate would work.)
- **`ready --json` is an array** [OK] (compatible with `_parse_json_list`); but
  **`list --json` is an object** [BREAK]. The asymmetry is the trap.
- **Status values:** `open` / `in_progress` / `closed` etc. match. [OK]

---

## Breaking differences → exact code that must change

| Gap | Symptom | bead-chain locations needing change |
|---|---|---|
| **A. No `--exclude-type`** | exit 2 on every queue read | `beads._exclude_type_arg` + all callers: `next_ready`, `next_ready_in_epic`, `next_blocking_bug`, `_list_by_status` (`beads_reads.py`). Would have to drop the flag and rely solely on the existing client-side `is_excluded_type` re-filter (which already exists as defence-in-depth!). |
| **B. `list --json` object shape** | `_parse_json_list` raises `non-list payload: dict`; `has_epic_in_progress` silently returns `False` forever | `beads._parse_json_list` (`beads.py`) must unwrap `{"issues":[…]}`; `has_epic_in_progress` (`beads_writes.py`). |
| **C. No `list --parent`** | exit 2 in `has_open_children` (soft-fails to `False` today → molecule fan-out gate treated as satisfied = wrong) | `has_open_children` (`beads_reads.py`) — re-scope via `br ready --parent` is insufficient (ready hides closed/in_progress children). Needs `list --json` + client-side `parent` filter. |
| **D. No `memories`** | `memories()` raises; `prompt.py` soft-fails to `{}` | None required — already soft-fails (`prompt.py:124`). Feature degraded: goal prompt loses the memory digest. `bd remember` (used by working agents per AGENTS.md) also absent → no way to *write* memories. |
| **E. No `gate`** | `check_gates()` raises; caller soft-fails | None required — `probe_resolved_gates` soft-fails (`lifecycle.py`). Feature degraded: gate-pending targets never get re-opened mid-session. |

### Bonus finding — close-guard is blind to `br`
`close_guard._BD_INVOCATION = r"(?:\S*/)?bd"` matches a binary basename of
exactly `bd`. If a user ran `BEADS_BIN=br`, an agent shelling out `br close
<id>` (or `br update <id> --status=closed`) mid-run would **bypass the LLM-judge
close-guard undetected**. Officially supporting `br` *requires* widening that
regex (and `_BD_UPDATE_STATUS_CLOSED_RE`) to also match `br`. This is a safety
gap, not just a feature gap.

---

## Storage / sync model

| Aspect | `bd` (Go) | `br` (Rust) |
|---|---|---|
| Dir | `.beads/` (`.beads/dolt/`) | `.beads/` (`beads.db` + `issues.jsonl`) |
| Backend | **Dolt** (or SQLite) | **SQLite + JSONL** (no Dolt) |
| Cross-machine sync | `bd dolt push/pull` over `refs/dolt/data` | `br sync --flush-only/--import-only/--merge` + you commit `.beads/` JSONL via git |
| Daemon / hooks | yes / auto | none / manual |

The **plugin code never calls Dolt** (`bd dolt` appears only in `AGENTS.md`
session-close + ADR-0001, which are *operator workflow*, not `_run_bd`). So the
backend swap doesn't break the plugin directly — BUT the project's documented
durability workflow (`AGENTS.md` "Dolt Sync Step", `notes/decisions/0001-…`)
is Dolt-specific and would have to be rewritten to `br sync --flush-only` +
`git add .beads/` for a `br`-based project. The `.beads/` parent dir is shared,
so the two backends can't co-habit a repo.

---

## Assessment: divergent fork, compatible subset

`br` is a deliberate **freeze of "classic beads"** (SQLite+JSONL), explicitly
diverging from where Steve Yegge is taking `bd` (Dolt/GasTown). It is **not** a
superset and not a strict subset — it's a *parallel* CLI that overlaps `bd` on
the mutation/show/lint/epic verbs but has its own query-flag vocabulary and JSON
envelope. For bead-chain specifically it's a **compatible subset on writes,
incompatible on reads.**

## Recommendation: **needs an adapter** (do not advertise as drop-in)

Today, `BEADS_BIN=br` is silently broken — the chain stops on its first read
with a confusing `--exclude-type` error. Three options:

1. **Do nothing / document as unsupported (recommended near-term).** Add a line
   to `Configuration.md`/FAQ: "`BEADS_BIN` must point to a `bd`-compatible
   (Go beads) binary; `br`/beads_rust is *not* supported — its `list --json`
   envelope and missing `--exclude-type` break the queue reads." Cheapest, honest.

2. **Build a backend-adapter shim (if `br` support is actually wanted).**
   Introduce a thin compatibility layer in `beads.py` keyed off a detected
   backend flavour, that:
   - drops `--exclude-type` and leans on the existing client-side
     `is_excluded_type` re-filter (already present!);
   - unwraps `{"issues":[…]}` in `_parse_json_list`;
   - reimplements `has_open_children` via `list --json` + client-side parent
     filter;
   - widens `close_guard` regex to also catch `br`;
   - accepts `br`'s integer priority and array-shaped `show`.
   `memories`/`gate` already soft-fail, so those degrade gracefully.
   **Estimate: ~1–1.5 days.** Roughly: 0.5d adapter + flavour detection in
   `beads.py`/`beads_reads.py`/`beads_writes.py`; 0.25d `close_guard` +
   `has_open_children` rework; 0.5d tests (parametrise the existing
   `_run_bd`-stub suite over both envelope shapes) + docs. Risk: ongoing — `br`
   is a one-author no-external-contributions project pinned to "classic", so
   future drift is the maintainer's call, not ours.

3. **Reject `br` loudly at startup (middle ground).** In `_validate_beads_bin`,
   run `<bin> --version` / probe `list --json` shape and raise a clear
   `BeadsError` ("beads_rust/br detected; unsupported, use Go beads `bd`") so
   the failure is legible instead of a cryptic mid-chain `--exclude-type` error.
   **Estimate: ~1–2 hrs.** Good cheap UX win even if we never do option 2.

**Suggested path:** ship option 1 + option 3 now (honest docs + legible early
failure); only invest in option 2 (the adapter) if real user demand appears.
