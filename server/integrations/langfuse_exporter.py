from __future__ import annotations

from collections.abc import Sequence

import httpx

from config import Settings
from observability_events import EventEnvelope


class LangfuseExporter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._endpoint = settings.obs_langfuse_host.rstrip("/") + "/api/public/ingestion"

    async def export_batch(self, events: Sequence[EventEnvelope]) -> None:
        if not events:
            return

        payload = {
            "batch": [
                {
                    "id": event.trace_id,
                    "timestamp": event.timestamp.isoformat(),
                    "type": event.event_type,
                    "metadata": {
                        "request_id": event.request_id,
                        "project_id": event.project_id,
                        "agent_id": event.agent_id,
                        "session_id": event.session_id,
                        "task_id": event.task_id,
                        "derived_metrics": event.derived_metrics,
                        "retry": event.retry.model_dump(mode="json"),
                    },
                    "body": event.payload,
                }
                for event in events
            ]
        }

        async with httpx.AsyncClient(timeout=self._settings.obs_export_timeout_seconds) as client:
            response = await client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._settings.obs_langfuse_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
