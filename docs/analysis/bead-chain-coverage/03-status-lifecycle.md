# Status Lifecycle — Coverage Findings

> Seeded stub. Fill from `_template.md`. Owner bead: bead_chain-npn.

| Field            | Value                                          |
| ---------------- | ---------------------------------------------- |
| Capability area  | `status-lifecycle`                                       |
| Field-guide ref  | `field-guide-03-status-lifecycle.html` (chapter 3)                          |
| Bead-chain owner | `bead_chain-npn`                                       |
| Primary modules  | `lifecycle.py`, `state.py`                                      |
| Status           | `not-started`                                  |

---

## 1. AVAILABLE — what the field guide documents

_TODO (bead_chain-npn): summarize the bd 1.0.4 feature surface for this area, citing
`field-guide-03-status-lifecycle.html` § "<section>"._

## 2. LEVERAGED — what bead-chain actually uses

_TODO (bead_chain-npn): what bead-chain consumes, with `file:line` citations. State
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
