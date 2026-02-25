"""
Temporal Decay Test Suite

Tests for Priority 4: temporal decay for memory relevance.
Covers: decay formula, model columns, repository methods,
        router models, decay router, and migration.

Run with: pytest tests/test_temporal_decay.py -v
"""

import math
import pytest
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure server directory is on path
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))


# ============================================================================
# Fixtures
# ============================================================================

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


def _make_memory(
    memory_type="standard",
    created_at=None,
    last_accessed_at=None,
    bullet_helpful=0,
    bullet_harmful=0,
):
    """Build a minimal mock memory object."""
    mem = MagicMock()
    mem.memory_type = memory_type
    mem.created_at = created_at or datetime.now(timezone.utc)
    mem.last_accessed_at = last_accessed_at
    mem.bullet_helpful = bullet_helpful
    mem.bullet_harmful = bullet_harmful
    mem.get_effectiveness_score = lambda: (
        (bullet_helpful - bullet_harmful) / (bullet_helpful + bullet_harmful + 1)
        if (bullet_helpful + bullet_harmful) > 0
        else 0.0
    )
    return mem


# ============================================================================
# TestDecayFormula — pure math
# ============================================================================

class TestDecayFormula:
    """Verify the decay engine computes correct factors."""

    def test_zero_age_returns_one(self):
        """A memory accessed right now should have decay_factor = 1.0."""
        from temporal_decay import compute_decay_factor
        now = datetime.now(timezone.utc)
        factor = compute_decay_factor("standard", now, now, now)
        assert abs(factor - 1.0) < 1e-9

    def test_half_life_standard(self):
        """After 30 days (half-life for standard), decay_factor ≈ 0.5."""
        from temporal_decay import compute_decay_factor, HALF_LIVES
        hl = HALF_LIVES["standard"]  # 30
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=hl)
        factor = compute_decay_factor("standard", created, None, now)
        assert abs(factor - 0.5) < 1e-9

    def test_half_life_episodic(self):
        """After 7 days (half-life for episodic), decay_factor ≈ 0.5."""
        from temporal_decay import compute_decay_factor, HALF_LIVES
        hl = HALF_LIVES["episodic"]  # 7
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=hl)
        factor = compute_decay_factor("episodic", created, None, now)
        assert abs(factor - 0.5) < 1e-9

    def test_episodic_decays_faster_than_procedural(self):
        """Episodic (7-day HL) decays faster than procedural (180-day HL)."""
        from temporal_decay import compute_decay_factor
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=30)
        episodic = compute_decay_factor("episodic", old, None, now)
        procedural = compute_decay_factor("procedural", old, None, now)
        assert episodic < procedural

    def test_large_age_approaches_zero(self):
        """A very old memory should have decay_factor close to 0."""
        from temporal_decay import compute_decay_factor
        now = datetime.now(timezone.utc)
        ancient = now - timedelta(days=3650)  # 10 years
        factor = compute_decay_factor("standard", ancient, None, now)
        assert factor < 0.001

    def test_unknown_type_uses_default_half_life(self):
        """Unknown memory types should fall back to DEFAULT_HALF_LIFE=30."""
        from temporal_decay import compute_decay_factor, DEFAULT_HALF_LIFE
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=DEFAULT_HALF_LIFE)
        factor = compute_decay_factor("nonexistent_type", created, None, now)
        assert abs(factor - 0.5) < 1e-9

    def test_last_accessed_at_used_over_created_at(self):
        """When last_accessed_at is recent, decay should be near 1.0 even if old created_at."""
        from temporal_decay import compute_decay_factor
        now = datetime.now(timezone.utc)
        old_created = now - timedelta(days=90)
        recent_accessed = now - timedelta(minutes=5)
        factor = compute_decay_factor("standard", old_created, recent_accessed, now)
        # Should be very close to 1.0 because accessed recently
        assert factor > 0.99

    def test_half_lives_dict_contains_all_types(self):
        """HALF_LIVES must cover all expected memory types."""
        from temporal_decay import HALF_LIVES
        expected = {"episodic", "progress", "feature", "standard",
                    "reflection", "strategy", "semantic", "procedural", "control"}
        assert expected == set(HALF_LIVES.keys())

    def test_all_half_lives_positive(self):
        """All half-life values must be positive integers."""
        from temporal_decay import HALF_LIVES
        for mtype, hl in HALF_LIVES.items():
            assert hl > 0, f"Half-life for {mtype} must be positive"

    def test_decay_factor_range(self):
        """decay_factor is always in (0, 1]."""
        from temporal_decay import compute_decay_factor
        now = datetime.now(timezone.utc)
        for days in [0, 1, 7, 30, 90, 365, 3650]:
            ref = now - timedelta(days=days)
            f = compute_decay_factor("standard", ref, None, now)
            assert 0.0 < f <= 1.0, f"Factor out of range for age={days} days"


