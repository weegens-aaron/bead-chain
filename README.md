# bead-chain  — dual-variant monorepo

**A beads-driven `/goal` variant that chains your ready queue into wiggum's goal
loop, one bead at a time.** Claim → `/goal` → close → repeat, until the queue is
empty or you hit Ctrl+C.

This repository ships **two independent variants of the same plugin**. Both
install under the same code_puppy plugin name (`bead_chain/`) — you pick exactly
one, depending on which beads CLI you run.

| Variant | Targets | Binary | Status | Directory |
|---------|---------|--------|--------|-----------|
| **`bd`** (default, recommended) | [Go beads](https://github.com/gastownhall/beads) (`bd`) | `bd` | Full feature set | [`bd/`](bd/) |
| **`br`** | [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`) | `br` | Compatible subset (some features degraded — see below) | [`br/`](br/) |

> **Both variants are functionally the same chain driver.** They differ only in
> how they talk to the underlying CLI. See each variant's own README for the
> full feature tour, architecture, and configuration:
> [`bd/README.md`](bd/README.md) · [`br/README.md`](br/README.md).

---

## Which variant should I install?

- **Use `bd` (the default) unless you have a specific reason not to.** It targets
  the Go beads CLI (`bd`), supports every bead-chain feature, and is the
  variant the project is developed and tested against first.
- **Use `br` only if you run the [beads_rust](https://github.com/Dicklesworthstone/beads_rust)
  (`br`) CLI** instead of the Go `bd` CLI. The `br` variant adapts bead-chain to
  `br`'s query-flag vocabulary and JSON envelope (no `--exclude-type`, the
  `list --json` object shape `{"issues":[…]}`, no `list --parent`, and a
  close-guard widened to also catch `br close` / `br update --status=closed`).

If you're unsure which CLI you have, run `bd --version` or `br --version` — the
one that exists is your variant.

### Feature degradations in the `br` variant

`br` is a deliberate freeze of "classic beads" (SQLite + JSONL) and lacks two
subcommands the `bd` variant uses. Both degrade **gracefully** (soft-fail, no
crash) — the chain still runs end to end, it just loses these enrichments:

| Feature | `bd` variant | `br` variant |
|---------|--------------|--------------|
| **Memories** (`memories` subcommand + `bd remember`) | Goal prompts include a memory digest; agents can write durable notes. | **Absent.** `br` has no `memories` subcommand and no `remember`, so goal prompts ship without the memory digest and agents can't persist memories. |
| **Gates** (`gate check`) | Resolved gates are detected mid-session and gate-pending targets re-opened. | **Absent.** `br` has no `gate` subcommand, so gate-pending targets are never re-opened mid-session. |

Everything else — claim/close/revert mutations, `show`, `lint`, epic rollup,
the work-time blocker gate, recovery mode, epic affinity, blocking-bug priority,
and the close-guard — works identically in both variants. The full compatibility
analysis lives in spike `bead_chain-5d3`
([notes/spikes/beads-rust-br-drop-in-compat-5d3.md](notes/spikes/beads-rust-br-drop-in-compat-5d3.md)).

---

## Install

Pick **one** variant. Each one-liner downloads that variant's release zip,
extracts it as `~/.code_puppy/plugins/bead_chain/`, and (after a code_puppy
restart) gives you the `/bead-chain` command. Don't install both — they share the
`bead_chain/` plugin name and would collide.

### `bd` variant (default / recommended)

**macOS / Linux (bash/zsh):**

```bash
curl -fsSL https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-bd.zip -o /tmp/bead-chain-bd.zip && unzip -o /tmp/bead-chain-bd.zip -d ~/.code_puppy/plugins/
```

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-bd.zip -OutFile $env:TEMP\bead-chain-bd.zip; Expand-Archive -Force $env:TEMP\bead-chain-bd.zip -DestinationPath ~\.code_puppy\plugins\
```

> The unqualified `bead-chain.zip` asset is a **backward-compatibility alias for
> the `bd` variant** — older install lines that reference it still resolve to
> `bd`. New installs should prefer the explicit `bead-chain-bd.zip` name.

### `br` variant (beads_rust users)

**macOS / Linux (bash/zsh):**

```bash
curl -fsSL https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-br.zip -o /tmp/bead-chain-br.zip && unzip -o /tmp/bead-chain-br.zip -d ~/.code_puppy/plugins/
```

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-br.zip -OutFile $env:TEMP\bead-chain-br.zip; Expand-Archive -Force $env:TEMP\bead-chain-br.zip -DestinationPath ~\.code_puppy\plugins\
```

Plugins live at `~/.code_puppy/plugins/` (macOS/Linux) or
`~\.code_puppy\plugins\` — i.e. `%USERPROFILE%\.code_puppy\plugins\` — on
Windows. Each zip contains a single top-level `bead_chain/` folder, so every
command above lands at `…/plugins/bead_chain/…`: **extract, don't nest.** After
installing, **restart code_puppy.**

Prefer a browser? Grab the matching `bead-chain-bd.zip` or `bead-chain-br.zip`
from the [**Releases** page](https://github.com/weegens-aaron/bead-chain/releases/latest)
and extract it so `bead_chain/` lands directly inside your plugins directory.

---

## Verify your download (optional but recommended)

Every release publishes a `.sha256` asset next to **each** variant's zip
(`bead-chain-bd.zip.sha256`, `bead-chain-br.zip.sha256`). Verifying confirms the
download is the exact artifact the maintainer built. This is optional — the
install one-liners work without it — but it's a quick guard against a corrupted
or tampered file. If verification fails, **don't install**; re-download or report
it.

Substitute the variant you installed for `<variant>` (`bd` or `br`) below.

**macOS / Linux (bash/zsh):**

```bash
curl -fsSL https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-<variant>.zip.sha256 -o /tmp/bead-chain-<variant>.zip.sha256
( cd /tmp && shasum -a 256 -c bead-chain-<variant>.zip.sha256 )   # prints "bead-chain-<variant>.zip: OK"
```

(`sha256sum -c bead-chain-<variant>.zip.sha256` works too on distros that ship
`sha256sum` instead of `shasum`.)

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri https://github.com/weegens-aaron/bead-chain/releases/latest/download/bead-chain-<variant>.zip.sha256 -OutFile $env:TEMP\bead-chain-<variant>.zip.sha256
$expected = (Get-Content $env:TEMP\bead-chain-<variant>.zip.sha256).Split(' ')[0]
$actual   = (Get-FileHash $env:TEMP\bead-chain-<variant>.zip -Algorithm SHA256).Hash
if ($actual -eq $expected) { "OK: checksum matches" } else { Write-Error "CHECKSUM MISMATCH — do not install" }
```

(`-eq` is case-insensitive in PowerShell, so the uppercase `Get-FileHash` output
matches the lowercase published hash.)

---

## Upgrade / Uninstall

| Action | macOS / Linux | Windows (PowerShell) |
|--------|---------------|----------------------|
| **Upgrade** | Re-run your variant's install line — it always pulls the latest release. | Re-run your variant's install line. |
| **Uninstall** | `rm -rf ~/.code_puppy/plugins/bead_chain` | `Remove-Item -Recurse -Force ~\.code_puppy\plugins\bead_chain` |
| **Switch variants** | Uninstall, then run the other variant's install line. | Uninstall, then run the other variant's install line. |

Both variants extract to the same `bead_chain/` directory, so switching is just
uninstall-then-reinstall — never run both at once.

---

## Repository layout

```
bead-chain/
├── README.md                 # ← you are here (dual-variant overview)
├── bd/                       # bd variant — Go beads CLI (default)
│   ├── README.md             #   variant-specific docs
│   ├── register_callbacks.py #   entry point
│   └── …                     #   runtime modules (beads*.py, lifecycle, …)
├── br/                       # br variant — beads_rust CLI
│   ├── README.md             #   variant-specific docs (+ degradation notes)
│   ├── register_callbacks.py
│   └── …
├── scripts/build-release.sh  # builds per-variant release zips + checksums
├── tests/                    # shared + variant test suites
└── notes/                    # ADRs, spikes, analysis (incl. 5d3 br spike)
```

The build script produces a release zip + `.sha256` for **each** variant
(`bead-chain-bd.zip`, `bead-chain-br.zip`), plus versioned copies. See
[`scripts/build-release.sh`](scripts/build-release.sh).

---

## See Also

- **[bead-chain on GitHub](https://github.com/weegens-aaron/bead-chain)** — source, full test suite, design notes (ADRs), and issue tracker.
- **[beads / `bd`](https://github.com/gastownhall/beads)** — the Go beads CLI the `bd` variant drives.
- **[beads_rust / `br`](https://github.com/Dicklesworthstone/beads_rust)** — the Rust beads CLI the `br` variant drives.
- **wiggum / code_puppy** — the `/goal` engine bead-chain delegates LLM-judged completion to.
