"""Read-only ``bd`` queries for bead-chain (queue waterfall + introspection).

This module is one of two domain splits carved out of the original
monolithic ``beads.py`` (bead_chain-7xv): it owns every **read** path —
the ``bd ready`` / ``bd list`` queue waterfall and the per-bead
introspection helpers (``show``, ``memories``, blocker/pin checks). Its
sibling :mod:`beads_writes` owns mutations and epic/gate housekeeping,
and :mod:`beads` keeps the shared subprocess core (``_run_bd``,
``_parse_json_list``, the classification predicates, the constants) and
re-exports both halves so existing ``from .beads import ...`` call sites
and the flat ``import beads`` test suite keep working unchanged.

Monkeypatch contract (why we route through ``_beads``)
------------------------------------------------------
The test suite does flat ``import beads`` and stubs ``beads._run_bd`` /
``beads._parse_json_list`` / ``beads.show`` by attribute assignment on
the *facade* module. For those stubs to take effect, the functions here
must look those three names up on the live ``beads`` module object at
call time (``_beads._run_bd(...)``) rather than binding a local copy at
import time. Everything else (stable constants and pure predicates that
no test patches) is imported directly for clarity.
"""

from __future__ import annotations

import json
from typing import Any

# ``_beads`` is the live facade module: the three monkeypatchable seams
# (``_run_bd``, ``_parse_json_list``, ``show``) are resolved through it so
# test stubs assigned to ``beads.<name>`` are honoured at call time. The
# try/except keeps this importable both as a package submodule (runtime)
# and flat under bare pytest. At import time ``beads`` is only partially
# initialised (its core ran first, then it imports us); that's fine — we
# touch ``_beads`` attributes only when our functions are actually called.
try:  # package context: code_puppy.plugins.bead_chain.beads_reads
    from . import beads as _beads
    from .beads import (
        BLOCKING_BUG_TYPES,
        BLOCKING_DEP_TYPES,
        IN_PROGRESS_STATUS,
        PARENT_EPIC_KEY,
        PINNED_STATUS,
        RECOVERABLE_STATUSES,
        SATISFIED_BLOCKER_STATUSES,
        _PARENT_EPIC_FALLBACK_KEYS,
        _validate_bead_id,
        BeadsError,
        is_excluded_type,
    )
except ImportError:  # flat context: bare ``import beads_reads`` under pytest
    import beads as _beads  # type: ignore[no-redef]
    from beads import (  # type: ignore[no-redef]
        BLOCKING_BUG_TYPES,
        BLOCKING_DEP_TYPES,
        IN_PROGRESS_STATUS,
        PARENT_EPIC_KEY,
        PINNED_STATUS,
        RECOVERABLE_STATUSES,
        SATISFIED_BLOCKER_STATUSES,
        _PARENT_EPIC_FALLBACK_KEYS,
        _validate_bead_id,
        BeadsError,
        is_excluded_type,
    )

__all__ = [
    "next_ready",
    "list_in_progress",
    "list_recoverable_strands",
    "next_in_progress",
    "next_ready_in_epic",
    "has_open_children",
    "extract_parent_epic_id",
    "open_blocker_ids",
    "is_blocked",
    "is_pinned",
    "next_blocking_bug",
    "show",
    "memories",
]


def next_ready() -> dict[str, Any] | None:
    """Return the top ready bead, or ``None`` if none remain.

    Honors whatever ordering ``br ready --json`` produces — we don't
    try to out-clever beads' own priority/blocker resolution.

    br variant: ``br ready`` has no ``--exclude-type`` flag, so
    container-only bead types (see ``EXCLUDED_TYPES``) are filtered out
    purely client-side via :func:`is_excluded_type` — which is now the
    sole filter (it already existed as defence-in-depth in the bd
    variant). See spike bead_chain-5d3.
    """
    raw = _beads._run_bd("ready", "--json")
    items = _beads._parse_json_list(raw, "br ready --json")
    for item in items:
        if isinstance(item, dict) and not is_excluded_type(item):
            return item
    return None


