# Recommendation — migrate the triage marker from a description sentinel to a real `bd` label

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| Status     | Recommended (not yet adopted)                                         |
| Date       | 2026-06-06                                                            |
| Bead       | `bead_chain-432` (FB-7), under epic `bead_chain-2p3`                  |
| Source     | `docs/analysis/bead-chain-coverage/01-anatomy.md` (gap #3), `GAPS.md` |
| Scope      | Recommendation only — FB-7's code change surfaces `design`/`labels`;  |
|            | the migration itself is deliberately **not** performed here.          |

## Background

When an agent discovers a *blocking* bug mid-chain (the bug-discovery
protocol in `prompt.py`), it files a `bug` bead whose `description` is
prefixed with the literal sentinel string:

```text
[bead-chain:triaged] <what you saw, what you fixed inline, why it blocked>
```

A later `/bead-chain` iteration that claims that bug runs
`prompt.is_triaged_bug()` — a substring check on the description — and,
on a hit, swaps the ordinary goal prompt for the triage-verification
preamble (`_TRIAGE_VERIFY_PREAMBLE`).

The sentinel lives in `description` for one historical reason, recorded
in the `TRIAGE_MARKER` comment:

> Labels/tags are a bd feature we haven't verified across versions.

## What changed

FB-7's audit work **verified `labels` is present** on this bd build's
`bd ready --json` and `bd show … --json` output (a list of strings), and
FB-7 now renders it into the goal prompt. The original caveat that
motivated a description sentinel over a label no longer holds: labels are
demonstrably available and demonstrably readable.

## Recommendation

**Adopt a real bd label — `bead-chain:triaged` — as the canonical triage
marker, but do so behind a backward-compatible reader, not a hard cutover.**

Concretely, in a *follow-up* bead (not this one):

1. **Detection reads both.** Update `is_triaged_bug()` to return true when
   *either* the `bead-chain:triaged` label is present in `bead["labels"]`
   *or* the legacy `[bead-chain:triaged]` substring is present in
   `description`. This keeps every already-filed triaged bug working —
   the sentinel is wire-stable across older bead-chain versions and
   orphaning those beads (silently downgrading them to the normal-work
   prompt) is the exact failure the `TRIAGE_MARKER` comment warns about.
2. **Filing writes the label.** Update the `_BUG_DISCOVERY_PROTOCOL`
   instructions so blocking-bug filing adds `--label=bead-chain:triaged`
   (keeping, for one release, the description prefix too as a
   human-readable breadcrumb in `bd show`).
3. **Deprecation window, then drop the prefix.** Once enough release
   cadence has passed that no open triaged bug predates the label era,
   a later change can stop writing the description prefix and (optionally)
   keep reading it indefinitely as a cheap compatibility shim.

### Why a label is the better home

- **Structured, queryable.** `bd list --label=bead-chain:triaged` becomes
  a first-class triage query; a description substring is not addressable.
- **No prose collision.** A description that merely *quotes* the protocol
  (e.g. this very document, or a bead explaining the system) can trip the
  substring check. A label is unambiguous metadata. (`is_triaged_bug()`
  already narrows to `issue_type == "bug"` to limit this, but a label
  removes the hazard entirely.)
- **Consistent with the codebase's new posture.** FB-7 surfaces labels as
  first-class prompt context; using one for triage state is coherent with
  treating labels as real, relied-upon metadata.

### Why not a hard cutover now

- **Wire stability.** Existing triaged bugs carry only the description
  sentinel. A label-only reader would silently strand them — the precise
  regression the marker comment guards against.
- **Out of FB-7's scope.** FB-7's acceptance criteria are (a) surface
  `design`/`labels` in the prompt and (b) *produce this recommendation*.
  The migration is a behavioral change to filing + detection that deserves
  its own bead, tests, and deprecation window (YAGNI: don't bundle it in).

## Suggested follow-up bead

> **Title:** Migrate `bead-chain:triaged` from description sentinel to a bd label
> **Type:** task · **Priority:** P2 · **Epic:** `bead_chain-2p3`
> **Acceptance:** `is_triaged_bug()` recognizes the label *and* the legacy
> description sentinel; bug-discovery protocol files the label; tests cover
> label-only, sentinel-only, and both; deprecation note recorded.
