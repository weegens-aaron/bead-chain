"""bead-chain: a beads-driven /goal variant.

Chains your `bd ready` queue into the /goal loop one bead at a time.
"""

# Single source of truth for the plugin version.
#
# Everything that needs a version number MUST derive it from here — there are
# deliberately no hardcoded duplicates anywhere else:
#   * the release zip name (`bead_chain-v<__version__>.zip`),
#   * the git release tag (`v<__version__>`),
#   * runtime introspection (`bead_chain.__version__`).
#
# A shell build script can read it without importing Python by grepping for the
# assignment below and slicing out the quoted value. The format below (a plain,
# single-line string literal that is the ONLY such assignment in this file) is
# part of the contract -- keep it greppable and keep it unique.
__version__ = "0.2.0"

__all__ = ["__version__"]
