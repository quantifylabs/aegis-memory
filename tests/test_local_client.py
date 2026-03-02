"""
Integration tests — full round-trip via AegisClient(mode="local").

Uses a FakeEmbeddingProvider to avoid network/GPU dependencies.
"""

import os

import numpy as np
import pytest

import httpx
from aegis_memory.client import AegisClient, AsyncAegisClient


# ---------------------------------------------------------------------------
# Fake embedding provider
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    dimensions = 32

    def embed(self, texts):
        return [self.embed_single(t) for t in texts]

    def embed_single(self, text):
        rng = np.random.RandomState(hash(text) % 2**31)
        vec = rng.randn(self.dimensions).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "test.db")
    c = AegisClient(
        mode="local",
        db_path=db,
        embedding_provider=FakeEmbeddingProvider(),
    )
    yield c
    c.close()


@pytest.fixture
def async_client(tmp_path):
    db = str(tmp_path / "test_async.db")
    c = AsyncAegisClient(
        mode="local",
        db_path=db,
        embedding_provider=FakeEmbeddingProvider(),
    )
    return c


# ---------------------------------------------------------------------------
# Sync Client Tests
# ---------------------------------------------------------------------------


class TestSyncClientLocal:
    def test_is_local(self, client):
        assert client.is_local is True

    def test_add_and_query(self, client):
        result = client.add("User prefers dark mode", agent_id="ui-agent")
        assert result.id

        # Query with same text to get a strong match
        memories = client.query("User prefers dark mode", agent_id="ui-agent")
        assert len(memories) >= 1
        assert "dark mode" in memories[0].content

    def test_add_batch(self, client):
        items = [
            {"content": "fact alpha", "agent_id": "a1"},
            {"content": "fact beta", "agent_id": "a1"},
        ]
        results = client.add_batch(items)
        assert len(results) == 2
        for r in results:
            assert r.id

    def test_get_and_delete(self, client):
        result = client.add("deletable", agent_id="a1")
        mem = client.get(result.id)
        assert mem is not None
        assert mem.content == "deletable"

        assert client.delete(result.id) is True
        # get() raises when not found in local mode
        with pytest.raises(httpx.HTTPStatusError):
            client.get(result.id)

    def test_vote(self, client):
        mem = client.add("votable", agent_id="a1")
        vote_result = client.vote(mem.id, vote="helpful", voter_agent_id="voter")
        assert vote_result.effectiveness_score >= 0

    def test_session_crud(self, client):
        session = client.create_session("s1", agent_id="a1")
        assert session.session_id == "s1"

        got = client.get_session("s1")
        assert got is not None

        updated = client.update_session("s1", completed_items=["item1"])
        assert "item1" in updated.completed_items

    def test_feature_crud(self, client):
        feat = client.create_feature("f1", "Feature description")
        assert feat.feature_id == "f1"

        got = client.get_feature("f1")
        assert got is not None

        updated = client.update_feature("f1", status="complete")
        assert updated.status == "complete"

        features = client.list_features()
        assert features.total >= 1

    def test_run_tracking(self, client):
        run = client.start_run("r1", agent_id="a1")
        assert run.run_id == "r1"

        got = client.get_run("r1")
        assert got is not None

        completed = client.complete_run(
            "r1", success=True, auto_vote=False, auto_reflect=False,
        )
        assert completed.status == "completed"

    def test_curate(self, client):
        client.add("curate me", agent_id="a1")
        result = client.curate()
        assert hasattr(result, "promoted")
        assert hasattr(result, "flagged")

    def test_handoff(self, client):
        client.add("handoff data", agent_id="src")
        baton = client.handoff("src", "tgt", task_context="migration")
        assert baton.source_agent_id == "src"
        assert baton.target_agent_id == "tgt"

    def test_export(self, client, tmp_path):
        client.add("exportable", agent_id="a1")
        out = str(tmp_path / "export.json")
        data = client.export_json(out)
        assert os.path.exists(out)

    def test_cross_agent_query(self, client):
        client.add("global info", agent_id="a1", scope="global")
        results = client.query_cross_agent(
            "global info", requesting_agent_id="a2",
        )
        assert len(results) >= 1

    def test_apply_delta(self, client):
        ops = [{"type": "add", "content": "delta fact", "agent_id": "a1"}]
        result = client.apply_delta(ops)
        assert len(result.results) == 1
        assert result.results[0].success is True

    def test_add_reflection(self, client):
        rid = client.add_reflection(
            "Learned something", agent_id="a1",
        )
        assert rid  # non-empty ID

    def test_query_playbook(self, client):
        client.add(
            "Always validate input",
            agent_id="a1",
            metadata={"memory_type": "strategy"},
        )
        result = client.query_playbook("validation", agent_id="a1")
        assert hasattr(result, "entries")

    def test_interaction_events(self, client):
        client.create_session("s1", agent_id="a1")
        event = client.record_interaction("s1", "User said hello", agent_id="a1")
        assert event.event_id

        timeline = client.get_session_interactions("s1")
        assert timeline.count >= 1

        agent_events = client.get_agent_interactions("a1")
        assert agent_events.count >= 1

    def test_security_methods_raise(self, client):
        with pytest.raises(NotImplementedError):
            client.scan_content("test")
        with pytest.raises(NotImplementedError):
            client.verify_integrity("test-id")
        with pytest.raises(NotImplementedError):
            client.get_flagged_memories()
        with pytest.raises(NotImplementedError):
            client.get_security_audit()
        with pytest.raises(NotImplementedError):
            client.get_security_config()


# ---------------------------------------------------------------------------
# Async Client Tests
# ---------------------------------------------------------------------------


class TestAsyncClientLocal:
    @pytest.mark.asyncio
    async def test_is_local(self, async_client):
        assert async_client.is_local is True

    @pytest.mark.asyncio
    async def test_add_and_query(self, async_client):
        result = await async_client.add("async dark mode", agent_id="ui")
        assert result.id

        memories = await async_client.query("async dark mode", agent_id="ui")
        assert len(memories) >= 1

    @pytest.mark.asyncio
    async def test_get_and_delete(self, async_client):
        result = await async_client.add("async deletable", agent_id="a1")
        mem = await async_client.get(result.id)
        assert mem is not None

        assert await async_client.delete(result.id) is True
        with pytest.raises(httpx.HTTPStatusError):
            await async_client.get(result.id)

    @pytest.mark.asyncio
    async def test_session_crud(self, async_client):
        session = await async_client.create_session("s1", agent_id="a1")
        assert session.session_id == "s1"

        got = await async_client.get_session("s1")
        assert got is not None

    @pytest.mark.asyncio
    async def test_run_tracking(self, async_client):
        run = await async_client.start_run("r1", agent_id="a1")
        assert run.run_id == "r1"

        completed = await async_client.complete_run(
            "r1", success=True, auto_vote=False, auto_reflect=False,
        )
        assert completed.status == "completed"

    @pytest.mark.asyncio
    async def test_security_methods_raise(self, async_client):
        with pytest.raises(NotImplementedError):
            await async_client.scan_content("test")


# ---------------------------------------------------------------------------
# Factory function test
# ---------------------------------------------------------------------------


class TestLocalClientFactory:
    def test_local_client_function(self, tmp_path):
        from aegis_memory import local_client

        db = str(tmp_path / "factory.db")
        c = local_client(db_path=db, embedding_provider=FakeEmbeddingProvider())
        assert c.is_local is True

        result = c.add("factory test", agent_id="a1")
        assert result.id
        c.close()
