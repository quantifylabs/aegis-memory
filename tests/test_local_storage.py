"""
Tests for aegis_memory.local._storage — LocalStorage (SQLite + numpy).

All tests use a temp SQLite database and a deterministic
FakeEmbedder (32-dim) so no network or GPU is needed.
"""

import numpy as np
import pytest

from aegis_memory.local._storage import LocalStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Deterministic embedder for tests."""

    dimensions = 32

    def embed_single(self, text):
        rng = np.random.RandomState(hash(text) % 2**31)
        vec = rng.randn(self.dimensions).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec

    def embed(self, texts):
        return [self.embed_single(t) for t in texts]


def _embed(text):
    return FakeEmbedder().embed_single(text)


def _embed_batch(texts):
    return FakeEmbedder().embed(texts)


@pytest.fixture
def storage(tmp_path):
    """Fresh LocalStorage for each test."""
    db = str(tmp_path / "test.db")
    s = LocalStorage(db_path=db, signing_key="test-key", embedding_dims=32)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


class TestAddAndGet:
    def test_add_returns_id(self, storage):
        result = storage.add_memory("hello world", _embed("hello world"), agent_id="a1")
        assert "id" in result
        assert result["id"]  # non-empty

    def test_get_memory(self, storage):
        result = storage.add_memory("remember this", _embed("remember this"), agent_id="a1")
        mem = storage.get_memory(result["id"])
        assert mem is not None
        assert mem["content"] == "remember this"
        assert mem["agent_id"] == "a1"

    def test_get_nonexistent(self, storage):
        assert storage.get_memory("nonexistent-id") is None

    def test_delete_memory(self, storage):
        result = storage.add_memory("to delete", _embed("to delete"), agent_id="a1")
        assert storage.delete_memory(result["id"]) is True
        assert storage.get_memory(result["id"]) is None

    def test_delete_nonexistent(self, storage):
        assert storage.delete_memory("nope") is False

    def test_deduplication(self, storage):
        """Adding the same content + namespace should return existing memory."""
        r1 = storage.add_memory("duplicate", _embed("duplicate"), agent_id="a1")
        r2 = storage.add_memory("duplicate", _embed("duplicate"), agent_id="a1")
        assert r1["id"] == r2["id"]

    def test_different_namespaces_no_dedup(self, storage):
        """Same content but different namespaces should create separate memories."""
        r1 = storage.add_memory("shared", _embed("shared"), agent_id="a1", namespace="ns1")
        r2 = storage.add_memory("shared", _embed("shared"), agent_id="a1", namespace="ns2")
        assert r1["id"] != r2["id"]


class TestAddBatch:
    def test_batch_add(self, storage):
        items = [
            {"content": "fact one", "agent_id": "a1"},
            {"content": "fact two", "agent_id": "a1"},
            {"content": "fact three", "agent_id": "a1"},
        ]
        embeddings = _embed_batch([i["content"] for i in items])
        results = storage.add_batch(items, embeddings)
        assert len(results) == 3
        for r in results:
            assert "id" in r


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------


class TestSemanticSearch:
    def test_basic_search_returns_results(self, storage):
        storage.add_memory("User prefers dark mode", _embed("User prefers dark mode"), agent_id="a1")
        storage.add_memory("Project deadline March 15", _embed("Project deadline March 15"), agent_id="a1")

        # Use same text for query to ensure at least one strong match
        results = storage.semantic_search(_embed("User prefers dark mode"), agent_id="a1")
        assert len(results) >= 1
        assert "dark mode" in results[0]["content"]

    def test_search_top_k(self, storage):
        for i in range(10):
            storage.add_memory(f"memory {i}", _embed(f"memory {i}"), agent_id="a1")

        results = storage.semantic_search(_embed("memory"), agent_id="a1", top_k=3)
        assert len(results) <= 3

    def test_search_min_score(self, storage):
        storage.add_memory("hello world", _embed("hello world"), agent_id="a1")
        # With min_score=0.99, likely nothing matches random vectors
        results = storage.semantic_search(_embed("completely unrelated"), agent_id="a1", min_score=0.99)
        assert len(results) == 0

    def test_search_namespace_filter(self, storage):
        storage.add_memory("ns1 fact", _embed("ns1 fact"), agent_id="a1", namespace="ns1")
        storage.add_memory("ns2 fact", _embed("ns2 fact"), agent_id="a1", namespace="ns2")

        results = storage.semantic_search(_embed("fact"), agent_id="a1", namespace="ns1")
        for r in results:
            assert r["namespace"] == "ns1"


class TestCrossAgentSearch:
    def test_global_scope_visible(self, storage):
        storage.add_memory(
            "Team standup at 10am",
            _embed("Team standup at 10am"),
            agent_id="a1",
            scope="global",
        )
        results = storage.cross_agent_search(
            _embed("Team standup at 10am"), requesting_agent_id="a2"
        )
        assert any("standup" in r["content"] for r in results)

    def test_private_not_visible(self, storage):
        storage.add_memory(
            "Secret agent info",
            _embed("Secret agent info"),
            agent_id="a1",
            scope="agent-private",
        )
        results = storage.cross_agent_search(
            _embed("Secret agent info"), requesting_agent_id="a2"
        )
        # Private memories should not appear for a different agent
        assert not any("Secret agent" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# ACE Operations
# ---------------------------------------------------------------------------


class TestVote:
    def test_helpful_vote(self, storage):
        mem = storage.add_memory("votable", _embed("votable"), agent_id="a1")
        result = storage.vote(mem["id"], "helpful", "voter-1")
        assert result["bullet_helpful"] == 1
        assert result["effectiveness_score"] >= 0

    def test_harmful_vote(self, storage):
        mem = storage.add_memory("votable", _embed("votable"), agent_id="a1")
        result = storage.vote(mem["id"], "harmful", "voter-1")
        assert result["bullet_harmful"] == 1


class TestApplyDelta:
    def test_add_operation(self, storage):
        ops = [
            {"type": "add", "content": "delta fact", "agent_id": "a1"},
        ]
        result = storage.apply_delta(ops, embed_fn=_embed)
        assert len(result["results"]) == 1
        assert result["results"][0]["success"] is True

    def test_deprecate_operation(self, storage):
        mem = storage.add_memory("old fact", _embed("old fact"), agent_id="a1")
        ops = [
            {"type": "deprecate", "memory_id": mem["id"]},
        ]
        result = storage.apply_delta(ops, embed_fn=_embed)
        assert len(result["results"]) == 1
        assert result["results"][0]["success"] is True


class TestReflection:
    def test_add_reflection(self, storage):
        rid = storage.add_reflection("Learned to use async", _embed("Learned to use async"), "a1")
        assert rid  # got a non-empty ID
        mem = storage.get_memory(rid)
        assert mem is not None
        assert mem["memory_type"] == "reflection"


class TestPlaybook:
    def test_query_playbook(self, storage):
        # Add a strategy memory
        storage.add_memory(
            "Always test edge cases",
            _embed("Always test edge cases"),
            agent_id="a1",
            memory_type="strategy",
        )
        result = storage.query_playbook(_embed("testing"), "a1")
        assert "entries" in result


# ---------------------------------------------------------------------------
# Session & Feature CRUD
# ---------------------------------------------------------------------------


class TestSession:
    def test_create_and_get(self, storage):
        result = storage.create_session("s1", agent_id="a1")
        assert result["session_id"] == "s1"

        got = storage.get_session("s1")
        assert got is not None

    def test_update_session(self, storage):
        storage.create_session("s1", agent_id="a1")
        updated = storage.update_session("s1", completed_items=["item1"])
        assert "item1" in updated["completed_items"]

    def test_get_nonexistent_session(self, storage):
        assert storage.get_session("nope") is None


class TestFeature:
    def test_create_and_get(self, storage):
        result = storage.create_feature("f1", "Feature one description")
        assert result["feature_id"] == "f1"

        got = storage.get_feature("f1")
        assert got is not None
        assert got["description"] == "Feature one description"

    def test_update_feature(self, storage):
        storage.create_feature("f1", "desc")
        updated = storage.update_feature("f1", status="complete", passes=True)
        assert updated["status"] == "complete"

    def test_list_features(self, storage):
        storage.create_feature("f1", "desc 1")
        storage.create_feature("f2", "desc 2")
        result = storage.list_features()
        assert result["total"] == 2


# ---------------------------------------------------------------------------
# Run Tracking
# ---------------------------------------------------------------------------


class TestRunTracking:
    def test_start_and_get(self, storage):
        result = storage.start_run("r1", agent_id="a1")
        assert result["run_id"] == "r1"
        assert result["status"] == "running"

        got = storage.get_run("r1")
        assert got is not None
        assert got["agent_id"] == "a1"

    def test_complete_run(self, storage):
        storage.start_run("r1", agent_id="a1")
        result = storage.complete_run(
            "r1",
            embed_fn=_embed,
            success=True,
            auto_vote=False,
            auto_reflect=False,
        )
        assert result["status"] == "completed"
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Curation
# ---------------------------------------------------------------------------


class TestCuration:
    def test_curate_returns_structure(self, storage):
        for i in range(5):
            storage.add_memory(f"fact {i}", _embed(f"fact {i}"), agent_id="a1")
        result = storage.curate()
        assert "promoted" in result
        assert "flagged" in result
        assert "consolidation_candidates" in result


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


class TestHandoff:
    def test_handoff_basic(self, storage):
        storage.add_memory("source fact", _embed("source fact"), agent_id="src")
        result = storage.handoff("src", "tgt", task_context="migration")
        assert result["source_agent_id"] == "src"
        assert result["target_agent_id"] == "tgt"


# ---------------------------------------------------------------------------
# Interaction Events
# ---------------------------------------------------------------------------


class TestInteractionEvents:
    def test_record_and_get(self, storage):
        storage.create_session("s1", agent_id="a1")

        result = storage.record_interaction("s1", "Hello world", agent_id="a1")
        assert "event_id" in result

        timeline = storage.get_session_interactions("s1")
        assert timeline["count"] >= 1

    def test_agent_interactions(self, storage):
        storage.create_session("s1", agent_id="a1")
        storage.record_interaction("s1", "Agent did X", agent_id="a1")

        result = storage.get_agent_interactions("a1")
        assert result["count"] >= 1

    def test_interaction_chain(self, storage):
        storage.create_session("s1", agent_id="a1")
        r1 = storage.record_interaction("s1", "step 1", agent_id="a1")
        r2 = storage.record_interaction(
            "s1", "step 2", agent_id="a1",
            parent_event_id=r1["event_id"],
        )
        chain = storage.get_interaction_chain(r2["event_id"])
        assert chain["chain_depth"] >= 1


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_json(self, storage):
        storage.add_memory("export me", _embed("export me"), agent_id="a1")
        data = storage.export_json()
        assert "memories" in data
        assert len(data["memories"]) >= 1


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------


class TestIntegrity:
    def test_memory_has_integrity_hash(self, storage):
        result = storage.add_memory("signed content", _embed("signed content"), agent_id="a1")
        mem = storage.get_memory(result["id"])
        assert mem["integrity_hash"] is not None
        assert len(mem["integrity_hash"]) > 0
