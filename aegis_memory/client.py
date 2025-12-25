"""
Aegis Python SDK v1.1

A production-ready Python client for Aegis Memory API.

Includes ACE (Agentic Context Engineering) features:
- Memory voting (helpful/harmful)
- Incremental delta updates
- Session progress tracking
- Feature status tracking
- Playbook queries

Example Usage:
    from aegis_memory import AegisClient

    client = AegisClient(api_key="your-key", base_url="http://localhost:8000")

    # Add a memory
    result = client.add("User prefers dark mode", agent_id="ui-agent")

    # Vote on memory usefulness
    client.vote(result.id, vote="helpful", voter_agent_id="qa-agent")

    # Query with playbook
    playbook = client.query_playbook("file organization task", agent_id="file-agent")
    for entry in playbook.entries:
        print(f"[{entry.effectiveness_score}] {entry.content}")
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import httpx


@dataclass
class Memory:
    """A memory from Aegis."""
    id: str
    content: str
    user_id: str | None
    agent_id: str | None
    namespace: str
    metadata: dict[str, Any]
    created_at: datetime
    scope: str
    shared_with_agents: list[str]
    derived_from_agents: list[str]
    coordination_metadata: dict[str, Any]
    score: float | None = None
    memory_type: str = "standard"
    bullet_helpful: int = 0
    bullet_harmful: int = 0


@dataclass
class AddResult:
    """Result of adding a memory."""
    id: str
    deduped_from: str | None = None
    inferred_scope: str | None = None


@dataclass
class VoteResult:
    """Result of voting on a memory."""
    memory_id: str
    bullet_helpful: int
    bullet_harmful: int
    effectiveness_score: float


@dataclass
class DeltaResultItem:
    """Result of a single delta operation."""
    operation: str
    success: bool
    memory_id: str | None = None
    error: str | None = None


@dataclass
class DeltaResult:
    """Result of applying delta updates."""
    results: list[DeltaResultItem]
    total_time_ms: float


@dataclass
class PlaybookEntry:
    """An entry from the playbook (strategy or reflection)."""
    id: str
    content: str
    memory_type: str
    effectiveness_score: float
    bullet_helpful: int
    bullet_harmful: int
    error_pattern: str | None
    created_at: datetime


@dataclass
class PlaybookResult:
    """Result of playbook query."""
    entries: list[PlaybookEntry]
    query_time_ms: float


@dataclass
class SessionProgress:
    """Session progress tracking."""
    id: str
    session_id: str
    status: str
    completed_count: int
    total_items: int
    progress_percent: float
    completed_items: list[str]
    in_progress_item: str | None
    next_items: list[str]
    blocked_items: list[dict]
    summary: str | None
    last_action: str | None
    updated_at: datetime


@dataclass
class Feature:
    """Feature tracking."""
    id: str
    feature_id: str
    description: str
    category: str | None
    status: str
    passes: bool
    test_steps: list[str]
    implemented_by: str | None
    verified_by: str | None
    updated_at: datetime


@dataclass
class FeatureList:
    """List of features with summary."""
    features: list[Feature]
    total: int
    passing: int
    failing: int
    in_progress: int


@dataclass
class EvalMetrics:
    """Aggregated evaluation metrics."""
    success_rate: float
    retrieval_precision: float
    pollution_rate: float
    mttr_seconds: float
    total_tasks: int
    passing_tasks: int
    total_memories: int
    helpful_votes: int
    harmful_votes: int
    window: str


@dataclass
class EvalCorrelation:
    """Correlation between votes and task success."""
    correlation_score: float
    prob_pass_given_helpful: float
    prob_pass_given_harmful: float
    sample_size: int
    helpful_count: int
    harmful_count: int


@dataclass
class HandoffBaton:
    """Handoff baton for agent-to-agent state transfer."""
    source_agent_id: str
    target_agent_id: str
    namespace: str
    user_id: str | None
    task_context: str | None
    summary: str | None
    active_tasks: list[str]
    blocked_on: list[str]
    recent_decisions: list[str]
    key_facts: list[str]
    memory_ids: list[str]


class AegisClient:
    """
    Aegis Memory API client with ACE enhancements.

    Args:
        api_key: API key for authentication
        base_url: Base URL of the Aegis API (default: http://localhost:8000)
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def close(self):
        """Close the client."""
        self.client.close()

    # ---------- Core Memory Operations ----------

    def add(
        self,
        content: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
        scope: str | None = None,
        shared_with_agents: list[str] | None = None,
        derived_from_agents: list[str] | None = None,
        coordination_metadata: dict[str, Any] | None = None,
    ) -> AddResult:
        """
        Add a single memory.

        Args:
            content: Memory content
            user_id: Optional user ID
            agent_id: Optional agent ID
            namespace: Namespace (default: "default")
            metadata: Optional metadata dict
            ttl_seconds: Optional TTL in seconds
            scope: Optional scope override (agent-private, agent-shared, global)
            shared_with_agents: Optional list of agent IDs to share with
            derived_from_agents: Optional list of source agent IDs
            coordination_metadata: Optional coordination metadata

        Returns:
            AddResult with memory ID and dedup info
        """
        body = {
            "content": content,
            "user_id": user_id,
            "agent_id": agent_id,
            "namespace": namespace,
            "metadata": metadata,
            "ttl_seconds": ttl_seconds,
            "scope": scope,
            "shared_with_agents": shared_with_agents,
            "derived_from_agents": derived_from_agents,
            "coordination_metadata": coordination_metadata,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.post("/memories/add", json=body)
        resp.raise_for_status()
        data = resp.json()

        return AddResult(
            id=data["id"],
            deduped_from=data.get("deduped_from"),
            inferred_scope=data.get("inferred_scope"),
        )

    def add_batch(
        self,
        items: list[dict[str, Any]],
    ) -> list[AddResult]:
        """
        Add multiple memories efficiently.

        Args:
            items: List of memory dicts with same fields as add()

        Returns:
            List of AddResult for each memory
        """
        resp = self.client.post("/memories/add_batch", json={"items": items})
        resp.raise_for_status()
        data = resp.json()

        return [
            AddResult(
                id=r["id"],
                deduped_from=r.get("deduped_from"),
                inferred_scope=r.get("inferred_scope"),
            )
            for r in data["results"]
        ]

    def query(
        self,
        query: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        namespace: str = "default",
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[Memory]:
        """
        Semantic search over memories.

        Args:
            query: Search query
            user_id: Optional user ID filter
            agent_id: Optional agent ID filter
            namespace: Namespace (default: "default")
            top_k: Maximum results (default: 10)
            min_score: Minimum similarity score (default: 0.0)

        Returns:
            List of matching memories with scores
        """
        body = {
            "query": query,
            "user_id": user_id,
            "agent_id": agent_id,
            "namespace": namespace,
            "top_k": top_k,
            "min_score": min_score,
        }

        resp = self.client.post("/memories/query", json=body)
        resp.raise_for_status()
        data = resp.json()

        return [self._parse_memory(m) for m in data["memories"]]

    def query_cross_agent(
        self,
        query: str,
        requesting_agent_id: str,
        *,
        target_agent_ids: list[str] | None = None,
        user_id: str | None = None,
        namespace: str = "default",
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[Memory]:
        """
        Cross-agent semantic search with scope-aware access control.

        Args:
            query: Search query
            requesting_agent_id: Agent making the request
            target_agent_ids: Optional specific agents to search
            user_id: Optional user ID filter
            namespace: Namespace (default: "default")
            top_k: Maximum results (default: 10)
            min_score: Minimum similarity score (default: 0.0)

        Returns:
            List of accessible memories with scores
        """
        body = {
            "query": query,
            "requesting_agent_id": requesting_agent_id,
            "target_agent_ids": target_agent_ids,
            "user_id": user_id,
            "namespace": namespace,
            "top_k": top_k,
            "min_score": min_score,
        }

        resp = self.client.post("/memories/query_cross_agent", json=body)
        resp.raise_for_status()
        data = resp.json()

        return [self._parse_memory(m) for m in data["memories"]]

    def get(self, memory_id: str) -> Memory:
        """Get a memory by ID."""
        resp = self.client.get(f"/memories/{memory_id}")
        resp.raise_for_status()
        return self._parse_memory(resp.json())

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        resp = self.client.delete(f"/memories/{memory_id}")
        return resp.status_code == 204

    def handoff(
        self,
        source_agent_id: str,
        target_agent_id: str,
        *,
        namespace: str = "default",
        user_id: str | None = None,
        task_context: str | None = None,
        max_memories: int = 20,
    ) -> HandoffBaton:
        """
        Generate handoff baton for agent-to-agent state transfer.

        Args:
            source_agent_id: Agent handing off
            target_agent_id: Agent receiving handoff
            namespace: Namespace (default: "default")
            user_id: Optional user ID
            task_context: Optional task context for relevance ranking
            max_memories: Maximum memories to include (default: 20)

        Returns:
            HandoffBaton with state transfer data
        """
        body = {
            "source_agent_id": source_agent_id,
            "target_agent_id": target_agent_id,
            "namespace": namespace,
            "user_id": user_id,
            "task_context": task_context,
            "max_memories": max_memories,
        }

        resp = self.client.post("/memories/handoff", json=body)
        resp.raise_for_status()
        data = resp.json()

        return HandoffBaton(
            source_agent_id=data["source_agent_id"],
            target_agent_id=data["target_agent_id"],
            namespace=data["namespace"],
            user_id=data.get("user_id"),
            task_context=data.get("task_context"),
            summary=data.get("summary"),
            active_tasks=data.get("active_tasks", []),
            blocked_on=data.get("blocked_on", []),
            recent_decisions=data.get("recent_decisions", []),
            key_facts=data.get("key_facts", []),
            memory_ids=data.get("memory_ids", []),
        )

    # ---------- ACE: Voting ----------

    def vote(
        self,
        memory_id: str,
        vote: Literal["helpful", "harmful"],
        voter_agent_id: str,
        *,
        context: str | None = None,
        task_id: str | None = None,
    ) -> VoteResult:
        """
        Vote on a memory's usefulness.

        ACE Pattern: Agents should vote on memories after using them
        to enable self-improvement through playbook curation.

        Args:
            memory_id: ID of memory to vote on
            vote: "helpful" or "harmful"
            voter_agent_id: Agent casting the vote
            context: Optional context explaining the vote
            task_id: Optional task ID for tracking

        Returns:
            VoteResult with updated counters and effectiveness score
        """
        body = {
            "vote": vote,
            "voter_agent_id": voter_agent_id,
            "context": context,
            "task_id": task_id,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.post(f"/memories/ace/vote/{memory_id}", json=body)
        resp.raise_for_status()
        data = resp.json()

        return VoteResult(
            memory_id=data["memory_id"],
            bullet_helpful=data["bullet_helpful"],
            bullet_harmful=data["bullet_harmful"],
            effectiveness_score=data["effectiveness_score"],
        )

    # ---------- ACE: Delta Updates ----------

    def apply_delta(
        self,
        operations: list[dict[str, Any]],
    ) -> DeltaResult:
        """
        Apply incremental delta updates to memories.

        ACE Pattern: Never rewrite entire context. Instead use
        incremental deltas that add, update, or deprecate memories.

        Args:
            operations: List of delta operations:
                - {"type": "add", "content": "...", ...}
                - {"type": "update", "memory_id": "...", "metadata_patch": {...}}
                - {"type": "deprecate", "memory_id": "...", "superseded_by": "..."}

        Returns:
            DeltaResult with results for each operation
        """
        resp = self.client.post("/memories/ace/delta", json={"operations": operations})
        resp.raise_for_status()
        data = resp.json()

        return DeltaResult(
            results=[
                DeltaResultItem(
                    operation=r["operation"],
                    success=r["success"],
                    memory_id=r.get("memory_id"),
                    error=r.get("error"),
                )
                for r in data["results"]
            ],
            total_time_ms=data["total_time_ms"],
        )

    def add_delta(
        self,
        content: str,
        *,
        memory_type: str = "standard",
        agent_id: str | None = None,
        namespace: str = "default",
        scope: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Convenience method to add a single memory via delta.

        Returns:
            Memory ID of created memory
        """
        result = self.apply_delta([{
            "type": "add",
            "content": content,
            "memory_type": memory_type,
            "agent_id": agent_id,
            "namespace": namespace,
            "scope": scope,
            "metadata": metadata,
        }])

        if result.results[0].success:
            return result.results[0].memory_id
        raise Exception(result.results[0].error)

    def deprecate(
        self,
        memory_id: str,
        *,
        agent_id: str | None = None,
        superseded_by: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        Deprecate a memory (soft delete).

        ACE Pattern: Preserve history by deprecating instead of deleting.
        Deprecated memories are excluded from queries but kept for audit.

        Returns:
            True if successful
        """
        result = self.apply_delta([{
            "type": "deprecate",
            "memory_id": memory_id,
            "agent_id": agent_id,
            "superseded_by": superseded_by,
            "deprecation_reason": reason,
        }])

        return result.results[0].success

    # ---------- ACE: Reflections ----------

    def add_reflection(
        self,
        content: str,
        agent_id: str,
        *,
        user_id: str | None = None,
        namespace: str = "default",
        source_trajectory_id: str | None = None,
        error_pattern: str | None = None,
        correct_approach: str | None = None,
        applicable_contexts: list[str] | None = None,
        scope: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a reflection memory from trajectory analysis.

        ACE Pattern: The Reflector extracts insights from successes
        and failures. These reflections help future tasks.

        Args:
            content: The reflection/insight
            agent_id: Agent that generated the reflection
            user_id: Optional user ID
            namespace: Namespace (default: "default")
            source_trajectory_id: ID of source task/trajectory
            error_pattern: Categorized error type
            correct_approach: What should have been done
            applicable_contexts: When this reflection applies
            scope: Scope override (defaults to global)
            metadata: Additional metadata

        Returns:
            Memory ID of created reflection
        """
        body = {
            "content": content,
            "agent_id": agent_id,
            "user_id": user_id,
            "namespace": namespace,
            "source_trajectory_id": source_trajectory_id,
            "error_pattern": error_pattern,
            "correct_approach": correct_approach,
            "applicable_contexts": applicable_contexts,
            "scope": scope,
            "metadata": metadata,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.post("/memories/ace/reflection", json=body)
        resp.raise_for_status()
        return resp.json()["id"]

    # ---------- ACE: Playbook ----------

    def query_playbook(
        self,
        query: str,
        agent_id: str,
        *,
        namespace: str = "default",
        include_types: list[str] | None = None,
        top_k: int = 20,
        min_effectiveness: float = -1.0,
    ) -> PlaybookResult:
        """
        Query playbook for relevant strategies and reflections.

        ACE Pattern: Before starting a task, consult the playbook
        for strategies, past mistakes to avoid, and proven approaches.

        Args:
            query: Task description or context
            agent_id: Agent making the query
            namespace: Namespace (default: "default")
            include_types: Memory types to include (default: strategy, reflection)
            top_k: Maximum entries (default: 20)
            min_effectiveness: Minimum effectiveness score (default: -1.0)

        Returns:
            PlaybookResult with ranked entries
        """
        body = {
            "query": query,
            "agent_id": agent_id,
            "namespace": namespace,
            "include_types": include_types or ["strategy", "reflection"],
            "top_k": top_k,
            "min_effectiveness": min_effectiveness,
        }

        resp = self.client.post("/memories/ace/playbook", json=body)
        resp.raise_for_status()
        data = resp.json()

        return PlaybookResult(
            entries=[
                PlaybookEntry(
                    id=e["id"],
                    content=e["content"],
                    memory_type=e["memory_type"],
                    effectiveness_score=e["effectiveness_score"],
                    bullet_helpful=e["bullet_helpful"],
                    bullet_harmful=e["bullet_harmful"],
                    error_pattern=e.get("error_pattern"),
                    created_at=datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")),
                )
                for e in data["entries"]
            ],
            query_time_ms=data["query_time_ms"],
        )

    # ---------- ACE: Session Progress ----------

    def create_session(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
        user_id: str | None = None,
        namespace: str = "default",
    ) -> SessionProgress:
        """
        Create a new session for progress tracking.

        Anthropic Pattern: Enables agents to quickly understand
        state when starting with fresh context.

        Args:
            session_id: Unique session identifier
            agent_id: Optional agent ID
            user_id: Optional user ID
            namespace: Namespace (default: "default")

        Returns:
            SessionProgress with initial state
        """
        body = {
            "session_id": session_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "namespace": namespace,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.post("/memories/ace/session", json=body)
        resp.raise_for_status()
        return self._parse_session(resp.json())

    def get_session(self, session_id: str) -> SessionProgress:
        """Get session progress by ID."""
        resp = self.client.get(f"/memories/ace/session/{session_id}")
        resp.raise_for_status()
        return self._parse_session(resp.json())

    def update_session(
        self,
        session_id: str,
        *,
        completed_items: list[str] | None = None,
        in_progress_item: str | None = None,
        next_items: list[str] | None = None,
        blocked_items: list[dict[str, str]] | None = None,
        summary: str | None = None,
        last_action: str | None = None,
        status: str | None = None,
        total_items: int | None = None,
    ) -> SessionProgress:
        """
        Update session progress.

        Args:
            session_id: Session to update
            completed_items: Items to mark complete
            in_progress_item: Current work item
            next_items: Prioritized queue
            blocked_items: Blocked items with reasons
            summary: Human-readable summary
            last_action: Last action taken
            status: Session status (active, paused, completed, failed)
            total_items: Total items in session

        Returns:
            Updated SessionProgress
        """
        body = {
            "completed_items": completed_items,
            "in_progress_item": in_progress_item,
            "next_items": next_items,
            "blocked_items": blocked_items,
            "summary": summary,
            "last_action": last_action,
            "status": status,
            "total_items": total_items,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.patch(f"/memories/ace/session/{session_id}", json=body)
        resp.raise_for_status()
        return self._parse_session(resp.json())

    def mark_complete(self, session_id: str, item: str) -> SessionProgress:
        """Convenience method to mark an item complete."""
        return self.update_session(session_id, completed_items=[item])

    def set_in_progress(self, session_id: str, item: str) -> SessionProgress:
        """Convenience method to set current work item."""
        return self.update_session(session_id, in_progress_item=item)

    # ---------- ACE: Feature Tracking ----------

    def create_feature(
        self,
        feature_id: str,
        description: str,
        *,
        session_id: str | None = None,
        namespace: str = "default",
        category: str | None = None,
        test_steps: list[str] | None = None,
    ) -> Feature:
        """
        Create a feature to track.

        Anthropic Pattern: Feature lists with pass/fail status
        prevent agents from declaring victory prematurely.

        Args:
            feature_id: Unique feature identifier
            description: Feature description
            session_id: Optional session to link
            namespace: Namespace (default: "default")
            category: Feature category
            test_steps: Verification steps

        Returns:
            Created Feature
        """
        body = {
            "feature_id": feature_id,
            "description": description,
            "session_id": session_id,
            "namespace": namespace,
            "category": category,
            "test_steps": test_steps,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.post("/memories/ace/feature", json=body)
        resp.raise_for_status()
        return self._parse_feature(resp.json())

    def get_feature(self, feature_id: str, namespace: str = "default") -> Feature:
        """Get feature by ID."""
        resp = self.client.get(
            f"/memories/ace/feature/{feature_id}",
            params={"namespace": namespace}
        )
        resp.raise_for_status()
        return self._parse_feature(resp.json())

    def update_feature(
        self,
        feature_id: str,
        *,
        namespace: str = "default",
        status: str | None = None,
        passes: bool | None = None,
        implemented_by: str | None = None,
        verified_by: str | None = None,
        implementation_notes: str | None = None,
        failure_reason: str | None = None,
    ) -> Feature:
        """
        Update feature status.

        Only mark passes=True after proper verification!

        Args:
            feature_id: Feature to update
            namespace: Namespace
            status: New status
            passes: Whether feature passes verification
            implemented_by: Agent that implemented
            verified_by: Agent that verified
            implementation_notes: Implementation notes
            failure_reason: Reason for failure

        Returns:
            Updated Feature
        """
        body = {
            "status": status,
            "passes": passes,
            "implemented_by": implemented_by,
            "verified_by": verified_by,
            "implementation_notes": implementation_notes,
            "failure_reason": failure_reason,
        }
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.patch(
            f"/memories/ace/feature/{feature_id}",
            params={"namespace": namespace},
            json=body
        )
        resp.raise_for_status()
        return self._parse_feature(resp.json())

    def mark_feature_complete(
        self,
        feature_id: str,
        verified_by: str,
        *,
        namespace: str = "default",
        notes: str | None = None,
    ) -> Feature:
        """Convenience method to mark feature as passing."""
        return self.update_feature(
            feature_id,
            namespace=namespace,
            status="complete",
            passes=True,
            verified_by=verified_by,
            implementation_notes=notes,
        )

    def mark_feature_failed(
        self,
        feature_id: str,
        reason: str,
        *,
        namespace: str = "default",
    ) -> Feature:
        """Convenience method to mark feature as failed."""
        return self.update_feature(
            feature_id,
            namespace=namespace,
            status="failed",
            passes=False,
            failure_reason=reason,
        )

    def list_features(
        self,
        *,
        namespace: str = "default",
        session_id: str | None = None,
        status: str | None = None,
    ) -> FeatureList:
        """
        List all features with status summary.

        Use at session start to see what's complete and what needs work.

        Args:
            namespace: Namespace
            session_id: Optional session filter
            status: Optional status filter

        Returns:
            FeatureList with features and summary
        """
        params = {"namespace": namespace}
        if session_id:
            params["session_id"] = session_id
        if status:
            params["status"] = status

        resp = self.client.get("/memories/ace/features", params=params)
        resp.raise_for_status()
        data = resp.json()

        return FeatureList(
            features=[self._parse_feature(f) for f in data["features"]],
            total=data["total"],
            passing=data["passing"],
            failing=data["failing"],
            in_progress=data["in_progress"],
        )

    # ---------- ACE: Evaluation Harness ----------

    def get_evaluation_report(
        self,
        *,
        namespace: str | None = None,
        agent_id: str | None = None,
        window: str = "global",
    ) -> EvalMetrics:
        """
        Get aggregated evaluation metrics for the confidence harness.

        Supported windows: 24h, 7d, 30d, global

        Args:
            namespace: Optional namespace filter
            agent_id: Optional agent filter
            window: Time window (default: "global")

        Returns:
            EvalMetrics with KPIs (Success Rate, Precision, MTTR, etc.)
        """
        params = {"window": window}
        if namespace:
            params["namespace"] = namespace
        if agent_id:
            params["agent_id"] = agent_id

        resp = self.client.get("/memories/ace/eval/metrics", params=params)
        resp.raise_for_status()
        data = resp.json()

        return EvalMetrics(**data)

    def get_evaluation_correlation(
        self,
        *,
        namespace: str | None = None,
        agent_id: str | None = None,
        window: str = "global",
    ) -> EvalCorrelation:
        """
        Calculate correlation between memory votes and actual task success.

        Answers: 'Do votes predict actual usefulness?'

        Args:
            namespace: Optional namespace filter
            agent_id: Optional agent filter
            window: Time window (default: "global")

        Returns:
            EvalCorrelation with scores and sample size
        """
        params = {"window": window}
        if namespace:
            params["namespace"] = namespace
        if agent_id:
            params["agent_id"] = agent_id

        resp = self.client.get("/memories/ace/eval/correlation", params=params)
        resp.raise_for_status()
        data = resp.json()

        return EvalCorrelation(**data)

    # ---------- Helpers ----------

    def _parse_memory(self, data: dict) -> Memory:
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
        )

    def _parse_session(self, data: dict) -> SessionProgress:
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

    def _parse_feature(self, data: dict) -> Feature:
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


# Async client for async applications
class AsyncAegisClient:
    """Async version of AegisClient using httpx.AsyncClient.

    Note: Async implementation is planned for a future release.
    For now, use the sync AegisClient which works in most scenarios.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        raise NotImplementedError(
            "AsyncAegisClient is not yet implemented. "
            "Please use the sync AegisClient for now. "
            "Async support is planned for v1.2. "
            "Track progress: https://github.com/quantifylabs/aegis-memory/issues"
        )
