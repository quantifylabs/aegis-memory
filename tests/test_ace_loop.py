"""
Aegis ACE Loop Test Suite

Tests for the formalized ACE loop: run tracking, auto-feedback, curation.
Covers: AceRun model, repository methods, route endpoints, SDK client.

Run with: pytest tests/test_ace_loop.py -v
"""

import pytest
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure server directory is on path
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


# ============================================================================
# Model Tests — AceRun Model and New Event Types
# ============================================================================

class TestAceRunModel:
    """Verify AceRun model and new MemoryEventType values."""

    def test_ace_run_table_name(self):
        from models import AceRun
        assert AceRun.__tablename__ == "ace_runs"

    def test_ace_run_columns_exist(self):
        from models import AceRun
        col_names = [c.name for c in AceRun.__table__.columns]
        expected = [
            "id", "project_id", "run_id", "agent_id", "task_type",
            "namespace", "status", "success", "evaluation", "logs",
            "memory_ids_used", "reflection_ids", "started_at",
            "completed_at", "created_at", "updated_at",
        ]
        for col in expected:
            assert col in col_names, f"Column {col} missing from AceRun"

    def test_ace_run_indexes(self):
        from models import AceRun
        index_names = [idx.name for idx in AceRun.__table__.indexes]
        assert "ix_ace_runs_project_run" in index_names
        assert "ix_ace_runs_project_agent" in index_names
        assert "ix_ace_runs_project_task_type" in index_names

    def test_ace_run_project_run_unique(self):
        from models import AceRun
        for idx in AceRun.__table__.indexes:
            if idx.name == "ix_ace_runs_project_run":
                assert idx.unique is True

    def test_run_started_event_type(self):
        from models import MemoryEventType
        assert MemoryEventType.RUN_STARTED.value == "run_started"

    def test_run_completed_event_type(self):
        from models import MemoryEventType
        assert MemoryEventType.RUN_COMPLETED.value == "run_completed"

    def test_curated_event_type(self):
        from models import MemoryEventType
        assert MemoryEventType.CURATED.value == "curated"

    def test_event_type_total_count(self):
        from models import MemoryEventType
        assert len(MemoryEventType) == 10


# ============================================================================
# Repository Tests — Run Operations
# ============================================================================

class TestCreateRun:
    """Test ACERepository.create_run()."""

    @pytest.mark.asyncio
    async def test_create_run(self, mock_db):
        """Create a run, verify status='running'."""
        from ace_repository import ACERepository

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            # Mock the refresh to set attributes
            async def set_attrs(run):
                run.status = "running"
                run.run_id = "test-run-1"
            mock_db.refresh = AsyncMock(side_effect=set_attrs)

            run = await ACERepository.create_run(
                mock_db,
                project_id="proj1",
                run_id="test-run-1",
                agent_id="agent-1",
                task_type="code-review",
                namespace="default",
                memory_ids_used=["mem1", "mem2"],
            )

            assert run.run_id == "test-run-1"
            assert run.status == "running"
            mock_db.add.assert_called_once()
            mock_events.create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_run_defaults(self, mock_db):
        """Create run with minimal args uses correct defaults."""
        from ace_repository import ACERepository

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            async def set_attrs(run):
                pass
            mock_db.refresh = AsyncMock(side_effect=set_attrs)

            run = await ACERepository.create_run(
                mock_db,
                project_id="proj1",
                run_id="test-run-2",
            )

            assert run.memory_ids_used == []
            assert run.reflection_ids == []
            assert run.evaluation == {}
            assert run.logs == {}


class TestGetRun:
    """Test ACERepository.get_run()."""

    @pytest.mark.asyncio
    async def test_get_run(self, mock_db):
        """Retrieve run by run_id."""
        from ace_repository import ACERepository
        from models import AceRun

        mock_run = MagicMock(spec=AceRun)
        mock_run.run_id = "test-run-1"
        mock_run.status = "running"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        run = await ACERepository.get_run(mock_db, "test-run-1", "proj1")
        assert run is not None
        assert run.run_id == "test-run-1"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, mock_db):
        """Return None for missing run."""
        from ace_repository import ACERepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        run = await ACERepository.get_run(mock_db, "nonexistent", "proj1")
        assert run is None


