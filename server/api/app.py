"""
Aegis Memory API Application (v1.7.0+ modular entry point)

This module provides the new modular FastAPI application using
the decomposed router structure from api/routers/.

The original main.py continues to work as a backward-compatible entry point.
"""

import importlib.metadata
import logging
from contextlib import asynccontextmanager

from config import get_settings
from database import check_db_health, init_db
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from observability import ObservabilityMiddleware
from observability_events import get_event_pipeline

from api.routers import (
    ace_delta,
    ace_eval,
    ace_features,
    ace_progress,
    ace_reflections,
    ace_votes,
    dashboard,
    handoffs,
    interaction_events,
    memories,
    typed_memory,
)

logger = logging.getLogger("aegis")
settings = get_settings()

try:
    __version__ = importlib.metadata.version("aegis-memory")
except importlib.metadata.PackageNotFoundError:
    __version__ = "dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Aegis Memory API starting...")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    try:
        from database import async_session_factory
        from playbook_loader import load_genesis_playbook
        async with async_session_factory() as db:
            stats = await load_genesis_playbook(db)
            if stats["loaded"] > 0:
                logger.info(f"Genesis playbook loaded: {stats['loaded']} entries")
    except Exception as e:
        logger.warning(f"Could not load genesis playbook: {e}")

    try:
        await get_event_pipeline().start()
    except Exception as e:
        logger.warning(f"Observability event pipeline failed to start: {e}")

    logger.info("Aegis Memory API ready")
    yield
    logger.info("Aegis Memory API shutting down...")
    await get_event_pipeline().stop()


def create_app() -> FastAPI:
    """Create the FastAPI application with modular routers."""
    app = FastAPI(
        title="Aegis Memory API",
        version=__version__,
        description="Production-grade multi-agent memory layer with ACE enhancements.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware
    cors_origins = settings.get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=settings.cors_allow_credentials(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ObservabilityMiddleware)

    # Root endpoints
    @app.get("/", tags=["root"])
    async def root():
        return {"name": "Aegis Memory API", "version": __version__, "docs": "/docs", "health": "/health"}

    @app.get("/health", tags=["health"])
    async def health():
        db_health = await check_db_health()
        return {"status": "healthy" if db_health["status"] == "healthy" else "degraded", "version": __version__, "database": db_health}

    @app.get("/ready", tags=["health"])
    async def ready():
        db_health = await check_db_health()
        if db_health["status"] != "healthy":
            return JSONResponse(status_code=503, content={"status": "not ready", "reason": "database unhealthy"})
        return {"status": "ready"}

    @app.get("/metrics", tags=["monitoring"])
    async def metrics():
        try:
            from observability import metrics_endpoint
            return await metrics_endpoint()
        except ImportError:
            return JSONResponse(status_code=501, content={"detail": "Metrics not available"})

    # Mount modular routers
    app.include_router(memories.router, prefix="/memories", tags=["memories"])
    app.include_router(handoffs.router, prefix="/memories", tags=["memories"])

    # ACE routers under /memories/ace
    app.include_router(ace_votes.router, prefix="/memories/ace", tags=["ACE"])
    app.include_router(ace_delta.router, prefix="/memories/ace", tags=["ACE"])
    app.include_router(ace_reflections.router, prefix="/memories/ace", tags=["ACE"])
    app.include_router(ace_progress.router, prefix="/memories/ace", tags=["ACE"])
    app.include_router(ace_features.router, prefix="/memories/ace", tags=["ACE"])
    app.include_router(ace_eval.router, prefix="/memories/ace", tags=["ACE"])

    # Typed Memory (v1.9.0)
    app.include_router(typed_memory.router, prefix="/memories/typed", tags=["typed-memory"])

    # Interaction Events (v1.9.11)
    app.include_router(interaction_events.router, prefix="/interaction-events", tags=["interaction-events"])

    # Dashboard
    app.include_router(dashboard.router)

    return app


# Module-level app instance for uvicorn
modular_app = create_app()
