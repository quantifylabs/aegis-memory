"""
Aegis Memory - Agent-native memory fabric for AI agents.

Aegis Memory is an open-source, self-hostable memory engine for LLM agents with:
- Agent-native semantics (namespace, scope, multi-agent ACLs)
- First-class multi-agent support (cross-agent queries, structured handoffs)
- Context-engineering patterns (ACE-style voting, deltas, reflections, playbooks)
- Production-oriented design (FastAPI + Postgres + pgvector)
- Smart Memory extraction (automatic extraction of valuable information)

Quick Start (Manual Control):
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

__version__ = "1.3.1"

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
