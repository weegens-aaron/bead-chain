# How-to: Diagnose and recover a stranded in_progress bead

Recover work that a crashed or cancelled `/bead-chain` run left claimed and
`in_progress`. Use this when `bd ready` looks empty or wrong, or when you
suspect a previous run died mid-bead.

This guide assumes familiarity with the codebase and `bd`. For the *why*
behind the recovery design, see [Why bead-chain respects blocks at claim
time](../explanation/work-time-blocker-gate.md).

## When to use this

- A `/bead-chain` run was interrupted (Ctrl+C, crash, SIGKILL, reboot).
- `bd ready` returns nothing but work clearly remains.
- You see a startup warning about `found N in_progress beads`.

## Steps

1. List what is currently claimed:

   ```bash
   bd list --status=in_progress
   ```

   bead-chain's discipline is one bead at a time, so normally you expect
   zero or one entry here. More than one means residue from a hard crash.

2. Inspect the stranded bead to understand its state:

   ```bash
   bd show <id>
   ```

   Check its `dependencies` for any open `blocks` edges — a stranded bead
   with open blockers must not be re-driven (it would only fail at
   `bd close`).

3. Re-run the chain. bead-chain recovers automatically — you do not close
   or revert by hand in the normal case:

   ```
   /bead-chain
   ```

   At startup `enforce_single_in_progress()` picks the head in_progress
   bead and re-prompts the agent with the recovery preamble ("assess
   current state before doing new work"). Any *extra* in_progress beads are
   left for subsequent recovery-tier iterations within the same run.

4. If a stranded bead is *blocked*, bead-chain reverts it to `open`
   automatically (via `_unblocked_in_progress`), pushing it back behind its
   blockers. You will see a warning naming the blocking issue ids.

## Variations and options

- **Manually unstick a single bead** (e.g. you want it back in the queue
  without running the chain):

  ```bash
  bd update <id> --status=open
  ```

  This is exactly what `revert_to_open` does internally.

- **A stranded epic appears** (an upstream filter leak). bead-chain refuses
  to close it and reverts it to open, then stops so you can investigate.
  See [Add a new excluded container bead
  type](add-excluded-bead-type.md) if a new container type is leaking.

## Done — verify

- `bd list --status=in_progress` shows at most the single bead the chain is
  actively driving (or nothing, once the chain has moved on).
- The recovered bead's partial work is intact on disk — recovery never
  discards changes; it re-pairs them with their bead.

## Related

- [/bead-chain command and configuration](../reference/command-and-configuration.md)
  — the recovery tier and startup probe order.
- [Modules and public functions](../reference/modules-and-functions.md) —
  `enforce_single_in_progress`, `revert_to_open`, `is_recovery_bead`.
