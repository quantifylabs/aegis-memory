"""
Integration tests for PATCH /memories/{memory_id} (v2.6.1).

Uses the `async_client` fixture (ASGI over the test Postgres). These skip
automatically when the integration DB is unavailable.
"""

import sys
from pathlib import Path

import pytest

# Ensure server directory is on path (mirrors other integration test modules).
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))

try:
    from httpx import AsyncClient  # noqa: F401
    _HTTPX_OK = True
except Exception:
    _HTTPX_OK = False


async def _add(async_client, content, **kw):
    r = await async_client.post("/memories/add", json={"content": content, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_patch_updates_content(async_client):
    mem_id = await _add(async_client, "Original content about retries", agent_id="a1")

    r = await async_client.patch(
        f"/memories/{mem_id}", json={"content": "Revised content about retries"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "Revised content about retries"

    # Persisted: a fresh GET reflects the new content.
    got = await async_client.get(f"/memories/{mem_id}")
    assert got.json()["content"] == "Revised content about retries"


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_patch_merges_metadata(async_client):
    mem_id = await _add(
        async_client, "A fact", agent_id="a1", metadata={"a": 1, "keep": True}
    )

    r = await async_client.patch(
        f"/memories/{mem_id}", json={"metadata": {"a": 2, "b": 3}}
    )
    assert r.status_code == 200, r.text
    meta = r.json()["metadata"]
    # merged, not replaced: existing "keep" survives, "a" overwritten, "b" added.
    assert meta["keep"] is True
    assert meta["a"] == 2
    assert meta["b"] == 3


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_patch_updates_trust_level(async_client):
    mem_id = await _add(async_client, "Some content", agent_id="a1")

    # Declaring a *lower* (more-screened) level is always allowed and applied.
    # (A caller can never elevate trust above its principal — that invariant is
    # exercised in test_patch_cannot_elevate_trust_level below.)
    r = await async_client.patch(
        f"/memories/{mem_id}", json={"trust_level": "untrusted"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["trust_level"] == "untrusted"


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_patch_cannot_elevate_trust_level(async_client):
    # The test principal resolves to "internal"; requesting "privileged" must be
    # capped to the principal's level (security invariant preserved on update).
    mem_id = await _add(async_client, "Some content", agent_id="a1")

    r = await async_client.patch(
        f"/memories/{mem_id}", json={"trust_level": "privileged"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["trust_level"] == "internal"


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_patch_missing_memory_returns_404(async_client):
    r = await async_client.patch(
        "/memories/does-not-exist", json={"content": "x"}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_patch_invalid_trust_level_rejected(async_client):
    mem_id = await _add(async_client, "Some content", agent_id="a1")
    r = await async_client.patch(
        f"/memories/{mem_id}", json={"trust_level": "not-a-level"}
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# SDK unit test (network-free): update_memory() issues the right PATCH request.
# ---------------------------------------------------------------------------

def test_sdk_update_memory_sends_patch(monkeypatch):
    from unittest.mock import MagicMock

    from aegis_memory.client import AegisClient

    client = AegisClient(api_key="test-key", base_url="http://example.invalid")

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "id": "m1",
        "content": "new",
        "namespace": "default",
        "scope": "agent-private",
        "created_at": "2026-07-05T00:00:00Z",
        "trust_level": "privileged",
        "metadata": {"k": "v"},
    })
    client.client = MagicMock()
    client.client.patch = MagicMock(return_value=resp)

    mem = client.update_memory(
        "m1", content="new", metadata={"k": "v"}, trust_level="privileged"
    )

    client.client.patch.assert_called_once_with(
        "/memories/m1",
        json={"content": "new", "metadata": {"k": "v"}, "trust_level": "privileged"},
    )
    assert mem.id == "m1"
    assert mem.content == "new"
    assert mem.trust_level == "privileged"


def test_sdk_update_memory_local_mode_raises():
    from aegis_memory import local_client

    client = local_client(db_path=":memory:")
    try:
        with pytest.raises(NotImplementedError):
            client.update_memory("m1", content="x")
    finally:
        client.close()
