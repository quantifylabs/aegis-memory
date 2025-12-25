"""
Aegis Memory Observability

Structured logging and Prometheus metrics for production monitoring.

Features:
- Structured JSON logging
- Request tracing with correlation IDs
- Prometheus metrics endpoint
- Operation latency tracking
- Error rate monitoring

Usage:
    # Logging is automatic via middleware

    # Access metrics at /metrics
    curl http://localhost:8000/metrics
"""

import json
import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ============================================================================
# Structured Logging
# ============================================================================

class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.123Z",
        "level": "INFO",
        "logger": "aegis.memory",
        "message": "Memory added",
        "request_id": "abc-123",
        "project_id": "proj-1",
        "duration_ms": 45.2,
        ...
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "project_id"):
            log_data["project_id"] = record.project_id
        if hasattr(record, "agent_id"):
            log_data["agent_id"] = record.agent_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "operation"):
            log_data["operation"] = record.operation
        if hasattr(record, "memory_count"):
            log_data["memory_count"] = record.memory_count

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(level: str = "INFO", json_format: bool = True):
    """
    Configure logging for Aegis Memory.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, use JSON format for structured logging
    """
    logger = logging.getLogger("aegis")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Add handler with appropriate formatter
    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))

    logger.addHandler(handler)
    return logger


# Create default logger
logger = setup_logging()


class LogContext:
    """
    Context manager for adding fields to log records.

    Usage:
        with LogContext(request_id="abc", project_id="proj-1"):
            logger.info("Processing request")  # Includes request_id and project_id
    """

    _context = {}

    def __init__(self, **kwargs):
        self.fields = kwargs
        self.previous = {}

    def __enter__(self):
        self.previous = LogContext._context.copy()
        LogContext._context.update(self.fields)
        return self

    def __exit__(self, *args):
        LogContext._context = self.previous


class ContextFilter(logging.Filter):
    """Add context fields to log records."""

    def filter(self, record):
        for key, value in LogContext._context.items():
            setattr(record, key, value)
        return True


# ============================================================================
# Prometheus Metrics
# ============================================================================

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


