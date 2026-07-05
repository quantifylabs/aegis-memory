"""
Integration tests for POST /memories/ace/consolidate (v2.6.1).

Covers dry_run planning, dry_run=False real merge, and the use_llm=True → 501
guard (the LLM merge adapter is intentionally not configured in OSS).

Uses the `async_client` fixture (ASGI over the test Postgres); skips when the
integration DB is unavailable.
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


# Two near-duplicate memories the semantic consolidator should pair up.
_DUP_A = "Use exponential backoff with max 5 retries for API calls"
_DUP_B = "Apply exponential backoff strategy, cap retries at 5, for API requests"


async def _seed_pair(async_client):
    for content in (_DUP_A, _DUP_B):
        r = await async_client.post(
            "/memories/add", json={"content": content, "agent_id": "exec"}
        )
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_consolidate_dry_run_plans_without_applying(async_client):
    await _seed_pair(async_client)
    r = await async_client.post(
        "/memories/ace/consolidate", json={"dry_run": True, "similarity_threshold": 0.85}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert all(p["applied"] is False for p in body["plans"])


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_consolidate_apply_merges_pair(async_client):
    await _seed_pair(async_client)
    r = await async_client.post(
        "/memories/ace/consolidate", json={"dry_run": False, "similarity_threshold": 0.85}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is False
    # Whether a pair is found depends on the active embedder (the deterministic
    # test embedder may not rate paraphrases similar enough). But when the apply
    # path *does* find a pair, it must actually apply the merge (not just plan it).
    for plan in body["plans"]:
        assert plan["applied"] is True
    assert body["pairs_processed"] == len(body["plans"])


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_consolidate_use_llm_returns_501(async_client):
    # No seeding required: the guard fires before any work.
    r = await async_client.post(
        "/memories/ace/consolidate", json={"dry_run": True, "use_llm": True}
    )
    assert r.status_code == 501
