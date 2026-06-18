#!/usr/bin/env bash
#
# build-release.sh — Build the clean bead-chain release zips from an explicit
# allowlist (see notes/decisions/0002-release-allowlist.md, bead_chain-2xg).
#
# This repo houses TWO independent plugin variants (bead_chain-3id):
#   * bd/ — the canonical bead-chain plugin (Go `bd` / Dolt backend)
#   * br/ — the beads_rust-compatible variant
# Both install as the SAME plugin name (~/.code_puppy/plugins/bead_chain/) —
# the user picks ONE. So each variant gets its own qualified release artifact:
#
#   dist/bead-chain-bd.zip            (+ versioned + .sha256)
#   dist/bead-chain-br.zip            (+ versioned + .sha256)
#   dist/bead-chain.zip               (backward-compat ALIAS of the bd variant)
#
# What it does per variant (deterministic, idempotent):
#   1. Reads __version__ from <variant>/__init__.py (single source of truth).
#   2. Copies ONLY the allowlisted runtime paths into
#      staging/<variant>/bead_chain/.
#   3. Zips so the archive's single top-level entry is bead_chain/ (NOT the
#      variant name — the plugin always installs as bead_chain/).
#   4. Writes BOTH a stable name (dist/bead-chain-<variant>.zip) and a
#      versioned name (dist/bead-chain-<variant>-v<version>.zip).
#   5. Writes a SHA256 checksum file alongside each zip (bead_chain-ixc).
#   6. Self-checks: extracts the stable zip to a temp dir and imports
#      bead_chain.register_callbacks. A missing runtime file => ImportError =>
#      the allowlist is incomplete and the build fails loudly.
#
# Design (per the bead): allowlist COPY, not `git archive`, so the clean subset
# is guaranteed regardless of git tracking state. The file list lives in ONE
# array below, sourced conceptually from ADR 0002 (the dec_manifest).

set -euo pipefail

# --- Locate the repo root (the dir that holds bd/, br/ and scripts/),
#     relative to this script, so the build works no matter the caller's CWD.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
cd "${REPO_ROOT}"

# --- The variants to build. Each name is BOTH the source subdirectory under
#     the repo root AND the qualifier in the artifact name
#     (bead-chain-<variant>.zip). Add a third variant by appending here.
VARIANTS=(bd br)

# --- The backward-compat alias: the unqualified dist/bead-chain.zip (and its
#     .sha256) is a byte-for-byte copy of THIS variant's stable zip, so the
#     legacy /releases/latest/download/bead-chain.zip URL keeps working.
ALIAS_VARIANT="bd"

# --- The allowlist (ADR 0002: SHIP = 10 runtime .py files + README.md +
#     LICENSE). Anything not named here is excluded by construction
#     (fail-closed). LICENSE ships so the MIT terms travel with the artifact
#     (bead_chain-aij). beads_reads.py / beads_writes.py are the read/write
#     halves split out of the once-monolithic beads.py (bead_chain-7xv) — they
#     are imported by beads.py's facade and MUST ship or every consumer breaks.
#     The allowlist is identical across variants (the variants differ only in
#     the *contents* of these files, not the set).
ALLOWLIST=(
  "__init__.py"
  "beads.py"
  "beads_reads.py"
  "beads_writes.py"
  "close_guard.py"
  "execution_hints.py"
  "lifecycle.py"
  "prompt.py"
  "register_callbacks.py"
  "state.py"
  "README.md"
  "LICENSE"
)

PKG_NAME="bead_chain"
STAGING_DIR="${REPO_ROOT}/staging"
DIST_DIR="${REPO_ROOT}/dist"

# --- Read the single-source __version__ from a variant's __init__.py (no
#     Python import needed — just slice the quoted value out of the one
#     assignment). -----------------------------------------------------------
read_version() {
  local src_dir="$1"
  local line
  line="$(grep -E '^__version__[[:space:]]*=' "${src_dir}/__init__.py" | head -n1)"
  if [[ -z "${line}" ]]; then
    echo "ERROR: could not find __version__ in ${src_dir}/__init__.py" >&2
    exit 1
  fi
  # Strip everything up to the first quote and the trailing quote.
  local ver
  ver="$(printf '%s\n' "${line}" | sed -E 's/^[^"]*"([^"]*)".*$/\1/')"
  if [[ -z "${ver}" || "${ver}" == "${line}" ]]; then
    echo "ERROR: could not parse a quoted version from: ${line}" >&2
    exit 1
  fi
  printf '%s\n' "${ver}"
}

# --- Cross-platform SHA256: macOS ships `shasum`, most Linux ships
#     `sha256sum`. Pick whichever exists; fail loudly if neither does. Runs
#     inside dist/ so the written checksum references the BARE filename, which
#     is exactly what `shasum -a 256 -c` / `sha256sum -c` expect when the user
#     has the zip and the .sha256 side by side. -------------------------------
sha256_in_dist() {
  local file="$1"  # bare filename, relative to DIST_DIR
  (
    cd "${DIST_DIR}"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum "${file}" > "${file}.sha256"
    elif command -v shasum >/dev/null 2>&1; then
      shasum -a 256 "${file}" > "${file}.sha256"
    else
      echo "ERROR: neither sha256sum nor shasum found — cannot checksum ${file}" >&2
      exit 1
    fi
  )
}

