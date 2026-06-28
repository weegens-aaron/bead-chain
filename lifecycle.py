"""Bead lifecycle helpers — the state-transition brain of bead-chain.

This module owns the *state transitions*: how to close, revert, enforce
the single-in_progress invariant, pick the next bead, and arm wiggum
for the next iteration. The companion :mod:`register_callbacks` module
owns the *wiring*: slash-command registration, hook registration,
the hook handlers themselves, CLI flag parsing.

Functions here are deliberately stateful (they mutate :mod:`state` and
shell out via :mod:`beads`) but each is self-contained — same input
state + same bd database → same output. That makes them safe to call
from any hook handler in any order without coupling to specific call
sites.

DO NOT add hook *registration* here. Hooks live in :mod:`register_callbacks`
so contributors have one obvious place to discover what bead-chain
listens to.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from code_puppy.messaging import (
    emit_info,
    emit_success,
    emit_warning,
)
from . import state

try:
    # bead-chain is a queue driver that delegates the LLM-judged completion
    # loop to wiggum's /goal mode — wiggum is a hard prerequisite (see
    # README). We still want this module to *import* cleanly when wiggum is
    # absent so the plugin loader doesn't spew a raw ImportError traceback:
    # register_callbacks gates every code path that would actually call
    # wiggum_state behind an availability check, so a None here is never
    # dereferenced. (bead_chain-c87)
    from code_puppy.plugins.wiggum import state as wiggum_state
except ImportError:  # pragma: no cover - exercised via register_callbacks
    wiggum_state = None  # type: ignore[assignment]
from .beads import BeadsError, RECOVERABLE_STATUSES, is_excluded_type
from .beads_reads import (
    extract_parent_epic_id,
    has_closed_children,
    has_open_children,
    is_pinned,
    list_recoverable_strands,
    next_blocking_bug,
    next_ready,
    next_ready_in_epic,
    open_blocker_ids,
    show,
)
from .beads_writes import (
    check_gates,
    claim,
    close,
    close_eligible_epics,
    has_epic_in_progress,
    revert_to_open,
)
from .execution_hints import apply_execution_hints
from .prompt import format_bead_as_goal

__all__ = [
    "is_recovery_bead",
    "enforce_single_in_progress",
    "close_current_bead_success",
    "rollup_completed_epics",
    "probe_resolved_gates",
    "ensure_epic_in_progress",
    "pick_next_bead",
    "activate_next_bead",
]

# Statuses that mark a picked bead as *already in flight* — i.e. residue
# from a prior run that crashed/cancelled before the LLM judges could
# rule. A bead in any of these was claimed (or hooked) but not closed,
# so bead-chain *recovers* it (re-drives with the recovery preamble)
# rather than re-claiming. Sourced from :data:`beads.RECOVERABLE_STATUSES`
# so the recovery query and the recovery-vs-fresh decision can never
# drift apart. See :func:`is_recovery_bead`.
_RECOVERY_STATUSES: frozenset[str] = frozenset(s.lower() for s in RECOVERABLE_STATUSES)


def is_recovery_bead(bead: dict[str, Any] | None) -> bool:
    """True if ``bead`` was already in flight when bead-chain picked it.

    The deliberate one-bead-at-a-time discipline means we should never
    see an in_progress (or hooked) bead at chain-start or between
    iterations — if we do, it's residue from a prior crashed/cancelled
    run, or a strand another agent left mid-flight. Centralised here so
    the recovery-mode signal stays consistent across both the startup
    path and the mid-chain pick path. DRY.

    Membership-tests against :data:`_RECOVERY_STATUSES` (case-insensitive)
    so a bead flipped to ``hooked`` mid-flight is recovered — not
    re-claimed as if it were fresh (FB-12 / lifecycle#2).
    """
    if not bead:
        return False
    return str(bead.get("status", "")).strip().lower() in _RECOVERY_STATUSES


# ---------------------------------------------------------------------------
# Startup invariant guard
# ---------------------------------------------------------------------------


def _unblocked_strands() -> list[dict[str, Any]]:
    """List the stranded in-flight non-epic beads that are *actually workable*.

    Enumerates every recoverable status (in_progress **and** hooked —
    see :data:`beads.RECOVERABLE_STATUSES`) via
    :func:`beads.list_recoverable_strands`, so a bead flipped to
    ``hooked`` mid-flight is no longer invisible to recovery (FB-12 /
    lifecycle#2).

    A stranded bead with open ``blocks`` dependencies must **never** be
    re-driven — that is the bdboard-oals bug: the recovery tier bypasses
    the ready frontier, so a bead claimed-while-ready and later
    re-blocked would get run to completion and only trip at ``bd
    close``. We refuse to perpetuate that: any blocked stranded bead is
    **reverted to open** (so it re-enters the queue behind its blockers)
    and dropped from the workable set.

    Eviction is best-effort — if the revert itself fails we log and still
    drop the bead from the workable list, so the chain never picks it up
    this pass regardless.

    Raises :class:`BeadsError` from the underlying ``bd list`` so callers
    keep the same soft-fail contract they had with
    :func:`beads.list_recoverable_strands`.
    """
    items = list_recoverable_strands()
    workable: list[dict[str, Any]] = []
    for bead in items:
        bead_id = str(bead.get("id", ""))
        blockers = open_blocker_ids(bead_id)
        if blockers:
            emit_warning(
                f"bead-chain: stranded in_progress bead {bead_id} is blocked "
                f"by open issue(s) [{', '.join(blockers)}] -- refusing to re-drive "
                "it and reverting to open (work-time blocks must be respected, "
                "not just at close-time)."
            )
            try:
                revert_to_open(bead_id)
                emit_info(f"reverted blocked {bead_id} to open")
            except BeadsError as exc:
                emit_warning(
                    f"also couldn't revert {bead_id} (still dropping it from "
                    f"this pass): {exc}"
                )
            continue
        workable.append(bead)
    return workable


def enforce_single_in_progress() -> dict[str, Any] | None:
    """Pick the head in_progress bead for recovery; leave the rest alone.

    The chain's contract is *one bead at a time*. Multiple in_progress
    beads should be impossible if the cancel hook and close-failure
    paths do their job — but hard crashes (SIGKILL, power loss, OS
    reboot) bypass every Python-level handler, and old sessions may
    have left residue.

    Behavior:

      * Zero in_progress beads → return ``None`` (clean slate; startup
        will pick a fresh ready bead).
      * One in_progress bead → return it (normal recovery).
      * More than one → return the head, **leave the rest in_progress**,
        and emit a warning so the user knows. The extras will be
        recovered one-at-a-time on subsequent iterations within this
        same run via :func:`pick_next_bead`'s tier-0 recovery branch.
        This preserves the work-paired-with-its-bead invariant: every
        in_progress bead represents real partial work on disk that the
        agent must assess via the recovery preamble before doing more.

    Beads with open work-time blockers are filtered out (and reverted
    to open) by :func:`_unblocked_strands` before any of the above
    — a blocked stranded bead is never recovered/re-driven (bdboard-oals).

    Soft-fails by design: a bd outage here shouldn't block the chain
    from running. If listing fails we emit a warning and return
    ``None``, letting the normal startup probe handle whatever it can
    see.
    """
    try:
        items = _unblocked_strands()
    except BeadsError as exc:
        emit_warning(
            f"🔗 bead-chain: couldn't enumerate in_progress beads ({exc}); "
            "continuing without invariant check."
        )
        return None

    if not items:
        return None
    if len(items) == 1:
        return items[0]

    head = items[0]
    extras = items[1:]
    extra_ids = [str(b.get("id", "?")) for b in extras]
    head_id = str(head.get("id", "?"))
    emit_warning(
        f"⚠️ bead-chain: found {len(items)} in_progress beads (residue from "
        f"a hard crash or pre-fix session). Recovering {head_id} first; "
        f"the rest will be picked up one-at-a-time via the recovery tier: "
        f"{', '.join(extra_ids)}"
    )
    return head


# ---------------------------------------------------------------------------
# Close current + rollup
# ---------------------------------------------------------------------------

# bd refuses to close a bead that still has open blockers, surfacing a
# message containing "blocked by open issue(s)" (the "(s)" is grammatical
# pluralisation, so we key off the singular stem). bead-chain's
# :func:`beads._run_bd` wraps that stderr verbatim into the BeadsError
# string, so a substring match against ``str(exc)`` is the authoritative
# (if string-keyed) signal. We keep the match deliberately NARROW: on any
# miss we degrade to the historical halt-loudly behavior, which is safe —
# never silent. See ADR 0004
# (notes/decisions/0004-close-failure-blocked-is-recoverable.md).
_BLOCKED_CLOSE_MARKER: str = "blocked by open issue"


def _is_blocked_close_error(exc: BeadsError) -> bool:
    """True iff ``exc`` is bd's *recoverable* "blocked by open issues" refusal.

    This distinguishes the one **recoverable** close-failure class — a
    blocker (typically a bug filed via the Bug Discovery Protocol with
    ``--blocks=<this bead>``) is still open, so bd won't let us close —
    from every other (infra-class) BeadsError, which must still halt the
    chain loudly. Narrow by design: an unrecognised message returns
    ``False`` and the caller falls back to the safe halt path.
    """
    return _BLOCKED_CLOSE_MARKER in str(exc).lower()


def close_current_bead_success() -> dict[str, Any] | None:
    """Close the bead we were just working on, if any.

    Returns the **just-closed bead dict** (or ``None`` if there was no
    current bead) so the caller can use fields like the parent epic
    when picking the next bead — see :func:`activate_next_bead`.
    Whether the ``bd close`` call succeeded or not, the returned dict
    still represents the bead we were working on; that's the right
    signal for epic-affinity routing (we *intended* to finish that
    epic's work).

    **Close-failure handling.** If ``bd close`` raises, we split on the
    error class (ADR 0004 — *a "blocked by open issues" close failure is
    recoverable, not a chain-halt*):

      * **Recoverable — "blocked by open issue(s)".** bd refused because
        a blocker is still open, typically a bug filed *during this
        bead's own run* with ``--blocks=<this bead>`` per the Bug
        Discovery Protocol. That is a documented, self-healing state,
        not a fault. We :func:`revert_to_open` the bead, clear
        ``current_bead``, and **continue** the chain. The next
        iteration's tier-0 (``_unblocked_strands``) and tier-1
        (blocking-bug routing) machinery drives the blocker first, then
        re-drives this bead — the recovery net that already exists.
        Detected narrowly via :func:`_is_blocked_close_error`; if the
        revert itself fails, that *is* infra-class and we fall through
        to the halt path below.
      * **Infra-class — everything else** (bd outage, permission issue,
        schema drift). We **leave the bead in_progress** (reverting
        would orphan partial work — the next ``bd ready`` could hand us
        a different bead and the half-done changes would silently attach
        to no tracked work) and **stop the chain**. Staying in_progress
        means the next ``/bead-chain`` run's recovery tier picks it up
        and re-prompts with the recovery preamble, so the agent
        assesses the current state before doing anything new. Halt
        loudly rather than barreling on.

    The caller distinguishes the success vs. failure case by checking
    ``state.is_active()`` after the call: if False, the chain was
    stopped here and the caller should bail without claiming another
    bead. (A recoverable blocked-close revert leaves the chain *active*,
    so the caller proceeds to pick the next bead as usual.)
    """
    just_closed = state.get_state().current_bead
    if not just_closed:
        return None
    bead_id = state.get_state().current_bead_id or ""

    # Last-line-of-defence assertion: bead-chain must never attempt to
    # close a container bead (epic, etc.). The server-side filter and
    # the client-side filter in :func:`beads.list_in_progress` /
    # :func:`beads.next_ready` should both have caught this upstream,
    # but if *both* failed and an epic somehow reached current_bead,
    # ``bd close`` would fail with 'open child issue(s)' and halt the
    # chain anyway — we may as well refuse here with a clearer message
    # AND revert the epic so it doesn't sit incorrectly in_progress.
    #
    # Why revert here but NOT on a normal close-failure? Two reasons:
    #   1. An in_progress epic is categorically broken (epics are
    #      containers, never doable work). Leaving it stranded would
    #      silently corrupt ``bd status`` displays.
    #   2. The tier-0 recovery path in :func:`pick_next_bead` reads
    #      :func:`_unblocked_strands` (which wraps
    #      :func:`beads.list_recoverable_strands`), and that query filters epics
    #      out via ``--exclude-type=epic``. So a stranded epic would
    #      never be picked up by the recovery preamble flow — it would
    #      just sit there forever. Reverting is the only path to sanity.
    if is_excluded_type(just_closed):
        emit_warning(
            f"🚫 bead-chain refused to close {bead_id}: it's an excluded "
            f"container type ({just_closed.get('issue_type', '?')}). "
            "An upstream filter leaked an epic into the chain — this is a bug."
        )
        try:
            revert_to_open(bead_id)
            emit_info(f"🔄 reverted {bead_id} to open")
        except BeadsError as revert_exc:
            emit_warning(f"🔗 also couldn't revert {bead_id}: {revert_exc}")
        emit_warning(
            "🔗 bead-chain stopping after epic-leak detection — "
            "investigate before re-running."
        )
        state.stop()
        state.get_state().current_bead = None
        return just_closed

    # Mid-flight pin guard (FB-12 / lifecycle#1). bead-chain claims a
    # bead while it's open, but another agent/tool can flip it to
    # ``pinned`` *after* the claim. Closing a pinned bead REQUIRES
    # ``--force`` (field guide §III), which :func:`beads.close` never
    # passes — so a pinned bead reaching close() would fail and halt the
    # whole loop (same stall family as the epic-close-fail hazard). We
    # re-read the live status here and, if it's been pinned, *respect
    # the pin*: a human deliberately parked this bead to stay open
    # indefinitely, so force-closing it would override that intent.
    # Instead we drop it as the current bead and trot on — the chain
    # keeps moving and the pin stands. The bead won't be re-picked
    # (``bd ready`` and recovery both exclude ``pinned``), so this can't
    # loop. We do NOT bump_completed: nothing was closed.
    if is_pinned(bead_id):
        emit_warning(
            f"bead {bead_id} was pinned mid-flight -- respecting the pin "
            "(closing a pinned bead needs --force, which bead-chain won't "
            "do over a human's explicit park). Leaving it pinned and moving "
            "on; the chain keeps trotting."
        )
        state.get_state().current_bead = None
        return just_closed

    try:
        close(bead_id, reason="bead-chain: LLM judges passed")
    except BeadsError as exc:
        # Two distinct error classes hide behind one BeadsError (ADR 0004):
        #
        #   1. RECOVERABLE — bd refused because a blocker is still open
        #      (e.g. a bug filed mid-run with --blocks=<this bead> per the
        #      Bug Discovery Protocol). This is a documented, self-healing
        #      state, NOT a fault: revert the bead to open and let the next
        #      iteration's tier-0 (_unblocked_strands) + tier-1
        #      (blocking-bug routing) machinery drive the blocker first and
        #      re-drive this bead afterwards. The chain CONTINUES.
        #
        #   2. INFRA — anything else (bd outage, permission, schema drift).
        #      Genuinely wrong: halt loudly, exactly as before.
        if _is_blocked_close_error(exc):
            emit_info(
                f"🔗 bead-chain can't close {bead_id} yet — it's blocked by an "
                "open issue (likely a bug filed during this run). This is "
                "recoverable, not a fault: reverting to open so the next "
                "iteration drives the blocker first, then re-drives this bead."
            )
            try:
                revert_to_open(bead_id)
            except BeadsError as revert_exc:
                # A failed revert IS infra-class — fall back to the safe
                # halt path rather than leaving the bead wedged in_progress.
                emit_warning(
                    f"🔗 bead-chain couldn't revert {bead_id} after a blocked "
                    f"close: {revert_exc}. Halting; investigate before "
                    "re-running."
                )
                state.stop()
                return just_closed
            emit_info(
                f"🔄 reverted {bead_id} to open — when it's re-driven, prior "
                "work may already satisfy the acceptance criteria; verify "
                "before redoing it to avoid burning tokens on a needless redo."
            )
            state.get_state().current_bead = None
            return just_closed

        emit_warning(f"🔗 bead-chain couldn't close {bead_id}: {exc}")
        # Leave the bead in_progress on purpose — see docstring.
        # The next /bead-chain run will recover it via tier-0 and
        # re-prompt with the recovery preamble so the agent assesses
        # current state (which may already satisfy the judges) before
        # doing any new work.
        emit_warning(
            f"🔖 Bead {bead_id} left in_progress — the next /bead-chain run "
            "will resume it with a recovery preamble. Stopping chain now; "
            "investigate the close failure before re-running."
        )
        state.stop()
        # Note: deliberately NOT clearing current_bead here. The chain
        # is stopping; the field gets cleared on the next start() call.
        return just_closed
    else:
        n = state.get_state().bump_completed()
        emit_success(f"🔗 bead-chain closed {bead_id} (#{n} completed this run)")
        state.get_state().current_bead = None
    return just_closed


def rollup_completed_epics() -> None:
    """Auto-close any epics whose children are now all complete.

    Called **once per session** when the queue is empty (drain pass in
    :func:`activate_next_bead`), NOT after every individual child close.
    This is mitigation for the over-close bug (bead_chain-tfn): bd's
    ``epic close-eligible`` cascade can unexpectedly close unrelated
    epics if called too frequently. By calling once-per-session, we
    dramatically reduce the surface for unintended side effects.

    bd handles cascades natively: closing epic A's last child may make
    A's parent epic B eligible too, and one call rolls both up.

    **Soft-fails by design.** Epic rollup is a courtesy cleanup, not
    bead-chain's core mission. A flaky/missing/old ``bd epic`` should
    log a warning and let the chain keep trotting — losing a rollup
    pass is way less bad than stranding the user's queue.
    """
    try:
        closed = close_eligible_epics()
    except BeadsError as exc:
        emit_warning(f"🎯 bead-chain: epic rollup failed (continuing): {exc}")
        return
    for epic in closed:
        epic_id = str(epic.get("id", "<unknown>"))
        title = str(epic.get("title", "")).strip()
        suffix = f" — {title}" if title else ""
        emit_success(f"🎯 epic {epic_id} rolled up (all children complete){suffix}")


def probe_resolved_gates() -> bool:
    """Re-evaluate open gates on an empty queue; report if any resolved.

    Called once from :func:`activate_next_bead` the moment ``bd ready``
    comes back empty, *before* the chain declares itself done. Resolvable
    gate types (``timer`` / ``gh:run`` / ``gh:pr`` / ``bead``) keep their
    target issues out of ``bd ready`` until the gate closes, and nothing
    else in bead-chain ever pokes them. So an empty queue might really be
    a queue waiting on a now-satisfied gate — we ask bd to close those
    and re-open their targets for the next pick.

    Returns ``True`` if at least one gate resolved (the caller should
    re-probe ``bd ready`` rather than stop), ``False`` otherwise.

    **Soft-fails by design.** Like :func:`rollup_completed_epics`, this
    is a courtesy nudge, not bead-chain's core mission. A flaky / missing
    / old ``bd gate`` logs a warning and returns ``False`` so the chain
    finishes its drain cleanly — losing a gate probe is far less bad than
    halting the loop.
    """
    try:
        counts = check_gates()
    except BeadsError as exc:
        emit_warning(f"⏳ bead-chain: gate check failed (continuing): {exc}")
        return False

    resolved = counts.get("resolved", 0)
    escalated = counts.get("escalated", 0)
    if resolved:
        emit_success(
            f"⏳ {resolved} gate(s) resolved on the empty-queue probe — "
            "re-opening their targets and re-checking for ready work."
        )
    if escalated:
        emit_warning(
            f"⏳ {escalated} gate(s) escalated (expired/failed) during the "
            "empty-queue probe — these need a human look."
        )
    return bool(resolved)


# ---------------------------------------------------------------------------
# Epic / bead claim helpers
# ---------------------------------------------------------------------------


def ensure_epic_in_progress(bead: dict[str, Any] | None) -> None:
    """If no epic is in_progress, claim ``bead``'s parent epic.

    Called whenever bead-chain has just claimed a new child bead — at
    chain startup and from inside :func:`activate_next_bead`. The goal
    is to give humans (and dashboards) a true "what is bead-chain
    working on" signal: the in_progress epic must be the parent of the
    bead actually in flight, not whatever happened to top ``bd ready
    --type=epic``.

    When the active bead has no parent epic, we no-op rather than
    guessing — surfacing no epic beats surfacing the wrong one.

    **Soft-fails by design.** This is a courtesy status update, not a
    gate — if bd is flaky we log and keep trotting. Never stalls the
    chain.
    """
    if not bead:
        return

    epic_id = extract_parent_epic_id(bead)
    if not epic_id:
        # Bead is a top-level item with no parent epic. Deliberately
        # do nothing rather than guess.
        return

    try:
        if has_epic_in_progress():
            return
    except BeadsError as exc:
        emit_warning(
            f"🎯 bead-chain: epic in-progress check failed (continuing): {exc}"
        )
        return

    # Try to enrich the log line with the epic's title. Pure cosmetics —
    # any failure here is silently swallowed, the claim still proceeds.
    title = ""
    try:
        epic = show(epic_id)
    except BeadsError:
        epic = None
    if epic:
        title = str(epic.get("title", "")).strip()

    try:
        claim(epic_id)
    except BeadsError as exc:
        emit_warning(
            f"🎯 bead-chain: couldn't start epic {epic_id} (continuing): {exc}"
        )
        return

    suffix = f" — {title}" if title else ""
    emit_info(f"🎯 bead-chain started epic {epic_id}{suffix}")


# ---------------------------------------------------------------------------
# Next-bead waterfall + activation
# ---------------------------------------------------------------------------


def pick_next_bead(
    just_closed: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Choose the next bead via a strict four-tier waterfall.

    Priority order (highest first):

    0. **Stranded in_progress bead.** If any non-epic bead is already
       in_progress, a previous run errored or was cancelled before the
       judges could close it. Recovery beats every other rule — the
       one-bead-at-a-time discipline means there can only be one in
       flight, so we must finish (or formally close) this one before
       starting anything new.
    1. **Blocking bug.** Any ready bug with ``dependent_count > 0`` —
       fixing it unblocks downstream work, so it always cuts the line.
    2. **Epic affinity.** If ``just_closed`` had a parent epic and that
       epic still has ready siblings, claim one of those. Coherent
       commits and PRs beat queue-order optimality (the 'finish what
       you start' rule).
    3. **Global ready queue.** Whatever bd hands us next.

    Beads with open work-time blockers are never returned: tier 0
    reverts+drops blocked stranded beads via :func:`_unblocked_strands`,
    and tiers 1-3 (which come from ``bd ready`` and so *should* already
    be unblocked) get a belt-and-suspenders :func:`beads.is_blocked`
    recheck — defence-in-depth against bd version drift, mirroring the
    epic ``--exclude-type`` filter. This is the bdboard-oals fix: the
    chain respects blocks at claim/start time, not just at close.

    Raises :class:`BeadsError` on infrastructure failure so the caller
    can stop the chain cleanly.

    .. note:: **Pick-then-activate race (bead_chain-hvi).** The bead this
       returns is read from the ready queue, not yet claimed. Another
       agent can claim it in the window before
       :func:`activate_next_bead` calls ``claim()``. That race is a known,
       accepted limitation; see the ``KNOWN RACE`` comment at the
       ``claim()`` call site for the window, the BeadsError mitigation,
       and why a distributed lock is not warranted.
    """
    workable = _unblocked_strands()
    if workable:
        stranded = workable[0]
        bead_id = str(stranded.get("id", "<unknown>"))
        emit_warning(
            f"bead-chain: found stranded in_progress bead {bead_id} -- "
            "recovering before picking new work."
        )
        return stranded

    blocking = next_blocking_bug()
    if blocking is not None and not _reject_if_blocked(blocking, "blocking bug"):
        bead_id = str(blocking.get("id", "<unknown>"))
        emit_info(f"bead-chain: blocking bug detected -> prioritising {bead_id}")
        return blocking

    epic_id = extract_parent_epic_id(just_closed)
    if epic_id:
        sibling = next_ready_in_epic(epic_id)
        if sibling is not None and not _reject_if_blocked(sibling, "epic affinity"):
            emit_info(f"bead-chain: epic affinity -> staying inside {epic_id}")
            return sibling

    nxt = next_ready()
    if nxt is not None and _reject_if_blocked(nxt, "global ready"):
        return None
    return nxt


def _reject_if_blocked(bead: dict[str, Any] | None, tier: str) -> bool:
    """True (and warn) if ``bead`` has open work-time blockers.

    Defence-in-depth for the non-recovery tiers, which source beads
    from ``bd ready`` (server-side blocker-filtered) and so should
    never be blocked. If one ever is — bd version drift, a ``blocks``
    edge wired between the ``ready`` query and now — we refuse to drive
    it rather than barrel into the close-time failure (bdboard-oals).
    """
    if not bead:
        return False
    bead_id = str(bead.get("id", ""))
    blockers = open_blocker_ids(bead_id)
    if not blockers:
        return False
    emit_warning(
        f"bead-chain: {tier} candidate {bead_id} has open blocker(s) "
        f"[{', '.join(blockers)}] -- refusing to claim it (bd ready leaked a "
        "blocked bead; respecting work-time blocks anyway)."
    )
    return True


def activate_next_bead(
    just_closed: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Pick the next ready bead, claim it, arm wiggum goal mode.

    If ``just_closed`` is provided and had a parent epic, we prefer the
    next ready bead under that same epic before falling back to the
    global ``bd ready`` queue — see :func:`pick_next_bead`.

    Returns the continuation dict for the runner, or ``None`` if we
    ran out of beads / hit an infrastructure error / hit the
    ``--max=N`` safety cap (in which case we've already stopped
    ourselves and emitted a message).
    """
    # Safety brake: stop before we even look at the queue if the
    # next activation would push us past the user-set cap. We check
    # *before* picking a bead so we don't waste a `bd ready` call.
    # NB: we do NOT close the current bead here — judges already
    # closed it in the previous turn (via close_current_bead_success)
    # before this iteration began.
    s = state.get_state()
    if s.max_iterations is not None and s.completed_count + 1 > s.max_iterations:
        emit_success(
            f"🛑 bead-chain: --max={s.max_iterations} cap reached "
            f"(closed {s.completed_count} bead(s) this run). Stopping. Good boy!"
        )
        state.stop()
        return None

    try:
        bead = pick_next_bead(just_closed)
    except BeadsError as exc:
        emit_warning(f"🔗 bead-chain stopping — `bd ready` failed: {exc}")
        state.stop()
        return None

    if bead is None:
        # Empty-queue gate probe (bead_chain-x3g / FB-3): before we declare
        # the chain done, ask bd to re-evaluate every open gate. Resolvable
        # gate types (timer / gh:run / gh:pr / bead) keep their targets out
        # of `bd ready` until the gate closes, and nothing else in
        # bead-chain pokes them — so an "empty" queue might just be waiting
        # on a now-satisfied gate. If any gate resolves, its target re-opens
        # and we re-probe the ready queue for one more iteration. Soft-fails
        # (see probe_resolved_gates) so a flaky `bd gate` never halts us.
        if probe_resolved_gates():
            try:
                bead = pick_next_bead(just_closed)
            except BeadsError as exc:
                emit_warning(f"🔗 bead-chain stopping — `bd ready` failed: {exc}")
                state.stop()
                return None

    if bead is None:
        # Drain pass: at session end, sweep any epics whose final child we
        # just closed. Per bead_chain-tfn (over-close bug fix), we call
        # rollup_completed_epics() ONLY HERE at the end of a session
        # (when the queue is empty), NOT after every individual bead close.
        #
        # Rationale: bd's ``epic close-eligible`` command runs a server-side
        # cascade: closing A's last child closes A, then checks if A's parent
        # B is now eligible, closes B, checks parent C, etc. When called
        # per-bead (after EVERY close), this cascade can unexpectedly close
        # unrelated epics that happen to have no open children.
        #
        # Fix: Calling it once per session limits the cascade to a single
        # pass at the end. This is mitigation (not prevention) — the cascade
        # still exists in bd, but is called far less frequently, reducing the
        # surface for unintended side effects. Parent epics may close one
        # session later, but data safety is preserved.
        #
        # See register_callbacks._on_interactive_turn_end for the detailed
        # explanation and the call-site of the per-bead rollup removal.
        rollup_completed_epics()
        emit_success(
            f"bead-chain: no more ready beads. "
            f"Closed {state.get_state().completed_count} this run. Good boy!"
        )
        state.stop()
        return None

    # Last-line-of-defence assertion: the picker is *not allowed* to
    # return a container bead (epic). All four tiers filter epics out
    # both server-side (``--exclude-type=epic``) and client-side via
    # :func:`is_excluded_type`. If one slipped through anyway, refuse
    # to arm wiggum with it — driving wiggum at an epic causes the
    # 'cannot close epic: N open child issue(s)' failure we hit in
    # prod, and halts the chain after wasted token spend.
    if is_excluded_type(bead):
        bead_id = str(bead.get("id", "<unknown>"))
        emit_warning(
            f"🚫 bead-chain refused to activate {bead_id}: it's an excluded "
            f"container type ({bead.get('issue_type', '?')}). "
            "An upstream filter leaked an epic into the chain — this is a bug."
        )
        state.stop()
        return None

    bead_id = str(bead.get("id", ""))
    recovery = is_recovery_bead(bead)

    # Call consolidation (bead_chain-lqf): both the work-time blocker
    # guard and the fan-out gate guard below need this bead's FULL
    # ``bd show`` record (the ``bd ready`` / ``bd list`` dict the picker
    # handed us lacks per-dependency status and the ``waits_for`` field).
    # We fetch it ONCE here and thread it into both checks rather than
    # letting each spawn its own identical ``bd show``. One fresh read at
    # the activation boundary preserves the mid-flight-mutation safety
    # (pinned/re-blocked detection) the two guards were written for, at
    # one subprocess instead of two. Soft-fails to ``None`` so the
    # guards fall back to their own fetch / safe defaults on a bd blip.
    try:
        full_bead = show(bead_id)
    except BeadsError:
        full_bead = None

    # Last-line-of-defence assertion: the picker is *not allowed* to
    # return a bead with open work-time blockers. Tier 0 reverts+drops
    # them; tiers 1-3 reject them via :func:`_reject_if_blocked`. If one
    # still reached here (e.g. a ``blocks`` edge wired in the moment
    # between pick and activate), refuse to claim/drive it rather than
    # running blocked work that ``bd close`` will later reject. This is
    # the bdboard-oals fix mirrored at the activation boundary. Recovery
    # beads are exempt from the revert path here (they were already
    # blocker-filtered in :func:`_unblocked_strands`); we just stop
    # if somehow one is blocked, leaving it in_progress for inspection.
    blockers = open_blocker_ids(bead_id, full_bead)
    if blockers:
        emit_warning(
            f"bead-chain refused to activate {bead_id}: it has open "
            f"blocker(s) [{', '.join(blockers)}]. Respecting work-time blocks "
            "at claim time, not just at close. Stopping chain."
        )
        if not recovery:
            try:
                revert_to_open(bead_id)
                emit_info(f"reverted {bead_id} to open")
            except BeadsError as exc:
                emit_warning(f"also couldn't revert {bead_id}: {exc}")
        state.stop()
        return None

    # WORKAROUND (bead_chain-9sc): Check for unsatisfied fan-out gates.
    # Beads with waits_for: children-of(...) are invisible to bd blocked,
    # so we detect and refuse to claim them here. Reuses ``full_bead``
    # fetched above (bead_chain-lqf) so we don't re-spawn ``bd show``.
    fan_out = _fan_out_gate_verdict(bead_id, full_bead)
    if fan_out.blocked:
        emit_warning(
            f"bead-chain refused to activate {bead_id}: it has an unsatisfied "
            "fan-out gate (waits_for: children-of(...) with unclosed spawned "
            "children). Stopping chain to avoid driving work that isn't ready yet."
        )
        # FB-13 (bead_chain-y0s): only revert when bd actually surfaced the
        # aggregation mode. When the mode is unknown, the gate *might* be
        # ``any-children`` and already satisfied — reverting would strand
        # that otherwise-ready waiter at ``open``. So we still stop the
        # chain (conservative refusal) but leave the bead in_progress for a
        # human to inspect, rather than wrongly flipping it back.
        if not recovery:
            if fan_out.mode_known:
                try:
                    revert_to_open(bead_id)
                    emit_info(f"reverted {bead_id} to open")
                except BeadsError as exc:
                    emit_warning(f"also couldn't revert {bead_id}: {exc}")
            else:
                emit_info(
                    f"leaving {bead_id} in_progress (fan-out aggregation mode "
                    "unknown — skipping revert so an any-children waiter that "
                    "is already ready is not stranded at open)"
                )
        state.stop()
        return None

    # Walk the hierarchy top-down: claim the parent epic FIRST, then
    # the child bead. bd's UI caches per-parent children-by-status
    # views, so flipping a leaf to in_progress under a still-open
    # parent produces a stale tree until the user navigates back to
    # the parent. Going parent-first keeps the hierarchy consistent
    # at every observable moment. Soft-fails internally — never
    # blocks the chain.
    ensure_epic_in_progress(bead)

    if not recovery:
        # KNOWN RACE — pick-then-activate (bead_chain-hvi):
        # There is an unavoidable window between pick_next_bead() reading
        # the ready queue (`bd ready` / `bd list`) and this claim() call
        # flipping the bead to in_progress. In that gap a *different* agent
        # — another bead-chain on another machine, a human in the bd UI,
        # CI — can claim the very same bead. pick/claim is read-then-write,
        # not a single atomic compare-and-swap, so two drivers can both see
        # the bead "ready" and race for it.
        #
        # MITIGATION (sufficient, by design): the claim is the serializing
        # point. bd's `update --claim` is atomic at the database layer, so
        # at most one racer wins; the loser's claim() raises BeadsError
        # (the bead is no longer claimable in the state it expected). We
        # catch that here, warn, and stop the chain cleanly rather than
        # double-driving a bead someone else owns. No work is lost or
        # duplicated — the winner drives it, the loser backs off. Worst
        # case is one wasted `bd ready` + `bd show` round-trip on the loser.
        #
        # WHY NO DISTRIBUTED LOCK: closing the window entirely would need a
        # cross-process/cross-machine lock (lease, advisory lock, CAS token)
        # spanning pick→claim. That's a large amount of distributed-systems
        # machinery (lock store, lease renewal, crash-recovery for orphaned
        # locks) to defend against a sub-second window whose only failure
        # mode is already handled gracefully by the claim-fails-→-stop path.
        # The race is rare (it requires two drivers targeting the same bead
        # in the same instant), self-healing (the loser simply stops), and
        # harmless (no corruption). YAGNI: the atomic claim *is* the lock we
        # need; a second locking layer would be redundant complexity.
        try:
            claim(bead_id)
        except BeadsError as exc:
            emit_warning(f"🔗 bead-chain couldn't claim {bead_id}: {exc} — stopping.")
            state.stop()
            return None
    # Recovery beads are already in_progress — skip the redundant claim
    # call (see handle_bead_chain_command for the same rationale).

    state.get_state().current_bead = bead

    # FB-8 (bead_chain-9n3): apply the bead's recognized execution_*
    # metadata hints (effort/model/agent_type) to the serial drive before
    # arming wiggum. Soft-fails per hint; no-op when none are present.
    applied_hints = apply_execution_hints(bead)
    if applied_hints:
        emit_info(f"\U0001f9ea execution hints: {'; '.join(applied_hints)}")

    goal_prompt = format_bead_as_goal(bead, recovery=recovery)

    # Hand the wheel to wiggum's /goal loop for the next N turns.
    wiggum_state.start(goal_prompt, mode="goal")

    action = "recovered" if recovery else "claimed"
    emit_info(f"🔗 bead-chain {action} {bead_id} — {bead.get('title', '')}")
    return {
        "prompt": goal_prompt,
        "clear_context": True,
        "delay": 0.5,
        "reason": "bead_chain",
    }


# ---------------------------------------------------------------------------
# Molecule fan-out gate aggregation mode (FB-13, bead_chain-y0s)
# ---------------------------------------------------------------------------
# A ``waits_for: children-of(spawner)`` gate can aggregate its spawned
# children two ways:
#   * ``all-children`` — satisfied only once EVERY child is closed.
#   * ``any-children`` — satisfied the moment the FIRST child closes.
# bd accepts ``--waits-for-gate {all-children,any-children}`` at *write*
# time but, through at least bd 1.0.5, does NOT surface the chosen mode in
# ``bd show --json`` / ``bd dep list`` — the mode is write-only. So today
# :func:`_fan_out_gate_mode` resolves to ``None`` (unknown) in practice;
# the plumbing below *honors* the mode the instant bd starts exposing it,
# with no further bead-chain change.
_FAN_OUT_MODE_ALL = "all-children"
_FAN_OUT_MODE_ANY = "any-children"

# Top-level ``bd show`` record keys that *might* carry the aggregation mode
# once bd surfaces it. Ordered most-likely-first; every one is a cheap
# dict lookup, so listing a few candidate spellings costs nothing and
# future-proofs against bd's eventual field name.
_FAN_OUT_MODE_KEYS: tuple[str, ...] = (
    "waits_for_gate",
    "waits_for_mode",
    "fan_out_mode",
    "gate_mode",
)

# Keys to probe inside each ``dependencies`` array entry, in case bd
# surfaces the mode on the dependency edge rather than the bead.
_FAN_OUT_DEP_MODE_KEYS: tuple[str, ...] = (
    "waits_for_gate",
    "gate",
    "gate_mode",
    "mode",
    "aggregation",
)


def _normalize_fan_out_mode(raw: Any) -> str | None:
    """Map a raw mode token to a canonical mode constant, or ``None``.

    Tolerant of spelling drift (``any`` / ``any-children`` / ``any_child``)
    so we honor whatever shape bd eventually emits. Anything unrecognised
    (including non-strings) reads as ``None`` — unknown, never a guess.
    """
    if not isinstance(raw, str):
        return None
    token = raw.strip().lower().replace("_", "-")
    if token in ("any", "any-child", "any-children"):
        return _FAN_OUT_MODE_ANY
    if token in ("all", "all-child", "all-children"):
        return _FAN_OUT_MODE_ALL
    return None


def _fan_out_gate_mode(bead: dict[str, Any] | None) -> str | None:
    """Resolve a fan-out gate's aggregation mode from a ``bd show`` record.

    Returns ``_FAN_OUT_MODE_ALL``, ``_FAN_OUT_MODE_ANY``, or ``None``
    (unknown). Checks the plausible top-level keys first, then any
    per-edge ``dependencies`` entries. Today (bd ≤ 1.0.5) the mode is
    write-only and this returns ``None`` for every real bead — that's the
    expected, documented state, not a bug. The verdict layer treats
    ``None`` as 'do not revert' so an otherwise-ready *any-children*
    waiter is never wrongly flipped back to open.
    """
    if not bead:
        return None
    for key in _FAN_OUT_MODE_KEYS:
        mode = _normalize_fan_out_mode(bead.get(key))
        if mode is not None:
            return mode
    deps = bead.get("dependencies")
    if isinstance(deps, list):
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            for key in _FAN_OUT_DEP_MODE_KEYS:
                mode = _normalize_fan_out_mode(dep.get(key))
                if mode is not None:
                    return mode
    return None


class _FanOutGateVerdict(NamedTuple):
    """Outcome of evaluating a bead's molecule fan-out gate.

    ``blocked``
        The gate is unsatisfied, so the bead must not be driven yet.
    ``mode_known``
        bd surfaced the aggregation mode, so a revert-to-open is safe.
        When the mode is unknown we *refuse* (stop) but deliberately
        *skip the revert*: an unknown gate might be ``any-children`` and
        already satisfied, and reverting would strand that ready waiter
        at ``open`` (FB-13 acceptance criterion #1).
    """

    blocked: bool
    mode_known: bool


# Canonical 'no gate / nothing to do' verdict. ``mode_known=True`` is
# inert here (no revert happens when ``blocked`` is False) but keeps the
# 'unknown ⇒ skip revert' signal meaningful only for real, blocked gates.
_NO_FAN_OUT_GATE = _FanOutGateVerdict(blocked=False, mode_known=True)


def _fan_out_gate_verdict(
    bead_id: str, bead: dict[str, Any] | None = None
) -> _FanOutGateVerdict:
    """Evaluate ``bead_id``'s molecule fan-out gate, honoring its mode.

    Beads with ``waits_for: children-of(spawner)`` are invisible to
    ``bd blocked`` (bead_chain-9sc upstream bug), so bead-chain evaluates
    the gate itself at claim time. The verdict honors the aggregation
    mode (FB-13, bead_chain-y0s):

    * **any-children** — unsatisfied only while *no* child has closed yet;
      satisfied the moment the first child closes.
    * **all-children** — unsatisfied while *any* child is still open
      (the historic, hardcoded behavior).
    * **unknown** (bd doesn't surface the mode) — evaluated with the
      conservative all-children rule for the *block* decision, but flagged
      ``mode_known=False`` so the caller skips the destructive revert.

    Call consolidation (bead_chain-lqf): pass an already-fetched
    ``bd show`` record as ``bead`` to avoid a redundant spawn. The
    spawner lookup is always a separate ``bd show`` — a different bead.

    Soft-fails to :data:`_NO_FAN_OUT_GATE` (not blocked) on any bd blip or
    malformed input, preserving the gate-detection path's fail-safe-open
    discipline.
    """
    if not bead_id:
        return _NO_FAN_OUT_GATE

    if bead is None:
        try:
            bead = show(bead_id)
        except BeadsError:
            # Can't determine gate status; assume no gate issue.
            return _NO_FAN_OUT_GATE
    if not bead:
        return _NO_FAN_OUT_GATE

    # Check for waits_for field.
    waits_for = bead.get("waits_for")
    if not waits_for or not isinstance(waits_for, str):
        return _NO_FAN_OUT_GATE

    # Check if it's a fan-out gate (children-of format).
    if not waits_for.startswith("children-of(") or not waits_for.endswith(")"):
        return _NO_FAN_OUT_GATE

    # Extract spawner ID.
    try:
        spawner_id = waits_for[len("children-of(") : -1].strip()
        if not spawner_id:
            return _NO_FAN_OUT_GATE
    except (ValueError, IndexError):
        return _NO_FAN_OUT_GATE

    # Confirm the spawner exists before querying its children.
    try:
        spawner = show(spawner_id)
    except BeadsError:
        # Can't determine; assume gate is satisfied.
        return _NO_FAN_OUT_GATE
    if not spawner:
        return _NO_FAN_OUT_GATE

    mode = _fan_out_gate_mode(bead)

    if mode == _FAN_OUT_MODE_ANY:
        # Satisfied the moment the first child closes. ``has_closed_children``
        # scopes the query to this one spawner (``bd list --parent=<id>``).
        blocked = not has_closed_children(spawner_id)
        return _FanOutGateVerdict(blocked=blocked, mode_known=True)

    # all-children OR unknown: unsatisfied iff the spawner still has an
    # unclosed child. ``has_open_children`` scopes the query to this one
    # spawner and soft-fails to False (gate satisfied) on infra error.
    blocked = has_open_children(spawner_id)
    return _FanOutGateVerdict(blocked=blocked, mode_known=(mode == _FAN_OUT_MODE_ALL))


def _has_fan_out_gate_issue(bead_id: str, bead: dict[str, Any] | None = None) -> bool:
    """True if ``bead_id`` has an unsatisfied fan-out gate.

    Thin bool wrapper over :func:`_fan_out_gate_verdict` (kept for its
    long-standing call sites and unit tests). The revert decision lives
    in the verdict's ``mode_known`` flag; callers that must decide whether
    to revert should use :func:`_fan_out_gate_verdict` directly.
    """
    return _fan_out_gate_verdict(bead_id, bead).blocked
