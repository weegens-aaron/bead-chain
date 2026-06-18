"""br (beads_rust) variant tests — the 5 CLI adaptations (bead_chain-26y).

The bead-chain plugin ships in two independent module trees:

* ``bd/`` — targets the Go ``bd`` CLI (the default everything else here
  tests, imported flat as ``import beads`` via :mod:`conftest`).
* ``br/`` — targets the beads_rust ``br`` CLI (spike bead_chain-5d3).

``br`` differs from ``bd`` in five ways the plugin had to adapt to, and
this module is the dedicated coverage for all five:

1. ``_parse_json_list`` accepts both a bare top-level array (``br ready``)
   and a ``{"issues": [...]}`` object envelope (``br list``).
2. Queue reads (``next_ready`` / ``_list_by_status`` / ``next_ready_in_epic``
   / ``next_blocking_bug``) pass **no** ``--exclude-type`` flag — ``br`` has
   no such flag, so the client-side :func:`is_excluded_type` re-filter is
   the *sole* epic/container gate.
3. ``has_open_children`` fetches the full list (``br list --json``, no
   ``--parent`` flag) and filters to direct children client-side.
4. ``close_guard`` matches both the ``bd`` and ``br`` binary names.
5. The default binary resolves to ``br`` (``DEFAULT_BD_BIN == "br"``).

Why a separate file instead of parametrizing the bd tests
---------------------------------------------------------
The two variants share flat module names (``beads``, ``beads_reads``,
``close_guard``), and the assertions here are about behaviour that
*differs* from the bd variant (absence of flags bd passes, an envelope bd
never emits). Parametrizing would mean asserting opposite things per
param — noisier than a focused br file. :mod:`conftest` already loads
``bd/`` flat as ``beads``; here we load ``br/`` as a *distinct* package
(``code_puppy.plugins.bead_chain_br``) via importlib so its
``from . import beads`` / ``from . import state`` package-relative imports
and facade re-exports resolve cleanly without colliding with the flat bd
modules in ``sys.modules``.

Pure-stdlib seams (``_run_bd`` / ``_parse_json_list``) are stubbed via
the same monkeypatch contract the bd suite uses: the moved read helpers
resolve those names on the live ``beads`` module at call time, so a
``monkeypatch.setattr(br_beads, "_run_bd", ...)`` is honoured.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys

import pytest

_BR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "br"
)
_BR_PKG = "code_puppy.plugins.bead_chain_br"


def _load_br():
    """Load the br/ tree as a real package and return its key modules.

    Mirrors :func:`conftest._register_package` but targets ``br/`` under a
    distinct package name so the br modules don't clobber (or get clobbered
    by) the flat ``beads`` the bd suite imports. Idempotent: re-importing a
    cached package is a no-op.
    """
    if _BR_PKG not in sys.modules:
        # Guarantees code_puppy.plugins exists (close_guard imports
        # code_puppy.messaging). If code_puppy isn't installed the
        # ImportError surfaces — these tests genuinely need it.
        import code_puppy.plugins  # noqa: F401

        spec = importlib.util.spec_from_file_location(
            _BR_PKG,
            os.path.join(_BR_DIR, "__init__.py"),
            submodule_search_locations=[_BR_DIR],
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[_BR_PKG] = module
        spec.loader.exec_module(module)

    beads = importlib.import_module(_BR_PKG + ".beads")
    beads_reads = importlib.import_module(_BR_PKG + ".beads_reads")
    close_guard = importlib.import_module(_BR_PKG + ".close_guard")
    return beads, beads_reads, close_guard


br_beads, br_reads, br_close_guard = _load_br()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RunRecorder:
    """Stub for ``beads._run_bd`` that records every arg tuple it sees.

    ``responses`` may be a single JSON string (returned for every call) or
    a list consumed one-per-call. Each recorded entry is the positional
    ``args`` tuple passed to ``_run_bd`` (the binary itself is resolved
    later inside the real ``_run_bd``, so it never appears here — exactly
    the surface we want to assert flags on).
    """

    def __init__(self, responses):
        self.calls: list[tuple[str, ...]] = []
        self._responses = responses
        self._idx = 0

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if isinstance(self._responses, list):
            resp = self._responses[min(self._idx, len(self._responses) - 1)]
            self._idx += 1
            return resp
        return self._responses

    @property
    def all_args(self) -> list[str]:
        """Flattened list of every positional arg across every call."""
        return [a for call in self.calls for a in call]


def _no_exclude_type(recorder: _RunRecorder) -> bool:
    """True iff no recorded arg mentions ``--exclude-type`` in any form."""
    return not any("--exclude-type" in str(a) for a in recorder.all_args)


# ---------------------------------------------------------------------------
# Adaptation 1: _parse_json_list — bare array AND {"issues": [...]} envelope
# ---------------------------------------------------------------------------


def test_parse_json_list_accepts_bare_array():
    """``br ready`` emits a bare array — must pass straight through."""
    out = br_beads._parse_json_list('[{"id": "a-1"}, {"id": "a-2"}]', "br ready --json")
    assert out == [{"id": "a-1"}, {"id": "a-2"}]


def test_parse_json_list_unwraps_issues_envelope():
    """``br list`` wraps results in ``{"issues": [...], "total": N}``."""
    raw = '{"issues": [{"id": "b-1"}], "total": 1, "filtered": 0}'
    out = br_beads._parse_json_list(raw, "br list --json")
    assert out == [{"id": "b-1"}]


def test_parse_json_list_unwraps_empty_issues_envelope():
    """An empty result set still arrives as an envelope, not a bare ``[]``."""
    out = br_beads._parse_json_list('{"issues": [], "total": 0}', "br list --json")
    assert out == []


def test_parse_json_list_rejects_non_json():
    with pytest.raises(br_beads.BeadsError):
        br_beads._parse_json_list("not json at all", "br ready --json")


def test_parse_json_list_rejects_object_without_issues_list():
    """A dict whose ``issues`` isn't a list is NOT a valid envelope."""
    with pytest.raises(br_beads.BeadsError):
        br_beads._parse_json_list('{"issues": "nope", "total": 1}', "br list --json")


