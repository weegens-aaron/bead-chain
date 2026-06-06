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

from .beads import BeadsError, extract_parent_epic_id, memories, show

# Char cap for the epic-description excerpt injected into the goal prompt.
# Big enough to convey purpose, small enough that ten chained beads under
# the same epic don't blow the LLM's context budget on duplicate prose.
_EPIC_EXCERPT_LIMIT: int = 280

# --- bd memory layer <-> host Kennel policy (coverage-audit gap FB-6) -------
#
# POLICY (one line): bead-chain surfaces *bd's* project-scoped memory
# layer (``bd remember``/``bd memories``, which travels with the Dolt DB)
# into the goal prompt and nudges agents to write back to it; it does NOT
# bridge to the host runtime's Kennel — the two are deliberately separate
# (bd memories = this project's shared facts; Kennel = the host agent's
# cross-repo diary), and coupling them would tie bead-chain to a
# host-specific backend. We document the split rather than bridge it.
#
# Caps for the persistent-memory digest injected into the goal prompt.
# Memories are high-signal but unbounded over a project's life; we cap
# both the count and per-entry length so a long-lived bd DB can't blow
# the LLM context budget. Newest-by-bd-order entries win the slots.
_MEMORY_DIGEST_MAX_ENTRIES: int = 12
_MEMORY_EXCERPT_LIMIT: int = 280

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


def _fetch_memory_digest() -> dict[str, str]:
    """Return bd's persistent memories as ``{key: insight}``, or ``{}``.

    Soft-fails by design (same rationale as :func:`_fetch_epic_context`):
    any :class:`BeadsError` — bd missing, timeout, this bd build lacking
    a ``memories`` subcommand, garbage JSON — yields ``{}`` so the goal
    prompt renders without a memory block rather than crashing the
    chain. The memory digest is a warm-start nicety, never a hard
    dependency.
    """
    try:
        return memories()
    except BeadsError:
        return {}


def _format_memory_digest_block(mems: dict[str, str]) -> str:
    """Render a ``## Persistent Memories`` prompt section, or ``""``.

    Bridges bd's memory layer into the goal prompt so a freshly-spawned
    working agent starts warm — it sees the project's durable insights
    (architecture decisions, gotchas, prior-bead learnings) the same way
    a human running ``bd prime`` would (coverage-audit gap FB-6,
    ``bead_chain-ndt``).

    Contract:

    * Non-empty dict → a block beginning with the literal ``## Persistent
      Memories`` heading, one ``- key: excerpt`` bullet per memory
      (capped at :data:`_MEMORY_DIGEST_MAX_ENTRIES`, each excerpt
      truncated to :data:`_MEMORY_EXCERPT_LIMIT`), then a trailing blank
      line so it slots between prompt sections.
    * Empty / non-dict → ``""`` (prompt byte-for-byte unchanged).

    Pure function, trivially testable — the impure fetch lives in
    :func:`_fetch_memory_digest`.
    """
    if not isinstance(mems, dict) or not mems:
        return ""
    lines = [
        "## Persistent Memories",
        "Durable project knowledge from bd's memory layer (`bd memories`). "
        "Treat as background context — verify before relying on it:",
    ]
    for key, insight in list(mems.items())[:_MEMORY_DIGEST_MAX_ENTRIES]:
        text = _first_paragraph_excerpt(str(insight), limit=_MEMORY_EXCERPT_LIMIT)
        if not text:
            continue
        lines.append(f"- {key}: {text}")
    # All entries truncated to nothing (pathological) -> emit nothing.
    if len(lines) == 2:
        return ""
    return "\n".join(lines) + "\n\n"


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


def _format_labels_line(bead: dict[str, Any]) -> list[str]:
    """Return a ``- Labels: a, b, c`` metadata line, or ``[]`` when absent.

    ``labels`` is a list of strings on the ``bd ready --json`` record
    bead-chain already hands to :func:`format_bead_as_goal` (verified
    present on this bd build — coverage-audit gap FB-7, anatomy #3), but
    the formatter historically never read it. Labels are the bead's
    cross-cutting tags (e.g. ``bead-chain``, ``prompt``, ``security``) —
    cheap, high-signal context for framing the work.

    Returns a single-element list so the caller can blindly ``extend()``
    the metadata block, matching :func:`_format_epic_metadata_lines`.

    Contract:

    * Non-empty list of stringy labels → ``['- Labels: a, b, c']``
      (each label stripped; empties/whitespace-only entries dropped).
    * Missing / empty / non-list / all-empty → ``[]`` (prompt unchanged).

    Pure function, trivially testable.
    """
    raw = bead.get("labels")
    if not isinstance(raw, (list, tuple)):
        return []
    labels = [str(item).strip() for item in raw if str(item).strip()]
    if not labels:
        return []
    return [f"- Labels: {', '.join(labels)}"]


