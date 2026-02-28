"""Aegis SDK response parsing helpers."""

from datetime import datetime
from typing import Any, Dict, Optional

from ._models import (
    ConsolidationCandidate,
    CurationEntry,
    CurationResult,
    Feature,
    InteractionEvent,
    Memory,
    RunResult,
    SessionProgress,
)


def _parse_memory_data(data: Dict[str, Any]) -> Memory:
    return Memory(
        id=data["id"],
        content=data["content"],
        user_id=data.get("user_id"),
        agent_id=data.get("agent_id"),
        namespace=data["namespace"],
        metadata=data.get("metadata", {}),
        created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        scope=data["scope"],
        shared_with_agents=data.get("shared_with_agents", []),
        derived_from_agents=data.get("derived_from_agents", []),
        coordination_metadata=data.get("coordination_metadata", {}),
        score=data.get("score"),
        memory_type=data.get("memory_type", "standard"),
        bullet_helpful=data.get("bullet_helpful", 0),
        bullet_harmful=data.get("bullet_harmful", 0),
        content_flags=data.get("content_flags", []),
        trust_level=data.get("trust_level", "internal"),
    )


def _parse_session_data(data: Dict[str, Any]) -> SessionProgress:
    return SessionProgress(
        id=data["id"],
        session_id=data["session_id"],
        status=data["status"],
        completed_count=data["completed_count"],
        total_items=data["total_items"],
        progress_percent=data["progress_percent"],
        completed_items=data["completed_items"],
        in_progress_item=data.get("in_progress_item"),
        next_items=data["next_items"],
        blocked_items=data["blocked_items"],
        summary=data.get("summary"),
        last_action=data.get("last_action"),
        updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
    )


def _parse_feature_data(data: Dict[str, Any]) -> Feature:
    return Feature(
        id=data["id"],
        feature_id=data["feature_id"],
        description=data["description"],
        category=data.get("category"),
        status=data["status"],
        passes=data["passes"],
        test_steps=data.get("test_steps", []),
        implemented_by=data.get("implemented_by"),
        verified_by=data.get("verified_by"),
        updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
    )


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


def _parse_run_data(data: Dict[str, Any]) -> RunResult:
    return RunResult(
        run_id=data["run_id"],
        status=data["status"],
        success=data.get("success"),
        agent_id=data.get("agent_id"),
        task_type=data.get("task_type"),
        namespace=data.get("namespace", "default"),
        evaluation=data.get("evaluation", {}),
        logs=data.get("logs", {}),
        memory_ids_used=data.get("memory_ids_used", []),
        reflection_ids=data.get("reflection_ids", []),
        started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")),
        completed_at=_parse_dt(data.get("completed_at")),
        created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
    )


def _parse_curation_data(data: Dict[str, Any]) -> CurationResult:
    return CurationResult(
        promoted=[
            CurationEntry(
                id=e["id"], content=e["content"], memory_type=e["memory_type"],
                effectiveness_score=e["effectiveness_score"],
                bullet_helpful=e["bullet_helpful"], bullet_harmful=e["bullet_harmful"],
                total_votes=e["total_votes"],
            )
            for e in data.get("promoted", [])
        ],
        flagged=[
            CurationEntry(
                id=e["id"], content=e["content"], memory_type=e["memory_type"],
                effectiveness_score=e["effectiveness_score"],
                bullet_helpful=e["bullet_helpful"], bullet_harmful=e["bullet_harmful"],
                total_votes=e["total_votes"],
            )
            for e in data.get("flagged", [])
        ],
        consolidation_candidates=[
            ConsolidationCandidate(
                memory_id_a=c["memory_id_a"], memory_id_b=c["memory_id_b"],
                content_a=c["content_a"], content_b=c["content_b"],
                reason=c["reason"],
            )
            for c in data.get("consolidation_candidates", [])
        ],
    )


def _parse_interaction_event(data: Dict[str, Any]) -> InteractionEvent:
    return InteractionEvent(
        event_id=data["event_id"],
        project_id=data["project_id"],
        session_id=data["session_id"],
        agent_id=data.get("agent_id"),
        content=data.get("content"),
        timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
        tool_calls=data.get("tool_calls", []),
        parent_event_id=data.get("parent_event_id"),
        namespace=data.get("namespace", "default"),
        extra_metadata=data.get("extra_metadata"),
        has_embedding=data.get("has_embedding", False),
    )