def test_parse_json_list_rejects_scalar_payload():
    with pytest.raises(br_beads.BeadsError):
        br_beads._parse_json_list("42", "br ready --json")


# ---------------------------------------------------------------------------
# Adaptation 2: queue reads omit --exclude-type; is_excluded_type is sole gate
# ---------------------------------------------------------------------------


def test_next_ready_omits_exclude_type_flag(monkeypatch):
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    br_reads.next_ready()
    assert rec.calls == [("ready", "--json")]
    assert _no_exclude_type(rec)


def test_list_in_progress_omits_exclude_type_flag(monkeypatch):
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    br_reads.list_in_progress()
    assert rec.calls == [("list", "--status=in_progress", "--json")]
    assert _no_exclude_type(rec)


def test_list_recoverable_strands_omits_exclude_type_flag(monkeypatch):
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    br_reads.list_recoverable_strands()
    # One comma-status spawn, no --exclude-type.
    assert len(rec.calls) == 1
    assert rec.calls[0][0] == "list"
    assert rec.calls[0][-1] == "--json"
    assert _no_exclude_type(rec)


def test_next_ready_in_epic_omits_exclude_type_flag(monkeypatch):
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    br_reads.next_ready_in_epic("bead_chain-3id")
    assert rec.calls == [("ready", "--parent=bead_chain-3id", "--json")]
    assert _no_exclude_type(rec)


def test_next_blocking_bug_omits_exclude_type_flag(monkeypatch):
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    br_reads.next_blocking_bug()
    # --type is fine (br supports it); --exclude-type must be absent.
    assert rec.calls, "next_blocking_bug should issue at least one query"
    for call in rec.calls:
        assert call[0] == "ready"
        assert any(a.startswith("--type=") for a in call)
    assert _no_exclude_type(rec)


def test_client_side_filter_is_sole_epic_gate_for_next_ready(monkeypatch):
    """With no server-side flag, ``is_excluded_type`` alone must drop epics.

    Simulate ``br ready`` leaking an epic (it has no --exclude-type to
    filter it server-side): next_ready must still skip it client-side and
    return the first non-container bead.
    """
    payload = (
        '[{"id": "epic-1", "issue_type": "epic"},'
        ' {"id": "task-1", "issue_type": "task"}]'
    )
    monkeypatch.setattr(br_beads, "_run_bd", _RunRecorder(payload))
    result = br_reads.next_ready()
    assert result is not None
    assert result["id"] == "task-1"


def test_client_side_filter_drops_all_container_types(monkeypatch):
    """Every container type in EXCLUDED_TYPES is filtered with no flag."""
    beads_json = ", ".join(
        f'{{"id": "{t}-1", "issue_type": "{t}"}}' for t in br_beads.EXCLUDED_TYPES
    )
    monkeypatch.setattr(br_beads, "_run_bd", _RunRecorder(f"[{beads_json}]"))
    # All are containers — frontier must come back empty.
    assert br_reads.next_ready() is None


def test_list_by_status_unwraps_envelope_and_filters_epics(monkeypatch):
    """End-to-end: br list envelope + client-side epic filter together."""
    raw = (
        '{"issues": ['
        '{"id": "epic-9", "issue_type": "epic", "status": "in_progress"},'
        '{"id": "task-9", "issue_type": "task", "status": "in_progress"}'
        '], "total": 2}'
    )
    monkeypatch.setattr(br_beads, "_run_bd", _RunRecorder(raw))
    out = br_reads.list_in_progress()
    assert [b["id"] for b in out] == ["task-9"]


# ---------------------------------------------------------------------------
# Adaptation 3: has_open_children — client-side parent filter, no --parent flag
# ---------------------------------------------------------------------------


