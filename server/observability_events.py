from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, Field

from config import Settings, get_settings

logger = logging.getLogger("aegis.observability.events")


class RetryMetadata(BaseModel):
    attempt: int = 0
    max_attempts: int = 3
    next_retry_at: datetime | None = None
    reason: str | None = None


class EventEnvelope(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str | None = None

    project_id: str
    agent_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None

    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    payload: dict[str, Any] = Field(default_factory=dict)
    derived_metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)

    retry: RetryMetadata = Field(default_factory=RetryMetadata)


class Exporter(Protocol):
    async def export_batch(self, events: Sequence[EventEnvelope]) -> None: ...


@dataclass(slots=True)
class ExportStats:
    exported: int = 0
    failed: int = 0
    dropped: int = 0


class ObservabilityEventPipeline:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=settings.obs_queue_max_size)
        self._worker_task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._exporters = self._build_exporters(settings)
        self._stats = ExportStats()

    def _build_exporters(self, settings: Settings) -> list[Exporter]:
        exporters: list[Exporter] = []

        if settings.obs_langfuse_enabled:
            from integrations.langfuse_exporter import LangfuseExporter

            exporters.append(LangfuseExporter(settings))

        if settings.obs_langsmith_enabled:
            from integrations.langsmith_exporter import LangSmithExporter

            exporters.append(LangSmithExporter(settings))

        return exporters

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._stopping.clear()
        self._worker_task = asyncio.create_task(self._worker(), name="observability-event-worker")
        logger.info("Observability event worker started", extra={"exporter_count": len(self._exporters)})

    async def stop(self) -> None:
        if self._worker_task is None:
            return

        self._stopping.set()
        await self._worker_task
        self._worker_task = None
        logger.info(
            "Observability event worker stopped",
            extra={
                "exported": self._stats.exported,
                "failed": self._stats.failed,
                "dropped": self._stats.dropped,
            },
        )

    def enqueue(self, envelope: EventEnvelope) -> bool:
        try:
            self._queue.put_nowait(envelope)
            return True
        except asyncio.QueueFull:
            self._stats.dropped += 1
            self._log_enqueue_failure(envelope, reason="queue_full")
            return False

    def _log_enqueue_failure(self, envelope: EventEnvelope, *, reason: str) -> None:
        base_delay = max(self._settings.obs_retry_base_delay_seconds, 1)
        retry_meta = {
            "attempt": envelope.retry.attempt,
            "max_attempts": self._settings.obs_retry_max_attempts,
            "next_retry_at": (datetime.now(UTC) + timedelta(seconds=base_delay)).isoformat(),
            "reason": reason,
            "durable": True,
        }
        logger.warning(
            "failed_to_enqueue_observability_event",
            extra={
                "event_type": envelope.event_type,
                "trace_id": envelope.trace_id,
                "request_id": envelope.request_id,
                "project_id": envelope.project_id,
                "retry": retry_meta,
                "payload": envelope.payload,
            },
        )

    async def _worker(self) -> None:
        while not self._stopping.is_set() or not self._queue.empty():
            batch = await self._drain_batch()
            if not batch:
                continue
            await self._export_with_retry(batch)

    async def _drain_batch(self) -> list[EventEnvelope]:
        batch_size = self._settings.obs_batch_size
        flush_interval = self._settings.obs_batch_flush_interval_ms / 1000

        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=flush_interval)
        except TimeoutError:
            return []

        batch = [first]
        started = time.monotonic()
        while len(batch) < batch_size:
            if time.monotonic() - started >= flush_interval:
                break
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                await asyncio.sleep(0)
                break
        return batch

    async def _export_with_retry(self, batch: Sequence[EventEnvelope]) -> None:
        if not self._exporters:
            return

        max_attempts = self._settings.obs_retry_max_attempts
        base_delay = max(self._settings.obs_retry_base_delay_seconds, 1)

        for attempt in range(max_attempts):
            try:
                await asyncio.gather(*(exp.export_batch(batch) for exp in self._exporters))
                self._stats.exported += len(batch)
                return
            except Exception as exc:
                self._stats.failed += len(batch)
                if attempt == max_attempts - 1:
                    now = datetime.now(UTC)
                    for event in batch:
                        event.retry = RetryMetadata(
                            attempt=attempt + 1,
                            max_attempts=max_attempts,
                            next_retry_at=now + timedelta(seconds=base_delay * (2**attempt)),
                            reason=str(exc),
                        )
                        self._log_enqueue_failure(event, reason="export_failed")
                    return
                await asyncio.sleep(base_delay * (2**attempt))


_pipeline: ObservabilityEventPipeline | None = None


def get_event_pipeline() -> ObservabilityEventPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ObservabilityEventPipeline(get_settings())
    return _pipeline


def enqueue_event(envelope: EventEnvelope) -> bool:
    return get_event_pipeline().enqueue(envelope)
