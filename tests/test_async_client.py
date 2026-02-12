import asyncio

import httpx
import pytest

from aegis_memory import AegisClient, AsyncAegisClient


def _build_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/memories/add":
            return httpx.Response(200, json={"id": "m-1", "inferred_scope": "agent-private"})
        if path == "/memories/query":
            return httpx.Response(
                200,
                json={
                    "memories": [
                        {
                            "id": "m-1",
                            "content": "remember this",
                            "namespace": "default",
                            "metadata": {},
                            "created_at": "2024-01-01T00:00:00Z",
                            "scope": "agent-private",
                        }
                    ]
                },
            )
        if path == "/memories/ace/vote/m-1":
            return httpx.Response(
                200,
                json={
                    "memory_id": "m-1",
                    "bullet_helpful": 2,
                    "bullet_harmful": 0,
                    "effectiveness_score": 0.66,
                },
            )
        if path == "/memories/ace/session" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "id": "s-1",
                    "session_id": "sess-1",
                    "status": "active",
                    "completed_count": 0,
                    "total_items": 3,
                    "progress_percent": 0.0,
                    "completed_items": [],
                    "next_items": ["a", "b"],
                    "blocked_items": [],
                    "updated_at": "2024-01-01T00:00:00Z",
                },
            )
        if path == "/memories/ace/session/sess-1" and request.method == "PATCH":
            body = request.read().decode() or "{}"
            completed = ["a"] if "completed_items" in body else []
            return httpx.Response(
                200,
                json={
                    "id": "s-1",
                    "session_id": "sess-1",
                    "status": "active",
                    "completed_count": len(completed),
                    "total_items": 3,
                    "progress_percent": 33.33 if completed else 0.0,
                    "completed_items": completed,
                    "next_items": ["b"],
                    "blocked_items": [],
                    "updated_at": "2024-01-01T00:01:00Z",
                },
            )
        return httpx.Response(404, json={"detail": f"No route for {request.method} {path}"})

    return httpx.MockTransport(handler)


def _build_sync_client() -> AegisClient:
    client = AegisClient(api_key="test", base_url="http://test")
    client.client = httpx.Client(base_url="http://test", transport=_build_transport())
    return client


def _build_async_client() -> AsyncAegisClient:
    client = AsyncAegisClient(api_key="test", base_url="http://test")
    client.client = httpx.AsyncClient(base_url="http://test", transport=_build_transport())
    return client


def test_sync_async_add_and_query_parity():
    sync = _build_sync_client()

    async def run_async_calls():
        async with _build_async_client() as async_client:
            add_result = await async_client.add("remember this", agent_id="agent-1")
            query_result = await async_client.query("remember", agent_id="agent-1")
            return add_result, query_result

    async_add, async_memories = asyncio.run(run_async_calls())
    sync_add = sync.add("remember this", agent_id="agent-1")
    sync_memories = sync.query("remember", agent_id="agent-1")

    assert async_add.id == sync_add.id
    assert async_add.inferred_scope == sync_add.inferred_scope
    assert async_memories[0].id == sync_memories[0].id
    assert async_memories[0].content == sync_memories[0].content


@pytest.mark.asyncio
async def test_async_vote_and_session_methods():
    async with _build_async_client() as client:
        vote_result = await client.vote("m-1", "helpful", voter_agent_id="agent-1")
        assert vote_result.memory_id == "m-1"
        assert vote_result.bullet_helpful == 2

        session = await client.create_session("sess-1", agent_id="agent-1")
        assert session.session_id == "sess-1"

        updated = await client.mark_complete("sess-1", "a")
        assert updated.completed_count == 1
        assert updated.completed_items == ["a"]


@pytest.mark.asyncio
async def test_async_aclose():
    client = _build_async_client()
    await client.aclose()
    assert client.client.is_closed