def list_in_progress() -> list[dict[str, Any]]:
    """Return **all** in_progress non-epic beads, in bd's listed order.

    Backbone for :func:`next_in_progress` (which is just the head of
    this list) and one of the two status queries :func:`list_recoverable_strands`
    merges. Both callers want the same ``br list --status=in_progress
    --json`` query, so we centralise it here. DRY.

    **Client-side epic filter (br variant).** ``br list`` has no
    ``--exclude-type`` flag, so the epic/container filter is applied
    purely client-side via :func:`is_excluded_type` — now the sole
    filter. In the bd variant this was belt-and-suspenders on top of a
    server-side flag; here it is the only line of defence, so it must
    not be removed. See spike bead_chain-5d3.

    Raises :class:`BeadsError` on infrastructure failure (bd missing,
    timeout, non-list payload, bad JSON) — same contract as the other
    list-returning helpers in this module.
    """
    return _list_by_status(IN_PROGRESS_STATUS)


def _list_by_status(*statuses: str) -> list[dict[str, Any]]:
    """Return all non-epic beads in any of ``statuses``, in bd's listed order.

    DRY core of :func:`list_in_progress` and :func:`list_recoverable_strands`:
    every stranded-work query is the same ``br list --status=<s[,s...]>
    --json`` shape with the same client-side epic re-filter. ``br list``
    has no ``--exclude-type`` flag, so :func:`is_excluded_type` is the
    sole epic filter (see spike bead_chain-5d3). Centralising it means a
    new recoverable status is a one-line edit to
    :data:`RECOVERABLE_STATUSES`.

    br's ``--status`` flag accepts a comma-separated list (``br list
    --status open,in_progress``), so **N statuses cost a single
    subprocess spawn**, not N. This is the consolidation behind
    bead_chain-lqf: ``list_recoverable_strands`` used to fan out one
    ``bd list`` call per recoverable status; it now issues exactly one.
    """
    status_arg = ",".join(statuses)
    raw = _beads._run_bd("list", f"--status={status_arg}", "--json")
    items = _beads._parse_json_list(raw, f"br list --status={status_arg} --json")
    return [
        item for item in items if isinstance(item, dict) and not is_excluded_type(item)
    ]


