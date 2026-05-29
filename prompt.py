"""Bead → ``/goal`` prompt formatting.

Pure (or near-pure) helpers that turn a ``bd ready``-shaped bead dict
into the prompt string we hand off to wiggum's ``/goal`` mode. Split
out of :mod:`register_callbacks` to keep that file under the 600-line
plugin cap; also gives the prompt-shape tests one obvious target.

The only impure helper is :func:`_fetch_epic_context`, which shells out
to ``bd show`` for epic enrichment — and it soft-fails to ``None`` so
the rest of the formatter stays deterministic.
"""

from __future__ import annotations

from typing import Any

from .beads import BeadsError, extract_parent_epic_id, show

# Char cap for the epic-description excerpt injected into the goal prompt.
# Big enough to convey purpose, small enough that ten chained beads under
# the same epic don't blow the LLM's context budget on duplicate prose.
_EPIC_EXCERPT_LIMIT: int = 280

# Preamble prepended to the goal prompt when bead-chain is resuming a
# bead that was left in_progress by a previous, errored or cancelled
# run. The agent must assess current state BEFORE redoing any work —
# the bead may already be satisfied, in which case it should report
# what's in place rather than churning. Kept as a module constant so
# the wording is easy to tune in one place. DRY.
_RECOVERY_PREAMBLE: str = (
    "⚠️ RECOVERY MODE: a previous bead-chain run did not finish this bead.\n"
    "You are picking up partial work — the bead is already claimed and in_progress.\n"
    "\n"
    "Before doing any new work, assess the current state of the repo:\n"
    "- What changes have already been made for this bead?\n"
    "- Are tests and linters passing?\n"
    "- Is the work effectively done?\n"
    "\n"
    "If the bead is already satisfied by the current state, reply with a\n"
    "summary of what's in place that meets the requirements. Do NOT redo\n"
    "work — the LLM judges will verify and close the bead based on your\n"
    "summary.\n"
    "\n"
    "Otherwise, continue from where the previous run left off.\n"
    "\n"
    "---\n"
    "\n"
)


