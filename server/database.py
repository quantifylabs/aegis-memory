"""
Aegis Production Database Layer

Key improvements:
1. Async SQLAlchemy with asyncpg (not psycopg2)
2. Connection pooling with sensible defaults
3. Read replica support for query scaling
4. Health checks and connection recycling
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

settings = get_settings()


def _create_engine(url: str, pool_size: int = 20, max_overflow: int = 10, is_read_replica: bool = False):
    """
    Create an async engine with production-ready pooling.

    Pool sizing guidelines:
    - pool_size: Number of persistent connections (match expected concurrency)
    - max_overflow: Burst capacity (for traffic spikes)
    - Total max connections = pool_size + max_overflow

    For a typical deployment:
    - 2 uvicorn workers × 20 pool_size = 40 connections
    - PostgreSQL default max_connections = 100
    - Leave headroom for migrations, monitoring, etc.
    """
    return create_async_engine(
        url,
        echo=settings.sql_echo,
        pool_pre_ping=True,  # Verify connections before use
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_timeout=30,  # Wait max 30s for a connection
        # SQLAlchemy automatically uses AsyncAdaptedQueuePool for async engines
        # Use NullPool for serverless (Lambda, Cloud Run) by setting pool_size=0
    )


# Primary (write) engine
primary_engine = _create_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

# Read replica engine (optional - falls back to primary if not configured)
_replica_url = settings.database_read_replica_url
if _replica_url:
    replica_engine = _create_engine(
        _replica_url.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=settings.db_pool_size * 2,  # Read replicas handle more load
        max_overflow=settings.db_max_overflow * 2,
        is_read_replica=True,
    )
else:
    replica_engine = primary_engine


# Session factories
AsyncSessionLocal = async_sessionmaker(
    bind=primary_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

AsyncReadSessionLocal = async_sessionmaker(
    bind=replica_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Alias for backwards compatibility
async_session_factory = AsyncSessionLocal


# Context manager versions (for use with 'async with')
@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for writes (context manager version)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_read_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for reads (context manager version)."""
    async with AsyncReadSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# FastAPI dependency versions (plain async generators)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for writes (FastAPI dependency)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for reads (FastAPI dependency)."""
    async with AsyncReadSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialize database schema and extensions."""
    async with primary_engine.begin() as conn:
        # Enable pgvector
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Import and create all tables
        from models import Base
        await conn.run_sync(Base.metadata.create_all)


async def check_db_health() -> dict:
    """Health check for database connectivity and performance."""
    try:
        async with AsyncSessionLocal() as session:
            start = asyncio.get_event_loop().time()
            await session.execute(text("SELECT 1"))
            latency = (asyncio.get_event_loop().time() - start) * 1000

            # Get pool stats
            pool = primary_engine.pool
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "pool_size": pool.size(),
                "pool_checked_in": pool.checkedin(),
                "pool_checked_out": pool.checkedout(),
                "pool_overflow": pool.overflow(),
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
