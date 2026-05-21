"""
Hybrid retrieval — sparse channel OR-semantics (Memory Depth v2.4.0).

These cover the regression fixed in server/hybrid_retrieval.py: the sparse
(tsvector) channel must rank documents by lexeme *overlap* via ts_rank_cd,
not filter by completeness. plainto_tsquery defaults to AND between lexemes,
so a natural-language query like "how do I fix error PG-2087" produced
'fix' & 'error' & 'pg' & '-2087' and matched zero documents (none contain
the intent word "fix"). We convert AND -> OR so the channel anchors on the
identifier/lexical terms it can actually find.

All tests here exercise the real SQL (tsvector is a Postgres generated
column), so they go through the `async_client` fixture and are skipped on
machines without the dev Postgres stack — same as tests/test_memory_depth.py.
"""

import sys
from pathlib import Path

import pytest

# Ensure server directory is on path (mirrors test_memory_depth.py).
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))


try:
    from httpx import AsyncClient  # noqa: F401
    _HTTPX_OK = True
except Exception:
    _HTTPX_OK = False


def _index_of(results, needle):
    """Rank position of the first result whose content contains `needle`, else None."""
    for i, r in enumerate(results):
        if needle in r["content"]:
            return i
    return None


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_sparse_ranks_by_overlap_not_completeness(async_client):
    """A natural-language query ranks the matching identifier higher by overlap.

    Under the old AND-semantics, plainto_tsquery('how do I fix error PG-2087')
    became 'fix' & 'error' & 'pg' & '-2087' and matched neither document
    (neither contains "fix"), so the sparse channel went silent. With
    OR-semantics the PG-2087 memory matches three lexemes (error, pg, -2087)
    vs the PG-1042 memory's two (error, pg) and ranks above it.
    """
    await async_client.post("/memories/add", json={
        "content": "Error PG-2087: replication lag exceeded threshold on the primary",
        "agent_id": "ops",
    })
    await async_client.post("/memories/add", json={
        "content": "Error PG-1042: connection pool exhausted under sustained load",
        "agent_id": "ops",
    })

    r = await async_client.post("/memories/hybrid_query", json={
        "query": "how do I fix error PG-2087?", "agent_id": "ops", "top_k": 2,
    })
    assert r.status_code == 200
    results = r.json()["results"]

    i_2087 = _index_of(results, "PG-2087")
    i_1042 = _index_of(results, "PG-1042")
    assert i_2087 is not None, "the PG-2087 memory should be retrieved"
    if i_1042 is not None:
        assert i_2087 < i_1042, "PG-2087 should rank above PG-1042 (more lexeme overlap)"


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_all_stopword_query_degrades_to_dense(async_client):
    """An all-stopword query yields an empty tsquery; sparse no-ops, no error.

    plainto_tsquery('english', 'the and a') is empty. The NULLIF(..., '')
    guard turns that into NULL and the `WHERE q.tsq IS NOT NULL` clause
    skips the sparse channel entirely, so hybrid degenerates gracefully to
    dense-only rather than raising.
    """
    await async_client.post("/memories/add", json={
        "content": "The deployment pipeline runs nightly at 02:00 UTC",
        "agent_id": "ops",
    })

    r = await async_client.post("/memories/hybrid_query", json={
        "query": "the and a", "agent_id": "ops", "top_k": 5,
    })
    assert r.status_code == 200
    # Dense channel still ranks the corpus; the call must not error.
    assert isinstance(r.json()["results"], list)


@pytest.mark.asyncio
@pytest.mark.skipif(not _HTTPX_OK, reason="httpx not installed")
async def test_absent_identifier_leaves_rrf_to_dense(async_client):
    """A unique token in no document yields no sparse matches; dense still scores.

    "PG-9999" tokenizes to lexemes ('pg', '-9999') that appear in none of the
    seeded memories, so the sparse channel returns nothing. RRF must still
    surface documents from the dense channel rather than returning empty.
    """
    for content in [
        "The deployment pipeline runs nightly at 02:00 UTC",
        "Caching layer uses Redis with a 5 minute TTL",
        "Background jobs are dispatched through a Celery worker queue",
    ]:
        await async_client.post("/memories/add", json={"content": content, "agent_id": "ops"})

    r = await async_client.post("/memories/hybrid_query", json={
        "query": "PG-9999", "agent_id": "ops", "top_k": 3,
    })
    assert r.status_code == 200
    results = r.json()["results"]
    assert results, "dense channel should still produce results via RRF"
    assert all("PG-9999" not in r["content"] for r in results), \
        "no seeded memory contains the token, so none should match it lexically"
