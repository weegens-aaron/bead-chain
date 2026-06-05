# Explanation: Why hooks register lazily so wiggum runs first

## About this topic

bead-chain listens for the `interactive_turn_end` event to decide whether to
close the current bead and grab the next one. wiggum listens for the same
event to decide whether its goal is complete. Both run on every turn, and
the *order* in which they run is not incidental — it is the difference
between bead-chain working and bead-chain misfiring. This piece explains why
bead-chain registers its turn hooks lazily, on first use, instead of at
import time.

## Context and background

code-puppy fires registered callbacks in registration order. wiggum is
loaded at startup, so its `interactive_turn_end` hook is already in the
callback list before any user command runs. bead-chain, by contrast, is
dormant until someone types `/bead-chain`.

The signal bead-chain depends on is `wiggum_state.is_active()`. On each
turn, wiggum decides whether the goal is still in progress and updates that
flag. bead-chain then reads it:

- `wiggum_state.is_active()` is `True` → goal still running → bead-chain
  returns `None` and lets wiggum's continuation win.
- `wiggum_state.is_active()` is `False` → wiggum just finished (judges
  ruled) → bead-chain closes the bead and activates the next one.

For that read to be correct, bead-chain **must run after wiggum on every
turn**. If bead-chain ran first, it would observe wiggum's state from the
*previous* turn and make the wrong call.

## How it fits together

`_ensure_hooks_registered` is the mechanism. It is guarded by a module-level
`_HOOKS_REGISTERED` flag and called from `handle_bead_chain_command` — i.e.
only when the user actually starts a chain, which is necessarily after
startup. By that point wiggum's hook is already registered, so bead-chain's
hook is appended *after* it and therefore runs *after* it each turn.

Note the deliberate asymmetry in registration strategy:

- The two **turn hooks** (`interactive_turn_end`,
  `interactive_turn_cancel`) register lazily, because their correctness
  depends on ordering relative to wiggum.
- The **`run_shell_command` hook** (the close guard) registers *eagerly* at
  module import. It has no ordering dependency on any other plugin, and it
  is a cheap no-op when `state.is_active()` is false, so there is no reason
  to defer it.

This split is documented in both `register_callbacks` and `close_guard` so a
contributor does not "tidy up" the inconsistency by making both eager —
which would reintroduce the ordering bug.

## Why this approach

Lazy registration is, on its face, slightly more complex than registering
everything at import — there is a flag, a guard function, and a comment
explaining the subtlety. So why not register the turn hooks eagerly and
sort the ordering some other way?

- **Eager registration with explicit ordering control.** code-puppy's
  callback system orders by registration, not by priority. There is no
  priority knob to lean on, so the only lever bead-chain has is *when* it
  registers. Lazy registration uses that lever directly.
- **Registering before wiggum.** Impossible to guarantee and backwards
  anyway — bead-chain needs to run *last*, not first.
- **Re-reading wiggum state defensively.** No amount of defensive reading
  fixes observing a stale flag; the only fix is running after the writer.

The cost is one boolean and a one-time guard. The benefit is a correct,
order-dependent handoff with no reliance on a priority feature the callback
system does not have. The lazy approach is the simplest thing that is
actually correct — which is the bar, not the simplest thing that compiles.

## Related

- [/bead-chain command and configuration](../reference/command-and-configuration.md)
  — the registered-callbacks table showing lazy vs eager.
- [Why bead-chain is a queue driver, not a goal engine](queue-driver-not-goal-engine.md)
  — why bead-chain's whole loop hinges on reading wiggum's state correctly.