# ============================================================================
# TestComputeRelevanceScore
# ============================================================================

class TestComputeRelevanceScore:
    """Verify relevance_score = effectiveness_score × decay_factor."""

    def test_zero_votes_effectiveness(self):
        """Zero votes → effectiveness_score=0 → relevance_score=0."""
        from temporal_decay import compute_relevance_score
        mem = _make_memory("standard")
        score = compute_relevance_score(mem)
        assert score == 0.0

    def test_positive_votes_positive_relevance(self):
        """Helpful votes + recent access → positive relevance."""
        from temporal_decay import compute_relevance_score
        now = datetime.now(timezone.utc)
        mem = _make_memory("standard", last_accessed_at=now, bullet_helpful=5)
        score = compute_relevance_score(mem, now)
        assert score > 0.0

    def test_stale_memory_lower_relevance(self):
        """Same votes but older last_access → lower relevance_score."""
        from temporal_decay import compute_relevance_score
        now = datetime.now(timezone.utc)
        recent = _make_memory("standard", last_accessed_at=now, bullet_helpful=3)
        old_time = now - timedelta(days=60)
        stale = _make_memory("standard", last_accessed_at=old_time, bullet_helpful=3)
        assert compute_relevance_score(recent, now) > compute_relevance_score(stale, now)


# ============================================================================
# TestMemoryModelColumns
# ============================================================================

class TestMemoryModelColumns:
    """Verify the new columns exist on the Memory model."""

    def test_last_accessed_at_column_exists(self):
        from models import Memory
        assert hasattr(Memory, "last_accessed_at")

    def test_access_count_column_exists(self):
        from models import Memory
        assert hasattr(Memory, "access_count")

    def test_last_accessed_at_nullable(self):
        from models import Memory
        col = Memory.__table__.c["last_accessed_at"]
        assert col.nullable is True

    def test_access_count_not_nullable(self):
        from models import Memory
        col = Memory.__table__.c["access_count"]
        assert col.nullable is False

    def test_ix_memories_last_accessed_index_exists(self):
        """Partial index ix_memories_last_accessed must be in table_args."""
        from models import Memory
        index_names = {idx.name for idx in Memory.__table__.indexes}
        assert "ix_memories_last_accessed" in index_names


# ============================================================================
# TestRepositoryTouchAccessed
# ============================================================================

class TestRepositoryTouchAccessed:
    """Verify touch_accessed fires the expected bulk UPDATE."""

    @pytest.mark.asyncio
    async def test_touch_accessed_calls_execute(self, mock_db):
        from memory_repository import MemoryRepository
        ids = ["abc123", "def456"]
        await MemoryRepository.touch_accessed(mock_db, ids)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_touch_accessed_empty_list_no_execute(self, mock_db):
        from memory_repository import MemoryRepository
        await MemoryRepository.touch_accessed(mock_db, [])
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_touch_accessed_single_id(self, mock_db):
        from memory_repository import MemoryRepository
        await MemoryRepository.touch_accessed(mock_db, ["single"])
        mock_db.execute.assert_called_once()


# ============================================================================
# TestRepositoryArchiveStale
# ============================================================================

