"""Thin subprocess wrapper around the ``bd`` CLI.

We intentionally shell out instead of importing any beads Python API:
beads is a Go binary, and its JSON output is its stable contract. This
keeps the plugin dependency-free and lets users on any bd version play.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

DEFAULT_TIMEOUT = 30.0
DEFAULT_BD_BIN = "bd"

# Retry policy for transient `bd` timeouts.
#
# bd talks to a sqlite database that can briefly contend on locks
# (concurrent agents, cold-cache opens, the daemon flushing, etc.).
# Stranding the entire chain on a single 30s blip is way worse than
# trying again, so we retry on ``subprocess.TimeoutExpired`` only.
# ``FileNotFoundError`` (bd not installed) and non-zero exits (real bd
# errors like 'bead not found', 'already closed') are NOT retried —
# those are permanent and retrying just delays the truth.
#
# Kept as module constants per YAGNI: if someone needs env-var knobs
# we add them later (5-line follow-up). Doing both up front overcommits.
MAX_ATTEMPTS: int = 3  # initial try + up to (MAX_ATTEMPTS - 1) retries
# Backoff delays applied BEFORE each retry. Length must be >= MAX_ATTEMPTS-1;
# extra entries are ignored. Short and exponential-ish — long enough to
# let a sqlite lock clear, short enough not to feel like a hang.
_RETRY_BACKOFFS: tuple[float, ...] = (0.5, 1.0)

# Bead types that /bead-chain must never try to drive directly.
# 'epic' is a container of child issues — we want the children, not
# the epic itself. Extend this tuple if other purely-organizational
# types appear (e.g. 'milestone'). One-line change, by design. DRY.
EXCLUDED_TYPES: tuple[str, ...] = ("epic",)


def is_excluded_type(bead: dict[str, Any] | None) -> bool:
    """True if ``bead`` is a container type bead-chain must never drive.

    Defence-in-depth companion to the server-side ``--exclude-type``
    filter we pass to ``bd``. The CLI flag *should* keep epics out of
    our queries, but — verified the hard way in prod — it sometimes
    leaks an epic through anyway (bd version drift, JSON casing
    differences, etc.). Filtering client-side as well makes the
    invariant ironclad: even if every server-side filter failed open,
    we still refuse to treat epics as drivable work.

    The check is case-insensitive on ``issue_type`` so an upstream
    bd that suddenly emits ``"Epic"`` instead of ``"epic"`` doesn't
    silently start leaking. None/missing/non-dict input is treated as
    'not excluded' (safer: a bead with a busted shape can still be
    surfaced for the caller to handle, rather than vanish silently).
    """
    if not isinstance(bead, dict):
        return False
    issue_type = str(bead.get("issue_type", "")).strip().lower()
    return issue_type in EXCLUDED_TYPES


# Dependency-edge type that means "this bead is blocked until the other
# one closes". bd uses the literal string ``"blocks"`` for both sides of
# the edge (it's the edge type, not a perspective) — see repo memory
# 'dep-edge-direction'. From a bead's *inbound* ``dependencies`` list a
# ``blocks`` entry reads as "X blocks me", i.e. a work-time blocker.
# ``parent-child`` / ``discovered-from`` / ``related`` edges do NOT gate
# work, so they are deliberately excluded. Tuple-constant so adding a
# future blocking edge type (e.g. ``"requires"``) stays a one-line edit.
BLOCKING_DEP_TYPES: tuple[str, ...] = ("blocks",)

# Statuses that mean a blocker is *satisfied* (no longer gates work).
# Only a closed blocker is satisfied; open / in_progress / blocked all
# still gate. Case-insensitive comparison, see :func:`open_blocker_ids`.
SATISFIED_BLOCKER_STATUSES: frozenset[str] = frozenset({"closed"})


# Issue types that count as 'bugs' for the blocking-bug priority pass.
# A blocking bug (type in here AND dependent_count > 0) jumps the queue
# ahead of every other selection rule because fixing it unblocks more
# work. Keeping this as a tuple constant makes adding a sibling type
# (e.g. 'regression') a one-line change. DRY.
BLOCKING_BUG_TYPES: tuple[str, ...] = ("bug",)


def _exclude_type_arg() -> str:
    """Return the ``--exclude-type=...`` CLI arg for EXCLUDED_TYPES.

    DRY helper: this exact arg string is needed by every function that
    queries ``bd ready`` or ``bd list``. Centralising it here means a
    new excluded type is a one-line edit to :data:`EXCLUDED_TYPES`.
    """
    return f"--exclude-type={','.join(EXCLUDED_TYPES)}"


# Key on a bd-ready bead dict that names the bead's parent epic, if any.
#
# ``bd ready --json`` surfaces the parent as a top-level ``"parent"``
# field (string id) on each child bead, alongside the more verbose
# ``dependencies`` array. We pick the top-level field as canonical
# because it's a one-key lookup and lines up with bd's own
# ``--parent=<id>`` filter on ``bd ready`` / ``bd list``.
PARENT_EPIC_KEY: str = "parent"

# Legacy/fallback keys checked by :func:`extract_parent_epic_id` after
# ``PARENT_EPIC_KEY``. Order is most-likely-first. Keep this list short —
# every entry is a subprocess-free dict lookup, but extras add noise.
_PARENT_EPIC_FALLBACK_KEYS: tuple[str, ...] = ("parent_id", "epic_id")


def _bd_bin() -> str:
    """Return the ``bd`` executable to invoke.

    Honors the ``BEADS_BIN`` environment variable so users with a
    non-standard install location can override the default ``bd``
    lookup on ``PATH``. An unset or empty value falls back to ``bd``.
    """
    override = os.environ.get("BEADS_BIN")
    if override:
        return override
    return DEFAULT_BD_BIN


class BeadsError(RuntimeError):
    """Raised when the ``bd`` CLI fails, is missing, or returns junk."""


def _parse_json_list(raw: str, context: str) -> list[Any]:
    """Parse JSON from bd output, expecting a list.

    DRY helper for the repeated pattern:
      1. Parse JSON (raise BeadsError on decode failure)
      2. Validate it's a list (raise BeadsError if not)
      3. Return the list for caller to filter

    Args:
        raw: Raw stdout from a bd command.
        context: Human-readable command description for error messages,
                 e.g. "bd ready --json" or "bd list --status=in_progress".

    Raises:
        BeadsError: On non-JSON output or non-list payload.
    """
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:200].replace("\n", " ")
        raise BeadsError(f"`{context}` returned non-JSON: {snippet!r}") from exc

    if not isinstance(items, list):
        raise BeadsError(
            f"`{context}` returned non-list payload: {type(items).__name__}"
        )
    return items


def _run_bd(*args: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Run ``bd <args>`` and return stdout, or raise :class:`BeadsError`.

    Transient timeouts are retried per :data:`MAX_ATTEMPTS` /
    :data:`_RETRY_BACKOFFS`. Non-zero exits and missing-binary errors
    are surfaced on the first failure — they're not transient.
    """
    bd = _bd_bin()
    last_timeout: subprocess.TimeoutExpired | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt > 0:
            # Cap the index so a future bump to MAX_ATTEMPTS without a
            # matching bump to _RETRY_BACKOFFS still works — the last
            # configured delay just gets reused. Belt-and-suspenders.
            delay_idx = min(attempt - 1, len(_RETRY_BACKOFFS) - 1)
            time.sleep(_RETRY_BACKOFFS[delay_idx])

        try:
            proc = subprocess.run(
                [bd, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            # Permanent — retrying won't make bd appear.
            raise BeadsError(f"`{bd}` not found on PATH — is beads installed?") from exc
        except subprocess.TimeoutExpired as exc:
            last_timeout = exc
            continue  # try again after backoff

        if proc.returncode != 0:
            # Real bd error (bead not found, already closed, etc.).
            # Permanent — surface immediately so callers can react.
            cmd = " ".join((bd, *args))
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise BeadsError(f"`{cmd}` failed (exit {proc.returncode}): {stderr}")

        return proc.stdout

    # Exhausted MAX_ATTEMPTS — every one of them timed out.
    cmd = " ".join((bd, *args))
    raise BeadsError(
        f"`{cmd}` timed out after {timeout}s on each of {MAX_ATTEMPTS} attempts"
    ) from last_timeout


def next_ready() -> dict[str, Any] | None:
    """Return the top ready bead, or ``None`` if none remain.

    Honors whatever ordering ``bd ready --json`` produces — we don't
    try to out-clever beads' own priority/blocker resolution.

    Container-only bead types (see ``EXCLUDED_TYPES``) are filtered out
    server-side via ``--exclude-type``, *and* re-filtered client-side
    via :func:`is_excluded_type` because the server-side flag has been
    observed to leak epics through in the wild. Defence in depth.
    """
    raw = _run_bd("ready", _exclude_type_arg(), "--json")
    items = _parse_json_list(raw, "bd ready --json")
    for item in items:
        if isinstance(item, dict) and not is_excluded_type(item):
            return item
    return None


def list_in_progress() -> list[dict[str, Any]]:
    """Return **all** in_progress non-epic beads, in bd's listed order.

    Backbone for :func:`next_in_progress` (which is just the head of
    this list) and for the chain-startup multi-stranded-bead guard
    that auto-reverts extras to keep the one-bead-at-a-time invariant.
    Both callers want the same `bd list --status=in_progress
    --exclude-type=epic --json` query, so we centralise it here. DRY.

    **Client-side epic filter.** We pass ``--exclude-type=epic`` to bd,
    *and* re-filter the returned list via :func:`is_excluded_type`.
    This is not paranoia — the server-side flag has been observed to
    leak epics through in production, which caused bead-chain to try
    closing an epic (which fails with 'open child issue(s)') and halt
    the chain. Belt-and-suspenders here is the difference between a
    silent foot-gun and a guaranteed invariant.

    Raises :class:`BeadsError` on infrastructure failure (bd missing,
    timeout, non-list payload, bad JSON) — same contract as the other
    list-returning helpers in this module.
    """
    raw = _run_bd("list", "--status=in_progress", _exclude_type_arg(), "--json")
    items = _parse_json_list(raw, "bd list --status=in_progress --json")
    return [
        item for item in items if isinstance(item, dict) and not is_excluded_type(item)
    ]


def next_in_progress() -> dict[str, Any] | None:
    """Return the first in_progress non-epic bead, or ``None``.

    Used by bead-chain to detect *stranded* work from a previous run
    that errored or was cancelled before the LLM judges could rule.
    The deliberate one-bead-at-a-time discipline (no token firehose,
    GasTown-style steady progress) means there should be **at most
    one** such bead at any time — if we find one, the previous run
    didn't get to close it.

    Thin convenience wrapper over :func:`list_in_progress` so callers
    that only want the head don't have to slice. Epics are excluded
    server-side; see :func:`list_in_progress` for the bd command.
    """
    items = list_in_progress()
    return items[0] if items else None


def next_ready_in_epic(epic_id: str) -> dict[str, Any] | None:
    """Return the top ready bead **under** ``epic_id``, or ``None``.

    Wraps ``bd ready --parent=<epic_id> --exclude-type=epic --json``,
    inheriting bd's own priority / blocker resolution. We pass
    ``--exclude-type=epic`` for the same reason :func:`next_ready` does:
    epics are containers, never doable work.
    """
    if not epic_id:
        return None
    raw = _run_bd("ready", f"--parent={epic_id}", _exclude_type_arg(), "--json")
    items = _parse_json_list(raw, f"bd ready --parent={epic_id} --json")
    # Client-side epic filter as well — see :func:`next_ready` for why.
    for item in items:
        if isinstance(item, dict) and not is_excluded_type(item):
            return item
    return None


def extract_parent_epic_id(bead: dict[str, Any] | None) -> str | None:
    """Return the parent epic id of ``bead`` if discoverable, else ``None``.

    Checks :data:`PARENT_EPIC_KEY` first (the canonical bd field name,
    ``"parent"``), then walks :data:`_PARENT_EPIC_FALLBACK_KEYS` for
    cross-version safety. Empty strings are treated as "no parent".
    """
    if not bead:
        return None
    for key in (PARENT_EPIC_KEY, *_PARENT_EPIC_FALLBACK_KEYS):
        value = bead.get(key)
        if value:
            return str(value)
    return None


def open_blocker_ids(bead_id: str) -> list[str]:
    """Return the ids of ``bead_id``'s **open** work-time blockers.

    An empty list means the bead is *ready to work* (no unresolved
    ``blocks`` dependencies). A non-empty list names the still-open
    issues that gate it — exactly the set ``bd close`` would later
    refuse on.

    Includes both work-time blockers (blocks edges) AND fan-out gates
    (waits_for: children-of(...) with unsatisfied spawned children).
    The latter is a workaround for beads CLI bug bead_chain-9sc.

    Why this exists
    ---------------
    ``bd ready`` already filters blocked beads server-side, but two
    chain paths bypass it and can therefore surface a blocked bead:

      1. The **recovery tier** reads ``bd list --status=in_progress``,
         which does NOT honour the ready frontier. A bead claimed while
         ready, then re-blocked (blocker reopened, or a ``blocks`` edge
         wired after the claim), would be re-driven to completion and
         only trip at ``bd close`` — the exact bug in bdboard-oals.
      2. **bd version drift.** Same defence-in-depth rationale as the
         epic ``--exclude-type`` filter: if a future ``bd ready`` ever
         leaked a blocked bead, we still refuse to drive it.
      3. **Fan-out gates (bead_chain-9sc).** Beads with
         `waits_for: children-of(...)` gates are invisible to both
         `bd ready` and `bd blocked` in the beads CLI. We detect them
         here and treat them as blocked until all children are closed.

    We re-fetch via :func:`show` because only ``bd show <id> --json``
    carries each dependency's *status* + *dependency_type*; the
    ``dependencies`` array on ``bd ready`` / ``bd list`` output is a
    list of bare edge records (no status), so it can't tell us whether
    a blocker is still open.

    Soft-fails to ``[]`` (treat as not-blocked) on any infrastructure
    error: a transient bd blip must not strand the chain, and the
    close-time guard remains as the final safety net.
    """
    if not bead_id:
        return []
    try:
        bead = show(bead_id)
    except BeadsError:
        # Can't determine blockers — don't strand the chain on a blip;
        # the close-time guard still backstops us.
        return []
    if not bead:
        return []

    deps = bead.get("dependencies")
    if not isinstance(deps, list):
        return []

    blockers: list[str] = []
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        dep_type = str(dep.get("dependency_type", "")).strip().lower()
        if dep_type not in BLOCKING_DEP_TYPES:
            continue
        status = str(dep.get("status", "")).strip().lower()
        if status in SATISFIED_BLOCKER_STATUSES:
            continue
        dep_id = str(dep.get("id", "")).strip()
        if dep_id:
            blockers.append(dep_id)

    return blockers


def is_blocked(bead_id: str) -> bool:
    """True if ``bead_id`` has at least one open work-time blocker.

    Thin convenience wrapper over :func:`open_blocker_ids` for callers
    that only need the boolean. Soft-fails to ``False`` for the same
    reasons (see that function's docstring).
    """
    return bool(open_blocker_ids(bead_id))


def next_blocking_bug() -> dict[str, Any] | None:
    """Return the top ready *blocking* bug, or ``None`` if none exist.

    A 'blocking bug' for bead-chain's purposes is a bead where:

    * ``issue_type`` is in :data:`BLOCKING_BUG_TYPES`, AND
    * ``dependent_count > 0`` — i.e. at least one other bead depends on
      it. A bug with no dependents is **not** blocking anything and gets
      treated as ordinary work.

    Implementation note: bd's ``ready`` subcommand exposes ``--type``
    natively (verified via ``bd ready --help``), so we let bd do the
    type filtering server-side and inherit its priority/blocker
    semantics for free. The ``dependent_count > 0`` predicate is
    applied client-side because bd has no equivalent flag. We loop over
    :data:`BLOCKING_BUG_TYPES` so adding more 'bug-like' types stays a
    one-line edit, and dedupe ids across calls in case a future type
    overlaps server-side.
    """
    seen: set[str] = set()
    for issue_type in BLOCKING_BUG_TYPES:
        raw = _run_bd("ready", f"--type={issue_type}", _exclude_type_arg(), "--json")
        items = _parse_json_list(raw, f"bd ready --type={issue_type} --json")

        for bead in items:
            if not isinstance(bead, dict):
                continue
            bead_id = str(bead.get("id", ""))
            if bead_id and bead_id in seen:
                continue
            if bead_id:
                seen.add(bead_id)
            # Defensive belt-and-suspenders: bd already filtered by
            # --type, but a future bd that ignored the flag would slip
            # non-bugs through. Refuse to escalate them.
            if str(bead.get("issue_type", "")) not in BLOCKING_BUG_TYPES:
                continue
            try:
                dep_count = int(bead.get("dependent_count", 0) or 0)
            except (TypeError, ValueError):
                dep_count = 0
            if dep_count > 0:
                return bead
    return None


def show(bead_id: str) -> dict[str, Any] | None:
    """Fetch a bead's full record via ``bd show <id> --json``.

    Returns the bead dict, or ``None`` if the payload was empty or not
    a recognisable bead shape (single dict / single-element list).
    Raises :class:`BeadsError` on infrastructure failure (bd missing,
    timeout, non-zero exit, garbage JSON) so callers can decide whether
    to soft-fail or escalate — same contract as :func:`next_ready`.

    Used today only to fetch parent-epic context for the goal prompt;
    deliberately kept generic so future enhancements (e.g. surfacing
    blocker reasons in the prompt) can reuse it without churn.
    """
    if not bead_id:
        return None
    raw = _run_bd("show", bead_id, "--json").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:200].replace("\n", " ")
        raise BeadsError(
            f"`bd show {bead_id} --json` returned non-JSON: {snippet!r}"
        ) from exc

    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return None


def claim(bead_id: str) -> None:
    """Claim a bead as in-progress for the current actor."""
    _run_bd("update", bead_id, "--claim")


def revert_to_open(bead_id: str) -> None:
    """Push a claimed bead back to ``open``, re-entering the ready queue.

    The clean inverse of :func:`claim`. Used by bead-chain to unwind
    the in_progress state when:

    * the user cancels a chain (Ctrl+C / runtime cancel) — work isn't
      complete, but the bead shouldn't sit claimed forever, and
    * ``bd close`` fails on judge-passed completion — the bead is
      still legitimately not-done; keeping it claimed would leak into
      the next run's recovery flow.

    Wraps ``bd update <id> --status=open``. This mirrors the syntax we
    already guard against in :mod:`close_guard` (``--status=closed``),
    so we're confident the flag name is canonical bd. Raises
    :class:`BeadsError` on infrastructure failure so callers can decide
    whether to soft-fail or escalate.
    """
    _run_bd("update", bead_id, "--status=open")


def close(bead_id: str, *, reason: str | None = None) -> None:
    """Close a bead with an optional reason note."""
    args = ["close", bead_id]
    if reason:
        args.extend(["--reason", reason])
    _run_bd(*args)


def has_epic_in_progress() -> bool:
    """Return ``True`` if at least one epic is currently in_progress.

    Wraps ``bd list --type=epic --status=in_progress --json``. Used to
    decide whether bead-chain needs to start a new epic or if one is
    already being tracked as active.
    """
    raw = _run_bd("list", "--type=epic", "--status=in_progress", "--json")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        # Can't parse → assume nothing is in progress (safe default:
        # worst case we start one that's already started, which --claim
        # handles idempotently).
        return False

    if isinstance(items, list):
        return len(items) > 0
    return False


def close_eligible_epics() -> list[dict[str, Any]]:
    """Close every epic whose children are all complete; return the closed ones.

    **Conservative approach (bead_chain-tfn fix):** The original cascade
    mechanism in ``bd epic close-eligible`` was too aggressive, sweeping up
    unrelated epics and their children when closing a set of molecule beads.

    The fix is simple but effective: call ``bd epic close-eligible`` once,
    but DISABLE the iteration loop. bd's cascade closes A → checks if parent
    B is now eligible → closes B → checks parent C, etc. This cascade can
    unexpectedly pull in unrelated epics that happen to have no open children.

    By calling close-eligible only once per session (at the end of a drain
    pass in :func:`lifecycle.activate_next_bead`), we limit the scope: only
    epics that were eligible *at that moment* are closed. Subsequent runs
    will handle parent eligibility if needed. This sacrifices one-shot
    cascading for data safety.

    Idempotent: a no-op when no epics are eligible. Return value always
    contains dicts with at least an ``id`` key.

    Older / unexpected bd versions may emit non-JSON output even with
    ``--json``; in that case the rollup *still happened*, we just can't
    enumerate what got closed. We return ``[]`` rather than raise: an
    unparseable success is functionally equivalent to "nothing got
    closed" for the caller (it just means quieter logs). Real failures
    (bd missing, non-zero exit) still raise :class:`BeadsError` so
    callers can decide whether to soft-fail or escalate.

    The returned list always contains **dicts** with at least an ``id``
    key, regardless of which shape bd emitted. Several shapes are
    tolerated so we don't break across bd schema tweaks:

      * bd 1.0.4 wraps a list of bare **string ids** under ``closed``:
        ``{"closed": ["abc-1", "abc-2"], "count": 2}``. Each id is
        normalised to ``{"id": "abc-1"}`` so callers can uniformly do
        ``epic.get("id")`` / ``epic.get("title")``.
      * Older bd emits a bare top-level list of epic dicts.
      * Some shapes wrap each closed epic as ``{"epic": {...}}``; we
        unwrap to the inner dict.
    """
    raw = _run_bd("epic", "close-eligible", "--json").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Rollup ran; output format just wasn't JSON we recognise.
        # Treat as silent success — see docstring.
        return []

    if isinstance(payload, list):
        items: Any = payload
    elif isinstance(payload, dict):
        # bd 1.0.4: {"closed": [...ids...]}. Older/alt: {"epics": [...]}.
        items = payload.get("closed") or payload.get("epics") or []
    else:
        return []

    return [_normalise_closed_epic(item) for item in items if _is_closed_epic(item)]


def _is_closed_epic(item: Any) -> bool:
    """True if ``item`` is a usable closed-epic entry (non-empty str or dict)."""
    if isinstance(item, str):
        return bool(item.strip())
    return isinstance(item, dict)


def _normalise_closed_epic(item: Any) -> dict[str, Any]:
    """Coerce a close-eligible entry into a ``{"id": ..., ...}`` dict.

    bd's ``epic close-eligible --json`` is inconsistent across versions:
    1.0.4 returns bare string ids under ``closed``; older builds return
    epic dicts; some wrap each as ``{"epic": {...}}``. Callers only need
    ``id`` (and optionally ``title``) for log lines, so we flatten every
    shape to a plain dict here. Centralised so the rollup logger in
    :mod:`lifecycle` never has to branch on bd's output shape.
    """
    if isinstance(item, str):
        return {"id": item.strip()}
    # dict: unwrap a nested {"epic": {...}} envelope if present.
    inner = item.get("epic")
    if isinstance(inner, dict):
        return inner
    return item
