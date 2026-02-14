"""Event pipeline re-export for the new package structure."""
from observability_events import get_event_pipeline, EventEnvelope, enqueue_event

__all__ = ["get_event_pipeline", "EventEnvelope", "enqueue_event"]