# Non-gating, context-bearing edge types bead-chain surfaces in the goal
# prompt (coverage-audit gap FB-11, ``bead_chain-n57``; dependency#2).
#
# These six edges carry *context* the working agent (and the LLM judges)
# otherwise can't see: provenance (``discovered-from``), causal bug links
# (``caused-by``), validating tests (``validates``), and plain related
# work (``related`` / ``relates-to`` / ``tracks``). The field guide
# classifies all six as Informational — they do NOT gate readiness, and
# bead-chain deliberately keeps it that way (see
# :data:`beads.BLOCKING_DEP_TYPES`). Surfacing them here is purely about
# context; gating behaviour is untouched.
#
# Mapping value is the human-readable gloss prefixed to the target id in
# the rendered block. Insertion order also defines the *display* order so
# the most causally-load-bearing edges (provenance / cause / validation)
# lead. Adding a future context edge is a one-line edit. DRY.
_CONTEXT_EDGE_GLOSSES: dict[str, str] = {
    "discovered-from": "Discovered while working on",
    "caused-by": "Caused by",
    "validates": "Validates",
    "related": "Related to",
    "relates-to": "Relates to",
    "tracks": "Tracks",
}


def _edge_type(dep: dict[str, Any]) -> str:
    """Return a dependency edge's lowercased type, shape-agnostic.

    bd reports edges with two different field names depending on the
    command: ``bd ready``/``bd list`` records carry ``type``, while
    ``bd show`` records carry ``dependency_type``. We accept either so
    this formatter works regardless of which shape upstream hands us.
    """
    raw = dep.get("type") or dep.get("dependency_type") or ""
    return str(raw).strip().lower()


def _edge_target_id(dep: dict[str, Any]) -> str:
    """Return the id of the bead an edge points at, shape-agnostic.

    ``bd ready``/``bd list`` name the far end ``depends_on_id``; the
    ``bd show`` dependency records inline the related bead and name its
    id ``id``. Prefer the explicit ``depends_on_id`` so we never mistake
    a ``bd show`` edge's own id for its target.
    """
    raw = dep.get("depends_on_id") or dep.get("id") or ""
    return str(raw).strip()


def _format_related_context_block(bead: dict[str, Any]) -> str:
    """Return a ``## Related Context`` prompt section, or ``""`` when absent.

    Folds the bead's *non-gating* context edges — ``discovered-from``,
    ``caused-by``, ``validates``, ``related``, ``relates-to``,
    ``tracks`` (see :data:`_CONTEXT_EDGE_GLOSSES`) — into a short block
    so the working agent (and the LLM judges) can see the bead's
    provenance, causal bug link, validating test, and related work
    instead of working blind (coverage-audit gap FB-11). The block opens
    with a one-line caveat making explicit these links are background,
    not blockers.

    Reads the ``dependencies`` array that ``bd ready --json`` already
    hands :func:`format_bead_as_goal`. Each edge is rendered
    ``- <gloss> <target-id>`` (with ``: <title>`` appended when the edge
    record carries one, as ``bd show`` records do). Entries are emitted
    grouped by :data:`_CONTEXT_EDGE_GLOSSES` insertion order, then in the
    order they appear within the array; duplicate ``(type, target)``
    pairs are dropped.

    Contract:

    * At least one recognised context edge → a block beginning with the
      ``## Related Context`` heading, the caveat line, the edge lines,
      then a trailing blank line so it slots between prompt sections.
    * No ``dependencies`` / no *context* edges (only gating/structural
      edges like ``blocks`` / ``parent-child``) / non-list / malformed →
      ``""`` (prompt byte-for-byte unchanged).

    Gating behaviour is untouched: this helper never inspects or alters
    readiness — it is pure presentation. Pure function, trivially
    testable.
    """
    deps = bead.get("dependencies")
    if not isinstance(deps, (list, tuple)):
        return ""

    # Collect (edge_type -> list of "target[: title]" lines), de-duped.
    seen: set[tuple[str, str]] = set()
    by_type: dict[str, list[str]] = {}
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        edge_type = _edge_type(dep)
        if edge_type not in _CONTEXT_EDGE_GLOSSES:
            continue
        target = _edge_target_id(dep)
        if not target:
            continue
        key = (edge_type, target)
        if key in seen:
            continue
        seen.add(key)
        title = str(dep.get("title", "")).strip()
        suffix = f": {title}" if title else ""
        by_type.setdefault(edge_type, []).append(f"{target}{suffix}")

    if not by_type:
        return ""

    lines = [
        "## Related Context",
        "These links are non-gating background (provenance, causal bug "
        "links, validating tests, related work) — they do NOT block this "
        "bead:",
    ]
    for edge_type, gloss in _CONTEXT_EDGE_GLOSSES.items():
        for entry in by_type.get(edge_type, []):
            lines.append(f"- {gloss} {entry}")
    return "\n".join(lines) + "\n\n"