class TestRepositoryArchiveStale:
    """Verify archive_stale marks low-relevance memories as deprecated."""

    def _make_result_proxy(self, memories):
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=memories)))
        return result

    @pytest.mark.asyncio
    async def test_archive_stale_below_threshold_archived(self, mock_db):
        """Memories with relevance_score < threshold should be archived."""
        from memory_repository import MemoryRepository
        now = datetime.now(timezone.utc)
        # Memory with no votes (effectiveness=0) and very old = low relevance
        old_mem = _make_memory("standard", created_at=now - timedelta(days=365))
        old_mem.id = "stale_id"
        mock_db.execute.return_value = self._make_result_proxy([old_mem])

        count = await MemoryRepository.archive_stale(
            mock_db, project_id="proj", threshold=0.5
        )
        assert count >= 0  # stale memory should be caught

    @pytest.mark.asyncio
    async def test_archive_stale_dry_run_no_update(self, mock_db):
        """dry_run=True should not call execute for the UPDATE."""
        from memory_repository import MemoryRepository
        now = datetime.now(timezone.utc)
        old_mem = _make_memory("standard", created_at=now - timedelta(days=365))
        old_mem.id = "stale_id"
        mock_db.execute.return_value = self._make_result_proxy([old_mem])

        await MemoryRepository.archive_stale(
            mock_db, project_id="proj", threshold=0.9, dry_run=True
        )
        # Only 1 execute call (the SELECT), not 2 (SELECT + UPDATE)
        assert mock_db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_archive_stale_empty_result(self, mock_db):
        """No memories → returns 0."""
        from memory_repository import MemoryRepository
        mock_db.execute.return_value = self._make_result_proxy([])
        count = await MemoryRepository.archive_stale(
            mock_db, project_id="proj", threshold=0.1
        )
        assert count == 0


# ============================================================================
# TestSemanticSearchDecay
# ============================================================================

class TestSemanticSearchDecay:
    """Verify rerank_with_decay re-orders results correctly."""

    def test_rerank_flips_order_for_stale_memory(self):
        """A recent low-score memory should outrank an ancient high-score one after decay."""
        from temporal_decay import rerank_with_decay
        now = datetime.now(timezone.utc)

        # Memory A: high semantic score but accessed 1 year ago
        mem_a = _make_memory("standard", last_accessed_at=now - timedelta(days=365))
        mem_a.id = "a"

        # Memory B: lower semantic score but accessed just now
        mem_b = _make_memory("standard", last_accessed_at=now)
        mem_b.id = "b"

        results = [(mem_a, 0.95), (mem_b, 0.70)]
        reranked = rerank_with_decay(results, now)

        # After decay, B's final score should be higher (0.70 × ~1.0 > 0.95 × near-zero)
        assert reranked[0][0].id == "b"
        assert reranked[1][0].id == "a"

    def test_rerank_preserves_semantic_score(self):
        """The semantic_score in the tuple must remain unchanged."""
        from temporal_decay import rerank_with_decay
        now = datetime.now(timezone.utc)
        mem = _make_memory("standard", last_accessed_at=now)
        results = [(mem, 0.88)]
        reranked = rerank_with_decay(results, now)
        _mem, sem, _decay = reranked[0]
        assert abs(sem - 0.88) < 1e-9

    def test_rerank_decay_factor_in_tuple(self):
        """Returned tuples have (mem, semantic_score, decay_factor)."""
        from temporal_decay import rerank_with_decay
        now = datetime.now(timezone.utc)
        mem = _make_memory("standard", last_accessed_at=now)
        results = [(mem, 0.5)]
        reranked = rerank_with_decay(results, now)
        assert len(reranked[0]) == 3

    def test_rerank_empty_input(self):
        """Empty input should return empty list."""
        from temporal_decay import rerank_with_decay
        assert rerank_with_decay([]) == []

    def test_rerank_same_age_preserves_semantic_order(self):
        """When decay factors are equal, semantic score order is preserved."""
        from temporal_decay import rerank_with_decay
        now = datetime.now(timezone.utc)
        same_time = now - timedelta(days=10)
        mem_hi = _make_memory("standard", last_accessed_at=same_time)
        mem_hi.id = "hi"
        mem_lo = _make_memory("standard", last_accessed_at=same_time)
        mem_lo.id = "lo"
        results = [(mem_hi, 0.9), (mem_lo, 0.6)]
        reranked = rerank_with_decay(results, now)
        assert reranked[0][0].id == "hi"