class TestCompleteRun:
    """Test ACERepository.complete_run()."""

    @pytest.mark.asyncio
    async def test_complete_run_success(self, mock_db):
        """Complete with success=True, verify auto-votes helpful."""
        from ace_repository import ACERepository
        from models import AceRun

        mock_run = MagicMock(spec=AceRun)
        mock_run.run_id = "test-run-1"
        mock_run.project_id = "proj1"
        mock_run.agent_id = "agent-1"
        mock_run.namespace = "default"
        mock_run.memory_ids_used = ["mem1", "mem2"]
        mock_run.task_type = "code-review"
        mock_run.status = "running"
        mock_run.success = None
        mock_run.reflection_ids = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            with patch.object(ACERepository, "vote_memory", new_callable=AsyncMock) as mock_vote:
                mock_vote.return_value = MagicMock()

                run = await ACERepository.complete_run(
                    mock_db,
                    run_id="test-run-1",
                    project_id="proj1",
                    success=True,
                    evaluation={"score": 0.95},
                    auto_vote=True,
                    auto_reflect=True,
                )

                assert run is not None
                assert run.status == "completed"
                assert run.success is True
                # Should have voted helpful on 2 memories
                assert mock_vote.call_count == 2
                for call in mock_vote.call_args_list:
                    assert call.kwargs.get("vote") == "helpful" or call[1].get("vote") == "helpful"

    @pytest.mark.asyncio
    async def test_complete_run_failure(self, mock_db):
        """Complete with success=False, verify auto-votes harmful."""
        from ace_repository import ACERepository
        from models import AceRun

        mock_run = MagicMock(spec=AceRun)
        mock_run.run_id = "test-run-1"
        mock_run.project_id = "proj1"
        mock_run.agent_id = "agent-1"
        mock_run.namespace = "default"
        mock_run.memory_ids_used = ["mem1"]
        mock_run.task_type = "debugging"
        mock_run.status = "running"
        mock_run.success = None
        mock_run.reflection_ids = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            with patch.object(ACERepository, "vote_memory", new_callable=AsyncMock) as mock_vote:
                mock_vote.return_value = MagicMock()

                run = await ACERepository.complete_run(
                    mock_db,
                    run_id="test-run-1",
                    project_id="proj1",
                    success=False,
                    evaluation={"error": "timeout", "error_pattern": "timeout_error"},
                    auto_vote=True,
                    auto_reflect=True,
                )

                assert run is not None
                assert run.status == "failed"
                assert run.success is False
                # Should have voted harmful on 1 memory
                assert mock_vote.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_run_no_auto_vote(self, mock_db):
        """auto_vote=False skips voting."""
        from ace_repository import ACERepository
        from models import AceRun

        mock_run = MagicMock(spec=AceRun)
        mock_run.run_id = "test-run-1"
        mock_run.project_id = "proj1"
        mock_run.agent_id = "agent-1"
        mock_run.namespace = "default"
        mock_run.memory_ids_used = ["mem1", "mem2"]
        mock_run.task_type = None
        mock_run.status = "running"
        mock_run.success = None
        mock_run.reflection_ids = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            with patch.object(ACERepository, "vote_memory", new_callable=AsyncMock) as mock_vote:
                run = await ACERepository.complete_run(
                    mock_db,
                    run_id="test-run-1",
                    project_id="proj1",
                    success=True,
                    auto_vote=False,
                    auto_reflect=False,
                )

                assert run is not None
                # No votes should have been cast
                mock_vote.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_run_not_found(self, mock_db):
        """Return None for missing run."""
        from ace_repository import ACERepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        run = await ACERepository.complete_run(
            mock_db,
            run_id="nonexistent",
            project_id="proj1",
            success=True,
        )
        assert run is None


# ============================================================================
# Repository Tests — Curation
# ============================================================================