def _format_design_block(bead: dict[str, Any]) -> str:
    """Return a ``## Design`` prompt section, or ``""`` when absent.

    ``design`` is bd's ADR/design-rationale field — the conventional home
    for ``decision``- and ``spike``-type beads (coverage-audit gap FB-7,
    anatomy #2). Unlike ``acceptance_criteria``/``labels``, bd *omits*
    the key entirely when it's unset, so this helper soft-defaults via
    ``.get`` and renders only when a non-empty string is present.

    Contract (mirrors :func:`_format_acceptance_criteria_block`):

    * Non-empty ``design`` → a block beginning with the literal
      ``## Design`` heading, then the design text, then a trailing blank
      line so it slots between prompt sections.
    * Missing / empty / whitespace-only / non-string → ``""`` (prompt
      byte-for-byte unchanged).
    * If the stored value already leads with a ``Design`` heading we
      don't double it up — the value is emitted as-is.

    Pure function, trivially testable.
    """
    raw = bead.get("design", "")
    if not isinstance(raw, str):
        return ""
    design = raw.strip()
    if not design:
        return ""
    heading = "## Design"
    if design.lstrip("# ").lower().startswith("design"):
        body = design
    else:
        body = f"{heading}\n{design}"
    return f"{body}\n\n"


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
# UPDATE (coverage-audit FB-7): ``labels`` is now *verified present* on
# the ``bd ready``/``bd show`` JSON for this bd build, so the second
# bullet's caveat no longer holds. A real ``bead-chain:triaged`` label
# would be the cleaner home for this marker. We are NOT migrating yet —
# the sentinel is wire-stable across older bead-chain versions and a
# migration needs a compatibility window. See the recommendation in
# ``docs/analysis/bead-chain-coverage/FB-7-triage-label-recommendation.md``.
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


