"""Aegis Memory observability bridge for OTEL, metrics, and timeline events."""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from collections import Counter as CollectionCounter
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from observability_events import EventEnvelope, enqueue_event

# Optional OpenTelemetry wiring (migration-safe)
try:
    from opentelemetry import metrics, trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    OTEL_AVAILABLE = False


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "project_id", "agent_id", "duration_ms", "operation", "memory_count"):
            if hasattr(record, field):
                log_data[field] = getattr(record, field)
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging(level: str = "INFO", json_format: bool = True):
    logger = logging.getLogger("aegis")
    logger.setLevel(getattr(logging, level.upper()))
    logger.handlers = []
    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    return logger


logger = setup_logging()


class OperationNames:
    MEMORY_ADD = "memory_add"
    MEMORY_ADD_BATCH = "memory_add_batch"
    MEMORY_QUERY = "memory_query"
    MEMORY_QUERY_CROSS_AGENT = "memory_query_cross_agent"
    MEMORY_DELETE = "memory_delete"
    MEMORY_FIND_DUPLICATE = "memory_find_duplicate"
    MEMORY_SEMANTIC_SEARCH = "memory_semantic_search"
    MEMORY_GET_BY_ID = "memory_get_by_id"
    MEMORY_GET_HANDOFF = "memory_get_handoff"
    MEMORY_VOTE = "memory_vote"
    MEMORY_DELTA = "memory_delta"
    MEMORY_DELTA_ADD = "memory_delta_add"
    MEMORY_DELTA_UPDATE = "memory_delta_update"
    MEMORY_DELTA_DEPRECATE = "memory_delta_deprecate"
    MEMORY_REFLECTION = "memory_reflection"
    MEMORY_SESSION_CREATE = "memory_session_create"
    MEMORY_SESSION_GET = "memory_session_get"
    MEMORY_SESSION_UPDATE = "memory_session_update"
    MEMORY_FEATURE_CREATE = "memory_feature_create"
    MEMORY_FEATURE_GET = "memory_feature_get"
    MEMORY_FEATURE_UPDATE = "memory_feature_update"
    MEMORY_FEATURE_LIST = "memory_feature_list"
    MEMORY_RUN_CREATE = "memory_run_create"
    MEMORY_RUN_GET = "memory_run_get"
    MEMORY_RUN_COMPLETE = "memory_run_complete"
    MEMORY_PLAYBOOK_AGENT = "memory_playbook_agent"
    MEMORY_CURATE = "memory_curate"
    INTERACTION_CREATE = "interaction_create"
    INTERACTION_GET = "interaction_get"
    INTERACTION_SESSION_TIMELINE = "interaction_session_timeline"
    INTERACTION_AGENT_HISTORY = "interaction_agent_history"
    INTERACTION_SEARCH = "interaction_search"
    INTERACTION_CHAIN = "interaction_chain"


class SpanNames:
    HTTP_REQUEST = "aegis.http.request"
    MEMORY_OPERATION = "aegis.memory.operation"


class EventNames:
    HTTP_COMPLETED = "http_request.completed"
    MEMORY_OPERATION = "memory.operation"


class LogContext:
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
    def filter(self, record):
        for key, value in LogContext._context.items():
            setattr(record, key, value)
        return True


_context_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_context_project_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("project_id", default=None)
_context_agent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("agent_id", default=None)
_context_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


