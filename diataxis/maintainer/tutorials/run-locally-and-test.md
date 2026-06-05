# Tutorial: Run bead-chain locally and pass the test suite

A guided first lesson for a newcomer to the `bead_chain` codebase. By the
end you will have the test suite running green on your own machine and will
have watched bead-chain's core logic execute. Follow every step in order;
each one tells you exactly what you should see.

## What you'll build

A working local checkout of the `bead_chain` plugin with all of its unit
and end-to-end tests passing — 49 green dots in your terminal — plus a
quick hands-on peek at the prompt-formatting code that turns a bead into a
`/goal` prompt.

## Prerequisites

- Python 3.10 or newer on your `PATH` (`python --version` prints `3.10`+).
- The `bead_chain` plugin checked out at
  `~/.code_puppy/plugins/bead_chain` (its tests resolve the package from
  that location — see [Modules and public
  functions](../reference/modules-and-functions.md) for the layout).
- `code_puppy` importable in your environment (the lifecycle tests import
  `code_puppy.plugins.wiggum`).

## Step 1 — Move into the plugin directory

```bash
cd ~/.code_puppy/plugins/bead_chain
```

You should now see the source modules when you list the directory:

```bash
ls *.py
```

Expected result — these files are listed:

```
__init__.py  beads.py  close_guard.py  lifecycle.py
prompt.py    register_callbacks.py     state.py
```

## Step 2 — Run the full test suite

```bash
python -m pytest -q
```

Expected result — a row of dots followed by a green summary line:

```
.................................................
49 passed in 15.23s
```

The exact count and timing may differ slightly as the suite grows; the
word you are looking for is **passed** with no failures.

## Step 3 — Run one test file on its own

Pick the blocker-gate test and run just that file:

```bash
python -m pytest tests/test_blocker_gate.py -v
```

Expected result — each test in that file is named and marked `PASSED`.

## Step 4 — Watch a bead become a goal prompt

Move up one directory so Python can import the plugin as a package
(`prompt.py` uses package-relative imports), then format a fake bead in a
single one-off command:

```bash
cd ~/.code_puppy/plugins
python -c "
from bead_chain import prompt
bead = {'id': 'demo-1', 'title': 'Say hello', 'description': 'Print a greeting', 'issue_type': 'task', 'priority': 2}
print(prompt.format_bead_as_goal(bead))
"
```

Expected result — a goal prompt that begins with
`Complete beads issue demo-1: Say hello`, lists the issue metadata, and
ends with the BUG DISCOVERY PROTOCOL section.

## You did it 

You ran the whole suite green, ran a single file in isolation, and saw
bead-chain turn a bead dict into a `/goal` prompt — the exact handoff that
drives the whole chain.

## Where next

- Ready to change behaviour? See the how-to guides:
  [Add a new excluded container bead type](../how-to/add-excluded-bead-type.md),
  [Diagnose and recover a stranded in_progress bead](../how-to/recover-stranded-bead.md),
  or [Extend the close-guard to block another bd command](../how-to/extend-close-guard.md).
- Want the precise map of every flag, env var, and function? See
  [/bead-chain command and configuration](../reference/command-and-configuration.md)
  and [Modules and public functions](../reference/modules-and-functions.md).
- Curious *why* it is built this way? Read
  [Why bead-chain is a queue driver, not a goal engine](../explanation/queue-driver-not-goal-engine.md).