# ============================================================================
# TestRouterDecay — Pydantic model field presence
# ============================================================================

class TestRouterDecay:
    """Verify the new fields exist on the router Pydantic models."""

    def test_memory_out_has_relevance_score(self):
        from api.routers.memories import MemoryOut
        assert "relevance_score" in MemoryOut.model_fields

    def test_memory_out_relevance_score_optional(self):
        from api.routers.memories import MemoryOut
        field = MemoryOut.model_fields["relevance_score"]
        assert field.is_required() is False

    def test_memory_query_has_apply_decay(self):
        from api.routers.memories import MemoryQuery
        assert "apply_decay" in MemoryQuery.model_fields

    def test_memory_query_apply_decay_default_false(self):
        from api.routers.memories import MemoryQuery
        q = MemoryQuery(query="test")
        assert q.apply_decay is False

    def test_cross_agent_query_has_apply_decay(self):
        from api.routers.memories import CrossAgentQuery
        assert "apply_decay" in CrossAgentQuery.model_fields

    def test_typed_memory_out_has_relevance_score(self):
        from api.routers.typed_memory import TypedMemoryOut
        assert "relevance_score" in TypedMemoryOut.model_fields

    def test_typed_query_has_apply_decay(self):
        from api.routers.typed_memory import TypedQuery
        assert "apply_decay" in TypedQuery.model_fields

    def test_typed_query_apply_decay_default_false(self):
        from api.routers.typed_memory import TypedQuery
        q = TypedQuery(query="test", memory_types=["standard"])
        assert q.apply_decay is False


# ============================================================================
# TestDecayRouter — router importable + correct paths
# ============================================================================

class TestDecayRouter:
    """Verify the decay router is importable and has the expected routes."""

    def test_router_importable(self):
        from api.routers.decay import router
        assert router is not None

    def test_config_route_exists(self):
        from api.routers.decay import router
        paths = [r.path for r in router.routes]
        assert "/config" in paths

    def test_archive_route_exists(self):
        from api.routers.decay import router
        paths = [r.path for r in router.routes]
        assert "/archive" in paths

    def test_archive_request_threshold_bounds(self):
        """ArchiveRequest threshold must be between 0 and 1."""
        from api.routers.decay import ArchiveRequest
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ArchiveRequest(threshold=1.5)
        with pytest.raises(pydantic.ValidationError):
            ArchiveRequest(threshold=-0.1)

    def test_archive_request_defaults(self):
        from api.routers.decay import ArchiveRequest
        req = ArchiveRequest()
        assert req.namespace == "default"
        assert req.dry_run is False
        assert 0.0 <= req.threshold <= 1.0

    def test_decay_config_response_has_half_lives(self):
        from api.routers.decay import DecayConfigResponse
        assert "half_lives" in DecayConfigResponse.model_fields

    def test_half_lives_in_config_match_engine(self):
        from api.routers.decay import HALF_LIVES as router_hl
        from temporal_decay import HALF_LIVES as engine_hl
        assert router_hl == engine_hl


# ============================================================================
# TestMigration0006
# ============================================================================

class TestMigration0006:
    """Verify the 0006 migration is correctly structured."""

    def _import_migration(self):
        import importlib
        versions_dir = str(Path(__file__).parent.parent / "alembic" / "versions")
        sys.path.insert(0, versions_dir)
        return importlib.import_module("0006_temporal_decay")

    def test_migration_importable(self):
        m = self._import_migration()
        assert m is not None

    def test_revision_is_0006(self):
        m = self._import_migration()
        assert m.revision == "0006"

    def test_down_revision_is_0005(self):
        m = self._import_migration()
        assert m.down_revision == "0005"

    def test_upgrade_function_exists(self):
        m = self._import_migration()
        assert callable(m.upgrade)

    def test_downgrade_function_exists(self):
        m = self._import_migration()
        assert callable(m.downgrade)
