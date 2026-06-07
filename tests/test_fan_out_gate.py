"""Unit tests for the fan-out gate (bead_chain-9sc).

``lifecycle.py`` implements :func:`_has_fan_out_gate_issue` to detect
fan-out gates (beads with ``waits_for: children-of(spawner_id)`` where
the spawner has unclosed children). These tests pin the logic against
the gate-detection model.

**Context:** Beads with ``waits_for: children-of(...)`` are invisible to
both ``bd ready`` and ``bd blocked`` in the beads CLI (upstream bug),
so bead-chain must detect them at claim time and refuse to drive them.

These tests import directly from ``lifecycle.py`` via conftest setup.
"""

from __future__ import annotations

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure code_puppy.plugins.bead_chain is importable
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = "code_puppy.plugins.bead_chain"

if _PKG not in sys.modules:
    import code_puppy.plugins  # noqa: F401

    spec = importlib.util.spec_from_file_location(
        _PKG,
        os.path.join(_PLUGIN_DIR, "__init__.py"),
        submodule_search_locations=[_PLUGIN_DIR],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PKG] = module
    spec.loader.exec_module(module)

# Now import from the plugin
from code_puppy.plugins.bead_chain import beads, lifecycle  # noqa: E402


def _patch_show(bead: dict | None):
    """Stub beads.show() to return a fixed bead record."""
    lifecycle.show = lambda _id: bead  # type: ignore[assignment]


def _patch_run_bd_and_parse(issues: list[dict]):
    """Stub beads._run_bd() and beads._parse_json_list() to return a bead list.

    This simulates ``bd list --json`` returning the given issues.
    """
    import json

    raw_json = json.dumps(issues)

    def mock_run_bd(*args, **kwargs):  # noqa: ARG001
        return raw_json

    def mock_parse_json(raw, context):  # noqa: ARG001
        return json.loads(raw)

    beads._run_bd = mock_run_bd  # type: ignore[assignment]
    beads._parse_json_list = mock_parse_json  # type: ignore[assignment]


def test_no_waits_for_field_is_unblocked():
    """A bead with no waits_for field has no gate issue."""
    _patch_show({"id": "x", "status": "open"})
    _patch_run_bd_and_parse([])
    assert lifecycle._has_fan_out_gate_issue("x") is False


def test_waits_for_non_children_of_format_is_unblocked():
    """A bead with waits_for in a different format has no gate issue."""
    _patch_show({"id": "x", "waits_for": "other-format"})
    _patch_run_bd_and_parse([])
    assert lifecycle._has_fan_out_gate_issue("x") is False


def test_waits_for_malformed_children_of_is_unblocked():
    """A malformed waits_for children-of(...) soft-fails to unblocked."""
    # Missing closing paren
    _patch_show({"id": "x", "waits_for": "children-of(spawner_id"})
    _patch_run_bd_and_parse([])
    assert lifecycle._has_fan_out_gate_issue("x") is False

    # Empty spawner id
    _patch_show({"id": "x", "waits_for": "children-of()"})
    _patch_run_bd_and_parse([])
    assert lifecycle._has_fan_out_gate_issue("x") is False


def test_spawner_has_unclosed_children_is_blocked():
    """A bead gated on spawner with unclosed children has a gate issue."""
    _patch_show(
        {
            "id": "finalize",
            "status": "open",
            "waits_for": "children-of(discover)",
        }
    )
    # Spawner exists and has an unclosed child
    _patch_run_bd_and_parse(
        [
            {"id": "discover", "status": "closed"},
            {"id": "discover.1", "parent": "discover", "status": "open"},
        ]
    )
    assert lifecycle._has_fan_out_gate_issue("finalize") is True


def test_spawner_has_multiple_unclosed_children_is_blocked():
    """Multiple unclosed children -> still blocked (any one blocks)."""
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "children-of(discover)",
        }
    )
    _patch_run_bd_and_parse(
        [
            {"id": "discover", "status": "closed"},
            {"id": "discover.1", "parent": "discover", "status": "open"},
            {"id": "discover.2", "parent": "discover", "status": "open"},
            {"id": "discover.3", "parent": "discover", "status": "in_progress"},
        ]
    )
    assert lifecycle._has_fan_out_gate_issue("finalize") is True


