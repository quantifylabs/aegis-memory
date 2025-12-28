# Smart Memory Guide

> **Zero-config intelligent memory for AI agents**

Smart Memory is Aegis's intelligent extraction layer that automatically determines what's worth remembering from conversations. Instead of storing everything (noise) or requiring manual decisions (burden), Smart Memory uses a two-stage process to extract and store only valuable information.

## Table of Contents

1. [Quick Start](#quick-start)
2. [How It Works](#how-it-works)
3. [Use Cases](#use-cases)
4. [Configuration](#configuration)
5. [Framework Integration](#framework-integration)
6. [What Gets Stored](#what-gets-stored)
7. [Customization](#customization)
8. [Best Practices](#best-practices)
9. [API Reference](#api-reference)

---

## Quick Start

### Installation

```bash
pip install aegis-memory
```

### Basic Usage (SmartMemory)

```python
from aegis_memory import SmartMemory

# Initialize with your API keys
memory = SmartMemory(
    aegis_api_key="your-aegis-key",
    llm_api_key="your-openai-key"
)

# After each conversation turn, process it
memory.process_turn(
    user_input="I'm John, a Python developer from Chennai. I prefer dark mode.",
    ai_response="Nice to meet you, John! I'll remember your preferences.",
    user_id="user_123"
)

# Later, get relevant context for a new query
context = memory.get_context(
    query="What color theme should I use?",
    user_id="user_123"
)

print(context.context_string)
# Output:
# - User's name is John
# - User is a Python developer
# - User is based in Chennai
# - User prefers dark mode for applications
```

### Full Auto (SmartAgent)

For the simplest experience, use `SmartAgent` which handles everything:

```python
from aegis_memory import SmartAgent

agent = SmartAgent(
    aegis_api_key="your-aegis-key",
    llm_api_key="your-openai-key",
    system_prompt="You are a helpful coding assistant."
)

# Memory is completely automatic
response = agent.chat("I'm John, I prefer Python over JavaScript", user_id="user_123")
response = agent.chat("What language should I use for this project?", user_id="user_123")
# Agent automatically knows user prefers Python!
```

---

## How It Works

Smart Memory uses a **two-stage process** to avoid expensive LLM calls while maintaining quality:

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONVERSATION TURN                            │
│  User: "I'm John, a developer from Chennai"                     │
│  AI: "Nice to meet you, John!"                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: FAST FILTER (Rule-based, ~0.1ms)                      │
│                                                                  │
│  Checks for memory signals:                                      │
│  ✓ "I'm" → Personal fact signal                                 │
│  ✓ "developer" → Professional fact signal                       │
│  ✓ "from Chennai" → Location signal                             │
│                                                                  │
│  Decision: WORTH EXTRACTING                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: LLM EXTRACTION (~200ms, only if Stage 1 passes)       │
│                                                                  │
│  Extracts atomic facts:                                          │
│  1. "User's name is John" (fact, confidence: 0.95)              │
│  2. "User is a developer" (fact, confidence: 0.90)              │
│  3. "User is based in Chennai" (fact, confidence: 0.92)         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3: STORE TO AEGIS                                        │
│                                                                  │
│  Each fact stored separately with:                               │
│  - Category (fact, preference, decision, etc.)                  │
│  - Confidence score                                              │
│  - Memory type (standard, strategy, reflection)                 │
│  - Metadata for filtering                                        │
└─────────────────────────────────────────────────────────────────┘
```

### Why Two Stages?

| Approach | LLM Calls | Cost | Quality |
|----------|-----------|------|---------|
| Store everything | 0 | Low | Poor (noisy) |
| LLM for everything | 100% | High | Good |
| **Two-stage (Smart)** | ~30% | Low | Good |

The filter catches obvious non-memories (greetings, confirmations) without LLM calls, saving ~70% of extraction costs.

---

## Use Cases

Smart Memory has built-in extraction profiles for different scenarios:

### Conversational (Default)

```python
memory = SmartMemory(use_case="conversational", ...)
```

**Extracts:** Preferences, personal facts, relationships
**Ignores:** Greetings, one-time questions, temporary states

### Task-Oriented

```python
memory = SmartMemory(use_case="task", ...)
```

**Extracts:** Decisions, constraints, problems solved, strategies
**Ignores:** Implementation details, debugging steps

### Coding

```python
memory = SmartMemory(use_case="coding", ...)
```

**Extracts:** Tech stack decisions, architecture choices, bugs and solutions, coding preferences
**Ignores:** Syntax questions, one-off debugging

### Research

```python
memory = SmartMemory(use_case="research", ...)
```

**Extracts:** Key findings, sources, contradictions, open questions
**Ignores:** General knowledge lookups, temporary search queries

### Creative

```python
memory = SmartMemory(use_case="creative", ...)
```

**Extracts:** Style preferences, project details, feedback preferences
**Ignores:** Draft iterations, rejected brainstorms

### Support

```python
memory = SmartMemory(use_case="support", ...)
```

**Extracts:** User setup, past issues, skill level, account details
**Ignores:** Troubleshooting steps, generic support talk

---

## Configuration

### Sensitivity Levels

Control how aggressively Smart Memory extracts:

```python
# High sensitivity - extract more, risk some noise
memory = SmartMemory(sensitivity="high", ...)

# Balanced (default) - good balance
memory = SmartMemory(sensitivity="balanced", ...)

# Low sensitivity - extract less, only high-confidence
memory = SmartMemory(sensitivity="low", ...)
```

### LLM Providers

```python
# OpenAI (default)
memory = SmartMemory(
    llm_provider="openai",
    llm_api_key="sk-...",
    llm_model="gpt-4o-mini"  # Cost-effective default
)

# Anthropic
memory = SmartMemory(
    llm_provider="anthropic",
    llm_api_key="sk-ant-...",
    llm_model="claude-3-haiku-20240307"
)

# Custom LLM
from aegis_memory import CustomLLMAdapter

def my_llm(prompt: str) -> str:
    # Your LLM call here
    return response

memory = SmartMemory(
    custom_llm=CustomLLMAdapter(sync_fn=my_llm)
)
```

### Auto-Store Control

```python
# Auto-store enabled (default)
memory = SmartMemory(auto_store=True, ...)

# Manual storage (extract but don't store automatically)
memory = SmartMemory(auto_store=False, ...)

result = memory.process_turn(user_input="...", ai_response="...")
for extracted in result.extracted:
    if should_store(extracted):  # Your logic
        memory.store_explicit(extracted.content, ...)
```

---

## Framework Integration

### LangChain

```python
from aegis_memory.integrations.langchain import AegisSmartMemory
from langchain.chains import ConversationChain
from langchain.chat_models import ChatOpenAI

memory = AegisSmartMemory(
    agent_id="assistant",
    aegis_api_key="your-aegis-key",
    llm_api_key="your-openai-key",
    use_case="conversational"
)

chain = ConversationChain(
    llm=ChatOpenAI(),
    memory=memory
)

# Smart extraction happens automatically on each chain call
response = chain.predict(input="I'm John, a Python developer")
```

### CrewAI

```python
from aegis_memory.integrations.crewai import AegisSmartCrewMemory
from crewai import Agent, Task, Crew

memory = AegisSmartCrewMemory(
    namespace="my-crew",
    aegis_api_key="your-aegis-key",
    llm_api_key="your-openai-key"
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    memory=memory
)
```

---

## What Gets Stored

### Categories

Smart Memory categorizes extracted information:

| Category | Description | Example |
|----------|-------------|---------|
| `preference` | Likes, dislikes, style | "User prefers dark mode" |
| `fact` | Personal information | "User is a developer in Chennai" |
| `decision` | Choices made | "User decided to use React" |
| `constraint` | Limits and requirements | "Budget is $5000" |
| `goal` | What user wants | "User wants to build a chatbot" |
| `strategy` | What worked | "Using async improved performance" |
| `mistake` | What didn't work | "Don't use range() for large pagination" |

### Memory Types Mapping

Categories map to Aegis `memory_type`:

| Category | Memory Type | Used For |
|----------|-------------|----------|
| preference, fact, decision, constraint, goal | `standard` | General retrieval |
| strategy | `strategy` | Playbook queries |
| mistake | `reflection` | Error prevention |

---

## Customization

### Custom Extraction Prompt

```python
from aegis_memory import MemoryExtractor, OpenAIAdapter

custom_prompt = """
You are extracting memories for a medical assistant.

Focus on:
- Patient symptoms and conditions
- Medications and allergies
- Treatment preferences
- Medical history

NEVER store:
- Specific test results (privacy)
- Appointment details (temporary)

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):
"""

extractor = MemoryExtractor(
    llm=OpenAIAdapter(api_key="..."),
    custom_prompt=custom_prompt
)

memory = SmartMemory(
    aegis_api_key="...",
    custom_llm=extractor.llm,
    # ... other settings
)
```

### Custom Filter Patterns

```python
from aegis_memory.filters import MessageFilter

class CustomFilter(MessageFilter):
    # Add domain-specific patterns
    PREFERENCE_PATTERNS = MessageFilter.PREFERENCE_PATTERNS + [
        r"\b(my stack|tech stack|tools i use)\b",
        r"\b(framework preference|library choice)\b",
    ]
    
    # Add skip patterns for your domain
    SKIP_PATTERNS = MessageFilter.SKIP_PATTERNS + [
        (r"^(checking|loading|processing)\.{3}$", "loading_indicator"),
    ]

memory = SmartMemory(
    aegis_api_key="...",
    llm_api_key="...",
)
memory.filter = CustomFilter(sensitivity="balanced")
```

---

## Best Practices

### 1. Choose the Right Use Case

```python
# Don't use "conversational" for coding tasks
memory = SmartMemory(use_case="coding", ...)  # ✓

# Match use case to your domain
use_cases = {
    "chatbot": "conversational",
    "code_assistant": "coding",
    "research_agent": "research",
    "writing_assistant": "creative",
    "customer_support": "support",
    "task_automation": "task",
}
```

### 2. Use Appropriate Sensitivity

```python
# High sensitivity for personal assistants (remember more)
memory = SmartMemory(sensitivity="high", use_case="conversational")

# Low sensitivity for task agents (only critical info)
memory = SmartMemory(sensitivity="low", use_case="task")
```

### 3. Monitor Extraction Stats

```python
# Periodically check extraction quality
stats = memory.get_stats()

print(f"Turns processed: {stats['turns_processed']}")
print(f"Filtered out: {stats['turns_filtered_out']} ({stats['filter_rate']:.1%})")
print(f"Memories extracted: {stats['memories_extracted']}")
print(f"LLM calls: {stats['llm_calls']}")

# If filter_rate is too high, increase sensitivity
# If filter_rate is too low, decrease sensitivity
```

### 4. Combine with Explicit Storage

```python
# Smart extraction for conversations
memory.process_turn(user_input, ai_response, user_id=user_id)

# Explicit storage for known-important info
memory.store_explicit(
    content="User completed onboarding",
    user_id=user_id,
    category="fact"
)
```

---

## API Reference

### SmartMemory

```python
class SmartMemory:
    def __init__(
        self,
        aegis_api_key: str,              # Aegis Memory API key
        aegis_base_url: str = "http://localhost:8000",
        llm_api_key: str = None,         # LLM API key
        llm_provider: str = "openai",    # "openai" or "anthropic"
        llm_model: str = None,           # Model for extraction
        use_case: str = "conversational", # Extraction profile
        sensitivity: str = "balanced",   # "high", "balanced", "low"
        auto_store: bool = True,         # Auto-store extracted memories
        namespace: str = "default",      # Aegis namespace
        default_agent_id: str = "smart-memory",
        custom_llm: LLMAdapter = None,   # Custom LLM adapter
    ): ...
    
    def process_turn(
        self,
        user_input: str,
        ai_response: str = "",
        user_id: str = None,
        agent_id: str = None,
        metadata: dict = None,
        force_extract: bool = False,
    ) -> ProcessResult: ...
    
    async def process_turn_async(...) -> ProcessResult: ...
    
    def get_context(
        self,
        query: str,
        user_id: str = None,
        agent_id: str = None,
        top_k: int = 5,
        max_tokens: int = 1000,
        include_scores: bool = False,
    ) -> ContextResult: ...
    
    def store_explicit(
        self,
        content: str,
        user_id: str = None,
        agent_id: str = None,
        category: str = "fact",
        metadata: dict = None,
    ) -> str: ...
    
    def get_stats(self) -> dict: ...
```

### SmartAgent

```python
class SmartAgent:
    def __init__(
        self,
        aegis_api_key: str,
        llm_api_key: str,
        aegis_base_url: str = "http://localhost:8000",
        llm_provider: str = "openai",
        chat_model: str = None,          # Model for chat
        memory_model: str = None,        # Model for extraction (cheaper)
        use_case: str = "conversational",
        system_prompt: str = "You are a helpful assistant.",
        namespace: str = "default",
    ): ...
    
    def chat(
        self,
        message: str,
        user_id: str,
        agent_id: str = "smart-agent",
    ) -> str: ...
    
    async def chat_async(...) -> str: ...
    
    def clear_history(self, user_id: str = None): ...
    
    def get_memory_stats(self) -> dict: ...
```

### ProcessResult

```python
@dataclass
class ProcessResult:
    extracted: List[ExtractedMemory]  # Extracted memories
    stored_ids: List[str]             # IDs of stored memories
    skipped_reason: Optional[str]     # Why skipped (if filtered)
    filter_result: Optional[FilterResult]
```

### ContextResult

```python
@dataclass
class ContextResult:
    context_string: str               # Formatted context for prompts
    memories: List[dict]              # Raw memory objects
    query_time_ms: float              # Query latency
```

---

## Troubleshooting

### "Nothing is being extracted"

1. Check sensitivity: `memory = SmartMemory(sensitivity="high", ...)`
2. Use `force_extract=True` to bypass filter: `memory.process_turn(..., force_extract=True)`
3. Check stats: `print(memory.get_stats())`

### "Too much noise being stored"

1. Lower sensitivity: `memory = SmartMemory(sensitivity="low", ...)`
2. Use a more specific use case
3. Create custom filter patterns

### "LLM costs too high"

1. Use cheaper models: `llm_model="gpt-4o-mini"` or `llm_model="claude-3-haiku-20240307"`
2. Lower sensitivity to reduce LLM calls
3. Use `auto_store=False` and implement your own storage logic

---

## Migration from Basic AegisClient

If you're currently using `AegisClient` with manual `add()` calls:

```python
# Before (manual)
client = AegisClient(api_key="...")
client.add("User prefers dark mode", user_id="user_123")

# After (smart)
memory = SmartMemory(aegis_api_key="...", llm_api_key="...")
memory.process_turn(
    user_input="I prefer dark mode",
    ai_response="Got it!",
    user_id="user_123"
)
# Automatically extracts: "User prefers dark mode"
```

Both can coexist - SmartMemory uses the same Aegis storage backend.
