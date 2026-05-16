"""
Memory Depth integration tests (v2.4.0).

Covers:
  P1 - Hybrid retrieval (RRF fusion, HybridRetriever wiring)
  P2 - Memory graph + contradiction detection
  P3 - Semantic consolidation

The model/import-level checks here run standalone. Integration tests that
depend on a live database use the `async_client` fixture (Context-Hub style)
and will be skipped where that fixture is unavailable.
"""

import sys
from pathlib import Path

import pytest

# Ensure server directory is on path
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))


# ============================================================================
# Schema-level checks (standalone)
# ============================================================================

class TestMemoryEdgeModel:
    """Verify MemoryEdge model and indexes."""

    def test_memory_edge_table_exists(self):
        from models import MemoryEdge
        assert MemoryEdge.__tablename__ == "memory_edges"

    def test_memory_edge_columns(self):
        from models import MemoryEdge
        col_names = {c.name for c in MemoryEdge.__table__.columns}
        for required in (
            "id", "project_id", "source_memory_id", "target_memory_id",
            "edge_type", "confidence", "detected_by", "detected_at",
            "metadata", "resolution", "resolved_by", "resolved_at", "created_at",
        ):
            assert required in col_names, f"missing column: {required}"

    def test_memory_edge_indexes(self):
        from models import MemoryEdge
        index_names = {ix.name for ix in MemoryEdge.__table__.indexes}
        assert "ix_edges_source" in index_names
        assert "ix_edges_target" in index_names
        assert "ix_edges_type_resolution" in index_names
        assert "ix_edges_pair_unique" in index_names


class TestMemoryEventTypeAdditions:
    """The four new event types ride on the existing MemoryEventType enum."""

    def test_new_event_types_exist(self):
        from models import MemoryEventType
        assert MemoryEventType.CONTRADICTION_DETECTED.value == "contradiction_detected"
        assert MemoryEventType.EDGE_CREATED.value == "edge_created"
        assert MemoryEventType.EDGE_RESOLVED.value == "edge_resolved"
        assert MemoryEventType.MEMORIES_CONSOLIDATED.value == "memories_consolidated"


class TestMemoryContentTsv:
    """Sparse retrieval relies on the content_tsv generated column."""

    def test_content_tsv_column_exists(self):
        from models import Memory
        col_names = {c.name for c in Memory.__table__.columns}
        assert "content_tsv" in col_names


# ============================================================================
# Edge enums + repository surface
# ============================================================================

class TestEdgeEnums:
    def test_edge_type_values(self):
        from memory_graph import EdgeType
        assert {e.value for e in EdgeType} == {
            "supersedes", "contradicts", "generalizes",
            "elaborates", "derives_from", "entity_rel",
        }

    def test_edge_resolution_values(self):
        from memory_graph import EdgeResolution
        assert {r.value for r in EdgeResolution} == {
            "unresolved", "kept_source", "kept_target",
            "both_valid", "both_invalid",
        }


class TestMemoryGraphRepository:
    def test_repository_has_methods(self):
        from memory_graph import MemoryGraphRepository
        for name in (
            "add_edge", "get_edges_for_memory",
            "list_unresolved_contradictions", "resolve", "contradiction_metrics",
        ):
            assert hasattr(MemoryGraphRepository, name)


# ============================================================================
# Hybrid retrieval (RRF) - pure unit tests
# ============================================================================

class TestReciprocalRankFusion:
    """RRF is pure math -- test it standalone."""

    def test_rrf_combines_rankings(self):
        from hybrid_retrieval import reciprocal_rank_fusion
        scores = reciprocal_rank_fusion([
            ["a", "b", "c"],
            ["b", "a", "d"],
        ], k=60)
        # 'a' and 'b' appear in both; 'b' is rank 1+2, 'a' is 1+2 -> tied
        assert scores["a"] > scores["c"]
        assert scores["b"] > scores["d"]

    def test_rrf_higher_rank_higher_score(self):
        from hybrid_retrieval import reciprocal_rank_fusion
        scores = reciprocal_rank_fusion([["first", "second", "third"]])
        assert scores["first"] > scores["second"] > scores["third"]

    def test_rrf_empty_input(self):
        from hybrid_retrieval import reciprocal_rank_fusion
        assert reciprocal_rank_fusion([]) == {}

    def test_rrf_default_k_is_60(self):
        from hybrid_retrieval import DEFAULT_RRF_K
        assert DEFAULT_RRF_K == 60


class TestHybridRetrieverShape:
    def test_hybrid_retriever_search_is_async(self):
        import inspect
        from hybrid_retrieval import HybridRetriever
        assert inspect.iscoroutinefunction(HybridRetriever.search)


# ============================================================================
# Contradiction detector - negation regex
# ============================================================================

class TestContradictionDetector:
    def test_negation_signal_detected(self):
        from contradiction_detector import ContradictionDetector
        assert ContradictionDetector.has_opposition_signal(
            "The bot uses neg-risk handling",
            "The bot does not use neg-risk handling",
        )

    def test_negation_signal_negative_case(self):
        from contradiction_detector import ContradictionDetector
        assert not ContradictionDetector.has_opposition_signal(
            "The bot uses neg-risk handling",
            "The bot uses neg-risk handling for outcome contracts",
        )

    def test_negation_signal_picks_up_synonyms(self):
        from contradiction_detector import ContradictionDetector
        # "wrong", "deprecated", "removed", "contradicts" all match
        assert ContradictionDetector.has_opposition_signal(
            "The old approach is deprecated",
            "The old approach works fine",
        )

    def test_detector_default_threshold(self):
        from contradiction_detector import ContradictionDetector
        d = ContradictionDetector()
        assert d.similarity_threshold == 0.80
        assert d.llm is None


