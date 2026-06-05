# bead-chain — maintainer documentation

Documentation for **contributors and maintainers** of the `bead_chain`
code-puppy plugin: the beads-driven `/goal` variant that chains your
`bd ready` queue through wiggum's goal loop, one bead at a time.

This documentation is organised around the four
[Diátaxis](https://diataxis.fr/) needs. Pick the section that matches what
you are trying to do right now:

- **[Tutorials](tutorials/)** — learning-oriented lessons. Start here if you
  are new to the codebase and want to get bead-chain running and tested on
  your own machine by following along.
- **[How-to guides](how-to/)** — task-oriented recipes. Use these when you
  already know your way around and need to accomplish a specific maintenance
  job (add an excluded type, recover a stranded bead, extend the close-guard).
- **[Reference](reference/)** — information-oriented descriptions. Consult
  these for the precise, factual map of the `/bead-chain` command, its
  configuration knobs, and the public functions in each module.
- **[Explanation](explanation/)** — understanding-oriented discussion. Read
  these to understand *why* bead-chain is built the way it is: the design
  decisions, the trade-offs, and the bugs that shaped its invariants.

## Where to begin

| If you are… | Go to… |
|-------------|--------|
| Brand new to the repo | [Tutorials](tutorials/) |
| Fixing or extending behaviour | [How-to guides](how-to/) |
| Looking up a flag, env var, or function | [Reference](reference/) |
| Trying to understand a design decision | [Explanation](explanation/) |

## Authoring contract

Every document in this tree is written against the rules in
[`_DiataxisGuide.md`](_DiataxisGuide.md) and tracked in
[`_Manifest.md`](_Manifest.md). If you add docs, classify each item with the
compass first, then follow the per-type template.