class TestCurate:
    """Test ACERepository.curate()."""

    @pytest.mark.asyncio
    async def test_curate_identifies_effective(self, mock_db):
        """Curation finds high-effectiveness entries."""
        from ace_repository import ACERepository
        from models import Memory, MemoryType

        mem1 = MagicMock(spec=Memory)
        mem1.id = "mem1"
        mem1.content = "Use cursor pagination for large datasets"
        mem1.memory_type = MemoryType.STRATEGY.value
        mem1.bullet_helpful = 5
        mem1.bullet_harmful = 0
        mem1.get_effectiveness_score.return_value = 0.83
        mem1.metadata_json = {}

        mem2 = MagicMock(spec=Memory)
        mem2.id = "mem2"
        mem2.content = "A different strategy"
        mem2.memory_type = MemoryType.STRATEGY.value
        mem2.bullet_helpful = 1
        mem2.bullet_harmful = 0
        mem2.get_effectiveness_score.return_value = 0.5
        mem2.metadata_json = {}

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mem1, mem2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            result = await ACERepository.curate(
                mock_db,
                project_id="proj1",
                namespace="default",
            )

            assert len(result["promoted"]) == 2
            assert result["promoted"][0]["id"] == "mem1"
            assert result["promoted"][0]["effectiveness_score"] == 0.83

    @pytest.mark.asyncio
    async def test_curate_flags_ineffective(self, mock_db):
        """Curation flags low-effectiveness entries."""
        from ace_repository import ACERepository
        from models import Memory, MemoryType

        mem_bad = MagicMock(spec=Memory)
        mem_bad.id = "bad1"
        mem_bad.content = "A bad strategy that causes issues"
        mem_bad.memory_type = MemoryType.STRATEGY.value
        mem_bad.bullet_helpful = 0
        mem_bad.bullet_harmful = 5
        mem_bad.get_effectiveness_score.return_value = -0.83
        mem_bad.metadata_json = {}

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mem_bad]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            result = await ACERepository.curate(
                mock_db,
                project_id="proj1",
                namespace="default",
                min_effectiveness_threshold=-0.3,
            )

            assert len(result["flagged"]) == 1
            assert result["flagged"][0]["id"] == "bad1"


# ============================================================================
# Observability Tests
# ============================================================================

class TestOperationNames:
    """Verify new operation names are added."""

    def test_run_create_operation(self):
        from observability import OperationNames
        assert OperationNames.MEMORY_RUN_CREATE == "memory_run_create"

    def test_run_get_operation(self):
        from observability import OperationNames
        assert OperationNames.MEMORY_RUN_GET == "memory_run_get"

    def test_run_complete_operation(self):
        from observability import OperationNames
        assert OperationNames.MEMORY_RUN_COMPLETE == "memory_run_complete"

    def test_playbook_agent_operation(self):
        from observability import OperationNames
        assert OperationNames.MEMORY_PLAYBOOK_AGENT == "memory_playbook_agent"

    def test_curate_operation(self):
        from observability import OperationNames
        assert OperationNames.MEMORY_CURATE == "memory_curate"


# ============================================================================
# Route Model Tests — Pydantic Validation
# ============================================================================

