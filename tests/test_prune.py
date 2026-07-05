"""
Tests for the prune surface (v2.6.1): SDK client.prune() + the CLI-facing
POST /memories/decay/archive endpoint it wraps.

Integration tests use the `async_client` fixture (ASGI over the test Postgres)
and skip when the DB is unavailable. The SDK unit test is network-free.
"""

import sys
from pathlib import Path

import pytest

server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))

try:
    from httpx import AsyncClient  # noqa: F401
    _HTTPX_OK = True
except Exception:
    _HTTPX_OK = False


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_archive_dry_run_reports_count(async_client):
    await async_client.post("/memories/add", json={"content": "a stale note", "agent_id": "a1"})
    r = await async_client.post(
        "/memories/decay/archive",
        json={"namespace": "default", "threshold": 0.1, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert "archived" in body
    assert body["namespace"] == "default"
    assert body["threshold"] == 0.1


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_archive_rejects_out_of_range_threshold(async_client):
    r = await async_client.post(
        "/memories/decay/archive", json={"threshold": 1.5}
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# SDK unit test (network-free): prune() posts to the archive endpoint.
# ---------------------------------------------------------------------------

def test_sdk_prune_sends_archive_request():
    from unittest.mock import MagicMock

    from aegis_memory.client import AegisClient

    client = AegisClient(api_key="test-key", base_url="http://example.invalid")

    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "archived": 3, "namespace": "research", "threshold": 0.2, "dry_run": True,
    })
    client.client = MagicMock()
    client.client.post = MagicMock(return_value=resp)

    result = client.prune(namespace="research", threshold=0.2, dry_run=True)

    client.client.post.assert_called_once_with(
        "/memories/decay/archive",
        json={"namespace": "research", "threshold": 0.2, "dry_run": True},
    )
    assert result["archived"] == 3


def test_sdk_prune_local_mode_raises():
    from aegis_memory import local_client

    client = local_client(db_path=":memory:")
    try:
        with pytest.raises(NotImplementedError):
            client.prune()
    finally:
        client.close()
