"""
Aegis Memory — Secure Context Engineering for AI Agents.

Aegis Memory is an open-source, self-hostable context engineering layer for LLM agents with:
- Content security pipeline (input validation, PII scanning, injection detection, LLM classification)
- HMAC-SHA256 integrity verification (tamper detection on every memory write)
- OWASP 4-tier trust hierarchy (untrusted, internal, privileged, system)
- Context-engineering patterns (ACE-style voting, deltas, reflections, playbooks)
- First-class multi-agent support (cross-agent queries, structured handoffs, scoped ACLs)
- Production-oriented design (FastAPI + Postgres + pgvector)

Quick Start (Local Mode - Zero Config):
    from aegis_memory import local_client

    client = local_client()
    client.add("User prefers dark mode", agent_id="ui-agent")
    memories = client.query("user preferences", agent_id="ui-agent")

Quick Start (Remote Server):
    from aegis_memory import AegisClient

    client = AegisClient(api_key="your-key", base_url="http://localhost:8000")

    # Add a memory
    result = client.add("User prefers dark mode", agent_id="ui-agent")

    # Query memories
    memories = client.query("user preferences", agent_id="ui-agent")

Quick Start (Smart Memory - Zero Config):
    from aegis_memory import SmartMemory
    
    memory = SmartMemory(
        aegis_api_key="your-aegis-key",
        llm_api_key="your-openai-key"
    )
    
    # Automatically extracts and stores valuable information
    memory.process_turn(
        user_input="I'm John, a developer from Chennai. I prefer dark mode.",
        ai_response="Nice to meet you, John!",
        user_id="user_123"
    )
    
    # Get relevant context for next response
    context = memory.get_context("What theme should I use?", user_id="user_123")

Quick Start (Smart Agent - Full Auto):
    from aegis_memory import SmartAgent
    
    agent = SmartAgent(
        aegis_api_key="your-aegis-key",
        llm_api_key="your-openai-key"
    )
    
    # Memory is handled automatically
    response = agent.chat("I prefer Python", user_id="user_123")
    response = agent.chat("What language for this project?", user_id="user_123")
    # Agent remembers user prefers Python!

For more examples, see: https://github.com/quantifylabs/aegis-memory/tree/main/examples
"""

__version__ = "2.2.0"

# Core client (manual control)
from aegis_memory.client import (
    AegisClient,
    AsyncAegisClient,
    Memory,
    PlaybookEntry,
    SessionProgress,
    Feature,
    RunResult,
    CurationResult,
    CurationEntry,
    ConsolidationCandidate,
)


def local_client(
    *,
    db_path: str = None,
    openai_api_key: str = None,
    embedding_model: str = None,
    embedding_provider=None,
    signing_key: str = "aegis-local-default-key",
) -> AegisClient:
    """
    Create a local-mode AegisClient (SQLite + numpy, no server needed).

    Usage::

        from aegis_memory import local_client
        client = local_client()
        client.add("User prefers dark mode", agent_id="ui-agent")
        memories = client.query("user preferences", agent_id="ui-agent")

    Args:
        db_path: SQLite database path (default: ~/.aegis/memory.db)
        openai_api_key: OpenAI key for embeddings (or set OPENAI_API_KEY env var).
            If omitted and sentence-transformers is installed, uses local embeddings.
        embedding_model: Override the embedding model name.
        embedding_provider: Custom EmbeddingProvider instance.
        signing_key: HMAC signing key for integrity hashes.
    """
    return AegisClient(
        mode="local",
        db_path=db_path,
        openai_api_key=openai_api_key,
        embedding_model=embedding_model,
        embedding_provider=embedding_provider,
    )

# Smart memory (automatic extraction)
from aegis_memory.smart import (
    SmartMemory,
    SmartAgent,
    ProcessResult,
    ContextResult,
    create_smart_memory,
)

# Extraction components (for customization)
from aegis_memory.extractors import (
    MemoryExtractor,
    ExtractedMemory,
    ExtractionResult,
    ExtractionPrompts,
    OpenAIAdapter,
    AnthropicAdapter,
    CustomLLMAdapter,
    create_extractor,
)

# Filters (for customization)
from aegis_memory.filters import (
    MessageFilter,
    ConversationFilter,
    FilterResult,
    SignalType,
)

__all__ = [
    # Core
    "AegisClient",
    "AsyncAegisClient",
    "local_client",
    "Memory",
    "PlaybookEntry",
    "SessionProgress",
    "Feature",
    "RunResult",
    "CurationResult",
    "CurationEntry",
    "ConsolidationCandidate",
    # Smart Memory
    "SmartMemory",
    "SmartAgent",
    "ProcessResult",
    "ContextResult",
    "create_smart_memory",
    # Extraction
    "MemoryExtractor",
    "ExtractedMemory",
    "ExtractionResult",
    "ExtractionPrompts",
    "OpenAIAdapter",
    "AnthropicAdapter",
    "CustomLLMAdapter",
    "create_extractor",
    # Filters
    "MessageFilter",
    "ConversationFilter",
    "FilterResult",
    "SignalType",
    # Meta
    "__version__",
]