# ============================================================================
# Semantic consolidator - cosine util
# ============================================================================

class TestCosineSimilarity:
    def test_identical_vectors_are_one(self):
        from consolidation import _cosine_similarity
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_are_zero(self):
        from consolidation import _cosine_similarity
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        from consolidation import _cosine_similarity
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestSemanticConsolidator:
    def test_default_threshold_is_strict(self):
        from consolidation import SemanticConsolidator
        c = SemanticConsolidator()
        assert c.similarity_threshold == 0.92
        assert c.llm is None


# ============================================================================
# Router registration & migration
# ============================================================================

class TestRouterRegistration:
    def test_memory_edges_router_registered(self):
        from api.routers import memory_edges
        assert memory_edges.router is not None

    def test_contradictions_router_registered(self):
        from api.routers import contradictions
        assert contradictions.router is not None

    def test_hybrid_query_endpoint_exists(self):
        from api.routers import memories
        paths = [
            getattr(route, "path", None) for route in memories.router.routes
        ]
        assert "/hybrid_query" in paths

    def test_consolidate_endpoint_exists(self):
        from api.routers import ace_curation
        paths = [
            getattr(route, "path", None) for route in ace_curation.router.routes
        ]
        assert "/consolidate" in paths


class TestMigration:
    def test_migration_file_importable(self):
        import importlib.util
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0009_memory_depth.py"
        spec = importlib.util.spec_from_file_location("memory_depth", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "0009_memory_depth"
        assert module.down_revision == "0008_context_hub"

    def test_migration_has_upgrade_and_downgrade(self):
        import importlib.util
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0009_memory_depth.py"
        spec = importlib.util.spec_from_file_location("memory_depth", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(module.upgrade)
        assert callable(module.downgrade)


# ============================================================================
# SDK surface
# ============================================================================

class TestSDKSurface:
    def test_sync_client_has_hybrid_query(self):
        from aegis_memory import AegisClient
        assert hasattr(AegisClient, "hybrid_query")

    def test_sync_client_has_contradiction_methods(self):
        from aegis_memory import AegisClient
        for name in (
            "scan_contradictions", "list_contradictions",
            "contradiction_metrics", "create_edge", "resolve_edge",
            "get_edges_for_memory",
        ):
            assert hasattr(AegisClient, name), f"missing SDK method: {name}"

    def test_sync_client_has_consolidate(self):
        from aegis_memory import AegisClient
        assert hasattr(AegisClient, "consolidate_memories")


# ============================================================================
# End-to-end integration tests (require live server via `async_client` fixture)
# ============================================================================
#
# These mirror the patterns in tests/test_context_hub.py. They will be
# collected but currently skipped — the project's async_client fixture
# wiring lives outside this file.

try:
    from httpx import AsyncClient  # noqa: F401
    _HTTPX_OK = True
except Exception:
    _HTTPX_OK = False


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_hybrid_outperforms_dense_for_exact_token(async_client):
    """[P1] Hybrid should rank an exact-token memory above dense-only neighbors."""
    await async_client.post("/memories/add", json={
        "content": "The pagination cursor token is 'ZX7-PAGE-94'", "agent_id": "a1",
    })
    for filler in [
        "Pagination requires a cursor parameter for stateful iteration",
        "Use the page argument when iterating large result sets",
        "API responses often include a next_token field for pagination",
    ]:
        await async_client.post("/memories/add", json={"content": filler, "agent_id": "a1"})

    r = await async_client.post("/memories/hybrid_query", json={
        "query": "ZX7-PAGE-94", "agent_id": "a1", "top_k": 4,
    })
    assert r.status_code == 200
    results = r.json()["results"]
    assert results, "hybrid should return at least one result"
    assert "ZX7-PAGE-94" in results[0]["content"]


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_contradiction_scan_finds_negation_pair(async_client):
    """[P2] Two contradictory memories should produce a `contradicts` edge."""
    await async_client.post("/memories/add", json={
        "content": "The Polymarket bot uses neg-risk handling for outcome contracts",
        "agent_id": "researcher",
    })
    await async_client.post("/memories/add", json={
        "content": "The Polymarket bot does not use neg-risk handling -- that's a different system",
        "agent_id": "researcher",
    })
    r = await async_client.post("/memories/contradictions/scan", json={
        "namespace": "default", "similarity_threshold": 0.70,
    })
    assert r.status_code == 200
    assert r.json()["edges_created"] >= 1

    listed = (await async_client.get("/memories/contradictions/")).json()
    assert len(listed) >= 1


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_contradiction_metrics_for_sri(async_client):
    """[P2] /metrics endpoint feeds the Simulation Reliability Index."""
    r = await async_client.get("/memories/contradictions/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "unresolved_contradictions" in body
    assert "total_contradictions_detected" in body


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_semantic_consolidation_dry_run(async_client):
    """[P3] dry_run=True should plan without applying."""
    await async_client.post("/memories/add", json={
        "content": "Use exponential backoff with max 5 retries for API calls",
        "agent_id": "exec",
    })
    await async_client.post("/memories/add", json={
        "content": "Apply exponential backoff strategy, cap retries at 5, for API requests",
        "agent_id": "exec",
    })
    r = await async_client.post("/memories/ace/consolidate", json={
        "dry_run": True, "similarity_threshold": 0.85,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert all(p["applied"] is False for p in body["plans"])