def test_has_open_children_omits_parent_flag(monkeypatch):
    """``br list`` has no --parent flag; the full list is fetched instead."""
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    br_reads.has_open_children("bead_chain-3id")
    assert rec.calls == [("list", "--json")]
    assert not any("--parent" in str(a) for a in rec.all_args)


def test_has_open_children_true_when_open_child_present(monkeypatch):
    raw = (
        '[{"id": "c-1", "parent": "p-1", "status": "open"},'
        ' {"id": "c-2", "parent": "p-1", "status": "closed"}]'
    )
    monkeypatch.setattr(br_beads, "_run_bd", _RunRecorder(raw))
    assert br_reads.has_open_children("p-1") is True


def test_has_open_children_false_when_all_children_closed(monkeypatch):
    raw = (
        '[{"id": "c-1", "parent": "p-1", "status": "closed"},'
        ' {"id": "c-2", "parent": "p-1", "status": "closed"}]'
    )
    monkeypatch.setattr(br_beads, "_run_bd", _RunRecorder(raw))
    assert br_reads.has_open_children("p-1") is False


def test_has_open_children_ignores_other_parents(monkeypatch):
    """Client-side parent match must scope to the requested parent only.

    An open child of a *different* parent must not make the gate fire —
    proving the ``parent`` field comparison is the real (and only) scope.
    """
    raw = (
        '[{"id": "c-1", "parent": "other", "status": "open"},'
        ' {"id": "c-2", "parent": "p-1", "status": "closed"}]'
    )
    monkeypatch.setattr(br_beads, "_run_bd", _RunRecorder(raw))
    assert br_reads.has_open_children("p-1") is False


def test_has_open_children_empty_parent_short_circuits(monkeypatch):
    """Falsy parent never spawns a subprocess (documented fast path)."""
    rec = _RunRecorder("[]")
    monkeypatch.setattr(br_beads, "_run_bd", rec)
    assert br_reads.has_open_children("") is False
    assert rec.calls == []


# ---------------------------------------------------------------------------
# Adaptation 4: close_guard matches both bd and br binary names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("binary", ["bd", "br"])
def test_close_guard_matches_close_for_both_binaries(binary):
    match = br_close_guard.detect_premature_close(f"{binary} close bead_chain-1")
    assert match is not None
    assert "close" in match.pattern_name


@pytest.mark.parametrize("binary", ["bd", "br"])
def test_close_guard_matches_update_status_closed_for_both_binaries(binary):
    match = br_close_guard.detect_premature_close(
        f"{binary} update bead_chain-1 --status=closed"
    )
    assert match is not None
    assert "update" in match.pattern_name


@pytest.mark.parametrize("binary", ["bd", "br"])
def test_close_guard_matches_pathed_invocation(binary):
    match = br_close_guard.detect_premature_close(
        f"/usr/local/bin/{binary} close bead_chain-1"
    )
    assert match is not None


@pytest.mark.parametrize("binary", ["bd", "br"])
def test_close_guard_allows_legitimate_claim(binary):
    """``update --claim`` / ``--status=in_progress`` must NOT be blocked."""
    assert br_close_guard.detect_premature_close(f"{binary} update x --claim") is None
    assert (
        br_close_guard.detect_premature_close(f"{binary} update x --status=in_progress")
        is None
    )


def test_close_guard_prefilter_lets_unrelated_commands_through():
    """The cheap substring pre-filter must short-circuit non-bd/br cmds."""
    assert br_close_guard.detect_premature_close("echo hello world") is None
    assert br_close_guard.detect_premature_close("git commit -m 'fix'") is None


def test_close_guard_prefilter_does_not_drop_br_only_commands():
    """Regression: a pre-filter that only checked ``"bd"`` would let every
    ``br close`` through, because ``"br"`` does not contain ``"bd"``."""
    assert "bd" not in "br close x"
    assert br_close_guard.detect_premature_close("br close x") is not None


def test_close_guard_ignores_quoted_br_close():
    """A ``br close`` inside a quoted string is text, not an invocation."""
    assert br_close_guard.detect_premature_close('echo "run: br close cpp-1"') is None


# ---------------------------------------------------------------------------
# Adaptation 5: default binary resolves to br
# ---------------------------------------------------------------------------


def test_default_bin_constant_is_br():
    assert br_beads.DEFAULT_BD_BIN == "br"


def test_bd_bin_resolves_to_br_when_unset(monkeypatch):
    monkeypatch.delenv("BEADS_BIN", raising=False)
    assert br_beads._bd_bin() == "br"


def test_bd_bin_resolves_to_br_when_env_empty(monkeypatch):
    monkeypatch.setenv("BEADS_BIN", "")
    assert br_beads._bd_bin() == "br"


def test_beads_bin_override_still_wins(monkeypatch, tmp_path):
    """An explicit BEADS_BIN override beats the ``br`` default."""
    import stat

    fake = tmp_path / "br-custom"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("BEADS_BIN", str(fake))
    assert br_beads._bd_bin() == str(fake)
