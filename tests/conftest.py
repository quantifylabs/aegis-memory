"""
Pytest configuration and fixtures for Aegis Memory tests.

Two things happen here:

1. Always: prepend `server/` to sys.path so unit tests can `from models import ...`.

2. Optionally: provide the `async_client` integration-test fixture used by
   tests/test_context_hub.py and tests/test_memory_depth.py. The fixture
   spins up the FastAPI app against a real PostgreSQL test DB
   (`aegis_test`) discovered via $AEGIS_TEST_DATABASE_URL or
   $DATABASE_URL, defaulting to the docker-compose Postgres on
   localhost:5432. If no Postgres is reachable, integration tests are
   skipped (not errored) so the unit-test suite keeps passing on
   machines without the dev stack.

   To keep async connections from leaking across pytest-asyncio's
   per-test event loops, we swap the module-level engine for a
   NullPool engine -- no connection reuse, no cross-loop crashes.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import socket
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 1) Path setup (must happen before any `from <server_module> import ...`)
# ---------------------------------------------------------------------------
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))

# ---------------------------------------------------------------------------
# 2) Env vars for integration tests.
#    These need to be set BEFORE `config.get_settings()` is called anywhere,
#    because that function is `@lru_cache`d. We do it at conftest import time.
# ---------------------------------------------------------------------------
DEFAULT_TEST_DB_URL = "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis_test"

_test_db_url = (
    os.environ.get("AEGIS_TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or DEFAULT_TEST_DB_URL
)
if _test_db_url.startswith("postgresql://"):
    _test_db_url = _test_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

os.environ["DATABASE_URL"] = _test_db_url
os.environ.setdefault("AEGIS_API_KEY", "test-key")
os.environ.setdefault("AEGIS_ENV", "development")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")
os.environ.setdefault("RATE_LIMIT_PER_HOUR", "1000000")
os.environ.setdefault("RATE_LIMIT_BURST", "10000")
os.environ.setdefault("PER_AGENT_RATE_LIMIT_PER_MINUTE", "100000")
os.environ.setdefault("PER_AGENT_RATE_LIMIT_PER_HOUR", "1000000")
os.environ.setdefault("ENABLE_LLM_INJECTION_CLASSIFIER", "false")


# ---------------------------------------------------------------------------
# 3) Reachability check -- decides whether integration tests run or skip
# ---------------------------------------------------------------------------
def _postgres_reachable() -> bool:
    """Best-effort TCP probe for the configured Postgres."""
    try:
        url = _test_db_url
        if "@" in url:
            _, host_port = url.rsplit("@", 1)
            host_port = host_port.split("/", 1)[0]
            if ":" in host_port:
                host, port_s = host_port.split(":", 1)
                port = int(port_s)
            else:
                host, port = host_port, 5432
        else:
            host, port = "localhost", 5432
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


_POSTGRES_OK = _postgres_reachable()


# ---------------------------------------------------------------------------
# 4) Deterministic embedder -- avoids any OpenAI call during tests.
#    Uses sentence-transformers' all-MiniLM-L6-v2 (384-dim) if available,
#    zero-padded to 1536. Falls back to a char-ngram hashing-trick embedder
#    if the library isn't installed (which is fine for tests that only
#    care about exact-token sparse matching, not semantic synonyms).
# ---------------------------------------------------------------------------
_EMBED_DIM = 1536

_SBERT = None
try:  # pragma: no cover - optional dependency
    from sentence_transformers import SentenceTransformer  # type: ignore

    _SBERT = SentenceTransformer("all-MiniLM-L6-v2")
except Exception:
    _SBERT = None


def _sbert_embedding(text: str) -> list[float]:
    """Compute a true semantic embedding, zero-padded to _EMBED_DIM."""
    raw = _SBERT.encode(text or "__empty__", convert_to_numpy=True, normalize_embeddings=True)
    vec = raw.tolist()
    if len(vec) < _EMBED_DIM:
        vec = vec + [0.0] * (_EMBED_DIM - len(vec))
    elif len(vec) > _EMBED_DIM:
        vec = vec[:_EMBED_DIM]
    return vec


def _ngram_embedding(text: str) -> list[float]:
    """Fallback: char-ngram hashing-trick embedder."""
    text = text.lower()
    vec = [0.0] * _EMBED_DIM
    padded = " " + " ".join(text.split()) + " "
    if not padded.strip():
        padded = " __empty__ "
    for n in (3, 4, 5):
        for i in range(len(padded) - n + 1):
            g = padded[i:i + n]
            h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % _EMBED_DIM
            sign = 1.0 if (h[4] & 1) else -1.0
            vec[idx] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        vec[0] = 1.0
        norm = 1.0
    return [x / norm for x in vec]


def _deterministic_embedding(text: str) -> list[float]:
    if _SBERT is not None:
        return _sbert_embedding(text)
    return _ngram_embedding(text)


class _FakeEmbeddingService:
    """Drop-in replacement for EmbeddingService for tests."""

    def __init__(self) -> None:
        self._cache_hits = 0
        self._cache_misses = 0

    async def embed_single(self, text: str, db=None) -> list[float]:
        self._cache_misses += 1
        return _deterministic_embedding(text)

    async def embed_batch(self, texts: list[str], db=None) -> list[list[float]]:
        self._cache_misses += len(texts)
        return [_deterministic_embedding(t) for t in texts]

    async def embed(self, text: str) -> list[float]:
        return _deterministic_embedding(text)

    def get_stats(self) -> dict:
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
        }


# ---------------------------------------------------------------------------
# 5) One-time engine swap to NullPool -- runs on first integration test use.
#    Doing this at conftest import time would break unit tests that don't
#    need a database (e.g. when Postgres isn't running).
# ---------------------------------------------------------------------------
_PATCHED = False


def _patch_for_integration() -> None:
    """Swap engines + embedding service exactly once per test session."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    import embedding_service as _embed_mod
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
    from sqlalchemy.pool import NullPool

    import database as _db_mod

    # New engine with NullPool: no pooled connections, no cross-loop reuse.
    test_engine = create_async_engine(
        _test_db_url, poolclass=NullPool, echo=False
    )
    new_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    _db_mod.primary_engine = test_engine
    _db_mod.replica_engine = test_engine
    _db_mod.AsyncSessionLocal = new_factory
    _db_mod.AsyncReadSessionLocal = new_factory
    _db_mod.async_session_factory = new_factory

    # Fake embedding service.
    fake = _FakeEmbeddingService()
    _embed_mod.get_embedding_service = lambda: fake  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 6) Session-scope schema reset, run inside a fresh loop just for setup
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def _integration_env():
    if not _POSTGRES_OK:
        pytest.skip(
            f"Integration DB not reachable at {_test_db_url}. "
            f"Start it with `docker compose up -d db` (or set "
            f"AEGIS_TEST_DATABASE_URL)."
        )

    _patch_for_integration()

    from sqlalchemy import text as sql_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from models import Base

    async def _reset_schema() -> None:
        # Use a dedicated engine for setup so we don't tangle with the
        # one that the app handlers will use.
        setup_engine = create_async_engine(
            _test_db_url, poolclass=NullPool, echo=False
        )
        try:
            async with setup_engine.begin() as conn:
                await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await setup_engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_reset_schema())
    finally:
        loop.close()

    yield


