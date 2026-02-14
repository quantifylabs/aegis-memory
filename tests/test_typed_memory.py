"""
Aegis Typed Memory Test Suite

Tests for cognitive memory types: episodic, semantic, procedural, control.
Covers: model enums, repository methods, typed router endpoints, backward compat.

Run with: pytest tests/test_typed_memory.py -v
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
# Model Tests — Enum and Column Validation
# ============================================================================

class TestMemoryTypeEnum:
    """Verify new MemoryType enum values exist."""

    def test_episodic_enum_exists(self):
        from models import MemoryType
        assert MemoryType.EPISODIC.value == "episodic"

    def test_semantic_enum_exists(self):
        from models import MemoryType
        assert MemoryType.SEMANTIC.value == "semantic"

    def test_procedural_enum_exists(self):
        from models import MemoryType
        assert MemoryType.PROCEDURAL.value == "procedural"

    def test_control_enum_exists(self):
        from models import MemoryType
        assert MemoryType.CONTROL.value == "control"

    def test_existing_types_unchanged(self):
        """Existing enum values must remain intact for backward compat."""
        from models import MemoryType
        assert MemoryType.STANDARD.value == "standard"
        assert MemoryType.REFLECTION.value == "reflection"
        assert MemoryType.PROGRESS.value == "progress"
        assert MemoryType.FEATURE.value == "feature"
        assert MemoryType.STRATEGY.value == "strategy"

    def test_total_enum_count(self):
        """Should have 9 total memory types (5 original + 4 new)."""
        from models import MemoryType
        assert len(MemoryType) == 9


class TestMemoryModelColumns:
    """Verify new nullable columns on the Memory model."""

    def test_session_id_column_exists(self):
        from models import Memory
        col_names = [c.name for c in Memory.__table__.columns]
        assert "session_id" in col_names

    def test_entity_id_column_exists(self):
        from models import Memory
        col_names = [c.name for c in Memory.__table__.columns]
        assert "entity_id" in col_names

    def test_sequence_number_column_exists(self):
        from models import Memory
        col_names = [c.name for c in Memory.__table__.columns]
        assert "sequence_number" in col_names

    def test_session_id_nullable(self):
        from models import Memory
        col = Memory.__table__.c.session_id
        assert col.nullable is True

    def test_entity_id_nullable(self):
        from models import Memory
        col = Memory.__table__.c.entity_id
        assert col.nullable is True

    def test_sequence_number_nullable(self):
        from models import Memory
        col = Memory.__table__.c.sequence_number
        assert col.nullable is True

    def test_memory_type_column_width(self):
        """memory_type should be String(32) after widening."""
        from models import Memory
        col = Memory.__table__.c.memory_type
        assert col.type.length == 32


class TestMemoryModelIndexes:
    """Verify partial indexes for session and entity queries."""

    def test_session_index_exists(self):
        from models import Memory
        index_names = [idx.name for idx in Memory.__table__.indexes]
        assert "ix_memories_session" in index_names

    def test_entity_index_exists(self):
        from models import Memory
        index_names = [idx.name for idx in Memory.__table__.indexes]
        assert "ix_memories_entity" in index_names


# ============================================================================
# Repository Tests — New Parameters and Methods
# ============================================================================

class TestRepositoryAdd:
    """Verify add() and add_batch() accept typed memory params."""

    @pytest.mark.asyncio
    async def test_add_with_session_id(self, mock_db):
        """add() should accept session_id parameter."""
        with patch("memory_repository.track_latency"), \
             patch("memory_repository.record_operation"):
            from memory_repository import MemoryRepository
            mem = await MemoryRepository.add(
                mock_db,
                project_id="proj",
                content="Discussed pricing",
                embedding=[0.1] * 1536,
                agent_id="sales",
                session_id="conv-42",
                sequence_number=1,
                memory_type="episodic",
            )
            assert mem.session_id == "conv-42"
            assert mem.sequence_number == 1
            assert mem.memory_type == "episodic"

    @pytest.mark.asyncio
    async def test_add_with_entity_id(self, mock_db):
        """add() should accept entity_id parameter."""
        with patch("memory_repository.track_latency"), \
             patch("memory_repository.record_operation"):
            from memory_repository import MemoryRepository
            mem = await MemoryRepository.add(
                mock_db,
                project_id="proj",
                content="User is a Python developer",
                embedding=[0.1] * 1536,
                entity_id="user_123",
                memory_type="semantic",
            )
            assert mem.entity_id == "user_123"
            assert mem.memory_type == "semantic"

    @pytest.mark.asyncio
    async def test_add_batch_reads_typed_fields(self, mock_db):
        """add_batch() should read session_id, entity_id, sequence_number from dicts."""
        with patch("memory_repository.track_latency"), \
             patch("memory_repository.record_operation"):
            from memory_repository import MemoryRepository
            batch = [
                {
                    "project_id": "proj",
                    "content": "Step 1",
                    "embedding": [0.1] * 1536,
                    "session_id": "s1",
                    "entity_id": "e1",
                    "sequence_number": 0,
                    "memory_type": "episodic",
                },
            ]
            mems = await MemoryRepository.add_batch(mock_db, batch)
            assert len(mems) == 1
            assert mems[0].session_id == "s1"
            assert mems[0].entity_id == "e1"
            assert mems[0].sequence_number == 0


class TestRepositorySessionTimeline:
    """Tests for get_session_timeline()."""

    @pytest.mark.asyncio
    async def test_get_session_timeline_returns_list(self, mock_db):
        """get_session_timeline should return a list of memories."""
        from memory_repository import MemoryRepository

        # Mock execute to return empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await MemoryRepository.get_session_timeline(
            mock_db,
            project_id="proj",
            session_id="sess-1",
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_session_timeline_calls_execute(self, mock_db):
        """get_session_timeline should execute a query."""
        from memory_repository import MemoryRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await MemoryRepository.get_session_timeline(
            mock_db,
            project_id="proj",
            session_id="sess-1",
            namespace="default",
        )
        mock_db.execute.assert_called_once()


class TestRepositoryEntityFacts:
    """Tests for get_entity_facts()."""

    @pytest.mark.asyncio
    async def test_get_entity_facts_returns_list(self, mock_db):
        """get_entity_facts should return a list of memories."""
        from memory_repository import MemoryRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await MemoryRepository.get_entity_facts(
            mock_db,
            project_id="proj",
            entity_id="user_123",
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_entity_facts_calls_execute(self, mock_db):
        """get_entity_facts should execute a query."""
        from memory_repository import MemoryRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await MemoryRepository.get_entity_facts(
            mock_db,
            project_id="proj",
            entity_id="user_123",
            namespace="default",
        )
        mock_db.execute.assert_called_once()


# ============================================================================
# Pydantic Model Tests — Typed Memory Request/Response
# ============================================================================

class TestPydanticModels:
    """Validate Pydantic models for typed memory endpoints."""

    def test_episodic_create_requires_session_id(self):
        """EpisodicCreate must require session_id."""
        from api.routers.typed_memory import EpisodicCreate
        with pytest.raises(Exception):
            EpisodicCreate(content="test", agent_id="a")

    def test_episodic_create_valid(self):
        from api.routers.typed_memory import EpisodicCreate
        m = EpisodicCreate(
            content="Discussed pricing",
            agent_id="sales",
            session_id="conv-42",
            sequence_number=1,
        )
        assert m.session_id == "conv-42"
        assert m.sequence_number == 1

    def test_semantic_create_entity_id_optional(self):
        from api.routers.typed_memory import SemanticCreate
        m = SemanticCreate(content="User likes Python")
        assert m.entity_id is None

    def test_semantic_create_with_entity(self):
        from api.routers.typed_memory import SemanticCreate
        m = SemanticCreate(content="User likes Python", entity_id="user_123")
        assert m.entity_id == "user_123"

    def test_procedural_create_stores_steps(self):
        from api.routers.typed_memory import ProceduralCreate
        m = ProceduralCreate(
            content="Use cursor-based pagination",
            agent_id="executor",
            steps=["Init cursor", "Fetch page", "Check has_more"],
        )
        assert m.steps == ["Init cursor", "Fetch page", "Check has_more"]

    def test_control_create_error_pattern(self):
        from api.routers.typed_memory import ControlCreate
        m = ControlCreate(
            content="Never use range() for unknown-length pagination",
            agent_id="reflector",
            error_pattern="pagination_incomplete",
            severity="high",
        )
        assert m.error_pattern == "pagination_incomplete"
        assert m.severity == "high"

    def test_typed_query_requires_memory_types(self):
        from api.routers.typed_memory import TypedQuery
        with pytest.raises(Exception):
            TypedQuery(query="test")

    def test_typed_query_valid(self):
        from api.routers.typed_memory import TypedQuery
        q = TypedQuery(query="pagination strategies", memory_types=["procedural", "control"])
        assert q.memory_types == ["procedural", "control"]

    def test_typed_memory_out_includes_new_fields(self):
        from api.routers.typed_memory import TypedMemoryOut
        fields = TypedMemoryOut.model_fields
        assert "memory_type" in fields
        assert "session_id" in fields
        assert "entity_id" in fields
        assert "sequence_number" in fields


# ============================================================================
# Backward Compatibility Tests
# ============================================================================

class TestBackwardCompatibility:
    """Ensure existing types and APIs are unaffected."""

    def test_existing_memory_types_still_valid(self):
        """Original 5 enum values must still exist."""
        from models import MemoryType
        original_values = {"standard", "reflection", "progress", "feature", "strategy"}
        current_values = {m.value for m in MemoryType}
        assert original_values.issubset(current_values)

    def test_memory_out_includes_new_fields_in_modular_router(self):
        """MemoryOut in memories.py should include typed memory fields."""
        from api.routers.memories import MemoryOut
        fields = MemoryOut.model_fields
        assert "memory_type" in fields
        assert "session_id" in fields
        assert "entity_id" in fields
        assert "sequence_number" in fields

    def test_memory_out_includes_new_fields_in_legacy_routes(self):
        """MemoryOut in routes.py should include typed memory fields."""
        from routes import MemoryOut
        fields = MemoryOut.model_fields
        assert "memory_type" in fields
        assert "session_id" in fields
        assert "entity_id" in fields
        assert "sequence_number" in fields

    def test_memory_query_supports_memory_types_filter(self):
        """MemoryQuery in memories.py should accept memory_types."""
        from api.routers.memories import MemoryQuery
        q = MemoryQuery(query="test", memory_types=["episodic", "semantic"])
        assert q.memory_types == ["episodic", "semantic"]

    def test_memory_query_memory_types_optional(self):
        """memory_types should default to None (no filter)."""
        from api.routers.memories import MemoryQuery
        q = MemoryQuery(query="test")
        assert q.memory_types is None

    def test_legacy_memory_query_supports_memory_types(self):
        """MemoryQuery in routes.py should accept memory_types."""
        from routes import MemoryQuery
        q = MemoryQuery(query="test", memory_types=["standard"])
        assert q.memory_types == ["standard"]

    def test_memory_out_default_memory_type(self):
        """MemoryOut memory_type should default to 'standard'."""
        from api.routers.memories import MemoryOut
        m = MemoryOut(
            id="x", content="test", user_id=None, agent_id=None,
            namespace="default", metadata={}, created_at=datetime.now(timezone.utc),
            scope="global", shared_with_agents=[], derived_from_agents=[],
            coordination_metadata={},
        )
        assert m.memory_type == "standard"


# ============================================================================
# Router Registration Tests
# ============================================================================

class TestRouterRegistration:
    """Verify typed memory router is registered in the app."""

    def test_typed_memory_router_imported(self):
        """typed_memory should be importable from api.routers."""
        from api.routers import typed_memory
        assert hasattr(typed_memory, "router")

    def test_typed_memory_router_has_endpoints(self):
        """Router should have the expected number of routes."""
        from api.routers.typed_memory import router
        paths = [route.path for route in router.routes]
        assert "/episodic" in paths
        assert "/semantic" in paths
        assert "/procedural" in paths
        assert "/control" in paths
        assert "/query" in paths
        assert "/episodic/session/{session_id}" in paths
        assert "/semantic/entity/{entity_id}" in paths


# ============================================================================
# Migration Tests
# ============================================================================

class TestMigration:
    """Verify migration 0003 structure."""

    def test_migration_file_importable(self):
        """Migration 0003 should be importable."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "alembic" / "versions"))
        import importlib
        mod = importlib.import_module("0003_typed_memory")
        assert mod.revision == "0003"
        assert mod.down_revision == "0002"

    def test_migration_has_upgrade_and_downgrade(self):
        sys.path.insert(0, str(Path(__file__).parent.parent / "alembic" / "versions"))
        import importlib
        mod = importlib.import_module("0003_typed_memory")
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
