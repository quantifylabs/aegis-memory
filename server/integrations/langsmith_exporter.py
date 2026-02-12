from __future__ import annotations

from collections.abc import Sequence

import httpx

from config import Settings
from observability_events import EventEnvelope


class LangSmithExporter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._endpoint = settings.obs_langsmith_host.rstrip("/") + "/runs/batch"

    async def export_batch(self, events: Sequence[EventEnvelope]) -> None:
        if not events:
            return

        payload = [
            {
                "id": event.trace_id,
                "name": event.event_type,
                "start_time": event.timestamp.isoformat(),
                "inputs": event.payload,
                "extra": {
                    "request_id": event.request_id,
                    "project_id": event.project_id,
                    "agent_id": event.agent_id,
                    "session_id": event.session_id,
                    "task_id": event.task_id,
                    "derived_metrics": event.derived_metrics,
                    "retry": event.retry.model_dump(mode="json"),
                },
            }
            for event in events
        ]

        async with httpx.AsyncClient(timeout=self._settings.obs_export_timeout_seconds) as client:
            response = await client.post(
                self._endpoint,
                headers={
                    "x-api-key": self._settings.obs_langsmith_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