# ---------------------------------------------------------------------------
# 7) Per-test isolation: TRUNCATE all tables in the test's own loop
# ---------------------------------------------------------------------------
async def _truncate_all() -> None:
    """TRUNCATE every user table in the current event loop."""
    from sqlalchemy import text as sql_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(_test_db_url, poolclass=NullPool, echo=False)
    table_names = [
        "memory_edges",
        "vote_history",
        "memory_shared_agents",
        "memory_events",
        "ace_runs",
        "interaction_events",
        "feature_tracker",
        "session_progress",
        "embedding_cache",
        "memories",
        "prompts",
        "skills",
        "subagents",
        "api_keys",
        "projects",
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sql_text(
                    "TRUNCATE TABLE "
                    + ", ".join(table_names)
                    + " RESTART IDENTITY CASCADE"
                )
            )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 8) The fixture every integration test actually depends on
# ---------------------------------------------------------------------------
@pytest.fixture
async def async_client(_integration_env):
    """
    httpx.AsyncClient bound to the FastAPI app via ASGI transport.

    No real network is involved. The client carries the test bearer token
    so `check_rate_limit` resolves a project_id without needing
    ENABLE_PROJECT_AUTH.

    Each test starts with empty tables and disposes the app's engine on
    exit so the next test's event loop is unencumbered.
    """
    await _truncate_all()

    from httpx import ASGITransport, AsyncClient

    # Import the app inside the fixture so env vars and the engine swap
    # are visible to it.
    from api.app import create_app
    import database as _db_mod

    app = create_app()
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": "Bearer test-key"},
        ) as client:
            yield client
    finally:
        # Dispose the engine in *this* loop so its connections close cleanly.
        await _db_mod.primary_engine.dispose()


# ---------------------------------------------------------------------------
# 9) Skip semantic-embedding tests when only the ngram fallback is available.
#    A few tests assert behavior that needs real semantic embeddings (negation-
#    pair contradiction detection, semantic skill matching). When sentence-
#    transformers isn't installed, the embedder above falls back to a char-ngram
#    hashing trick that can't model meaning, so those tests can't pass. CI runs
#    the lean dependency set (no sentence-transformers), so skip them there.
#    Centralized here so the policy lives in one place.
# ---------------------------------------------------------------------------
_SEMANTIC_DEPENDENT_SUFFIXES = (
    "test_memory_depth.py::test_contradiction_scan_finds_negation_pair",
    "test_context_hub.py::test_skill_create_and_match",
)


def pytest_collection_modifyitems(config, items):
    if _SBERT is not None:
        return
    skip_marker = pytest.mark.skip(
        reason="needs semantic embeddings (sentence-transformers); "
        "ngram fallback can't model meaning"
    )
    for item in items:
        if item.nodeid.endswith(_SEMANTIC_DEPENDENT_SUFFIXES):
            item.add_marker(skip_marker)
