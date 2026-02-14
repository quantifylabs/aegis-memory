"""
Aegis Production Main Application

Key improvements:
1. Proper lifespan management (replaces deprecated @app.on_event)
2. Structured logging
3. Request ID tracking
4. Graceful shutdown
5. Prometheus metrics

ACE Enhancements (v1.1):
6. Voting, delta updates, progress tracking, feature tracking endpoints
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
from routes import router as memory_router
from routes_ace import router as ace_router
from routes_dashboard import router as dashboard_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("aegis")

settings = get_settings()

try:
    __version__ = importlib.metadata.version("aegis-memory")
except importlib.metadata.PackageNotFoundError:
    __version__ = "dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown.

    Replaces deprecated @app.on_event("startup") and @app.on_event("shutdown").
    """
    # Startup
    logger.info("Aegis Memory API starting...")

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Load genesis playbook if database is empty
    try:
        from database import async_session_factory
        from playbook_loader import load_genesis_playbook

        async with async_session_factory() as db:
            stats = await load_genesis_playbook(db)
            if stats["loaded"] > 0:
                logger.info(f"Genesis playbook loaded: {stats['loaded']} entries")
            elif stats["already_exists"]:
                logger.info("Genesis playbook already present")
    except Exception as e:
        logger.warning(f"Could not load genesis playbook: {e}")
        # Non-fatal - continue startup

    try:
        await get_event_pipeline().start()
    except Exception as e:
        logger.warning(f"Observability event pipeline failed to start: {e}")

    logger.info("Aegis Memory API ready")

    yield

    # Shutdown
    logger.info("Aegis Memory API shutting down...")
    await get_event_pipeline().stop()


app = FastAPI(
    title="Aegis Memory API",
    version=__version__,
    description="""
    # Aegis Memory

    **Production-grade multi-agent memory layer with ACE enhancements.**

    ## Features

    - **Semantic Search**: pgvector HNSW index for fast similarity search
    - **Multi-Agent Support**: Scope-aware access control, cross-agent queries, handoffs
    - **ACE Patterns**: Memory voting, incremental updates, reflections, progress tracking
    - **Production Ready**: Connection pooling, caching, rate limiting, observability

    ## Quick Start

    ```python
    from aegis_memory import AegisClient

    client = AegisClient(api_key="your-key")
    client.add("User prefers dark mode", agent_id="assistant")
    memories = client.query("user preferences", agent_id="assistant")
    ```

    ## Links

    - [Documentation](https://github.com/quantifylabs/aegis-memory)
    - [ACE Patterns Guide](https://github.com/quantifylabs/aegis-memory/blob/main/docs/ACE-PATTERNS.md)
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------- Middleware ----------

# CORS
cors_origins = settings.get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)



app.add_middleware(
    ObservabilityMiddleware,
)

# ---------- Routes ----------

@app.get("/", tags=["root"])
async def root():
    """API root - returns basic info."""
    return {
        "name": "Aegis Memory API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint."""
    db_health = await check_db_health()

    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "version": __version__,
        "features": ["voting", "delta_updates", "progress_tracking", "feature_tracking"],
        "database": db_health,
    }


@app.get("/ready", tags=["health"])
async def ready():
    """Readiness probe for Kubernetes."""
    db_health = await check_db_health()

    if db_health["status"] != "healthy":
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "database unhealthy"}
        )

    return {"status": "ready"}


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint.

    Exposes:
    - HTTP request counts and latencies
    - Memory operation metrics
    - Embedding cache statistics
    - Database connection pool health
    - ACE pattern usage
    """
    try:
        from observability import metrics_endpoint
        return await metrics_endpoint()
    except ImportError:
        return JSONResponse(
            status_code=501,
            content={"detail": "Metrics not available - install prometheus_client"}
        )


# Mount memory routes
app.include_router(memory_router, prefix="/memories", tags=["memories"])

# Mount ACE-enhanced routes (voting, delta, progress, features)
app.include_router(ace_router, prefix="/memories", tags=["ace"])

# Mount dashboard routes (stats, activity, sessions)
app.include_router(dashboard_router)  # Already has prefix="/memories/ace/dashboard"


# ---------- Run ----------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,  # Use 1 for dev, increase for prod
    )
