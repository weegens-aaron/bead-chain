#!/usr/bin/env python3
"""One-shot scaffolder: seed the 9 capability-area section stubs.

Run once from the bead_chain repo root. Idempotent: skips files that already
have findings (size grown past the seed). This script exists so the scaffold is
reproducible and the 9 stubs stay DRY-identical to the template's shape.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path("docs/analysis/bead-chain-coverage")

# (num, slug, title, fg_chapter_file, fg_chapter_num, bead, modules)
AREAS = [
    (
        "01",
        "anatomy",
        "Anatomy of a Bead",
        "field-guide-01-anatomy-of-a-bead.html",
        1,
        "bead_chain-bn4",
        "`prompt.py` (`format_bead_as_goal`, prompt.py:258)",
    ),
    (
        "02",
        "dependency-graph",
        "Dependency Graph",
        "field-guide-02-dependency-graph.html",
        2,
        "bead_chain-xoq",
        "`lifecycle.py` (`pick_next_bead`, `_reject_if_blocked`)",
    ),
    (
        "03",
        "status-lifecycle",
        "Status Lifecycle",
        "field-guide-03-status-lifecycle.html",
        3,
        "bead_chain-npn",
        "`lifecycle.py`, `state.py`",
    ),
    (
        "04",
        "memories-recall",
        "Memories & Recall",
        "field-guide-04-memories-and-recall.html",
        4,
        "bead_chain-a10",
        "`prompt.py`",
    ),
    (
        "05",
        "formulas-molecules",
        "Formulas & Molecules",
        "field-guide-05-formulas-and-molecules.html",
        5,
        "bead_chain-5xh",
        "`lifecycle.py` (`rollup_completed_epics`, `_has_fan_out_gate_issue`)",
    ),
    (
        "06",
        "gates-coordination",
        "Gates & Coordination",
        "field-guide-06-gates-and-coordination.html",
        6,
        "bead_chain-5cd",
        "`lifecycle.py`, `close_guard.py`",
    ),
    (
        "07",
        "swarms",
        "Swarms",
        "field-guide-07-swarms.html",
        7,
        "bead_chain-jmo",
        "`lifecycle.py`, `register_callbacks.py`",
    ),
    (
        "08",
        "data-layer",
        "Data Layer (Dolt)",
        "field-guide-08-data-layer.html",
        8,
        "bead_chain-p6o",
        "`lifecycle.py`, `register_callbacks.py`, `state.py`",
    ),
    (
        "09",
        "quality-hygiene",
        "Quality & Hygiene",
        "field-guide-09-quality-and-hygiene.html",
        9,
        "bead_chain-tl0",
        "`close_guard.py`, `lifecycle.py`",
    ),
]

SEED = """# {title} — Coverage Findings

> Seeded stub. Fill from `_template.md`. Owner bead: {bead}.

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `{slug}`                                       |
| Field-guide ref  | `{fg}` (chapter {ch})                          |
| Bead-chain owner | `{bead}`                                       |
| Primary modules  | {modules}                                      |
| Status           | `not-started`                                  |

---

## 1. AVAILABLE — what the field guide documents

_TODO ({bead}): summarize the bd 1.0.4 feature surface for this area, citing
`{fg}` § "<section>"._

## 2. LEVERAGED — what bead-chain actually uses

_TODO ({bead}): what bead-chain consumes, with `file:line` citations. State
explicitly anything that is NOT leveraged._

## 3. GAPS — what's missing, and how much it matters

| #   | Gap (one line) | Severity | Recommended follow-up (one line) |
| --- | -------------- | -------- | -------------------------------- |
| 1   | _TODO_         | _Px_     | _TODO_                           |

### Severity rubric

| Sev | Meaning                                                                       |
| --- | ---------------------------------------------------------------------------- |
| P0  | Correctness/data-loss hazard in the drain loop (e.g. closes wrong bead).      |
| P1  | Feature silently dropped where it changes which bead runs or how it's framed. |
| P2  | Feature unused where leveraging it would materially improve goal quality.     |
| P3  | Minor gap; workaround exists or impact is narrow.                            |
| P4  | Cosmetic / future-proofing only.                                            |

---

## Notes / open questions

_None yet._
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for num, slug, title, fg, ch, bead, modules in AREAS:
        path = OUT / f"{num}-{slug}.md"
        body = SEED.format(
            title=title, slug=slug, fg=fg, ch=ch, bead=bead, modules=modules
        )
        if path.exists() and len(path.read_text()) > len(body) + 200:
            print(f"skip (has findings): {path}")
            continue
        path.write_text(body)
        print(f"wrote: {path}")


if __name__ == "__main__":
    main()
