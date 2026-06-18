"""Keyless local-mode behaviour for the MCP server (Task 8.1-A).

These tests assert the server is usable with **no** ``AEGIS_API_KEY`` and **no**
backend: the deterministic ``inspect``/``replay`` tools work, while memory-runtime
tools degrade with a clear message instead of crashing. Hosted mode is unchanged.

Mirrors ``test_mcp_server.py``: exercises the module-level ``run_*`` helpers directly
(version-robust across FastMCP releases) rather than the decorated tools.
"""

from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from aegis_memory.mcp_server import (
    AddMemoryInput,
    FeatureStatusInput,
    InspectProjectInput,
    QueryMemoryInput,
    ReplayAttackInput,
    _LOCAL_DEGRADE_MSG,
    _hosted_required,
    _resolve_mode,
    run_feature_status_resource,
    run_inspect_project,
    run_replay_attack,
)

FIXTURES = Path(__file__).parent / "fixtures" / "inspect"


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("AEGIS_API_KEY", raising=False)


class TestModeResolution:
    def test_local_when_key_unset(self, no_key):
        assert _resolve_mode() == "local"

    def test_hosted_when_key_set(self, monkeypatch):
        monkeypatch.setenv("AEGIS_API_KEY", "sk-test")
        assert _resolve_mode() == "hosted"

    def test_hosted_required_payload_is_non_fatal(self):
        payload = _hosted_required()
        assert payload["mode"] == "local"
        assert payload["error"] == "hosted_required"
        assert payload["message"] == _LOCAL_DEGRADE_MSG


class TestKeylessTools:
    def test_inspect_project_runs_with_no_key(self, no_key):
        """A local tool call succeeds with no key and no server."""
        out = run_inspect_project(InspectProjectInput(path=str(FIXTURES), write=False))
        assert out["mode"] == "local"
        assert isinstance(out["score"]["score"], int)
        assert out["finding_count"] >= 1
        assert out["findings"], "expected at least one finding from the inspect fixtures"
        assert out["run_dir"] is None  # write=False -> nothing written

    def test_inspect_respects_max_findings(self, no_key):
        out = run_inspect_project(
            InspectProjectInput(path=str(FIXTURES), write=False, max_findings=1)
        )
        assert len(out["findings"]) <= 1
        # finding_count reports the true total even when the returned list is capped.
        assert out["finding_count"] >= len(out["findings"])

    def test_replay_attack_blocks_poison_with_no_key(self, no_key):
        out = run_replay_attack(ReplayAttackInput())
        assert out["mode"] == "local"
        assert out["attack"] == "memory-poisoning"
        # Unguarded baseline stores the poison; Aegis blocks it.
        assert out["without_aegis"]["stored"] is True
        assert out["with_aegis"]["allowed"] is False

    def test_replay_unknown_attack_is_non_fatal(self, no_key):
        # ReplayAttackInput's Literal blocks invalid values at construction; the guard
        # inside run_replay_attack is belt-and-braces. Bypass validation to exercise it.
        model = ReplayAttackInput.model_construct(attack="sql-injection")
        result = run_replay_attack(model)
        assert result["error"] == "unknown_attack"
        assert result["mode"] == "local"


class TestFeatureStatusMode:
    def test_local_mode_surfaces_degrade(self):
        out = run_feature_status_resource(None, FeatureStatusInput(), mode="local")
        assert out["mode"] == "local"
        assert out["message"] == _LOCAL_DEGRADE_MSG
        assert out["summary"] == {"total": 0, "passing": 0, "failing": 0, "in_progress": 0}
        assert out["features"] == []


class TestInputSchemas:
    def test_inspect_defaults(self):
        m = InspectProjectInput()
        assert m.path == "." and m.write is False and m.max_findings == 20

    def test_memory_inputs_still_validate(self):
        # Memory tool schemas are unchanged by local mode.
        AddMemoryInput(content="hi")
        QueryMemoryInput(query="hi")
