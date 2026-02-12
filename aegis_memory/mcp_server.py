"""MCP server exposing Aegis Memory operations as tools and resources."""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from aegis_memory.client import AegisClient


class MCPError(RuntimeError):
    """Domain-specific MCP tool error with readable message."""


class AddMemoryInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    user_id: str | None = Field(default=None, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    namespace: str = Field(default="default", max_length=64)
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1, le=31_536_000)
    scope: Literal["agent-private", "agent-shared", "global"] | None = None
    shared_with_agents: list[str] | None = None
    derived_from_agents: list[str] | None = None
    coordination_metadata: dict[str, Any] | None = None


class QueryMemoryInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    user_id: str | None = None
    agent_id: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class CrossAgentQueryInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    requesting_agent_id: str = Field(..., min_length=1, max_length=64)
    target_agent_ids: list[str] | None = None
    user_id: str | None = None
    namespace: str = "default"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class VoteInput(BaseModel):
    memory_id: str = Field(..., min_length=1)
    vote: Literal["helpful", "harmful"]
    voter_agent_id: str = Field(..., min_length=1, max_length=64)
    context: str | None = Field(default=None, max_length=1000)
    task_id: str | None = Field(default=None, max_length=64)


class ReflectionInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    agent_id: str = Field(..., min_length=1, max_length=64)
    user_id: str | None = None
    namespace: str = "default"
    source_trajectory_id: str | None = Field(default=None, max_length=64)
    error_pattern: str | None = Field(default=None, max_length=128)
    correct_approach: str | None = Field(default=None, max_length=10_000)
    applicable_contexts: list[str] | None = None
    scope: Literal["agent-private", "agent-shared", "global"] | None = None
    metadata: dict[str, Any] | None = None


