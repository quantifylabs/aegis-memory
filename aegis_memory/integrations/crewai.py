"""
Aegis Memory CrewAI Integration

Provides CrewAI-compatible memory that uses Aegis Memory as the backend
for persistent, multi-agent memory with support for crew coordination.

Usage:
    from aegis_memory.integrations.crewai import AegisCrewMemory
    from crewai import Crew, Agent, Task

    memory = AegisCrewMemory(
        api_key="your-aegis-key",
        base_url="http://localhost:8000",
        namespace="research-crew"
    )

    researcher = Agent(
        role="Researcher",
        goal="Find information",
        backstory="Expert researcher",
        memory=True,
    )

    crew = Crew(
        agents=[researcher],
        tasks=[...],
        memory=memory,  # Aegis Memory for long-term storage
    )
"""

from typing import Any

from aegis_memory.client import AegisClient


class AegisCrewMemory:
    """
    CrewAI-compatible memory backed by Aegis Memory.

    This provides long-term memory for CrewAI crews, enabling:
    - Persistent memory across crew runs
    - Agent-specific memory with scope control
    - Cross-agent memory sharing
    - ACE patterns for self-improvement

    Args:
        api_key: Aegis Memory API key
        base_url: Aegis Memory server URL
        namespace: Memory namespace for this crew
        default_scope: Default scope for memories ("global" recommended for crews)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        namespace: str = "crewai",
        default_scope: str = "global",
    ):
        self.client = AegisClient(api_key=api_key, base_url=base_url)
        self.namespace = namespace
        self.default_scope = default_scope

    def save(
        self,
        value: str,
        agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Save a memory from an agent's work.

        Args:
            value: The content to remember
            agent: Agent role/name that created this memory
            metadata: Additional metadata

        Returns:
            Memory ID
        """
        result = self.client.add(
            content=value,
            agent_id=agent,
            namespace=self.namespace,
            scope=self.default_scope,
            metadata={
                "source": "crewai",
                "agent_role": agent,
                **(metadata or {}),
            },
        )
        return result["id"]

    def search(
        self,
        query: str,
        agent: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search memories relevant to a query.

        Args:
            query: Search query
            agent: Optional agent to search as (for cross-agent access control)
            limit: Maximum results

        Returns:
            List of memory dicts with 'content' and 'metadata'
        """
        if agent:
            memories = self.client.query_cross_agent(
                query=query,
                requesting_agent_id=agent,
                namespace=self.namespace,
                top_k=limit,
            )
        else:
            memories = self.client.query(
                query=query,
                namespace=self.namespace,
                top_k=limit,
            )

        return [
            {
                "content": mem.content,
                "metadata": mem.metadata,
                "score": mem.score,
                "agent_id": mem.agent_id,
            }
            for mem in memories
        ]

    def reset(self) -> None:
        """
        Reset memory.

        Note: This is a no-op for Aegis Memory. Use TTL or
        explicit deletion through the client if needed.
        """
        pass


class AegisAgentMemory:
    """
    Per-agent memory wrapper for use with CrewAI agents.

    Provides agent-scoped memory within a crew context.

    Usage:
        memory = AegisCrewMemory(api_key="...", namespace="my-crew")

        agent_memory = AegisAgentMemory(
            crew_memory=memory,
            agent_id="researcher"
        )
    """

    def __init__(
        self,
        crew_memory: AegisCrewMemory,
        agent_id: str,
        scope: str = "agent-shared",
    ):
        self.crew_memory = crew_memory
        self.agent_id = agent_id
        self.scope = scope
        self.client = crew_memory.client
        self.namespace = crew_memory.namespace

    def save(
        self,
        value: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save memory for this agent."""
        result = self.client.add(
            content=value,
            agent_id=self.agent_id,
            namespace=self.namespace,
            scope=self.scope,
            metadata={
                "source": "crewai",
                "agent_role": self.agent_id,
                **(metadata or {}),
            },
        )
        return result["id"]

    def search(
        self,
        query: str,
        limit: int = 10,
        include_other_agents: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search memories.

        Args:
            query: Search query
            limit: Maximum results
            include_other_agents: If True, search across all accessible memories.
                                  If False, only search this agent's memories.
        """
        if include_other_agents:
            memories = self.client.query_cross_agent(
                query=query,
                requesting_agent_id=self.agent_id,
                namespace=self.namespace,
                top_k=limit,
            )
        else:
            memories = self.client.query(
                query=query,
                agent_id=self.agent_id,
                namespace=self.namespace,
                top_k=limit,
            )

        return [
            {
                "content": mem.content,
                "metadata": mem.metadata,
                "score": mem.score,
            }
            for mem in memories
        ]

    def handoff_to(
        self,
        target_agent_id: str,
        task_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a handoff baton for another agent.

        This is the ACE pattern for structured agent-to-agent
        state transfer.

        Args:
            target_agent_id: Agent receiving the handoff
            task_context: Optional context about the current task

        Returns:
            Handoff baton dict
        """
        return self.client.handoff(
            source_agent_id=self.agent_id,
            target_agent_id=target_agent_id,
            namespace=self.namespace,
            task_context=task_context,
        )

    def add_reflection(
        self,
        content: str,
        error_pattern: str | None = None,
        correct_approach: str | None = None,
    ) -> str:
        """
        Add a reflection memory (ACE pattern).

        Use this to record insights from task successes or failures.

        Args:
            content: The insight/reflection
            error_pattern: Category of error (if from failure)
            correct_approach: What should be done instead

        Returns:
            Memory ID
        """
        result = self.client.reflection(
            content=content,
            agent_id=self.agent_id,
            namespace=self.namespace,
            error_pattern=error_pattern,
            correct_approach=correct_approach,
        )
        return result["id"]

    def get_playbook(
        self,
        query: str,
        top_k: int = 10,
        min_effectiveness: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Get relevant strategies and reflections (ACE pattern).

        Query the playbook for proven approaches before starting a task.

        Args:
            query: Task description to find relevant strategies
            top_k: Maximum entries to return
            min_effectiveness: Minimum effectiveness score

        Returns:
            List of playbook entries
        """
        entries = self.client.playbook(
            query=query,
            agent_id=self.agent_id,
            namespace=self.namespace,
            top_k=top_k,
            min_effectiveness=min_effectiveness,
        )

        return [
            {
                "content": e.content,
                "effectiveness_score": e.effectiveness_score,
                "error_pattern": e.error_pattern,
                "memory_type": e.memory_type,
            }
            for e in entries
        ]
