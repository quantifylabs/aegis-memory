"""
Aegis ACL Test Suite

Tests for normalized memory_shared_agents join table (Phase 3).
Covers: dual-write, join-based read, backfill, cascade delete.

Run with: pytest tests/test_acl.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone

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


class TestMemorySharedAgentModel:
    """Tests for MemorySharedAgent ORM model."""

    def test_model_exists(self):
        """MemorySharedAgent model should be importable."""
        from models import MemorySharedAgent
        assert MemorySharedAgent.__tablename__ == "memory_shared_agents"

    def test_model_has_composite_pk(self):
        """MemorySharedAgent should have composite PK (memory_id, shared_agent_id)."""
        from models import MemorySharedAgent
        pk_cols = [c.name for c in MemorySharedAgent.__table__.primary_key.columns]
        assert "memory_id" in pk_cols
        assert "shared_agent_id" in pk_cols

    def test_model_has_project_and_namespace(self):
        """MemorySharedAgent should have project_id and namespace columns."""
        from models import MemorySharedAgent
        col_names = [c.name for c in MemorySharedAgent.__table__.columns]
        assert "project_id" in col_names
        assert "namespace" in col_names

    def test_memory_relationship_exists(self):
        """Memory model should have shared_agents relationship."""
        from models import Memory
        assert hasattr(Memory, "shared_agents"), "Memory.shared_agents relationship missing"


class TestDualWrite:
    """Tests for dual-write on add/add_batch."""

    @pytest.mark.asyncio
    async def test_dual_write_creates_join_rows_on_add(self, mock_db):
        """Adding a memory with shared_with_agents should write to join table."""
        from models import MemorySharedAgent

        # Track what gets added to the session
        added_objects = []
        original_add = mock_db.add

        def track_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        mock_db.add = track_add

        with patch("memory_repository.track_latency"), \
             patch("memory_repository.record_operation"):
            from memory_repository import MemoryRepository

            await MemoryRepository.add(
                mock_db,
                project_id="proj-1",
                content="Test content",
                embedding=[0.1] * 1536,
                agent_id="agent-a",
                namespace="default",
                shared_with_agents=["agent-b", "agent-c"],
                scope="agent-shared",
            )

        # Should have added Memory + 2 MemorySharedAgent rows
        msa_rows = [o for o in added_objects if isinstance(o, MemorySharedAgent)]
        assert len(msa_rows) == 2
        agents = {r.shared_agent_id for r in msa_rows}
        assert agents == {"agent-b", "agent-c"}

    @pytest.mark.asyncio
    async def test_no_join_rows_when_no_shared_agents(self, mock_db):
        """Adding a memory without shared_with_agents should not create join rows."""
        from models import MemorySharedAgent

        added_objects = []
        original_add = mock_db.add

        def track_add(obj):
            added_objects.append(obj)
            return original_add(obj)

        mock_db.add = track_add

        with patch("memory_repository.track_latency"), \
             patch("memory_repository.record_operation"):
            from memory_repository import MemoryRepository

            await MemoryRepository.add(
                mock_db,
                project_id="proj-1",
                content="Private content",
                embedding=[0.1] * 1536,
                agent_id="agent-a",
                namespace="default",
            )

        msa_rows = [o for o in added_objects if isinstance(o, MemorySharedAgent)]
        assert len(msa_rows) == 0


class TestJoinTableACL:
    """Tests for join-table based ACL in queries."""

    def test_join_table_acl_uses_subquery(self):
        """semantic_search should use MemorySharedAgent subquery, not JSONB."""
        import inspect
        from memory_repository import MemoryRepository

        source = inspect.getsource(MemoryRepository.semantic_search)
        assert "MemorySharedAgent" in source, "semantic_search should reference MemorySharedAgent"
        # Should NOT use JSONB containment for ACL
        assert "shared_with_agents, JSONB" not in source or "cast(Memory.shared_with_agents" not in source

    def test_playbook_query_uses_join_table(self):
        """query_playbook should use MemorySharedAgent subquery."""
        import inspect
        from ace_repository import ACERepository

        source = inspect.getsource(ACERepository.query_playbook)
        assert "MemorySharedAgent" in source, "query_playbook should reference MemorySharedAgent"


class TestBackfillScript:
    """Tests for the ACL backfill script."""

    def test_backfill_module_importable(self):
        """backfill_acl module should be importable."""
        import backfill_acl
        assert hasattr(backfill_acl, "backfill")

    def test_backfill_is_async(self):
        """backfill() should be an async function."""
        import asyncio
        import backfill_acl
        assert asyncio.iscoroutinefunction(backfill_acl.backfill)


class TestCascadeDelete:
    """Tests for cascade delete behavior."""

    def test_memory_shared_agents_has_cascade_fk(self):
        """memory_shared_agents FK should have CASCADE delete."""
        from models import MemorySharedAgent

        fk = None
        for col in MemorySharedAgent.__table__.columns:
            if col.name == "memory_id":
                for fk_obj in col.foreign_keys:
                    fk = fk_obj
                    break

        assert fk is not None, "memory_id should have a foreign key"
        assert fk.ondelete == "CASCADE", "FK should cascade on delete"

    def test_memory_relationship_cascades(self):
        """Memory.shared_agents relationship should cascade all, delete-orphan."""
        from models import Memory
        from sqlalchemy.orm import RelationshipProperty

        # Get the relationship
        mapper = Memory.__mapper__
        rel = mapper.relationships.get("shared_agents")
        assert rel is not None, "shared_agents relationship missing"
        assert "delete-orphan" in str(rel.cascade) or "delete" in str(rel.cascade)
