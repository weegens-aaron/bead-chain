# How-to: Add a new excluded container bead type

Teach bead-chain to never *drive* a new container-style bead type (the way
it already refuses to drive `epic`). Use this when beads gains another
purely-organisational type — for example `milestone` — that groups child
work items but is not itself doable work.

This guide assumes you know the codebase layout and can run the test suite
(see [Run bead-chain locally and pass the test
suite](../tutorials/run-locally-and-test.md) if not).

## When to use this

- A new bd issue type appears that is a *container*, not a leaf work item.
- bead-chain is attempting to claim/drive instances of it (you will see a
  `cannot close epic: N open child issue(s)`-style halt, or the equivalent
  for your new type).

## Steps

1. Open `beads.py` and find the `EXCLUDED_TYPES` tuple:

   ```python
   EXCLUDED_TYPES: tuple[str, ...] = ("epic",)
   ```

2. Add your new type. Keep the values lowercase — the comparison in
   `is_excluded_type` lowercases `issue_type` before matching:

   ```python
   EXCLUDED_TYPES: tuple[str, ...] = ("epic", "milestone")
   ```

3. That single edit is enough. `_exclude_type_arg()` builds the
   `--exclude-type=epic,milestone` CLI argument from this tuple, so every
   query helper (`next_ready`, `list_in_progress`, `next_ready_in_epic`,
   `next_blocking_bug`) filters the new type server-side, and
   `is_excluded_type` re-filters it client-side as defence in depth.

4. Add a regression test asserting your type is excluded. A minimal check:

   ```python
   from beads import is_excluded_type
   assert is_excluded_type({"issue_type": "milestone"}) is True
   assert is_excluded_type({"issue_type": "MILESTONE"}) is True  # case-insensitive
   ```

5. Run the suite:

   ```bash
   python -m pytest -q
   ```

## Variations and options

- **Different casing from upstream bd.** No action needed — the match is
  case-insensitive, so `"Milestone"` and `"MILESTONE"` are both caught.
- **A type that is sometimes a leaf.** Do not add it here. `EXCLUDED_TYPES`
  is for types that are *never* doable work. Mixed types belong in the
  ready-queue selection logic, not the exclusion filter.

## Done — verify

- `python -m pytest -q` is green.
- A quick manual probe shows the type filtered:

  ```bash
  python -c "from beads import is_excluded_type; print(is_excluded_type({'issue_type':'milestone'}))"
  # prints: True
  ```

## Related

- [Modules and public functions](../reference/modules-and-functions.md) —
  the precise contract of `EXCLUDED_TYPES`, `is_excluded_type`, and
  `_exclude_type_arg`.
- [Why bead-chain is a queue driver, not a goal
  engine](../explanation/queue-driver-not-goal-engine.md) — why containers
  are out of scope by design.