class ObservabilityBridge:
    """Bridge layer that enriches OTEL context and mirrors legacy Prometheus metrics."""

    def __init__(self):
        if OTEL_AVAILABLE:
            self.tracer = trace.get_tracer("aegis.observability")
            self.meter = metrics.get_meter("aegis.observability")
            self.http_counter = self.meter.create_counter("aegis.http.requests")
            self.http_latency = self.meter.create_histogram("aegis.http.request.duration", unit="s")
            self.memory_counter = self.meter.create_counter("aegis.memory.operations")
            self.memory_latency = self.meter.create_histogram("aegis.memory.operation.duration", unit="s")
        else:
            self.tracer = None
            self.meter = None
            self.http_counter = None
            self.http_latency = None
            self.memory_counter = None
            self.memory_latency = None

    def current(self) -> dict[str, str | None]:
        return {
            "request_id": _context_request_id.get(),
            "project_id": _context_project_id.get(),
            "agent_id": _context_agent_id.get(),
            "trace_id": _context_trace_id.get(),
        }

    def set_context(self, *, request_id: str, project_id: str, agent_id: str | None, trace_id: str):
        return (
            _context_request_id.set(request_id),
            _context_project_id.set(project_id),
            _context_agent_id.set(agent_id),
            _context_trace_id.set(trace_id),
        )

    def reset_context(self, tokens):
        _context_request_id.reset(tokens[0])
        _context_project_id.reset(tokens[1])
        _context_agent_id.reset(tokens[2])
        _context_trace_id.reset(tokens[3])

    def active_span(self):
        if not OTEL_AVAILABLE:
            return None
        return trace.get_current_span()

    def emit_span_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        span = self.active_span()
        if span is not None:
            span.add_event(name, attributes=attributes or {})

    def emit_timeline_event(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        derived_metrics: dict[str, Any] | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ):
        ctx = self.current()
        project_id = ctx["project_id"] or "unknown"
        enqueue_event(
            EventEnvelope(
                trace_id=ctx["trace_id"] or str(uuid.uuid4()),
                request_id=ctx["request_id"],
                project_id=project_id,
                agent_id=ctx["agent_id"],
                session_id=session_id,
                task_id=task_id,
                event_type=event_type,
                payload=payload,
                derived_metrics=derived_metrics or {},
            )
        )