def test_all_children_closed_is_unblocked():
    """When all children are closed, gate is satisfied; no gate issue."""
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "children-of(discover)",
        }
    )
    _patch_run_bd_and_parse(
        [
            {"id": "discover", "status": "closed"},
            {"id": "discover.1", "parent": "discover", "status": "closed"},
            {"id": "discover.2", "parent": "discover", "status": "closed"},
        ]
    )
    assert lifecycle._has_fan_out_gate_issue("finalize") is False


def test_no_children_means_gate_satisfied():
    """If spawner exists but has no children, gate is satisfied."""
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "children-of(discover)",
        }
    )
    # Only the spawner, no children listed
    _patch_run_bd_and_parse([{"id": "discover", "status": "closed"}])
    assert lifecycle._has_fan_out_gate_issue("finalize") is False


def test_spawner_does_not_exist_soft_fails():
    """If spawner can't be found, soft-fail to unblocked."""
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "children-of(nonexistent)",
        }
    )

    # Stub show() to raise BeadsError when called with nonexistent
    def mock_show(bead_id):
        if bead_id == "finalize":
            return {"id": "finalize", "waits_for": "children-of(nonexistent)"}
        if bead_id == "nonexistent":
            raise beads.BeadsError("not found")
        return None

    lifecycle.show = mock_show  # type: ignore[assignment]
    _patch_run_bd_and_parse([])

    # Should soft-fail to False (assume gate is satisfied)
    assert lifecycle._has_fan_out_gate_issue("finalize") is False


def test_bead_does_not_exist_soft_fails():
    """If the gated bead itself doesn't exist, soft-fail to unblocked."""
    # Mock show to return None
    lifecycle.show = lambda _id: None  # type: ignore[assignment]
    _patch_run_bd_and_parse([])

    assert lifecycle._has_fan_out_gate_issue("missing") is False


def test_empty_bead_id_soft_fails():
    """Empty bead_id soft-fails to unblocked (no gate issue)."""
    _patch_show({"id": "", "waits_for": "children-of(x)"})
    _patch_run_bd_and_parse([])
    assert lifecycle._has_fan_out_gate_issue("") is False


def test_case_sensitivity_in_children_of_format():
    """Verify children-of() format is case-sensitive (exact match)."""
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "CHILDREN-OF(discover)",  # uppercase
        }
    )
    _patch_run_bd_and_parse([{"id": "discover", "status": "closed"}])
    # Should NOT match because format check is case-sensitive
    assert lifecycle._has_fan_out_gate_issue("finalize") is False


def test_waits_for_as_non_string_type():
    """waits_for as non-string (e.g., dict) soft-fails."""
    _patch_show(
        {
            "id": "x",
            "waits_for": {"type": "children-of", "spawner": "y"},  # dict, not string
        }
    )
    _patch_run_bd_and_parse([])
    assert lifecycle._has_fan_out_gate_issue("x") is False


def test_gate_unblock_transition():
    """Regression test: gate becomes satisfied when last child closes.

    This test captures the unblock transition: we query the current state
    and find the gate satisfied because all children are now closed.
    """
    # Initial state: finalize waits on discover, discover.1 and discover.2 are open
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "children-of(discover)",
        }
    )
    _patch_run_bd_and_parse(
        [
            {"id": "discover", "status": "closed"},
            {"id": "discover.1", "parent": "discover", "status": "open"},
            {"id": "discover.2", "parent": "discover", "status": "open"},
        ]
    )
    assert lifecycle._has_fan_out_gate_issue("finalize") is True

    # Transition: discover.1 and discover.2 both close
    _patch_show(
        {
            "id": "finalize",
            "waits_for": "children-of(discover)",
        }
    )
    _patch_run_bd_and_parse(
        [
            {"id": "discover", "status": "closed"},
            {"id": "discover.1", "parent": "discover", "status": "closed"},
            {"id": "discover.2", "parent": "discover", "status": "closed"},
        ]
    )
    assert lifecycle._has_fan_out_gate_issue("finalize") is False


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:
                failures += 1
                print(f"ERROR {name}: {exc}")
    sys.exit(1 if failures else 0)