def _format_acceptance_criteria_block(bead: dict[str, Any]) -> str:
    """Return a ``## Acceptance Criteria`` prompt section, or ``""`` if absent.

    ``acceptance_criteria`` is already a key on the ``bd ready --json``
    record bead-chain hands to :func:`format_bead_as_goal`, but the
    formatter historically never read it — so the LLM judges verified
    completion against a contract the prompt never showed the agent
    (coverage-audit gap FB-2, ``bead_chain-2zx``).

    Contract:

    * Non-empty ``acceptance_criteria`` → a block beginning with the
      literal ``## Acceptance Criteria`` heading, then the criteria text,
      then a trailing blank line so it slots between prompt sections.
    * Missing / empty / whitespace-only / non-string → ``""`` (the
      prompt is byte-for-byte unchanged, preserving old behaviour).
    * If the stored value *already* leads with the ``## Acceptance
      Criteria`` heading (some beads embed it in the field text), we
      don't double it up — the value is emitted as-is under the blank
      line.

    Pure function, trivially testable.
    """
    raw = bead.get("acceptance_criteria", "")
    if not isinstance(raw, str):
        return ""
    criteria = raw.strip()
    if not criteria:
        return ""
    heading = "## Acceptance Criteria"
    if criteria.lstrip("# ").lower().startswith("acceptance criteria"):
        body = criteria
    else:
        body = f"{heading}\n{criteria}"
    return f"{body}\n\n"


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

    When the bead carries a non-empty ``acceptance_criteria`` field (it
    is already a key on the ``bd ready --json`` record), a
    ``## Acceptance Criteria`` section is injected just before the
    "When you believe this is done" checklist via
    :func:`_format_acceptance_criteria_block`, so the agent is shown the
    same contract the LLM judges grade it against. Absent/empty → the
    prompt is unchanged.

    Likewise (coverage-audit gap FB-7), a non-empty ``design`` field is
    rendered as a ``## Design`` block (:func:`_format_design_block`)
    just before the acceptance block — high-value for ``decision``/
    ``spike`` beads whose rationale lives there — and any ``labels`` are
    appended to the issue-metadata block (:func:`_format_labels_line`).
    Both soft-default to no-ops when absent so existing prompts are
    byte-for-byte unchanged.

    Finally (coverage-audit gap FB-11), the bead's *non-gating* context
    edges — ``discovered-from`` / ``caused-by`` / ``validates`` /
    ``related`` / ``relates-to`` / ``tracks`` — are folded into a
    ``## Related Context`` block (:func:`_format_related_context_block`)
    just after the acceptance block, so the agent can see the bead's
    provenance, causal bug link and validating test. This is pure
    context: gating behaviour is unchanged, and the block is ``""`` when
    the bead carries no such edges.

    Finally (coverage-audit gap FB-6, ``bead_chain-ndt``), bd's
    persistent memory layer (``bd remember`` / ``bd memories``) is folded
    into a ``## Persistent Memories`` block
    (:func:`_format_memory_digest_block`) near the top of the body so a
    freshly-spawned agent starts *warm* with the project's durable
    insights instead of cold. The done-checklist also nudges the agent to
    write durable learnings back via ``bd remember``, closing the loop.
    The fetch (:func:`_fetch_memory_digest`) soft-fails to ``{}`` so the
    prompt is unchanged when bd has no memories or lacks the subcommand.
    Policy note: this surfaces *bd's* project-scoped memory only — it is
    deliberately NOT bridged to the host runtime's Kennel (see the policy
    comment near :data:`_MEMORY_DIGEST_MAX_ENTRIES`).
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
    metadata_lines.extend(_format_labels_line(bead))
    metadata = "\n".join(metadata_lines)

    # Render the bead's own design rationale + acceptance_criteria (both
    # already on the bd ready dict) so the agent — and the LLM judges —
    # work from the same context and grade against the same contract.
    # Each is "" when absent, so the prompt is unchanged in that case.
    design_block = _format_design_block(bead)
    acceptance_block = _format_acceptance_criteria_block(bead)

    # FB-11 (bead_chain-n57): fold the bead's non-gating context edges
    # (discovered-from / caused-by / validates / related / relates-to /
    # tracks) into a 'Related Context' block so the agent isn't blind to
    # provenance, causal bug links and validating tests. "" when absent;
    # gating behaviour is untouched.
    related_block = _format_related_context_block(bead)

    # FB-6 (bead_chain-ndt): warm-start the agent with bd's persistent
    # memory layer so each bead doesn't begin cold. Soft-fails to "" when
    # bd has no memories (or lacks the subcommand); placed at the top of
    # the body — above the bead-specific content — because it's whole-
    # project framing, not per-bead detail.
    memory_block = _format_memory_digest_block(_fetch_memory_digest())

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
        f"{memory_block}"
        f"Issue metadata:\n"
        f"{metadata}\n"
        f"\n"
        f"{design_block}"
        f"{acceptance_block}"
        f"{related_block}"
        f"When you believe this is done:\n"
        f"1. Run linters (`ruff check --fix`, `ruff format .`).\n"
        f"2. Run any relevant tests.\n"
        f"3. Commit the work (no Claude co-author, per project rules).\n"
        f"4. Record any durable, reusable insight you learned (a gotcha, a\n"
        f"   design decision, a non-obvious root cause) so the next bead\n"
        f"   starts warm: `bd remember <insight> --key=<short-slug>`.\n"
        f"\n"
        f"LLM judges will verify completion before this bead is closed."
        f"{_BUG_DISCOVERY_PROTOCOL}"
    )