class TestRoutePydanticModels:
    """Verify Pydantic request/response models."""

    def test_run_create_model(self):
        from routes_ace import RunCreate
        body = RunCreate(run_id="run-1", agent_id="agent-1", task_type="debug")
        assert body.run_id == "run-1"
        assert body.namespace == "default"

    def test_run_complete_model(self):
        from routes_ace import RunComplete
        body = RunComplete(success=True, evaluation={"score": 0.9})
        assert body.success is True
        assert body.auto_vote is True
        assert body.auto_reflect is True

    def test_run_complete_no_auto(self):
        from routes_ace import RunComplete
        body = RunComplete(success=False, auto_vote=False, auto_reflect=False)
        assert body.auto_vote is False
        assert body.auto_reflect is False

    def test_agent_playbook_request(self):
        from routes_ace import AgentPlaybookRequest
        body = AgentPlaybookRequest(query="pagination", agent_id="executor")
        assert body.task_type is None
        assert body.top_k == 20

    def test_curate_request(self):
        from routes_ace import CurateRequest
        body = CurateRequest(namespace="prod", agent_id="agent-1")
        assert body.top_k == 10
        assert body.min_effectiveness_threshold == -0.3

    def test_run_response_model(self):
        from routes_ace import RunResponse
        now = datetime.now(timezone.utc)
        resp = RunResponse(
            run_id="r1", agent_id="a1", task_type="t1", namespace="ns",
            status="running", success=None, evaluation={}, logs={},
            memory_ids_used=[], reflection_ids=[], started_at=now,
            completed_at=None, created_at=now, updated_at=now,
        )
        assert resp.status == "running"

    def test_curation_response_model(self):
        from routes_ace import CurationResponse, CurationEntryResponse, ConsolidationCandidate
        resp = CurationResponse(
            promoted=[CurationEntryResponse(
                id="m1", content="test", memory_type="strategy",
                effectiveness_score=0.5, bullet_helpful=3,
                bullet_harmful=1, total_votes=4,
            )],
            flagged=[],
            consolidation_candidates=[],
        )
        assert len(resp.promoted) == 1


# ============================================================================
# SDK Client Tests — Dataclass Parsing
# ============================================================================

class TestSDKDataclasses:
    """Test SDK dataclass parsing."""

    def test_parse_run_data(self):
        from aegis_memory.client import _parse_run_data
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "run_id": "run-1",
            "status": "running",
            "success": None,
            "agent_id": "agent-1",
            "task_type": "debug",
            "namespace": "default",
            "evaluation": {},
            "logs": {},
            "memory_ids_used": ["m1"],
            "reflection_ids": [],
            "started_at": now,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        result = _parse_run_data(data)
        assert result.run_id == "run-1"
        assert result.status == "running"
        assert result.memory_ids_used == ["m1"]

    def test_parse_curation_data(self):
        from aegis_memory.client import _parse_curation_data
        data = {
            "promoted": [{
                "id": "m1", "content": "good", "memory_type": "strategy",
                "effectiveness_score": 0.8, "bullet_helpful": 4,
                "bullet_harmful": 0, "total_votes": 4,
            }],
            "flagged": [],
            "consolidation_candidates": [{
                "memory_id_a": "m2", "memory_id_b": "m3",
                "content_a": "abc", "content_b": "abc",
                "reason": "similar_content_prefix",
            }],
        }
        result = _parse_curation_data(data)
        assert len(result.promoted) == 1
        assert result.promoted[0].id == "m1"
        assert len(result.consolidation_candidates) == 1

    def test_run_result_dataclass(self):
        from aegis_memory.client import RunResult
        now = datetime.now(timezone.utc)
        r = RunResult(
            run_id="r1", status="completed", success=True,
            agent_id="a1", task_type="t1", namespace="ns",
            evaluation={"score": 1.0}, logs={},
            memory_ids_used=["m1"], reflection_ids=[],
            started_at=now, completed_at=now,
            created_at=now, updated_at=now,
        )
        assert r.success is True

    def test_curation_result_dataclass(self):
        from aegis_memory.client import CurationResult, CurationEntry, ConsolidationCandidate
        r = CurationResult(
            promoted=[CurationEntry(
                id="m1", content="test", memory_type="strategy",
                effectiveness_score=0.5, bullet_helpful=3,
                bullet_harmful=1, total_votes=4,
            )],
            flagged=[],
            consolidation_candidates=[],
        )
        assert len(r.promoted) == 1


# ============================================================================
# SDK Client Tests — HTTP Methods
# ============================================================================

