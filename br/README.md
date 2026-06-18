# bead-chain  (br / beads_rust variant)

> **This is the `br` variant** — adapted for the
> [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`) CLI
> instead of the Go `bd` CLI. It defaults to the `br` binary and accounts for
> `br`'s differences: no `--exclude-type` query flag (container types are
> filtered client-side), the `list --json` object envelope (`{"issues":[…]}`),
> no `list --parent` (`has_open_children` filters client-side), and a
> close-guard widened to catch `br close`/`br update --status=closed`. The
> `memories` and `gate` subcommands are absent in `br` and soft-fail. See the
> spike `bead_chain-5d3` for the full compatibility analysis. If you run the Go
> `bd` CLI, use the `bd/` variant instead.

**A beads-driven `/goal` variant that chains your `br ready` queue into wiggum's goal loop, one bead at a time.**

Claim → `/goal` → close → repeat — until the queue is empty or you hit Ctrl+C. No manual bead juggling, no lost context between tasks, no forgotten commits. Just steady progress.

---

## Install

Pick your platform — one line, copy, paste, run. Then **restart code_puppy** and the `/bead-chain` command is available.

### macOS / Linux (bash/zsh)

```bash
curl -fsSL https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-br.zip -o /tmp/bead-chain-br.zip && unzip -o /tmp/bead-chain-br.zip -d ~/.code_puppy/plugins/
```

Plugins live at `~/.code_puppy/plugins/`.

### Windows (PowerShell)

```powershell
Invoke-WebRequest -Uri https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-br.zip -OutFile $env:TEMP\bead-chain-br.zip; Expand-Archive -Force $env:TEMP\bead-chain-br.zip -DestinationPath ~\.code_puppy\plugins\
```

Plugins live at `~\.code_puppy\plugins\` (i.e. `%USERPROFILE%\.code_puppy\plugins\`).

### Manual download (any platform, no CLI)

Prefer the browser?

1. Go to the [**Releases** page](https://github.com/weegens-aaron/bead-chain/releases/latest).
2. Download **`bead-chain-br.zip`** from the latest release's assets.
3. Extract it so that the `bead_chain/` folder lands directly inside your plugins directory:
   - macOS / Linux: `~/.code_puppy/plugins/bead_chain/`
   - Windows: `~\.code_puppy\plugins\bead_chain\`
4. Restart code_puppy.

The zip contains a single top-level `bead_chain/` folder, so every path above results in `…/plugins/bead_chain/…` — extract, don't nest.

### Verify your download (optional but recommended)

Every release publishes a `bead-chain-br.zip.sha256` asset next to the zip. Verifying it confirms the download is the exact artifact the maintainer built — a quick guard against a corrupted or tampered file. **This is optional**: the install one-liners above work fine on their own. If you skip it, nothing breaks.

#### macOS / Linux (bash/zsh)

After running the install one-liner (which leaves the zip at `/tmp/bead-chain-br.zip`):

```bash
curl -fsSL https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-br.zip.sha256 -o /tmp/bead-chain-br.zip.sha256
( cd /tmp && shasum -a 256 -c bead-chain-br.zip.sha256 )   # prints "bead-chain-br.zip: OK"
```

(`sha256sum -c bead-chain-br.zip.sha256` works too on distros that ship `sha256sum` instead of `shasum`.)

#### Windows (PowerShell)

After running the install one-liner (which leaves the zip at `$env:TEMP\bead-chain-br.zip`):

```powershell
Invoke-WebRequest -Uri https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-br.zip.sha256 -OutFile $env:TEMP\bead-chain-br.zip.sha256
$expected = (Get-Content $env:TEMP\bead-chain-br.zip.sha256).Split(' ')[0]
$actual   = (Get-FileHash $env:TEMP\bead-chain-br.zip -Algorithm SHA256).Hash
if ($actual -eq $expected) { "OK: checksum matches" } else { Write-Error "CHECKSUM MISMATCH — do not install" }
```

(`-eq` is case-insensitive in PowerShell, so the uppercase `Get-FileHash` output matches the lowercase published hash.)

If verification fails, **don't install** — re-download or report it.

### Upgrade / Uninstall

| Action | macOS / Linux | Windows (PowerShell) |
|--------|---------------|----------------------|
| **Upgrade** | Re-run the install line — it always pulls the latest release. | Re-run the install line — it always pulls the latest release. |
| **Uninstall** | `rm -rf ~/.code_puppy/plugins/bead_chain` | `Remove-Item -Recurse -Force ~\.code_puppy\plugins\bead_chain` |

Every command uses the stable `/releases/latest/download/bead-chain-br.zip` URL — a fixed asset name on the latest release — so nothing ever needs version-editing for new releases.

### Prerequisites

- **code_puppy** (or wiggum) with `/goal` mode — bead-chain delegates LLM-judged completion to it.
- **`br` (beads_rust)** on your `PATH` — the issue tracker this variant drives. Override the binary with the `BEADS_BIN` env var if it lives elsewhere.

---

## Usage

```bash
/bead-chain           # Start chaining — runs until queue empty
/bead-chain --max=3   # Stop after completing 3 beads (safety cap)
```

**To stop:** Press `Ctrl+C`. The current bead stays `in_progress` — the next `/bead-chain` run will resume it with a recovery preamble.

---

## How It Works

```
┌────────────────────────────────────────────────────────────────┐
│  /bead-chain                                                   │
│       │                                                        │
│       ▼                                                        │
│  ┌─────────┐    ┌────────────┐    ┌─────────┐    ┌──────────┐ │
│  │bd ready │───▶│   claim    │───▶│  /goal  │───▶│ LLM pass │ │
│  └─────────┘    └────────────┘    └─────────┘    └──────────┘ │
│       ▲                                               │        │
│       │         ┌────────────┐    ┌─────────┐         │        │
│       └─────────│ next bead  │◀───│bd close │◀────────┘        │
│                 └────────────┘    └─────────┘                  │
│                       │                                        │
│                       ▼                                        │
│                 (queue empty? stop)                            │
└────────────────────────────────────────────────────────────────┘
```

1. **Probe** — Check `bd ready` for work (or recover a stranded bead)
2. **Claim** — `bd update <id> --claim` marks the bead in_progress  
3. **Drive** — Hand the bead to wiggum's `/goal` mode as a goal prompt
4. **Judge** — Wiggum's LLM judges evaluate completion each turn
5. **Close** — On pass, `bd close <id>` and grab the next bead
6. **Repeat** — Until queue empty, `--max` cap hit, or Ctrl+C

---

## Features

### Recovery Mode
If a previous run crashed or was cancelled mid-bead, `/bead-chain` detects the stranded `in_progress` bead at startup and resumes it with a recovery preamble:

> ⚠️ RECOVERY MODE: Assess current state before doing new work. Is the work effectively done? If yes, summarize what's in place. Otherwise, continue from where the previous run left off.

**Why:** Partial work stays paired with its bead — no orphaning, no duplicate effort.

### Work-Time Blocker Gate
bead-chain only works beads on the `bd ready` frontier — it respects `blocks` dependencies at **claim/start time**, not just at close time. A bead with an open `DEPENDS ON` (inbound `blocks`) edge is never claimed or driven.

This matters because two paths can otherwise surface a blocked bead:
- the **recovery tier** reads `bd list --status=in_progress`, which ignores the ready frontier — a bead claimed-while-ready and later re-blocked would be re-driven; and
- **bd version drift** could let `bd ready` leak a blocked bead.

At every claim site the chain rechecks blockers (via `bd show`); a blocked stranded bead is reverted to `open` (re-entering the queue behind its blockers) rather than re-run.

**Why:** Running blocked work to completion wastes cycles on stale inputs and only trips at `bd close` ("blocked by open issues") — far too late. The close-time guard is a safety net; this is the prevention (bdboard-oals).

### Epic Affinity
After closing a bead, bead-chain prefers the next ready sibling **under the same parent epic** before falling back to the global queue.

**Why:** Coherent commits and PRs beat queue-order optimality. Finish what you start.

### Blocking Bug Priority
A ready bug with `dependent_count > 0` jumps to the front of the queue (tier 1 in the waterfall). Fixing it unblocks downstream work.

**Why:** Blockers block. Clear them first.

### Close Guard
While bead-chain is active, agent attempts to run `bd close` or `bd update --status=closed` are **blocked** with a reminder:

> 🛑 bead-chain blocked `bd close`. The bead will be closed automatically once the LLM judges sign off — do NOT close it yourself.

**Why:** Only the LLM judges should close a bead. Agents doing their own closing short-circuits the quality gate.

### Epic Rollup
At session-end (when the queue is empty), bead-chain runs `bd epic close-eligible` to auto-close any epics whose children are now all complete.

**Implementation note (bead_chain-tfn):** Rollup runs **once per session** at the drain pass, not after every bead close. This prevents bd's server-side cascade from unexpectedly closing unrelated epics. Parent epics may close one session later, but this trade-off prioritizes data safety over single-pass cascading.

**Recurring-molecule protection (bead_chain-wot):** A poured `patrol` molecule is a *recurring* monitor — auto-closing its epic when its children finish would kill the recurrence. Since `bd epic close-eligible` has no exclude flag, rollup first **previews** the eligible set with `--dry-run` and skips any epic flagged by `is_recurring_epic` (a `patrol`/`recurring` label, or a `mol-type=patrol` field), closing only the safe ones. Ephemeral **wisps** never reach the queue at all — `bd ready` excludes them by default and bead-chain never passes `--include-ephemeral`.

**Why:** Epics shouldn't linger as zombies once their work is done.

---

## Bug Discovery Protocol

Every goal prompt includes a bug-discovery protocol. When an agent finds an unrelated bug mid-task:

| Scenario | Action |
|----------|--------|
| **Non-blocking** (doesn't prevent current goal) | File via `bd create --type=bug` and keep working. Priority-1 routing picks it up later. |
| **Blocking** (can't complete current bead without fixing) | File with `[bead-chain:triaged]` marker, fix inline as scope expansion, summarize both for judges. Bug stays open for verification. |

**Important:** Agents do NOT close beads themselves. The judges are the only legitimate closer.

---

## Architecture

```
bead_chain/
├── __init__.py           # Package docstring
├── register_callbacks.py # Wiring: /bead-chain command, hook handlers
├── lifecycle.py          # State transitions: close, pick next, arm wiggum
├── beads.py              # Subprocess core for `bd` + facade re-export
├── beads_reads.py        # Read/query waterfall (ready, list, show, blockers)
├── beads_writes.py       # Mutations + epic/gate/lint housekeeping
├── prompt.py             # Bead → goal prompt formatting
├── close_guard.py        # Shell hook that blocks premature closes
└── state.py              # Singleton dataclass for chain state
```

**Module responsibilities:**

| Module | Does | Doesn't |
|--------|------|---------|
| `register_callbacks` | Slash command, hook registration, CLI flag parsing | State transitions, bd calls |
| `lifecycle` | Close/claim/pick logic, invariant guards | Hook registration |
| `beads` | Subprocess core (`_run_bd`, retries, predicates, constants) + re-export facade for the two halves | Know about chain state |
| `beads_reads` | Read-only `bd` queries: ready/list waterfall, `show`, memories, blocker/pin checks | Mutate bead state |
| `beads_writes` | Mutations (`claim`/`close`/`revert`) + epic rollup, gate probe, lint warnings | Drive the ready queue |
| `prompt` | Format goal prompts, recovery/triage preambles | Execute commands |
| `close_guard` | Detect+block agent `bd close` attempts | Close beads itself |
| `state` | Hold active/current_bead/completed_count | Behavior logic |

**Design principle:** This plugin is a *queue driver*, not a goal engine. It delegates LLM-judged completion to wiggum's `/goal` mode.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_BIN` | `br` | Path to the `br` (beads_rust) executable (for non-standard installs) |

**Timeouts & retries (hardcoded, not configurable):**
- `bd` command timeout: 30 seconds  
- Retry policy: 3 attempts with 0.5s/1.0s backoff (timeout only, not errors)

**Excluded types:** Container / handle types — `epic`, `milestone`, `gate`, `molecule` — are filtered out **client-side** (`br` has no `--exclude-type` query flag). bead-chain never tries to drive container beads — only leaf work items.

---

## Quick Reference

```bash
# Start the chain
/bead-chain

# Limit iterations
/bead-chain --max=5

# Stop
Ctrl+C

# Check what's in progress (outside bead-chain)
bd list --status=in_progress

# See the ready queue
bd ready
```

---

## See Also

- **[bead-chain on GitHub](https://github.com/weegens-aaron/bead-chain)** — source, full test suite, design notes (ADRs), and issue tracker.
- **wiggum / code_puppy** — the `/goal` engine that bead-chain delegates LLM-judged completion to.
- **[beads / `bd`](https://github.com/gastownhall/beads)** — the underlying issue tracker CLI bead-chain drives.