if PROMETHEUS_AVAILABLE:
    # Request metrics
    REQUEST_COUNT = Counter(
        "aegis_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"]
    )

    REQUEST_LATENCY = Histogram(
        "aegis_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "endpoint"],
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    # Memory operation metrics
    MEMORY_OPERATIONS = Counter(
        "aegis_memory_operations_total",
        "Total memory operations",
        ["operation", "status"]  # operation: add, query, delete, vote
    )

    MEMORY_OPERATION_LATENCY = Histogram(
        "aegis_memory_operation_duration_seconds",
        "Memory operation latency",
        ["operation"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
    )

    # Embedding metrics
    EMBEDDING_CACHE_HITS = Counter(
        "aegis_embedding_cache_hits_total",
        "Embedding cache hits"
    )

    EMBEDDING_CACHE_MISSES = Counter(
        "aegis_embedding_cache_misses_total",
        "Embedding cache misses"
    )

    EMBEDDING_LATENCY = Histogram(
        "aegis_embedding_duration_seconds",
        "Embedding generation latency",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
    )

    # Database metrics
    DB_POOL_SIZE = Gauge(
        "aegis_db_pool_size",
        "Database connection pool size"
    )

    DB_POOL_CHECKED_OUT = Gauge(
        "aegis_db_pool_checked_out",
        "Database connections currently in use"
    )

    # Memory count metrics
    MEMORY_COUNT = Gauge(
        "aegis_memories_total",
        "Total memories stored",
        ["project_id", "namespace"]
    )

    # ACE metrics
    ACE_VOTES = Counter(
        "aegis_ace_votes_total",
        "ACE memory votes",
        ["vote_type"]  # helpful, harmful
    )

    ACE_REFLECTIONS = Counter(
        "aegis_ace_reflections_total",
        "ACE reflections created"
    )

    ACE_SESSIONS = Gauge(
        "aegis_ace_sessions_active",
        "Active ACE sessions"
    )


def record_operation(operation: str, status: str = "success"):
    """Record a memory operation."""
    if PROMETHEUS_AVAILABLE:
        MEMORY_OPERATIONS.labels(operation=operation, status=status).inc()


@contextmanager
def track_latency(operation: str):
    """Context manager to track operation latency."""
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        if PROMETHEUS_AVAILABLE:
            MEMORY_OPERATION_LATENCY.labels(operation=operation).observe(duration)
        logger.debug(
            f"Operation {operation} completed",
            extra={"operation": operation, "duration_ms": duration * 1000}
        )


def record_embedding_cache(hit: bool):
    """Record embedding cache hit/miss."""
    if PROMETHEUS_AVAILABLE:
        if hit:
            EMBEDDING_CACHE_HITS.inc()
        else:
            EMBEDDING_CACHE_MISSES.inc()


def record_vote(vote_type: str):
    """Record ACE vote."""
    if PROMETHEUS_AVAILABLE:
        ACE_VOTES.labels(vote_type=vote_type).inc()


# ============================================================================
# FastAPI Middleware
# ============================================================================

class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for request tracing and metrics.

    Adds:
    - Request ID tracking
    - Request/response logging
    - Prometheus metrics
    - Latency headers
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", f"req-{int(time.time() * 1000)}")

        # Extract project ID from auth (if available)
        project_id = getattr(request.state, "project_id", "unknown")

        # Set up logging context
        start = time.monotonic()

        with LogContext(request_id=request_id, project_id=project_id):
            logger.info(
                f"Request started: {request.method} {request.url.path}",
                extra={"operation": "request_start"}
            )

            try:
                response = await call_next(request)
                status = response.status_code
            except Exception:
                status = 500
                logger.exception("Request failed", extra={"operation": "request_error"})
                raise
            finally:
                duration = time.monotonic() - start

                # Log completion
                logger.info(
                    f"Request completed: {request.method} {request.url.path} -> {status}",
                    extra={
                        "operation": "request_complete",
                        "duration_ms": duration * 1000,
                    }
                )

                # Record metrics
                if PROMETHEUS_AVAILABLE:
                    endpoint = self._normalize_path(request.url.path)
                    REQUEST_COUNT.labels(
                        method=request.method,
                        endpoint=endpoint,
                        status=status
                    ).inc()
                    REQUEST_LATENCY.labels(
                        method=request.method,
                        endpoint=endpoint
                    ).observe(duration)

        # Add tracing headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration * 1000:.2f}ms"

        return response

    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics (remove IDs)."""
        parts = path.split("/")
        normalized = []
        for part in parts:
            # Replace UUIDs and hex IDs with placeholder
            if len(part) == 32 and all(c in "0123456789abcdef" for c in part):
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/".join(normalized)


# ============================================================================
# Metrics Endpoint
# ============================================================================

async def metrics_endpoint():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    """
    if not PROMETHEUS_AVAILABLE:
        return Response(
            content="prometheus_client not installed",
            status_code=501
        )

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ============================================================================
# Health Check Helpers
# ============================================================================

async def check_database_health(db_pool) -> dict:
    """Check database connection health."""
    try:
        # Try to get a connection
        async with db_pool.connect() as conn:
            await conn.execute("SELECT 1")

        # Update pool metrics
        if PROMETHEUS_AVAILABLE:
            DB_POOL_SIZE.set(db_pool.pool.size())
            DB_POOL_CHECKED_OUT.set(db_pool.pool.checkedout())

        return {
            "status": "healthy",
            "pool_size": db_pool.pool.size(),
            "checked_out": db_pool.pool.checkedout(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def check_embedding_service_health(embed_service) -> dict:
    """Check embedding service health."""
    try:
        # Try a simple embedding
        await embed_service.embed_single("health check", None)
        return {
            "status": "healthy",
            "model": embed_service.model,
            "cache_stats": embed_service.get_stats(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