def _first_paragraph_excerpt(text: str, *, limit: int = _EPIC_EXCERPT_LIMIT) -> str:
    """Return the first paragraph of ``text``, truncated to ``limit`` chars.

    Splits on the first blank line (``\\n\\n``) to grab just the lede, then
    word-boundary-truncates with an ellipsis if still too long. Empty /
    None-ish input → ``""``. Pure function, trivially testable.
    """
    if not text:
        return ""
    paragraph = text.split("\n\n", 1)[0].strip()
    if len(paragraph) <= limit:
        return paragraph
    cut = paragraph[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _fetch_epic_context(epic_id: str) -> tuple[str, str] | None:
    """Return ``(title, excerpt)`` for an epic, or ``None`` if unavailable.

    Soft-fails by design: any :class:`BeadsError` (bd missing, timeout,
    bead not found, garbage JSON) yields ``None`` and lets the caller
    fall back to a minimal "Parent epic: <id>" line. Epic context is a
    nice-to-have for the LLM — we never want it to crash the goal
    prompt or stall the chain.
    """
    try:
        epic = show(epic_id)
    except BeadsError:
        return None
    if not epic:
        return None
    title = str(epic.get("title", "")).strip()
    excerpt = _first_paragraph_excerpt(str(epic.get("description", "")))
    return title, excerpt


def _format_epic_metadata_lines(bead: dict[str, Any]) -> list[str]:
    """Build the ``Parent epic: ...`` metadata lines for the goal prompt.

    Returns ``[]`` when the bead has no parent epic, so the caller can
    blindly ``extend()`` without conditionals.

    Three outcomes:

    * no parent epic → ``[]``
    * parent epic found and fetched → ``['- Parent epic: id — title',
      '  > excerpt']`` (the excerpt line is omitted if blank)
    * parent epic known but ``bd show`` failed → ``['- Parent epic: id']``
      (we still tell the LLM this bead is part of a larger effort)
    """
    epic_id = extract_parent_epic_id(bead)
    if not epic_id:
        return []

    context = _fetch_epic_context(epic_id)
    if context is None:
        return [f"- Parent epic: {epic_id}"]

    title, excerpt = context
    label = f"{epic_id} — {title}" if title else epic_id
    lines = [f"- Parent epic: {label}"]
    if excerpt:
        lines.append(f"  > {excerpt}")
    return lines


# Sentinel marker injected into a bug bead's description when an agent
# files it mid-chain via the bug-discovery protocol (see
# :data:`_BUG_DISCOVERY_PROTOCOL`). When a *future* /bead-chain iteration
# claims that bug, :func:`is_triaged_bug` spots the marker and
# :func:`format_bead_as_goal` swaps the standard goal prompt for the
# triage-verification preamble (:data:`_TRIAGE_VERIFY_PREAMBLE`).
#
# Why a description sentinel instead of a bd label/tag:
#   * Descriptions are guaranteed-supported (we already render them).
#   * Labels/tags are a bd feature we haven't verified across versions.
#   * The marker doubles as a human-readable breadcrumb in ``bd show``
#     — anyone inspecting the bug knows immediately how it was filed.
#
# Keep this string stable across releases: changing it would orphan
# every triaged bug filed by older bead-chain versions, silently
# downgrading them to the normal-work prompt path. If we ever need to
# evolve the format, add a second sentinel and have
# :func:`is_triaged_bug` recognise both.
TRIAGE_MARKER: str = "[bead-chain:triaged]"

# Preamble used when the claimed bead is a bug that was filed mid-chain
# by a previous bead's agent (detected via :data:`TRIAGE_MARKER`).
#
# Semantics: the *filing* agent already attempted an inline fix as part
# of their original bead's scope expansion. The fix may or may not have
# survived intact — maybe the judges sent them back for revisions and
# they backed it out; maybe the fix works but the bug deserves a real
# test; maybe the inline patch was a band-aid and a proper fix is
# needed. This preamble tells the verifying agent to assess all three.
#
# Precedence note: if the bug also got stranded in_progress (verifying
# agent crashed), the recovery preamble (:data:`_RECOVERY_PREAMBLE`)
# wins via the ordering in :func:`format_bead_as_goal` — "assess current
# state" subsumes "verify a prior fix" cleanly.
_TRIAGE_VERIFY_PREAMBLE: str = (
    "🔍 TRIAGE VERIFICATION: this bug was discovered and inline-fixed by\n"
    "a previous bead's agent as part of their scope expansion. It now\n"
    "needs proper assessment before being closed.\n"
    "\n"
    "Your job:\n"
    "1. Read the bug description below to understand what was reported.\n"
    "2. Use ``git log`` and ``bd show`` to see what the prior agent did.\n"
    "3. Decide which of these is true:\n"
    "   a. The inline fix is correct and complete → add/verify tests,\n"
    "      then summarize for the judges. The bead closes normally.\n"
    "   b. The inline fix is a band-aid and a proper fix is needed →\n"
    "      implement the proper fix, then summarize the upgrade.\n"
    "   c. The fix was backed out or never landed → implement it now\n"
    "      as ordinary work on this bead.\n"
    "\n"
    "Do NOT assume the fix is good just because the marker is present.\n"
    "The marker only proves the bug was *triaged*, not *resolved*.\n"
    "\n"
    "---\n"
    "\n"
)

# Bug-discovery protocol appended to every goal prompt. Short rubric
# format so agents can scan it without burning attention budget.
#
# Design decisions baked in (per design discussion):
#   * Raw ``bd create`` — no plugin slash-command wrapper. Less magic.
#   * One bead, one bug — multiple discoveries get multiple beads.
#   * Blocking bugs get fixed *inline* as scope expansion, AND filed
#     as a bd bead with the triage marker so the fix gets proper
#     verification in a later iteration.
#   * Non-blocking bugs get filed and ignored — tier-1 priority in
#     :func:`lifecycle.pick_next_bead` will route them naturally.
#   * The blocking criterion is task-completion-relative, not
#     theoretical: "can't satisfy THIS bead's acceptance criteria".
#
# Why every prompt: agents shouldn't need to remember bug-handling
# rules differently depending on which iteration they're in. The token
# cost (~25 lines) buys consistency across the entire chain.
_BUG_DISCOVERY_PROTOCOL: str = (
    "\n"
    "---\n"
    "\n"
    "🐛 BUG DISCOVERY PROTOCOL\n"
    "\n"
    "If you find a bug while working this bead that is unrelated to the\n"
    "bead's stated goal, file it as a bd bead. One bug per bead — if you\n"
    "discover multiple unrelated issues, file each separately.\n"
    "\n"
    "Blocking rubric (decide per-bug):\n"
    "  BLOCKING  = you cannot satisfy THIS bead's acceptance criteria\n"
    "              without fixing the bug first.\n"
    "  NON-BLOCKING = the bug exists but doesn't prevent you from\n"
    "              completing the current bead's stated goal.\n"
    "\n"
    "NON-BLOCKING bug — file and keep working:\n"
    "  bd create --type=bug --title='<short title>' \\\n"
    "    --description='<what you saw, repro steps, suspected cause>' \\\n"
    "    --priority=2\n"
    "  Then continue with your original bead. Priority-1 routing will\n"
    "  pick the bug up in a later /bead-chain iteration.\n"
    "\n"
    f"BLOCKING bug — file with triage marker, fix inline, finish work:\n"
    f"  bd create --type=bug --title='<short title>' \\\n"
    f"    --description='{TRIAGE_MARKER} <what you saw, what you fixed "
    "inline, why it blocked>' \\\n"
    "    --blocks=<current-bead-id> --priority=1\n"
    "  Then fix the bug AS PART OF this bead's work (scope expansion),\n"
    "  finish the original goal, and present both in your summary so\n"
    "  the judges see the expanded scope. The filed bug stays open and\n"
    "  will be claimed in a future iteration for proper verification —\n"
    "  that's intentional, not a bug in the system.\n"
    "\n"
    "Do NOT close any bead yourself — the judges are the only legitimate\n"
    "closer. The bug-discovery protocol is about *filing*, not closing.\n"
)


def is_triaged_bug(bead: dict[str, Any] | None) -> bool:
    """True if ``bead``'s description carries the :data:`TRIAGE_MARKER`.

    Used by :func:`format_bead_as_goal` to switch a bug bead claimed by
    a future /bead-chain iteration from the normal-work prompt to the
    triage-verification preamble (:data:`_TRIAGE_VERIFY_PREAMBLE`).

    The check is intentionally narrow:

    * Only ``issue_type == 'bug'`` qualifies. A task with the marker in
      its description (e.g., someone documenting the system) shouldn't
      flip into verification mode — the marker is meaningful only for
      bug beads filed via the discovery protocol.
    * Marker presence is a substring check on ``description``. We don't
      anchor to start-of-string because users may prepend their own
      formatting (e.g., a triage timestamp).

    Defensive against non-dict / missing fields — returns False rather
    than raising, same contract as :func:`beads.is_excluded_type`.
    """
    if not isinstance(bead, dict):
        return False
    if str(bead.get("issue_type", "")).strip().lower() != "bug":
        return False
    description = str(bead.get("description", ""))
    return TRIAGE_MARKER in description


def format_bead_as_goal(bead: dict[str, Any], *, recovery: bool = False) -> str:
    """Turn a bd-ready JSON record into a goal prompt for /goal.

    When the bead has a parent epic (canonical ``parent`` field on bd's
    output, plus legacy ``parent_id`` / ``epic_id`` fallbacks), the
    prompt is enriched with the epic's title and a short description
    excerpt so the LLM has context about the larger effort it's
    contributing to. See :func:`_format_epic_metadata_lines` for the
    soft-fail semantics.

    Three preamble states, mutually exclusive, evaluated in this order:

    1. ``recovery=True`` → :data:`_RECOVERY_PREAMBLE`. The bead was
       left in_progress by a previous run — assess current state
       before doing new work. Wins over triage because "figure out
       what's already done" subsumes any other preamble.
    2. Bead is a triaged bug (:func:`is_triaged_bug`) →
       :data:`_TRIAGE_VERIFY_PREAMBLE`. A previous bead's agent filed
       and inline-fixed this bug as scope expansion; verify the fix.
    3. Otherwise → no preamble (ordinary work).

    Every prompt gets :data:`_BUG_DISCOVERY_PROTOCOL` appended at the
    bottom regardless of preamble — the bug-handling rules apply on
    every iteration of every bead.
    """
    bead_id = str(bead.get("id", "<unknown>"))
    title = str(bead.get("title", "")).strip() or "(no title)"
    description = str(bead.get("description", "")).strip() or "(no description)"
    issue_type = str(bead.get("issue_type", "task"))
    priority = bead.get("priority", "?")

    metadata_lines = [
        f"- Type: {issue_type}",
        f"- Priority: P{priority}",
    ]
    metadata_lines.extend(_format_epic_metadata_lines(bead))
    metadata = "\n".join(metadata_lines)

    preamble = ""
    if recovery:
        preamble = _RECOVERY_PREAMBLE
    elif is_triaged_bug(bead):
        preamble = _TRIAGE_VERIFY_PREAMBLE

    return preamble + (
        f"Complete beads issue {bead_id}: {title}\n"
        f"\n"
        f"{description}\n"
        f"\n"
        f"Issue metadata:\n"
        f"{metadata}\n"
        f"\n"
        f"When you believe this is done:\n"
        f"1. Run linters (`ruff check --fix`, `ruff format .`).\n"
        f"2. Run any relevant tests.\n"
        f"3. Commit the work (no Claude co-author, per project rules).\n"
        f"\n"
        f"LLM judges will verify completion before this bead is closed."
        f"{_BUG_DISCOVERY_PROTOCOL}"
    )
