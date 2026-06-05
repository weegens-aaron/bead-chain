# Vendored Skills

This directory holds skills that `bead_chain` depends on, **vendored into version
control** so fixes are committable, pushable, and durable across machine reinstalls.

## Why this exists

Code Puppy skills normally live at `~/.code_puppy/skills/<name>/`, which is **not**
under any git repository. That meant fixes to a skill (e.g. the `md-to-html`
converter that builds this project's Diataxis docs site) could not be committed or
pushed — directly conflicting with the project's "work isn't done until `git push`
succeeds" rule. A Code Puppy reinstall can also wipe `~/.code-puppy-venv` and risk
the skills tree, so unversioned fixes were one reinstall away from oblivion.

See bead `bead_chain-e6o` for the full backstory.

## How it works

- The **source of truth** for the `md-to-html` skill is here:
  `bead_chain/skills/md-to-html/` (tracked + pushed to GitHub).
- The **live skill location** Code Puppy loads from is a symlink pointing here:

  ```
  ~/.code_puppy/skills/md-to-html -> <repo>/skills/md-to-html
  ```

This is a single source of truth — edits go in one place (the repo), are tracked
automatically, and the running Code Puppy picks them up through the symlink. No
copy-paste drift (DRY).

## Recovery after a reinstall / on a new machine

If `~/.code_puppy/skills/md-to-html` is missing (fresh install, wiped skills tree,
or a new machine), recreate the symlink after cloning this repo:

```bash
# from anywhere; adjust the repo path if you cloned elsewhere
ln -sfn "$HOME/.code_puppy/plugins/bead_chain/skills/md-to-html" \
        "$HOME/.code_puppy/skills/md-to-html"
```

Verify:

```bash
cd ~/.code_puppy/skills/md-to-html
git rev-parse --show-toplevel        # -> .../plugins/bead_chain  (NOT "fatal: not a git repository")
python -m pytest tests/ -q           # -> 10 passed
```

If you'd rather not symlink, you can instead copy the directory into place — but
then remember to copy fixes back here before committing, or you'll reintroduce the
exact divergence problem this setup was created to kill.