class SessionUpdateInput(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    completed_items: list[str] | None = None
    in_progress_item: str | None = None
    next_items: list[str] | None = None
    blocked_items: list[dict[str, str]] | None = None
    summary: str | None = None
    last_action: str | None = None
    status: str | None = None
    total_items: int | None = None


class FeatureListInput(BaseModel):
    namespace: str = "default"
    session_id: str | None = None
    status: str | None = None


class RecentMemoriesInput(BaseModel):
    namespace: str | None = None
    agent_id: str | None = None
    limit: int = Field(default=20, ge=1, le=500)


class SessionStateInput(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)


class FeatureStatusInput(BaseModel):
    namespace: str = "default"
    session_id: str | None = None
    status: str | None = None


def _client() -> AegisClient:
    api_key = os.getenv("AEGIS_API_KEY")
    if not api_key:
        raise MCPError("Missing AEGIS_API_KEY environment variable.")

    base_url = os.getenv("AEGIS_BASE_URL", "http://localhost:8000")
    timeout = float(os.getenv("AEGIS_TIMEOUT_SECONDS", "30"))
    return AegisClient(api_key=api_key, base_url=base_url, timeout=timeout)


def _handle_http_error(exc: httpx.HTTPStatusError) -> MCPError:
    detail = exc.response.text.strip() or exc.response.reason_phrase
    return MCPError(
        f"Aegis request failed ({exc.response.status_code} {exc.request.method} "
        f"{exc.request.url.path}): {detail}"
    )


def run_add_memory(client: AegisClient, input_data: AddMemoryInput) -> dict[str, Any]:
    result = client.add(**input_data.model_dump(exclude_none=True))
    return result.__dict__


def run_query_memory(client: AegisClient, input_data: QueryMemoryInput) -> dict[str, Any]:
    memories = client.query(**input_data.model_dump())
    return {"memories": [memory.__dict__ for memory in memories]}


def run_cross_agent_query(client: AegisClient, input_data: CrossAgentQueryInput) -> dict[str, Any]:
    memories = client.query_cross_agent(**input_data.model_dump())
    return {"memories": [memory.__dict__ for memory in memories]}


def run_vote_memory(client: AegisClient, input_data: VoteInput) -> dict[str, Any]:
    payload = input_data.model_dump(exclude={"memory_id"}, exclude_none=True)
    result = client.vote(memory_id=input_data.memory_id, **payload)
    return result.__dict__


def run_add_reflection(client: AegisClient, input_data: ReflectionInput) -> dict[str, Any]:
    memory_id = client.add_reflection(**input_data.model_dump(exclude_none=True))
    return {"id": memory_id}


def run_update_session(client: AegisClient, input_data: SessionUpdateInput) -> dict[str, Any]:
    payload = input_data.model_dump(exclude={"session_id"}, exclude_none=True)
    result = client.update_session(session_id=input_data.session_id, **payload)
    return result.__dict__


def run_list_features(client: AegisClient, input_data: FeatureListInput) -> dict[str, Any]:
    result = client.list_features(**input_data.model_dump(exclude_none=True))
    return {
        "features": [feature.__dict__ for feature in result.features],
        "total": result.total,
        "passing": result.passing,
        "failing": result.failing,
        "in_progress": result.in_progress,
    }


def run_recent_memories_resource(client: AegisClient, query: RecentMemoriesInput) -> dict[str, Any]:
    response = client.client.post(
        "/memories/export",
        json={
            "format": "json",
            "namespace": query.namespace,
            "agent_id": query.agent_id,
            "limit": query.limit,
        },
    )
    response.raise_for_status()
    payload = response.json()
    memories = payload.get("memories", [])
    return {"memories": list(reversed(memories))[: query.limit], "stats": payload.get("stats", {})}


def run_session_state_resource(client: AegisClient, query: SessionStateInput) -> dict[str, Any]:
    result = client.get_session(query.session_id)
    return result.__dict__


def run_feature_status_resource(client: AegisClient, query: FeatureStatusInput) -> dict[str, Any]:
    result = client.list_features(**query.model_dump(exclude_none=True))
    return {
        "summary": {
            "total": result.total,
            "passing": result.passing,
            "failing": result.failing,
            "in_progress": result.in_progress,
        },
        "features": [feature.__dict__ for feature in result.features],
    }


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("aegis-memory")

    @mcp.tool()
    def add_memory(input_data: AddMemoryInput) -> dict[str, Any]:
        """Add a memory with scope-aware metadata."""
        with _client() as client:
            try:
                return run_add_memory(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.tool()
    def query_memory(input_data: QueryMemoryInput) -> dict[str, Any]:
        """Semantic query over memories."""
        with _client() as client:
            try:
                return run_query_memory(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.tool()
    def cross_agent_query(input_data: CrossAgentQueryInput) -> dict[str, Any]:
        """Cross-agent query with ACL-aware retrieval."""
        with _client() as client:
            try:
                return run_cross_agent_query(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.tool()
    def vote_memory(input_data: VoteInput) -> dict[str, Any]:
        """Vote a memory as helpful or harmful."""
        with _client() as client:
            try:
                return run_vote_memory(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.tool()
    def add_reflection(input_data: ReflectionInput) -> dict[str, Any]:
        """Add an ACE reflection memory."""
        with _client() as client:
            try:
                return run_add_reflection(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.tool()
    def update_session(input_data: SessionUpdateInput) -> dict[str, Any]:
        """Patch session progress state for long-running tasks."""
        with _client() as client:
            try:
                return run_update_session(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.tool()
    def list_features(input_data: FeatureListInput) -> dict[str, Any]:
        """List features and current status summary."""
        with _client() as client:
            try:
                return run_list_features(client, input_data)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.resource("aegis://memories/recent")
    def recent_memories(query: RecentMemoriesInput) -> dict[str, Any]:
        """Read-only resource: recent memories from export snapshot."""
        with _client() as client:
            try:
                return run_recent_memories_resource(client, query)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.resource("aegis://session/state")
    def session_state(query: SessionStateInput) -> dict[str, Any]:
        """Read-only resource: active session progress view."""
        with _client() as client:
            try:
                return run_session_state_resource(client, query)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    @mcp.resource("aegis://features/status")
    def feature_status(query: FeatureStatusInput) -> dict[str, Any]:
        """Read-only resource: feature status snapshot."""
        with _client() as client:
            try:
                return run_feature_status_resource(client, query)
            except httpx.HTTPStatusError as exc:
                raise _handle_http_error(exc) from exc

    return mcp


def main() -> None:
    """Run Aegis MCP server over stdio."""
    server = create_mcp_server()
    server.run()


if __name__ == "__main__":
    main()