OBS_BRIDGE = ObservabilityBridge()

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    REQUEST_COUNT = Counter("aegis_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
    REQUEST_LATENCY = Histogram(
        "aegis_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "endpoint"],
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    MEMORY_OPERATIONS = Counter("aegis_memory_operations_total", "Total memory operations", ["operation", "status"])
    MEMORY_OPERATION_LATENCY = Histogram(
        "aegis_memory_operation_duration_seconds",
        "Memory operation latency",
        ["operation"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    )
    EMBEDDING_CACHE_HITS = Counter("aegis_embedding_cache_hits_total", "Embedding cache hits")
    EMBEDDING_CACHE_MISSES = Counter("aegis_embedding_cache_misses_total", "Embedding cache misses")
    EMBEDDING_LATENCY = Histogram(
        "aegis_embedding_duration_seconds",
        "Embedding generation latency",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    DB_POOL_SIZE = Gauge("aegis_db_pool_size", "Database connection pool size")
    DB_POOL_CHECKED_OUT = Gauge("aegis_db_pool_checked_out", "Database connections currently in use")
    MEMORY_COUNT = Gauge("aegis_memories_total", "Total memories stored", ["project_id", "namespace"])
    ACE_VOTES = Counter("aegis_ace_votes_total", "ACE memory votes", ["vote_type"])
    ACE_REFLECTIONS = Counter("aegis_ace_reflections_total", "ACE reflections created")
    ACE_SESSIONS = Gauge("aegis_ace_sessions_active", "Active ACE sessions")
    QUERY_ATTEMPTS = Counter("aegis_memory_query_attempts_total", "Total memory query attempts", ["source", "requested_scope", "effective_scope"])
    QUERY_RESULTS_COUNT = Histogram("aegis_memory_query_results_count", "Distribution of number of results returned by each query", ["source"], buckets=[0, 1, 2, 5, 10, 20, 50, 100])
    QUERY_ZERO_RESULTS = Counter("aegis_memory_query_miss_total", "Total memory queries that returned zero results", ["source", "effective_scope"])
    QUERY_LATENCY = Histogram(
        "aegis_memory_query_execution_duration_seconds",
        "End-to-end query latency",
        ["source"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    QUERY_FILTER_USAGE = Counter("aegis_memory_query_filter_usage_total", "Usage of query filters", ["scope", "memory_type", "min_effectiveness", "target_agent_ids_used"])
    MEMORY_SCOPE_STORED = Counter("aegis_memory_scope_stored_total", "Distribution of memory scopes at write time", ["scope"])
    MEMORY_SCOPE_RETRIEVED = Counter("aegis_memory_scope_retrieved_total", "Distribution of memory scopes in retrievals", ["scope"])


_QUERY_EVENT_LIMIT = 2000
_QUERY_EVENTS = deque(maxlen=_QUERY_EVENT_LIMIT)


def _safe_scope(value: str | None) -> str:
    return value or "unspecified"


def normalize_query_intent(query: str) -> str:
    normalized = " ".join(query.strip().lower().split())
    if not normalized:
        return "empty"
    tokens = [token.strip(".,!?;:\"'()[]{}") for token in normalized.split(" ")]
    tokens = [token for token in tokens if token]
    return " ".join(tokens[:4]) or "empty"


def record_memory_stored_scope(scope: str, count: int = 1):
    if PROMETHEUS_AVAILABLE:
        MEMORY_SCOPE_STORED.labels(scope=_safe_scope(scope)).inc(count)


def record_query_execution(
    *,
    source: str,
    duration_seconds: float,
    total_returned: int,
    requested_scope: str | None,
    effective_scope: str,
    memory_type: str | None = None,
    min_effectiveness: float | None = None,
    target_agent_ids_used: bool = False,
    query_text: str | None = None,
    retrieved_scopes: list[str] | None = None,
    retrieved_agent_ids: list[str] | None = None,
):
    if PROMETHEUS_AVAILABLE:
        QUERY_ATTEMPTS.labels(source=source, requested_scope=_safe_scope(requested_scope), effective_scope=effective_scope).inc()
        QUERY_RESULTS_COUNT.labels(source=source).observe(total_returned)
        QUERY_LATENCY.labels(source=source).observe(duration_seconds)
        QUERY_FILTER_USAGE.labels(
            scope=_safe_scope(requested_scope),
            memory_type=memory_type or "any",
            min_effectiveness="used" if min_effectiveness is not None else "not_used",
            target_agent_ids_used="true" if target_agent_ids_used else "false",
        ).inc()
        if total_returned == 0:
            QUERY_ZERO_RESULTS.labels(source=source, effective_scope=effective_scope).inc()
        if retrieved_scopes:
            for scope in retrieved_scopes:
                MEMORY_SCOPE_RETRIEVED.labels(scope=_safe_scope(scope)).inc()

    OBS_BRIDGE.emit_span_event(
        "memory.query.results",
        {
            "source": source,
            "total_returned": total_returned,
            "requested_scope": _safe_scope(requested_scope),
            "effective_scope": effective_scope,
        },
    )

    _QUERY_EVENTS.append(
        {
            "timestamp": datetime.utcnow(),
            "source": source,
            "intent": normalize_query_intent(query_text or ""),
            "hit": total_returned > 0,
            "total_returned": total_returned,
            "requested_scope": _safe_scope(requested_scope),
            "effective_scope": effective_scope,
            "retrieved_agent_ids": retrieved_agent_ids or [],
        }
    )


def get_query_analytics(window_minutes: int = 60, bucket_minutes: int = 10) -> dict:
    now = datetime.utcnow()
    window_start = now.timestamp() - (window_minutes * 60)
    events = [event for event in _QUERY_EVENTS if event["timestamp"].timestamp() >= window_start]
    intent_counts = CollectionCounter(event["intent"] for event in events)
    scope_usage = CollectionCounter(event["requested_scope"] for event in events)
    agent_counts = CollectionCounter()
    for event in events:
        for agent_id in event.get("retrieved_agent_ids", []):
            if agent_id:
                agent_counts[agent_id] += 1

    bucket_seconds = max(1, bucket_minutes) * 60
    trend_buckets: dict[int, dict[str, int]] = {}
    for event in events:
        ts = int(event["timestamp"].timestamp())
        bucket = ts - (ts % bucket_seconds)
        stats = trend_buckets.setdefault(bucket, {"queries": 0, "hits": 0})
        stats["queries"] += 1
        if event["hit"]:
            stats["hits"] += 1

    hit_rate_trend = []
    for bucket in sorted(trend_buckets):
        stats = trend_buckets[bucket]
        queries = stats["queries"]
        hit_rate_trend.append(
            {
                "bucket_start": datetime.utcfromtimestamp(bucket),
                "queries": queries,
                "hits": stats["hits"],
                "hit_rate": (stats["hits"] / queries) if queries else 0.0,
            }
        )

    total_agent_retrievals = sum(agent_counts.values())
    per_agent_share = [
        {
            "agent_id": agent_id,
            "retrievals": count,
            "share": (count / total_agent_retrievals) if total_agent_retrievals else 0.0,
        }
        for agent_id, count in agent_counts.most_common(10)
    ]

    return {
        "window_minutes": window_minutes,
        "sample_size": len(events),
        "top_query_intents": [{"intent": intent, "count": count} for intent, count in intent_counts.most_common(10)],
        "hit_rate_trend": hit_rate_trend,
        "scope_usage_breakdown": [{"scope": scope, "count": count} for scope, count in scope_usage.items()],
        "per_agent_retrieval_share": per_agent_share,
    }


def record_operation(operation: str, status: str = "success"):
    attrs = {"operation": operation, "status": status}
    if OTEL_AVAILABLE and OBS_BRIDGE.memory_counter is not None:
        OBS_BRIDGE.memory_counter.add(1, attributes=attrs)
    if PROMETHEUS_AVAILABLE:
        MEMORY_OPERATIONS.labels(operation=operation, status=status).inc()

    OBS_BRIDGE.emit_span_event("memory.operation.status", attrs)
    OBS_BRIDGE.emit_timeline_event(
        event_type=EventNames.MEMORY_OPERATION,
        payload={"operation": operation, "status": status},
    )


@contextmanager
def track_latency(operation: str):
    start = time.monotonic()
    span_ctx = None
    if OTEL_AVAILABLE and OBS_BRIDGE.tracer is not None:
        span_ctx = OBS_BRIDGE.tracer.start_as_current_span(
            SpanNames.MEMORY_OPERATION,
            kind=SpanKind.INTERNAL,
            attributes={
                "aegis.operation.name": operation,
                "aegis.request_id": _context_request_id.get() or "",
                "aegis.project_id": _context_project_id.get() or "unknown",
                "aegis.agent_id": _context_agent_id.get() or "",
            },
        )
        span_ctx.__enter__()

    try:
        yield
        if OTEL_AVAILABLE and span_ctx is not None:
            trace.get_current_span().set_status(Status(status_code=StatusCode.OK))
    except Exception as exc:
        if OTEL_AVAILABLE and span_ctx is not None:
            span = trace.get_current_span()
            span.record_exception(exc)
            span.set_status(Status(status_code=StatusCode.ERROR, description=str(exc)))
        raise
    finally:
        duration = time.monotonic() - start
        if OTEL_AVAILABLE and OBS_BRIDGE.memory_latency is not None:
            OBS_BRIDGE.memory_latency.record(duration, attributes={"operation": operation})
        if PROMETHEUS_AVAILABLE:
            MEMORY_OPERATION_LATENCY.labels(operation=operation).observe(duration)

        OBS_BRIDGE.emit_span_event("memory.operation.timing", {"operation": operation, "duration_ms": duration * 1000})
        logger.debug(f"Operation {operation} completed", extra={"operation": operation, "duration_ms": duration * 1000})
        if span_ctx is not None:
            span_ctx.__exit__(None, None, None)


def record_embedding_cache(hit: bool):
    if PROMETHEUS_AVAILABLE:
        if hit:
            EMBEDDING_CACHE_HITS.inc()
        else:
            EMBEDDING_CACHE_MISSES.inc()


def record_vote(vote_type: str):
    if PROMETHEUS_AVAILABLE:
        ACE_VOTES.labels(vote_type=vote_type).inc()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID", f"req-{int(time.time() * 1000)}")
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        request.state.trace_id = trace_id

        project_id = request.headers.get("X-Project-ID") or getattr(request.state, "project_id", "unknown")
        agent_id = request.headers.get("X-Agent-ID")
        session_id = request.headers.get("X-Session-ID")
        task_id = request.headers.get("X-Task-ID")
        start = time.monotonic()

        tokens = OBS_BRIDGE.set_context(request_id=request_id, project_id=project_id, agent_id=agent_id, trace_id=trace_id)
        span_ctx = None
        status = 500
        endpoint = self._normalize_path(request.url.path)

        if OTEL_AVAILABLE and OBS_BRIDGE.tracer is not None:
            span_ctx = OBS_BRIDGE.tracer.start_as_current_span(
                SpanNames.HTTP_REQUEST,
                kind=SpanKind.SERVER,
                attributes={
                    "http.method": request.method,
                    "http.route": endpoint,
                    "url.path": request.url.path,
                    "aegis.request_id": request_id,
                    "aegis.project_id": project_id,
                    "aegis.agent_id": agent_id or "",
                },
            )
            span_ctx.__enter__()

        with LogContext(request_id=request_id, project_id=project_id, agent_id=agent_id):
            try:
                response = await call_next(request)
                status = response.status_code
            except Exception as exc:
                if OTEL_AVAILABLE and span_ctx is not None:
                    span = trace.get_current_span()
                    span.record_exception(exc)
                    span.set_status(Status(status_code=StatusCode.ERROR, description=str(exc)))
                logger.exception("Request failed", extra={"operation": "request_error"})
                raise
            finally:
                duration = time.monotonic() - start
                if OTEL_AVAILABLE and OBS_BRIDGE.http_counter is not None:
                    attrs = {"http.method": request.method, "http.route": endpoint, "http.status_code": status}
                    OBS_BRIDGE.http_counter.add(1, attributes=attrs)
                    OBS_BRIDGE.http_latency.record(duration, attributes={"http.method": request.method, "http.route": endpoint})

                if PROMETHEUS_AVAILABLE:
                    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=status).inc()
                    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)

                OBS_BRIDGE.emit_span_event("http.request.completed", {"status_code": status, "duration_ms": duration * 1000})
                OBS_BRIDGE.emit_timeline_event(
                    event_type=EventNames.HTTP_COMPLETED,
                    payload={"method": request.method, "path": request.url.path, "endpoint": endpoint, "status_code": status},
                    derived_metrics={"duration_ms": round(duration * 1000, 3)},
                    session_id=session_id,
                    task_id=task_id,
                )

                logger.info(
                    f"Request completed: {request.method} {request.url.path} -> {status}",
                    extra={"operation": "request_complete", "duration_ms": duration * 1000},
                )

                if span_ctx is not None:
                    if OTEL_AVAILABLE:
                        trace.get_current_span().set_attribute("http.status_code", status)
                    span_ctx.__exit__(None, None, None)
                OBS_BRIDGE.reset_context(tokens)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Response-Time"] = f"{duration * 1000:.2f}ms"
        return response

    def _normalize_path(self, path: str) -> str:
        parts = path.split("/")
        normalized = []
        for part in parts:
            if len(part) == 32 and all(c in "0123456789abcdef" for c in part):
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/".join(normalized)


async def metrics_endpoint():
    if not PROMETHEUS_AVAILABLE:
        return Response(content="prometheus_client not installed", status_code=501)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def check_database_health(db_pool) -> dict:
    try:
        async with db_pool.connect() as conn:
            await conn.execute("SELECT 1")
        if PROMETHEUS_AVAILABLE:
            DB_POOL_SIZE.set(db_pool.pool.size())
            DB_POOL_CHECKED_OUT.set(db_pool.pool.checkedout())
        return {"status": "healthy", "pool_size": db_pool.pool.size(), "checked_out": db_pool.pool.checkedout()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_embedding_service_health(embed_service) -> dict:
    try:
        await embed_service.embed_single("health check", None)
        return {"status": "healthy", "model": embed_service.model, "cache_stats": embed_service.get_stats()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
