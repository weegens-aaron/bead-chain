#!/usr/bin/env bash
#
# build-release.sh — Build the clean bead-chain release zip from an explicit
# allowlist (see notes/decisions/0002-release-allowlist.md, bead_chain-2xg).
#
# What it does (deterministic, idempotent):
#   1. Reads __version__ from __init__.py (single source of truth, no dupes).
#   2. Cleans staging/ and dist/.
#   3. Copies ONLY the allowlisted runtime paths into staging/bead_chain/.
#   4. Zips staging/ so the archive's single top-level entry is bead_chain/.
#   5. Writes BOTH a stable name (dist/bead-chain.zip — enables the
#      /releases/latest/download/bead-chain.zip URL) and a versioned name
#      (dist/bead-chain-v<version>.zip).
#   6. Self-checks: extracts the stable zip to a temp dir and imports
#      bead_chain.register_callbacks. A missing runtime file => ImportError =>
#      the allowlist is incomplete and the build fails loudly.
#
# Design (per the bead): allowlist COPY, not `git archive`, so the clean subset
# is guaranteed regardless of git tracking state. The file list lives in ONE
# array below, sourced conceptually from ADR 0002 (the dec_manifest).

set -euo pipefail

# --- Locate the repo root (the dir that holds __init__.py), relative to this
#     script, so the build works no matter the caller's CWD. -----------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
cd "${REPO_ROOT}"

# --- The allowlist (ADR 0002: SHIP = 8 runtime .py files + README.md +
#     LICENSE). Anything not named here is excluded by construction
#     (fail-closed). LICENSE ships so the MIT terms travel with the artifact
#     (bead_chain-aij).
ALLOWLIST=(
  "__init__.py"
  "beads.py"
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
STABLE_ZIP="${DIST_DIR}/bead-chain.zip"

# --- 1. Read the single-source __version__ from __init__.py (no Python import
#        needed — just slice the quoted value out of the one assignment). -----
read_version() {
  local line
  line="$(grep -E '^__version__[[:space:]]*=' "${REPO_ROOT}/__init__.py" | head -n1)"
  if [[ -z "${line}" ]]; then
    echo "ERROR: could not find __version__ in __init__.py" >&2
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

VERSION="$(read_version)"
VERSIONED_ZIP="${DIST_DIR}/bead-chain-v${VERSION}.zip"

echo "==> bead-chain release build (v${VERSION})"

# --- 2. Clean staging/ and dist/ (idempotent re-runs). ----------------------
echo "==> Cleaning staging/ and dist/"
rm -rf "${STAGING_DIR}" "${DIST_DIR}"
mkdir -p "${STAGING_DIR}/${PKG_NAME}" "${DIST_DIR}"

# --- 3. Copy ONLY the allowlisted paths into staging/bead_chain/. -----------
echo "==> Copying ${#ALLOWLIST[@]} allowlisted paths into staging/${PKG_NAME}/"
for path in "${ALLOWLIST[@]}"; do
  if [[ ! -e "${REPO_ROOT}/${path}" ]]; then
    echo "ERROR: allowlisted path is missing from the repo: ${path}" >&2
    exit 1
  fi
  cp -f "${REPO_ROOT}/${path}" "${STAGING_DIR}/${PKG_NAME}/"
  echo "    + ${path}"
done

# --- 4 & 5. Zip staging/ so the single top-level entry is bead_chain/. -------
echo "==> Building ${STABLE_ZIP}"
(
  cd "${STAGING_DIR}"
  # -X strips extra file attributes (no .DS_Store-style noise); -r recursive.
  zip -X -r -q "${STABLE_ZIP}" "${PKG_NAME}"
)
cp -f "${STABLE_ZIP}" "${VERSIONED_ZIP}"
echo "    wrote $(basename "${STABLE_ZIP}") and $(basename "${VERSIONED_ZIP}")"

# --- 6. Self-check: extract to a temp dir and import the entry point. --------
echo "==> Self-check: extracting and importing ${PKG_NAME}.register_callbacks"
TMP_CHECK="$(mktemp -d)"
cleanup() { rm -rf "${TMP_CHECK}"; }
trap cleanup EXIT

unzip -q "${STABLE_ZIP}" -d "${TMP_CHECK}"

python3 -c "import sys; sys.path.insert(0, '${TMP_CHECK}'); import ${PKG_NAME}.register_callbacks; print('    import OK:', ${PKG_NAME}.register_callbacks.__name__)"

# --- Report the archive contents so the build is auditable at a glance. ------
echo "==> Archive contents:"
unzip -l "${STABLE_ZIP}"

echo "==> Done. Release artifacts in dist/:"
ls -1 "${DIST_DIR}"
