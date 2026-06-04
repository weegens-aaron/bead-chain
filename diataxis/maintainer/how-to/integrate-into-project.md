# How-to: Integrate bead-chain into a project

## How to integrate bead-chain into your project

**When to use this:** You have a beads-enabled project and want bead-chain to automatically drive your task queue without manual `/goal` invocations. This is the recipe for continuous, hands-free bead processing.

---

## Prerequisites

- A project with `.beads/` directory (run `bd init` if you don't have one)
- Code Puppy running
- At least one task or bug bead in your queue (`bd ready` shows items)

---

## Steps

### 1. Verify bead-chain is loaded

Check that the Code Puppy plugin is available:
```bash
/bead-chain --help
```

**Expected:** You see usage info for `/bead-chain`.

### 2. Start the chain in dry-run mode (optional)

If you're nervous, preview what bead-chain will pick up without committing to it:
```bash
bd ready
```

**Expected:** You see a list of open beads. bead-chain will work these in order.

### 3. Start bead-chain with a safety cap

Run the chain, limited to 3 beads:
```bash
/bead-chain --max=3
```

**Why the cap?** Confidence building. Start small, watch the loop complete, then remove the cap.

**Expected:**
- bead-chain picks the first ready bead
- Claims it (`in_progress`)
- Hands it to `/goal`
- On LLM pass, closes it and picks the next
- Repeats 3 times, then stops

### 4. Verify the beads are closed

Check your work:
```bash
bd list --status=closed | grep -c ✓
```

**Expected:** You see \"3\" (or however many beads you processed).

### 5. Run without a cap for steady progress

Once you're confident, remove `--max`:
```bash
/bead-chain
```

This runs until the queue is empty — the natural integration point.

---

## Variations & options

### Stop gracefully anytime

Press `Ctrl+C` to stop. The current bead stays `in_progress` — the next `/bead-chain` run will resume it with a recovery preamble. No work is lost.

### Resume from interruption

If you hit Ctrl+C mid-bead, just re-run:
```bash
/bead-chain
```

bead-chain detects the `in_progress` bead and asks if the work is done. If not, it picks up where you left off.

### Debug a stuck chain

If `/bead-chain` seems hung, check:
```bash
bd list --status=in_progress
```

**What to look for:** Only one bead should be `in_progress`. If there are multiples, see [how-to/debug-stuck-bead.md](./debug-stuck-bead.md).

### Run bead-chain as a scheduled job

You can wire bead-chain into cron or a scheduler to run unattended. The one-at-a-time discipline and automatic closing make this safe (no firehose, no manual babysitting):

```bash
# Run up to 5 beads, then exit cleanly
cd /path/to/project && /bead-chain --max=5 >> /tmp/bead-chain.log 2>&1
```

---

## Done — verify

You've successfully integrated bead-chain. Markers of success:

- ✓ Beads move from `open` → `in_progress` → `closed` automatically
- ✓ No manual `/goal` commands needed (bead-chain runs them)
- ✓ Ctrl+C stops safely without stranding work
- ✓ Recovery mode picks up where you left off

---

## Related

- **Stuck?** See [debug-stuck-bead.md](./debug-stuck-bead.md) for recovery strategies.
- **Want to extend bead-chain?** Read [extend-with-custom-logic.md](./extend-with-custom-logic.md).
- **Understand the architecture?** Check [../reference/architecture.md](../reference/architecture.md).
"