class TestSDKStartAndCompleteRun:
    """Test SDK client start_run and complete_run."""

    def test_sdk_start_run(self):
        from aegis_memory.client import AegisClient
        import httpx
        from unittest.mock import MagicMock

        now = datetime.now(timezone.utc).isoformat()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "run_id": "run-1", "status": "running", "success": None,
            "agent_id": "agent-1", "task_type": "debug", "namespace": "default",
            "evaluation": {}, "logs": {}, "memory_ids_used": ["m1"],
            "reflection_ids": [], "started_at": now, "completed_at": None,
            "created_at": now, "updated_at": now,
        }
        mock_response.raise_for_status = MagicMock()

        client = AegisClient(api_key="test-key")
        client.client = MagicMock()
        client.client.post = MagicMock(return_value=mock_response)

        result = client.start_run("run-1", "agent-1", memory_ids_used=["m1"])
        assert result.run_id == "run-1"
        assert result.status == "running"

    def test_sdk_complete_run(self):
        from aegis_memory.client import AegisClient
        from unittest.mock import MagicMock

        now = datetime.now(timezone.utc).isoformat()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "run_id": "run-1", "status": "completed", "success": True,
            "agent_id": "agent-1", "task_type": None, "namespace": "default",
            "evaluation": {"score": 0.9}, "logs": {}, "memory_ids_used": ["m1"],
            "reflection_ids": [], "started_at": now, "completed_at": now,
            "created_at": now, "updated_at": now,
        }
        mock_response.raise_for_status = MagicMock()

        client = AegisClient(api_key="test-key")
        client.client = MagicMock()
        client.client.post = MagicMock(return_value=mock_response)

        result = client.complete_run("run-1", success=True, evaluation={"score": 0.9})
        assert result.status == "completed"
        assert result.success is True

    def test_sdk_get_run(self):
        from aegis_memory.client import AegisClient
        from unittest.mock import MagicMock

        now = datetime.now(timezone.utc).isoformat()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "run_id": "run-1", "status": "running", "success": None,
            "agent_id": None, "task_type": None, "namespace": "default",
            "evaluation": {}, "logs": {}, "memory_ids_used": [],
            "reflection_ids": [], "started_at": now, "completed_at": None,
            "created_at": now, "updated_at": now,
        }
        mock_response.raise_for_status = MagicMock()

        client = AegisClient(api_key="test-key")
        client.client = MagicMock()
        client.client.get = MagicMock(return_value=mock_response)

        result = client.get_run("run-1")
        assert result.run_id == "run-1"


class TestSDKPlaybookForAgent:
    """Test SDK client get_playbook_for_agent."""

    def test_sdk_get_playbook_for_agent(self):
        from aegis_memory.client import AegisClient
        from unittest.mock import MagicMock

        now = datetime.now(timezone.utc).isoformat()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "entries": [{
                "id": "e1", "content": "strategy text", "memory_type": "strategy",
                "effectiveness_score": 0.8, "bullet_helpful": 4,
                "bullet_harmful": 0, "error_pattern": None,
                "created_at": now,
            }],
            "query_time_ms": 15.2,
        }
        mock_response.raise_for_status = MagicMock()

        client = AegisClient(api_key="test-key")
        client.client = MagicMock()
        client.client.post = MagicMock(return_value=mock_response)

        result = client.get_playbook_for_agent("agent-1", query="pagination")
        assert len(result.entries) == 1
        assert result.entries[0].effectiveness_score == 0.8


class TestSDKCurate:
    """Test SDK client curate."""

    def test_sdk_curate(self):
        from aegis_memory.client import AegisClient
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "promoted": [{
                "id": "m1", "content": "good", "memory_type": "strategy",
                "effectiveness_score": 0.9, "bullet_helpful": 5,
                "bullet_harmful": 0, "total_votes": 5,
            }],
            "flagged": [{
                "id": "m2", "content": "bad", "memory_type": "reflection",
                "effectiveness_score": -0.5, "bullet_helpful": 1,
                "bullet_harmful": 3, "total_votes": 4,
            }],
            "consolidation_candidates": [],
        }
        mock_response.raise_for_status = MagicMock()

        client = AegisClient(api_key="test-key")
        client.client = MagicMock()
        client.client.post = MagicMock(return_value=mock_response)

        result = client.curate(namespace="prod")
        assert len(result.promoted) == 1
        assert len(result.flagged) == 1
        assert result.promoted[0].effectiveness_score == 0.9


