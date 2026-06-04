# Tutorial: Setting up bead-chain

## What you'll build

You'll set up a bead-chain plugin in a fresh beads-enabled project, verify it works end-to-end, and run one complete bead through the chain to confirm the integration is solid.

**Happy path:** Install → verify → run → see a bead close successfully.

---

## Prerequisites

- A working `bd` (beads) CLI installation on your PATH
- A project already initialized with `bd init` (a `.beads/` directory exists)
- Python 3.10+
- Code Puppy running (for the `/bead-chain` command)

If you don't have a project yet, run:
```bash
mkdir my-beads-project && cd my-beads-project
bd init
```

---

## Step 1: Verify `bd` is working

Run a quick health check:
```bash
bd ready --help
```

**Expected result:** You see the `bd` help output with no errors.

---

## Step 2: Create a test bead

Create a simple task bead to run through the chain:
```bash
bd create --type=task --priority=2 --title=\"Test: hello world\"
```

**Expected result:** Output shows a new bead ID (e.g., `test-1abc`). Note this ID.

---

## Step 3: Start bead-chain

In your Code Puppy environment, run:
```
/bead-chain --max=1
```

**Expected result:**
- bead-chain picks up your test bead
- Claims it as `in_progress`
- Hands it to the `/goal` mode (wiggum)
- You see the goal prompt for your bead

---

## Step 4: Complete the goal

When `/goal` prompts you, write a simple completion:
```
I've set up bead-chain successfully. Test bead working.
```

**Expected result:**
- The LLM judges evaluate and accept the completion
- bead-chain closes the bead automatically
- The chain prints \"✓ 1 bead(s) completed\"

---

## Step 5: Verify the bead is closed

Confirm the work stuck:
```bash
bd show <bead-id>
```

**Expected result:** Status shows `closed` (or `✓` in `bd list` output).

---

## You did it!

You've successfully set up and run bead-chain end-to-end. The chain:
1. ✓ Found your bead
2. ✓ Claimed it safely
3. ✓ Handed it to `/goal` for LLM judgment
4. ✓ Closed it automatically on pass

---

## Where next

- **Want to run multiple beads?** See [how-to/integrate-into-project.md](../how-to/integrate-into-project.md) to wire bead-chain into your daily workflow.
- **Stuck or in_progress?** Check [how-to/debug-stuck-bead.md](../how-to/debug-stuck-bead.md) for recovery strategies.
- **How does bead-chain actually work?** Read [reference/architecture.md](../reference/architecture.md) to understand the modules and state machine.
- **Why does epic affinity matter?** See [explanation/epic-affinity-philosophy.md](../explanation/epic-affinity-philosophy.md) for the design rationale.
"