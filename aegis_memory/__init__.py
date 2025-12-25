"""
Aegis Memory - Agent-native memory fabric for AI agents.

Aegis Memory is an open-source, self-hostable memory engine for LLM agents with:
- Agent-native semantics (namespace, scope, multi-agent ACLs)
- First-class multi-agent support (cross-agent queries, structured handoffs)
- Context-engineering patterns (ACE-style voting, deltas, reflections, playbooks)
- Production-oriented design (FastAPI + Postgres + pgvector)

Quick Start:
    from aegis_memory import AegisClient

    client = AegisClient(api_key="your-key", base_url="http://localhost:8000")

    # Add a memory
    result = client.add("User prefers dark mode", agent_id="ui-agent")

    # Query memories
    memories = client.query("user preferences", agent_id="ui-agent")

    # Cross-agent query with access control
    memories = client.query_cross_agent(
        "user settings",
        requesting_agent_id="settings-agent"
    )

For more examples, see: https://github.com/quantifylabs/aegis-memory/tree/main/examples
"""

__version__ = "1.2.0"

from aegis_memory.client import (
    AegisClient,
    Feature,
    Memory,
    PlaybookEntry,
    SessionProgress,
)

__all__ = [
    "AegisClient",
    "Memory",
    "PlaybookEntry",
    "SessionProgress",
    "Feature",
    "__version__",
]
