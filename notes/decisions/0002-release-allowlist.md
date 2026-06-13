# ADR 0002 — The v0.1.0 release artifact is an explicit allowlist (runtime files vs dev-only)

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| Status     | Accepted                                                              |
| Date       | 2026-06-08                                                            |
| Bead       | `bead_chain-2xg`, under epic `bead_chain-spl` (Release v0.1.0)         |
| Source     | Epic `bead_chain-spl` acceptance; working-tree audit                  |
| Supersedes | —                                                                     |

## Context

Goal of epic `bead_chain-spl`: a user runs one `curl | unzip` line and gets a
clean `bead_chain/` plugin in `~/.code_puppy/plugins/` with **zero dev cruft**.

The working tree intermixes runtime code with a lot of things a user must never
receive:

- `.beads/` — the local Dolt DB, formulas, audit logs, interaction journal.
- `tests/` — the pytest suite (245 tests).
- `notes/` — ADRs, the bead-chain coverage analysis, DRY/SOLID triage artifacts.
- `docs/` — generated user-facing HTML (a *build output*, not source).
- `__docs/` — FlowDoc maintainer markdown *source* the HTML is built from.
- `skills/` — the vendored `md-to-html` tooling used by `.beads` formulas.
- caches/OS junk — `__pycache__/`, `*.pyc`, `.DS_Store`, `.ruff_cache`,
  `.pytest_cache`.
- contributor files — `AGENTS.md` (bd/contributor workflow), `.gitignore`.

This decision is the single source of truth referenced by three downstream
beads: the build script, the `.gitignore` chore, and the install docs.

## Decision

**The release artifact is built from an explicit allowlist, not a denylist.**
Only named paths are copied into the zip; anything not listed is, by
construction, excluded.

### SHIP — runtime allowlist (11 paths)

| Path                    | Why it ships                                            |
| ----------------------- | ------------------------------------------------------ |
| `__init__.py`           | Package marker for `code_puppy.plugins.bead_chain`.     |
| `beads.py`              | `bd` subprocess core (`_run_bd`, retries, predicates) + facade re-export. |
| `beads_reads.py`        | Read/query waterfall split from beads.py (bead_chain-7xv). |
| `beads_writes.py`       | Mutations + epic/gate/lint housekeeping split from beads.py (bead_chain-7xv). |
| `close_guard.py`        | Premature-`bd close` shell-hook guard.                  |
| `execution_hints.py`    | Per-bead execution-hint enrichment.                     |
| `lifecycle.py`          | Chain drain / claim / rollup engine.                    |
| `prompt.py`             | Goal-prompt construction from a bead.                   |
| `register_callbacks.py` | Plugin entry point — wires hooks + the `/bead-chain` cmd.|
| `state.py`              | In-process chain-state singleton.                       |
| `README.md`             | User-facing install + usage doc.                        |

### EXCLUDE — dev-only (never ship)

`.beads/`, `tests/`, `notes/`, `docs/`, `__docs/`, `skills/`, `__pycache__/`,
`*.pyc`, `.DS_Store`, `.gitignore`, `AGENTS.md`, `.ruff_cache`, `.pytest_cache`.

### Notable exclusion calls

- **`skills/` is NOT plugin runtime.** It was tooling (`md-to-html`) invoked by
  `.beads` formulas to build documentation; it is not imported by any runtime
  module. Verified: `grep -rn "skills" *.py` over the ten SHIP `.py` files
  returns nothing. It does **not** ship.
- **`AGENTS.md` does NOT ship.** It is the contributor / `bd` workflow guide
  (session-close protocol, dolt-sync step), not user-facing material. The
  user-facing entry point is `README.md`.
- **`docs/` does NOT ship.** It is a *generated* HTML build output (from
  `__docs/`), not plugin runtime. Neither the source nor the output belongs in a
  drop-in plugin.

## Zip internal layout

The archive contains a **single top-level `bead_chain/` directory** holding the
SHIP files, so it extracts straight into `~/.code_puppy/plugins/`:

```
bead_chain-v0.1.0.zip
└── bead_chain/
    ├── __init__.py
    ├── beads.py
    ├── beads_reads.py
    ├── beads_writes.py
    ├── close_guard.py
    ├── execution_hints.py
    ├── lifecycle.py
    ├── prompt.py
    ├── register_callbacks.py
    ├── state.py
    └── README.md
```

`unzip bead_chain-v0.1.0.zip -d ~/.code_puppy/plugins/` then yields exactly
`~/.code_puppy/plugins/bead_chain/`.

## Rationale

- **Fail-safe by construction.** An allowlist *fails closed*: when a new dev
  artifact type appears (another `notes/` subdir, a new triage file, a second
  vendored skill), it is excluded automatically because it was never named. A
  denylist *fails open* — every new artifact silently leaks until someone
  remembers to add an exclusion.
- **Omissions are loud.** If a genuinely-needed runtime file is left off the
  allowlist, the build (and the SHIP-only import validation below) breaks
  immediately with a missing-file/`ImportError`, caught in CI rather than
  shipped broken. A leak, by contrast, is silent.
- **Matches the "no bs" install goal.** The user gets eleven files, no Dolt DB, no
  tests, no maintainer notes.

## Alternatives considered

1. **`git archive` + `.gitattributes export-ignore` (denylist).** Leaner, but
   *fails open*: it relies on git tracking being perfect and on someone
   remembering to mark every new dev path `export-ignore`. One forgotten mark
   ships cruft. **Rejected.**
2. **Ship the whole repo, tell users to ignore the cruft.** Violates the "no bs"
   goal and drags the Dolt DB + tests into every install. **Rejected.**
3. **Python wheel / sdist packaging.** Overkill for a directory-drop code_puppy
   plugin and forces a `pip` step into the one-liner install. **Rejected for
   v0.1.0** (revisit if the plugin ever grows real package dependencies).

## Validation — allowlist completeness

Performed for this ADR and to be re-run by the build script:

```bash
# Copy ONLY the SHIP files into an isolated bead_chain/ package, then import
# the plugin entry point. A missing runtime module => ImportError => allowlist
# is incomplete.
mkdir -p /tmp/ship_validate/bead_chain
for f in __init__.py beads.py beads_reads.py beads_writes.py close_guard.py execution_hints.py \
         lifecycle.py prompt.py register_callbacks.py state.py README.md; do
  cp -f "$f" /tmp/ship_validate/bead_chain/
done
python3 -c "import sys; sys.path.insert(0,'/tmp/ship_validate'); \
            import bead_chain.register_callbacks"
```

Result: **import succeeds** with only the eleven SHIP files present, confirming the
runtime allowlist is self-contained. The runtime depends only on the Python
stdlib and the host `code_puppy.*` framework (provided by the install
environment), plus relative imports among the SHIP modules — nothing outside the
allowlist.

## Consequences

- **Positive:** new dev artifacts can never accidentally ship; the build is
  deterministic and auditable; the install is genuinely clean.
- **Negative / accepted:** adding a *new runtime module* in the future requires
  remembering to extend the allowlist — but that failure is loud (import/build
  break), which is exactly the trade we want.

## Follow-up

Consumed by, under epic `bead_chain-spl`:

- the build script (uses this allowlist verbatim + re-runs the validation),
- the `.gitignore` chore (mirrors the EXCLUDE set),
- the install docs (document the one-line `curl | unzip` and the resulting
  `~/.code_puppy/plugins/bead_chain/` layout).
