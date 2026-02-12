from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import ValidationError

from aegis_memory.client import AddResult, Feature, FeatureList, Memory, SessionProgress, VoteResult
from aegis_memory.mcp_server import (
    AddMemoryInput,
    FeatureStatusInput,
    QueryMemoryInput,
    RecentMemoriesInput,
    SessionUpdateInput,
    VoteInput,
    _handle_http_error,
    run_add_memory,
    run_feature_status_resource,
    run_query_memory,
    run_recent_memories_resource,
    run_update_session,
    run_vote_memory,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestMCPSchemas:
    def test_add_memory_requires_content(self):
        with pytest.raises(ValidationError):
            AddMemoryInput(content="")

    def test_query_memory_top_k_bounds(self):
        with pytest.raises(ValidationError):
            QueryMemoryInput(query="hello", top_k=101)

    def test_vote_literal_restricted(self):
        with pytest.raises(ValidationError):
            VoteInput(memory_id="m1", vote="bad", voter_agent_id="agent")


class TestMCPToolMappings:
    def test_run_add_memory_maps_to_client_add(self):
        client = MagicMock()
        client.add.return_value = AddResult(id="mem-1", deduped_from=None, inferred_scope="global")

        output = run_add_memory(client, AddMemoryInput(content="hello", namespace="prod"))

        assert output["id"] == "mem-1"
        client.add.assert_called_once_with(content="hello", namespace="prod")

    def test_run_query_memory_returns_memory_list(self):
        client = MagicMock()
        client.query.return_value = [
            Memory(
                id="m1",
                content="stored",
                user_id=None,
                agent_id="agent-1",
                namespace="default",
                metadata={},
                created_at=_now(),
                scope="global",
                shared_with_agents=[],
                derived_from_agents=[],
                coordination_metadata={},
                score=0.9,
            )
        ]

        output = run_query_memory(client, QueryMemoryInput(query="stored"))

        assert output["memories"][0]["id"] == "m1"
        client.query.assert_called_once()

    def test_run_vote_memory_maps_memory_id_and_vote_payload(self):
        client = MagicMock()
        client.vote.return_value = VoteResult(
            memory_id="m1", bullet_helpful=2, bullet_harmful=0, effectiveness_score=0.66
        )

        output = run_vote_memory(
            client,
            VoteInput(memory_id="m1", vote="helpful", voter_agent_id="critic", context="worked"),
        )

        assert output["memory_id"] == "m1"
        client.vote.assert_called_once_with(
            memory_id="m1", vote="helpful", voter_agent_id="critic", context="worked"
        )

    def test_run_update_session_maps_patch_fields(self):
        client = MagicMock()
        client.update_session.return_value = SessionProgress(
            id="s-1",
            session_id="sess-1",
            status="active",
            completed_count=1,
            total_items=5,
            progress_percent=20.0,
            completed_items=["setup"],
            in_progress_item="tests",
            next_items=["docs"],
            blocked_items=[],
            summary="moving",
            last_action="write tests",
            updated_at=_now(),
        )

        output = run_update_session(
            client,
            SessionUpdateInput(session_id="sess-1", completed_items=["setup"], in_progress_item="tests"),
        )

        assert output["session_id"] == "sess-1"
        client.update_session.assert_called_once_with(
            session_id="sess-1", completed_items=["setup"], in_progress_item="tests"
        )


class TestMCPResourcesAndErrors:
    def test_run_recent_memories_resource_orders_desc(self):
        response = MagicMock()
        response.json.return_value = {
            "memories": [{"id": "old"}, {"id": "new"}],
            "stats": {"total_exported": 2},
        }
        response.raise_for_status.return_value = None

        inner = MagicMock()
        inner.post.return_value = response

        client = MagicMock()
        client.client = inner

        output = run_recent_memories_resource(client, RecentMemoriesInput(limit=2))

        assert [m["id"] for m in output["memories"]] == ["new", "old"]

    def test_run_feature_status_resource_returns_summary(self):
        client = MagicMock()
        client.list_features.return_value = FeatureList(
            features=[
                Feature(
                    id="f1",
                    feature_id="feature-1",
                    description="A feature",
                    category="core",
                    status="complete",
                    passes=True,
                    test_steps=["run test"],
                    implemented_by="agent-a",
                    verified_by="agent-b",
                    updated_at=_now(),
                )
            ],
            total=1,
            passing=1,
            failing=0,
            in_progress=0,
        )

        output = run_feature_status_resource(client, FeatureStatusInput(namespace="default"))

        assert output["summary"]["passing"] == 1
        assert output["features"][0]["feature_id"] == "feature-1"

    def test_http_error_is_wrapped_with_endpoint_context(self):
        request = httpx.Request("POST", "http://localhost:8000/memories/query")
        response = httpx.Response(status_code=422, request=request, text="invalid payload")
        error = httpx.HTTPStatusError("boom", request=request, response=response)

        wrapped = _handle_http_error(error)

        assert "422" in str(wrapped)
        assert "/memories/query" in str(wrapped)
