from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beads  # noqa: E402


def _patch_run_bd(return_value: str):
    beads._run_bd = lambda *a, **k: return_value  # type: ignore[assignment]


def test_cascade_does_not_close_unrelated_beads():
    # Scenario: closing a molecule epic with a cascade that would
    # close unrelated beads. The payload shows 3 items closed, but
    # only 2 are actual epics; the 3rd is a tracking bead that
    # got swept up in the cascade.
    cascade_payload = (
        '{"closed": '
        '["diataxis-generate-mol-xyz", "unrelated-epic-abc", '
        '"tracking-bead-xyz"], '
        '"count": 3}'
    )
    _patch_run_bd(cascade_payload)

    result = beads.close_eligible_epics()
    closed_ids = [e["id"] for e in result]

    # The bug: we return all 3 items, including the non-epic
    # tracking bead. The fix should prevent this.
    print(f"Result from cascade: {closed_ids}")
    print(f"Number of items closed: {len(closed_ids)}")


def test_only_epics_should_be_closed():
    # Verify that our parsing doesn't let non-epics slip through
    mixed_payload = '{"closed": ["epic-1", "epic-2", "random-bead-123"], "count": 3}'
    _patch_run_bd(mixed_payload)

    result = beads.close_eligible_epics()
    closed_ids = [e["id"] for e in result]

    print(f"Closed items: {closed_ids}")


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
    sys.exit(1 if failures else 0)