# ============================================================================
# Migration Tests
# ============================================================================

class TestMigration0004:
    """Verify migration 0004 structure."""

    def _load_migration(self):
        import importlib.util
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0004_ace_runs.py"
        spec = importlib.util.spec_from_file_location("migration_0004", str(migration_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_migration_revision(self):
        m = self._load_migration()
        assert m.revision == "0004"

    def test_migration_down_revision(self):
        m = self._load_migration()
        assert m.down_revision == "0003"

    def test_migration_has_upgrade(self):
        m = self._load_migration()
        assert callable(m.upgrade)

    def test_migration_has_downgrade(self):
        m = self._load_migration()
        assert callable(m.downgrade)


# ============================================================================
# Integration Tests — Full ACE Loop
# ============================================================================

class TestFullACELoop:
    """End-to-end ACE loop: create run -> complete -> verify feedback -> query playbook."""

    @pytest.mark.asyncio
    async def test_full_ace_loop(self, mock_db):
        """Full ACE loop: create -> complete -> auto-vote -> curation."""
        from ace_repository import ACERepository
        from models import AceRun, Memory, MemoryType

        # Step 1: Create run
        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            async def refresh_run(run):
                pass
            mock_db.refresh = AsyncMock(side_effect=refresh_run)

            run = await ACERepository.create_run(
                mock_db,
                project_id="proj1",
                run_id="loop-run-1",
                agent_id="agent-1",
                task_type="code-review",
                memory_ids_used=["strategy-1"],
            )
            assert run.status == "running"

        # Step 2: Complete run with success
        mock_run = MagicMock(spec=AceRun)
        mock_run.run_id = "loop-run-1"
        mock_run.project_id = "proj1"
        mock_run.agent_id = "agent-1"
        mock_run.namespace = "default"
        mock_run.memory_ids_used = ["strategy-1"]
        mock_run.task_type = "code-review"
        mock_run.status = "running"
        mock_run.success = None
        mock_run.reflection_ids = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            with patch.object(ACERepository, "vote_memory", new_callable=AsyncMock) as mock_vote:
                mock_vote.return_value = MagicMock()

                completed = await ACERepository.complete_run(
                    mock_db,
                    run_id="loop-run-1",
                    project_id="proj1",
                    success=True,
                    evaluation={"score": 0.95},
                )

                assert completed.status == "completed"
                assert completed.success is True
                # Auto-voted helpful on strategy-1
                mock_vote.assert_called_once()
                call_kwargs = mock_vote.call_args
                assert "helpful" in str(call_kwargs)

        # Step 3: Curate
        mem_good = MagicMock(spec=Memory)
        mem_good.id = "strategy-1"
        mem_good.content = "Use cursor pagination for large datasets"
        mem_good.memory_type = MemoryType.STRATEGY.value
        mem_good.bullet_helpful = 5
        mem_good.bullet_harmful = 0
        mem_good.get_effectiveness_score.return_value = 0.83
        mem_good.metadata_json = {}

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mem_good]
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result2)

        with patch("ace_repository.EventRepository") as mock_events:
            mock_events.create_event = AsyncMock()

            curation = await ACERepository.curate(
                mock_db,
                project_id="proj1",
            )

            assert len(curation["promoted"]) == 1
            assert curation["promoted"][0]["id"] == "strategy-1"


# ============================================================================
# Exports Tests
# ============================================================================

class TestExports:
    """Verify new types are exported from aegis_memory package."""

    def test_run_result_exported(self):
        from aegis_memory import RunResult
        assert RunResult is not None

    def test_curation_result_exported(self):
        from aegis_memory import CurationResult
        assert CurationResult is not None

    def test_curation_entry_exported(self):
        from aegis_memory import CurationEntry
        assert CurationEntry is not None

    def test_consolidation_candidate_exported(self):
        from aegis_memory import ConsolidationCandidate
        assert ConsolidationCandidate is not None

    def test_version_bumped(self):
        from aegis_memory import __version__
        assert __version__ == "1.3.1"
