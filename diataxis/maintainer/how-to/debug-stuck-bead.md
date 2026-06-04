# How-to: Debug a stuck or stranded bead

## How to debug a stuck or stranded bead

**When to use this:** A bead is stuck in `in_progress`, the chain won't pick up other work, or recovery mode keeps asking the same question. This guide walks you through safe diagnostics and recovery.

---

## Symptoms and diagnosis

### Symptom: Bead stays `in_progress` after hitting Ctrl+C

**This is normal.** bead-chain leaves the bead claimed so it doesn't get re-assigned. Run `/bead-chain` again — it will offer recovery mode.

**Fix:** In recovery mode, answer \"is the work done?\" honestly. If yes, the bead closes. If no, continue working it.

---

### Symptom: `/bead-chain` says \"all beads blocked\" and refuses to pick work

**Root cause:** A blocker dependency is open (likely an open bug that other beads depend on).

**Fix:** Find and fix the blocker:
```bash
bd ready  # This will be empty if nothing is unblocked
bd list --type=bug --status=open  # Find open bugs
bd show <bug-id>  # See what depends on it
```

Once the blocker is closed, `/bead-chain` will resume picking work.

---

### Symptom: Multiple beads are `in_progress` at once

**Root cause:** A previous agent run crashed without cleanup (very rare, but can happen).

**This is serious.** Only ONE bead should be in progress at a time. Fix:

```bash
bd list --status=in_progress
# You'll see multiple beads

# For each one that's NOT actually being worked, revert it:
bd update <bead-id> --status=open
```

Then restart bead-chain normally.

---

### Symptom: Recovery mode keeps asking the same question

**Root cause:** The `/goal` loop isn't advancing (possible infinite loop in the prompt, or judges stuck).

**Fix:** Interrupt the goal prompt:
1. Hit `Ctrl+C` in the current `/goal` session
2. bead-chain will ask recovery questions
3. If the work truly is incomplete, say so and let the human continue manually
4. If you're confident it's done, accept the completion

---

## Safe recovery steps

### Step 1: Check overall queue health

```bash
bd list
```

**Look for:**
- How many beads are `in_progress`? (Should be 0 or 1)
- How many are `open`? (Your queue)
- Any `blocked` beads? (They're waiting for dependencies)

### Step 2: Check the stranded bead details

```bash
bd show <bead-id> --json | jq '.'
```

**Look for:**
- `status` — should be `in_progress`
- `dependencies` — any open `blocks` edges?
- `close_reason` — why was it attempted to close?

### Step 3: Inspect the work itself

If the bead is about code changes:
```bash
git status
git log --oneline -5
```

**Question:** Is the work actually done in your working directory? Or is something incomplete?

### Step 4: Manually reset if needed

If you're confident the work is stale and should be abandoned:
```bash
bd update <bead-id> --status=open
```

This reverts it to the queue so another agent can pick it up fresh.

---

## When to ask for help

If you see:
- ✗ More than 2 beads `in_progress` at once (likely db corruption)
- ✗ `/goal` hanging (not responding to input) for >30s (possible infinite loop)
- ✗ `bd show` returning parse errors or garbage JSON (likely db corruption)

Then **stop** and contact the maintainers. Don't try to force cleanup — corrupted beads state can cascade.

---

## Done — verify

Your queue is healthy when:
- ✓ `bd list` shows **at most one** `in_progress` bead
- ✓ Blocked beads have actual open blockers
- ✓ `/bead-chain` picks work and drives it forward

---

## Related

- **Need to understand blocker logic?** Read [../reference/blocker-gate-logic.md](../reference/blocker-gate-logic.md).
- **Ready to integrate bead-chain?** See [integrate-into-project.md](./integrate-into-project.md).
- **Want to extend bead-chain?** Check [extend-with-custom-logic.md](./extend-with-custom-logic.md).
"