# Explanation: Epic affinity and coherent commits

## About epic affinity and coherent commits

Epic affinity is a deliberate design choice in bead-chain that prefers keeping related work together during execution, not splitting across unrelated tasks. The goal is **coherent commits and PRs** — finishing what you start, keeping history readable, and reducing cognitive load.

This is a strategic tradeoff: we sacrifice absolute queue optimality (\"pick the highest-priority bead globally\") to gain commit quality and narrative coherence.

---

## The problem: queue-only ordering

Picture a typical project with multiple epics:

```
Epic A: Refactor authentication         Epic B: Add user profiles
  ├─ task-1a: extract JWT utils      ├─ task-1b: create Profile model
  ├─ task-2a: revoke tokens          ├─ task-2b: build UI forms
  └─ task-3a: document changes       └─ task-3b: add tests
```

**Without affinity** (pure global queue by priority):
- Finish task-1a (JWT utils)
- Pick task-1b (Profile model) — *switching context to Epic B*
- Pick task-2a (Revoke tokens) — *back to Epic A, mid-flow*
- Pick task-2b (UI forms) — *back to Epic B again*
- ...

**Result:**
1. Each commit jumps between A and B (git history is a pinball machine)
2. Each context switch has cognitive cost
3. Code review becomes hard (\"why are JWT changes mixed with Profile changes?\")
4. Bisecting bugs later is painful (features are interleaved)

**With epic affinity:**
- Finish task-1a
- Pick task-2a (same epic A; prefer sibling) — *stay in context*
- Pick task-3a (same epic A; still in context) — *finish the whole epic*
- Commit the whole epic at once (coherent PR)
- Then switch to Epic B and repeat

**Result:**
1. Each epic is a self-contained, reviewable unit
2. Context is sticky; less switching
3. History is readable (\"these 3 commits finished Epic A\")
4. Bisecting is easier (each feature is isolated)

---

## The mechanism

**In `lifecycle.py::pick_next_bead()`:**

```python
def pick_next_bead() -> dict | None:
    # Tier 1: Blocking bugs (unblock others)
    bug = next_blocking_bug()
    if bug:
        return bug
    
    # Tier 2: Epic siblings (affinity)
    if state.active_bead:  # Did we just finish a bead?
        parent_epic = extract_parent_epic_id(state.active_bead)
        sibling = next_ready_in_epic(parent_epic)  # Any unblocked siblings?
        if sibling:
            return sibling  # Stay in the same epic
    
    # Tier 3: Global queue (fallback)
    return next_ready()
```

**Translation:**
1. If a bead that blocks others is ready, fix it first (unblock downstream)
2. If we just closed a bead, look for its siblings (same parent epic) before jumping to a new epic
3. If no siblings, jump to the global queue

**Key insight:** After closing a bead, we check the *parent epic* of the bead we just finished. If that epic has other ready work, we prefer it. Only when all siblings are blocked or done do we jump to a new epic.

---

## Tradeoffs: why affinity wins

### What we gain

1. **Coherent commits**
   - A whole epic closes in one session → one PR
   - Reviewers see \"here's what changed for feature X\", not \"random mix of features\"

2. **Reduced context switching**
   - Less \"OK, what was I thinking about feature A?\" — you stay in flow
   - Fewer mental context resets (psychologically expensive)

3. **Better blame history**
   - `git log` is readable: \"Epic A: done in commits 1-3\", \"Epic B: done in commits 4-7\"
   - Bisecting is faster (features aren't interleaved)

4. **Explicit epic ownership**
   - If you claim task-1a of Epic A, you're implicitly committing to finish the epic (or interrupt cleanly)
   - Reduces work-in-progress (WIP) paralysis

### What we sacrifice

1. **Absolute priority ordering**
   - A P2 sibling of the current epic can be picked before a P1 from another epic
   - Exception: blocking bugs (tier 1) still jump the queue

2. **Latency for urgent new work**
   - If a critical bug arrives while you're finishing an epic, you don't interrupt — you finish the epic first
   - Mitigated by: `--max=1` (stop after current bead) or Ctrl+C (pause cleanly)

3. **Load balancing across epics**
   - If Epic A is huge and Epic B is tiny, Epic B might wait longer
   - Mitigated by: human judgment (don't create unbalanced epics)

---

## Why not make it configurable?

**Simple answer:** Complexity. If affinity is optional (a flag), then:
- Two code paths to test
- Two behaviors to document and support
- Configuration confusion (\"should I use affinity here?\")
- Testing explosion (every scenario in both modes)

**Philosophy:** Core design decisions should be baked in. If your project needs different behavior, override `pick_next_bead()` in your extension (see [../how-to/extend-with-custom-logic.md](../how-to/extend-with-custom-logic.md)).

One-line change in your code beats building knobs nobody uses.

---

## How it plays with other features

### Epic affinity + Blocking bug priority

**Interaction:** Blocking bugs (tier 1) bypass affinity.

**Scenario:**
```
You're finishing Epic A (task-3a of 3).
A critical bug arrives.
/bead-chain picks the bug immediately, not task-3a.
You fix the bug.
After the bug closes, /bead-chain resumes task-3a (affinity restored).
```

**Rationale:** Unblocking work is more important than finishing your current epic. Fairness to downstream work.

### Epic affinity + Blocker gate

**Interaction:** If all siblings are blocked, affinity doesn't apply; we fall back to global queue.

**Scenario:**
```
Epic A has task-2a and task-3a ready, but also task-1a in progress.
You close task-1a.
/bead-chain looks for siblings in Epic A.
  - task-2a is ready ✓ → pick it
You close task-2a.
/bead-chain looks for siblings again.
  - task-3a is ready ✓ → pick it
You close task-3a.
/bead-chain looks for siblings.
  - No more siblings → fall back to global queue
```

**Rationale:** Only ready (unblocked) siblings are considered. Blockers are a hard constraint.

### Epic affinity + Recovery mode

**Interaction:** Recovery mode restores state from the previous session, so affinity *continues* where it left off.

**Scenario:**
```
Session 1:
/bead-chain
You finish task-1a of Epic A.
bead-chain claims task-2a (sibling affinity).
You're working task-2a when Ctrl+C.
task-2a stays in_progress.

Session 2:
/bead-chain
Recovery mode: \"Is task-2a work done?\" → \"No, I'll continue.\"
bead-chain resumes task-2a (state.active_bead is set to Epic A context).
You finish task-2a.
bead-chain claims task-3a (sibling affinity still applies).
```

**Rationale:** Resuming is seamless; context doesn't get lost.

---

## Real-world impact: case study

### Without affinity (queue-ordered)

```bash
Git history:
commit 1a: Add JWT extraction
commit 2b: Create Profile model
commit 1b: Update token revocation
commit 2a: Add form validation
# ...
```

**Cost:** Reviews jump between features. \"Why are auth and profiles changing together?\" (They're not, commits are just mixed.)

### With affinity (epic-ordered)

```bash
Git history:
commit 1a: Add JWT extraction
commit 1b: Update token revocation
commit 1c: Revoke tokens API tests
[PR: \"Epic A: Refactor authentication\"] ← reviewed as one unit

commit 2a: Create Profile model
commit 2b: Add form validation
commit 2c: Profile routes and tests
[PR: \"Epic B: Add user profiles\"] ← reviewed as one unit
```

**Benefit:** Reviewers see coherent feature work. Context is clear. Blame history is readable.

---

## Alternatives considered (why affinity won)

### Alternative 1: Pure global queue (no affinity)

**Pros:** Maximizes priority compliance (always pick the highest-priority ready bead)

**Cons:** Incoherent commits, context thrashing, hard to review and bisect

**Verdict:** Worse than affinity. Used by naive/simple queue drivers.

### Alternative 2: Strict epic blocking (finish entire epic before next)

**Pros:** Forces epic-level coherence

**Cons:** One blocked sibling holds the entire epic. No parallelism across epics. Too rigid.

**Verdict:** Worse than affinity. Overly constraining.

### Alternative 3: Affinity + timeout (stay in epic for N minutes, then switch)

**Pros:** Prevents long stickiness to one epic

**Cons:** Time-based heuristic (bad). Arbitrary. Breaks \"finish what you start\".

**Verdict:** Worse than affinity. Unnecessary complexity.

### Alternative 4: Affinity + \"soft\" preference (sibling has priority boost, not hard rule)

**Pros:** Balances affinity with global priority

**Cons:** Configuration nightmare. Hard to explain. Ambiguous behavior.

**Verdict:** Not worth the complexity. Affinity is cleaner.

**Winner:** Affinity (current design). Simple, clear semantics: finish your epic before jumping.

---

## When affinity is NOT right

**Affinity assumes:**
- Epics are well-scoped (not 50 tasks each)
- Work is mostly sequential (one person per epic at a time)
- Coherent commits are valued over latency
- Urgent new work is rare (or managed via blocking bugs)

**If your project has:**
- Massive epics (100+ tasks) → Affinity keeps you stuck too long
- High parallelism (10 agents) → Affinity limits cross-epic pickup
- Real-time responsiveness critical → Affinity adds latency
- Queue discipline (always global priority) required → Affinity breaks it

**Then:** Disable affinity in your extension (override `pick_next_bead()`).

No shame in it — different projects, different needs. bead-chain's design assumes coherence over pure optimization.

---

## Deeper reading

**Why coherent commits matter:**
- Martin Fowler, \"Refactoring: Improving the Design of Existing Code\" — chapters on code review and blame history
- Git best practices: \"Each commit should be a logical unit of work\"

**Context switching psychology:**
- Cal Newport, \"Deep Work\" — on flow state and interruptions
- Research on programmer productivity (context loss costs 15+ minutes to recover)

**Queue theory (why affinity beats pure priority):**
- Not a scheduling optimization (that's a different domain)
- But a **narrative optimization** (history and coherence, not throughput)

---

## Related

- **How does the picking logic actually work?** See [../reference/architecture.md](../reference/architecture.md).
- **What about blocker priority?** Read [../reference/blocker-gate-logic.md](../reference/blocker-gate-logic.md).
- **Want to change the picking logic?** Check [../how-to/extend-with-custom-logic.md](../how-to/extend-with-custom-logic.md).
"