def list_recoverable_strands() -> list[dict[str, Any]]:
    """Return all non-epic beads stranded in a recoverable in-flight status.

    The recovery tier's eyes (FB-12 / lifecycle#2). Historically the
    chain only queried ``--status=in_progress``, so a bead flipped to
    ``hooked`` mid-flight by another agent/tool was invisible to BOTH
    ``bd ready`` (hooked is out of the ready frontier) AND recovery —
    stranded work that no run ever resumed. We now query every status in
    :data:`RECOVERABLE_STATUSES` in **one** ``bd list --status=a,b``
    subprocess call (bead_chain-lqf: the prior implementation fanned out
    one spawn per status).

    Ordering: in_progress strands come first, hooked strands follow,
    preserving the prior per-status-merge behaviour for the common case.
    Because a single comma-status call returns beads in bd's own sort
    order (not grouped by our tuple), we restore the contract with a
    *stable* client-side sort keyed on each bead's position in
    :data:`RECOVERABLE_STATUSES`. Unknown/missing statuses sort last.

    Duplicate ids are de-duped (first occurrence wins) — a bead can only
    hold one status, but bd version drift could echo one twice, and the
    one-at-a-time recovery contract must never see the same id twice.

    Epics are excluded client-side per :func:`_list_by_status` (br has
    no --exclude-type flag). Raises :class:`BeadsError` on infra failure
    — same soft-fail contract callers already expect from
    :func:`list_in_progress`.
    """
    rank = {status: i for i, status in enumerate(RECOVERABLE_STATUSES)}
    last = len(RECOVERABLE_STATUSES)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bead in _list_by_status(*RECOVERABLE_STATUSES):
        bead_id = str(bead.get("id", "")).strip()
        if bead_id and bead_id in seen:
            continue
        if bead_id:
            seen.add(bead_id)
        deduped.append(bead)

    # Stable sort keeps bd's intra-status order while restoring the
    # in_progress-before-hooked contract the per-status merge used to give.
    deduped.sort(key=lambda b: rank.get(str(b.get("status", "")).strip().lower(), last))
    return deduped


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

    Wraps ``br ready --parent=<epic_id> --json``, inheriting bd's own
    priority / blocker resolution. br's ``ready`` supports ``--parent``
    but has no ``--exclude-type`` flag, so the epic/container filter is
    applied client-side via :func:`is_excluded_type` (see
    :func:`next_ready`): epics are containers, never doable work.
    """
    if not epic_id:
        return None
    _validate_bead_id(epic_id)
    raw = _beads._run_bd("ready", f"--parent={epic_id}", "--json")
    items = _beads._parse_json_list(raw, f"br ready --parent={epic_id} --json")
    # Client-side epic filter as well — see :func:`next_ready` for why.
    for item in items:
        if isinstance(item, dict) and not is_excluded_type(item):
            return item
    return None


def has_open_children(parent_id: str) -> bool:
    """True if ``parent_id`` has at least one direct child that isn't closed.

    This is the public entry point backing the molecule fan-out gate check
    in :func:`lifecycle._has_fan_out_gate_issue`: a ``waits_for:
    children-of(spawner)`` field is satisfied only once *every* child of
    the spawner is closed, so a single still-open child means the gate is
    unsatisfied.

    br variant: no ``br list --parent``
    -----------------------------------
    The bd variant scoped this with ``bd list --parent=<id> --json`` so
    only that parent's children were fetched server-side. ``br`` has no
    ``--parent`` flag on ``list`` (verified against ``br 0.2.15``, spike
    bead_chain-5d3), and ``br ready --parent`` is *insufficient* because
    ``ready`` hides closed/in_progress children — it would report the gate
    satisfied while children are still in flight. So we fetch the full
    issue list (``br list --json``) and filter to direct children of
    ``parent_id`` client-side via the ``parent`` field. This is O(total
    issues) rather than O(children), but it is the only correct option
    against br, and the fan-out gate fires rarely.

    Soft-fails to ``False`` (treat the gate as satisfied) on any
    infrastructure error, mirroring the rest of the gate-detection path.
    """
    if not parent_id:
        return False
    _validate_bead_id(parent_id)
    try:
        raw = _beads._run_bd("list", "--json")
        children = _beads._parse_json_list(raw, "br list --json")
    except BeadsError:
        return False
    for child in children:
        if not isinstance(child, dict):
            continue
        # No server-side --parent filter on br, so the client-side
        # parent match is the *only* scoping — not just defence-in-depth.
        if child.get("parent") != parent_id:
            continue
        if child.get("status", "").lower() != "closed":
            return True
    return False


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


def open_blocker_ids(bead_id: str, bead: dict[str, Any] | None = None) -> list[str]:
    """Return the ids of ``bead_id``'s **open** work-time blockers.

    Empty list ⇒ ready to work; a non-empty list names the still-open
    issues ``bd close`` would later refuse on. Counts every inbound edge
    whose ``dependency_type`` is in :data:`BLOCKING_DEP_TYPES` and whose
    status is not in :data:`SATISFIED_BLOCKER_STATUSES`. Re-fetches via
    :func:`show` because only ``bd show --json`` carries each dep's
    *status* + *dependency_type*; pass an already-fetched record as
    ``bead`` to skip the redundant spawn.

    Soft-fails to ``[]`` on any bd blip — a transient failure must not
    strand the chain; the close-guard is the final net.

    Why it exists (recovery/version-drift defence-in-depth) and the
    distinction from the molecule fan-out-gate field:
    see ``__docs/Flows/StrandedBeadRecovery.md`` and
    ``__docs/Flows/BeadClaimAndBlockerRecheck.md``.
    """
    if not bead_id:
        return []
    _validate_bead_id(bead_id)
    if bead is None:
        try:
            # Routed through ``_beads`` so a test that stubs ``beads.show``
            # is honoured (the blocker-gate tests patch that exact seam).
            bead = _beads.show(bead_id)
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


def is_pinned(bead_id: str) -> bool:
    """True if ``bead_id``'s **live** status is ``pinned`` (FB-12 / lifecycle#1).

    Re-fetches via :func:`show` rather than trusting a cached bead dict:
    the hazard this guards against is a bead that was ``open`` when
    bead-chain claimed it but got flipped to ``pinned`` *mid-flight* by
    another agent/tool. The cached ``current_bead`` still says
    ``in_progress`` (or ``open``); only a fresh read reveals the pin.

    Why it matters: closing a ``pinned`` bead **requires ``--force``**
    (field guide §III), and bead-chain's :func:`close` never passes it.
    So a pinned bead reaching ``close()`` would fail and halt the whole
    loop — the same family of stall as the epic-close-fail hazard. The
    caller (:func:`lifecycle.close_current_bead_success`) checks this
    first and *respects the pin* (leaves it pinned, drops it as current,
    trots on) rather than force-closing a bead a human deliberately
    parked.

    Soft-fails to ``False`` (treat as not-pinned) on any infrastructure
    error: a transient bd blip must not block a legitimate close — the
    worst case is the close attempt itself surfaces the real error.
    """
    if not bead_id:
        return False
    _validate_bead_id(bead_id)
    try:
        # Routed through ``_beads`` so a test that stubs ``beads.show``
        # is honoured (the pinned-strand tests patch that exact seam).
        bead = _beads.show(bead_id)
    except BeadsError:
        return False
    if not bead:
        return False
    return str(bead.get("status", "")).strip().lower() == PINNED_STATUS


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
        raw = _beads._run_bd("ready", f"--type={issue_type}", "--json")
        items = _beads._parse_json_list(raw, f"br ready --type={issue_type} --json")

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
    _validate_bead_id(bead_id)
    raw = _beads._run_bd("show", bead_id, "--json").strip()
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


# Keys that ``bd memories --json`` emits as bookkeeping rather than as a
# real, agent-facing insight. We drop these so the goal-prompt digest is
# all signal. Currently just bd's payload version stamp; extend if bd
# starts mixing more metadata into the same object.
_NON_MEMORY_KEYS: frozenset[str] = frozenset({"schema_version"})


def memories() -> dict[str, str]:
    """Return bd's persistent memories as a ``{key: insight}`` dict.

    Bridges bd's memory layer (``bd remember`` / ``bd memories`` /
    ``bd prime``'s '## Persistent Memories' section) into bead-chain so a
    freshly-spawned working agent starts warm instead of cold
    (coverage-audit gap FB-6, ``bead_chain-ndt``).

    ``bd memories --json`` returns a JSON *object* (not a list) mapping
    each memory's key to its insight text, plus bookkeeping keys we strip
    (:data:`_NON_MEMORY_KEYS`). Non-string values are dropped defensively
    so a future bd schema change can't inject junk into the prompt.

    Insertion order (which bd emits sorted by key) is preserved so the
    digest is deterministic.

    Returns ``{}`` when bd reports no memories. Raises
    :class:`BeadsError` on infrastructure failure (bd missing, timeout,
    non-zero exit, garbage JSON, non-object payload) — same contract as
    :func:`show`, so the prompt layer can soft-fail and never stall the
    chain over a nice-to-have.
    """
    raw = _beads._run_bd("memories", "--json").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:200].replace("\n", " ")
        raise BeadsError(
            f"`bd memories --json` returned non-JSON: {snippet!r}"
        ) from exc

    if not isinstance(payload, dict):
        raise BeadsError(
            f"`bd memories --json` returned non-object payload: "
            f"{type(payload).__name__}"
        )

    out: dict[str, str] = {}
    for key, value in payload.items():
        if key in _NON_MEMORY_KEYS:
            continue
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        out[str(key)] = text
    return out