# --- Build one variant: stage -> zip (stable + versioned) -> checksum ->
#     self-check import. Echoes nothing the caller needs to capture; all
#     artifacts land in dist/. ------------------------------------------------
build_variant() {
  local variant="$1"
  local src_dir="${REPO_ROOT}/${variant}"

  if [[ ! -d "${src_dir}" ]]; then
    echo "ERROR: variant source dir is missing: ${variant}/" >&2
    exit 1
  fi

  local version
  version="$(read_version "${src_dir}")"

  local stable_zip="${DIST_DIR}/bead-chain-${variant}.zip"
  local versioned_zip="${DIST_DIR}/bead-chain-${variant}-v${version}.zip"
  local stage_pkg="${STAGING_DIR}/${variant}/${PKG_NAME}"

  echo "==> [${variant}] bead-chain release build (v${version})"

  # Stage ONLY the allowlisted paths into staging/<variant>/bead_chain/.
  mkdir -p "${stage_pkg}"
  echo "    copying ${#ALLOWLIST[@]} allowlisted paths into staging/${variant}/${PKG_NAME}/"
  local path
  for path in "${ALLOWLIST[@]}"; do
    if [[ ! -e "${src_dir}/${path}" ]]; then
      echo "ERROR: allowlisted path is missing from ${variant}/: ${path}" >&2
      exit 1
    fi
    cp -f "${src_dir}/${path}" "${stage_pkg}/"
  done

  # Zip so the single top-level entry is bead_chain/ (run from the variant's
  # staging dir so the variant name is NOT included in the archive paths).
  echo "    building $(basename "${stable_zip}")"
  (
    cd "${STAGING_DIR}/${variant}"
    # -X strips extra file attributes (no .DS_Store-style noise); -r recursive.
    zip -X -r -q "${stable_zip}" "${PKG_NAME}"
  )
  cp -f "${stable_zip}" "${versioned_zip}"
  echo "    wrote $(basename "${stable_zip}") and $(basename "${versioned_zip}")"

  # SHA256 checksums alongside each zip (bead_chain-ixc).
  sha256_in_dist "$(basename "${stable_zip}")"
  sha256_in_dist "$(basename "${versioned_zip}")"
  echo "    wrote .sha256 for both"

  # Self-check: extract to a temp dir and import the entry point. Each variant
  # gets a FRESH temp dir + a subprocess so a cached bead_chain module from a
  # previous variant can't mask a missing file in this one.
  echo "    self-check: importing ${PKG_NAME}.register_callbacks"
  local tmp_check
  tmp_check="$(mktemp -d)"
  unzip -q "${stable_zip}" -d "${tmp_check}"
  python3 -c "import sys; sys.path.insert(0, '${tmp_check}'); import ${PKG_NAME}.register_callbacks; print('    import OK:', ${PKG_NAME}.register_callbacks.__name__)"
  rm -rf "${tmp_check}"
}

echo "==> bead-chain multi-variant release build (${VARIANTS[*]})"

# --- Clean staging/ and dist/ once, up front (idempotent re-runs). ----------
echo "==> Cleaning staging/ and dist/"
rm -rf "${STAGING_DIR}" "${DIST_DIR}"
mkdir -p "${STAGING_DIR}" "${DIST_DIR}"

# --- Build every variant. ---------------------------------------------------
for variant in "${VARIANTS[@]}"; do
  build_variant "${variant}"
done

# --- Backward-compat alias: dist/bead-chain.zip == the bd variant's stable
#     zip, so the legacy /releases/latest/download/bead-chain.zip URL and any
#     existing install one-liner keep resolving (bead_chain-szm). --------------
ALIAS_STABLE="${DIST_DIR}/bead-chain-${ALIAS_VARIANT}.zip"
LEGACY_ZIP="${DIST_DIR}/bead-chain.zip"
echo "==> Aliasing legacy bead-chain.zip -> bead-chain-${ALIAS_VARIANT}.zip (backward compat)"
cp -f "${ALIAS_STABLE}" "${LEGACY_ZIP}"
sha256_in_dist "$(basename "${LEGACY_ZIP}")"
echo "    wrote $(basename "${LEGACY_ZIP}") and its .sha256"

# --- Report all artifacts so the build is auditable at a glance. ------------
echo "==> Done. Release artifacts in dist/:"
ls -1 "${DIST_DIR}"

# --- Release reminder: the GitHub Release must carry ALL zips AND their
#     .sha256 files as assets (bead_chain-ixc). With the GitHub CLI a single
#     glob uploads everything in dist/ (both variants, the alias, and every
#     checksum):
echo
echo "==> To publish: upload ALL dist artifacts (both variants + alias + checksums), e.g."
echo "      gh release create v<version> ${DIST_DIR}/bead-chain*.zip ${DIST_DIR}/bead-chain*.zip.sha256"
echo "    (the .sha256 assets are what the README's verify step downloads)"
