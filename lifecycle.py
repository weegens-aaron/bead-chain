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

from typing import Any

from code_puppy.messaging import (
    emit_info,
    emit_success,
    emit_warning,
)
from code_puppy.plugins.wiggum import state as wiggum_state

from . import state
from .beads import (
    BeadsError,
    claim,
    close,
    close_eligible_epics,
    extract_parent_epic_id,
    has_epic_in_progress,
    is_excluded_type,
    list_in_progress,
    next_blocking_bug,
    next_in_progress,
    next_ready,
    next_ready_in_epic,
    revert_to_open,
    show,
)
from .prompt import format_bead_as_goal

# Status value bd assigns to a bead that's been claimed but not yet
# closed. Used to detect *stranded* work — a bead left in this state
# when no chain is running implies the previous run errored or was
# cancelled before the LLM judges could rule. See :func:`is_recovery_bead`.
_IN_PROGRESS_STATUS: str = "in_progress"


def is_recovery_bead(bead: dict[str, Any] | None) -> bool:
    """True if ``bead`` was already in_progress when bead-chain picked it.

    The deliberate one-bead-at-a-time discipline means we should never
    see an in_progress bead at chain-start or between-iterations — if
    we do, it's residue from a prior crashed/cancelled run. Centralised
    here so the recovery-mode signal stays consistent across both the
    startup path and the mid-chain pick path. DRY.
    """
    if not bead:
        return False
    return str(bead.get("status", "")) == _IN_PROGRESS_STATUS


# ---------------------------------------------------------------------------
# Startup invariant guard
# ---------------------------------------------------------------------------


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

    Soft-fails by design: a bd outage here shouldn't block the chain
    from running. If listing fails we emit a warning and return
    ``None``, letting the normal startup probe handle whatever it can
    see.
    """
    try:
        items = list_in_progress()
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


def close_current_bead_success() -> dict[str, Any] | None:
    """Close the bead we were just working on, if any.

    Returns the **just-closed bead dict** (or ``None`` if there was no
    current bead) so the caller can use fields like the parent epic
    when picking the next bead — see :func:`activate_next_bead`.
    Whether the ``bd close`` call succeeded or not, the returned dict
    still represents the bead we were working on; that's the right
    signal for epic-affinity routing (we *intended* to finish that
    epic's work).

    **Close-failure handling.** If ``bd close`` raises, the bead is
    still legitimately in_progress in bd's view. We:

      1. **Leave it in_progress.** Reverting would orphan the partial
         work from its bead — the next ``bd ready`` could hand us a
         different bead and the half-done changes would silently
         attach to no tracked work. Staying in_progress means the
         next ``/bead-chain`` run's recovery tier picks it up and
         re-prompts with the recovery preamble, so the agent assesses
         the current state before doing anything new.
      2. **Stop the chain.** A close failure means something is
         genuinely wrong (bd outage, permission issue, schema drift).
         Halt loudly rather than barreling on.

    The caller distinguishes the success vs. failure case by checking
    ``state.is_active()`` after the call: if False, the chain was
    stopped here and the caller should bail without claiming another
    bead.
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
    #   2. The tier-0 recovery path in :func:`pick_next_bead` calls
    #      :func:`beads.next_in_progress`, which filters epics out via
    #      ``--exclude-type=epic``. So a stranded epic would never be
    #      picked up by the recovery preamble flow — it would just sit
    #      there forever. Reverting is the only path back to sanity.
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

    try:
        close(bead_id, reason="bead-chain: LLM judges passed")
    except BeadsError as exc:
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

    Runs ``bd epic close-eligible`` after every successful child close
    so finished epics don't linger as zombie containers. bd handles
    cascades natively: closing epic A's last child may make A's parent
    epic B eligible too, and one call rolls both up.

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

    Raises :class:`BeadsError` on infrastructure failure so the caller
    can stop the chain cleanly.
    """
    stranded = next_in_progress()
    if stranded is not None:
        bead_id = str(stranded.get("id", "<unknown>"))
        emit_warning(
            f"⚠️ bead-chain: found stranded in_progress bead {bead_id} — "
            "recovering before picking new work."
        )
        return stranded

    blocking = next_blocking_bug()
    if blocking is not None:
        bead_id = str(blocking.get("id", "<unknown>"))
        emit_info(f"🔗 bead-chain: blocking bug detected → prioritising {bead_id}")
        return blocking

    epic_id = extract_parent_epic_id(just_closed)
    if epic_id:
        sibling = next_ready_in_epic(epic_id)
        if sibling is not None:
            emit_info(f"🔗 bead-chain: epic affinity → staying inside {epic_id}")
            return sibling
    return next_ready()


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
        emit_success(
            f"🦴 bead-chain: no more ready beads. "
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

    # Walk the hierarchy top-down: claim the parent epic FIRST, then
    # the child bead. bd's UI caches per-parent children-by-status
    # views, so flipping a leaf to in_progress under a still-open
    # parent produces a stale tree until the user navigates back to
    # the parent. Going parent-first keeps the hierarchy consistent
    # at every observable moment. Soft-fails internally — never
    # blocks the chain.
    ensure_epic_in_progress(bead)

    if not recovery:
        try:
            claim(bead_id)
        except BeadsError as exc:
            emit_warning(f"🔗 bead-chain couldn't claim {bead_id}: {exc} — stopping.")
            state.stop()
            return None
    # Recovery beads are already in_progress — skip the redundant claim
    # call (see handle_bead_chain_command for the same rationale).

    state.get_state().current_bead = bead

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
