# Aegis Memory

[![CI](https://github.com/quantifylabs/aegis-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/quantifylabs/aegis-memory/actions)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**The open-source memory layer for AI agents.**

Aegis Memory is a production-ready, self-hostable memory engine designed for multi-agent systems. It provides semantic search, scope-aware access control, and ACE (Agentic Context Engineering) patterns that help agents learn and improve over time.

## Quick Start: Smart Memory (Zero Config)

```python
from aegis_memory import SmartMemory

memory = SmartMemory(
    aegis_api_key="your-key",
    llm_api_key="your-openai-key"
)

# Automatically extracts and stores valuable information
memory.process_turn(
    user_input="I'm John, a Python developer from Manchester. I prefer dark mode.",
    ai_response="Nice to meet you, John!",
    user_id="user_123"
)
# Stores: "User's name is John", "User is a Python developer", 
#         "User is based in Mnachester", "User prefers dark mode"

# Get relevant context for any query
context = memory.get_context("What theme should I use?", user_id="user_123")
print(context.context_string)
# "- User prefers dark mode"
```

**Smart Memory handles the hard part:** deciding what's worth remembering. It filters out greetings and noise, extracts atomic facts, and stores them with proper categorization.

[📚 Full Smart Memory Guide](docs/SMART-MEMORY.md)

## Manual Control: AegisClient

For full control over what gets stored:

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="your-key")

# Add a memory
client.add("User prefers concise responses", agent_id="assistant")

# Query memories
memories = client.query("user preferences", agent_id="assistant")

# Vote on usefulness (ACE pattern)
client.vote(memories[0].id, "helpful", voter_agent_id="assistant")
```

## Why Aegis Memory?

| Challenge | DIY Solution | Aegis Memory |
|-----------|--------------|--------------|
| Multi-agent memory sharing | Custom access control | Built-in scopes (private/shared/global) |
| Long-running agent state | File-based progress tracking | Structured session & feature tracking |
| Context window limits | Dump everything in prompt | Semantic search + effectiveness scoring |
| Learning from mistakes | Manual prompt tuning | Memory voting + reflection patterns |

**Aegis Memory is not another vector database.** It's an *agent-native memory fabric* with primitives designed for how AI agents actually work.

## Choosing the Right Memory Solution

Different memory solutions excel at different problems. Here's when to choose what:

| Use Case | Best Choice | Why |
|----------|-------------|-----|
| **Personal AI assistant** that remembers user preferences across sessions | **mem0** | Optimized for user personalization, graph-based relationships, managed platform with enterprise compliance |
| **Second brain / knowledge base** with document sync from Drive, Notion | **Supermemory** | Built for personal knowledge management, document integrations, fast RAG retrieval |
| **Multi-agent systems** where agents need to share knowledge with access control | **Aegis Memory** | Native scopes (private/shared/global), cross-agent queries, structured handoffs |
| **Long-running agents** that need to track progress across context resets | **Aegis Memory** | Session progress tracking, feature completion tracking, survives context windows |
| **Self-improving agents** that learn what works over time | **Aegis Memory** | ACE patterns: memory voting, playbooks, reflections |
| **Enterprise chat** with compliance requirements (SOC 2, HIPAA) | **mem0** | Built-in enterprise controls, managed platform option |

### Quick Feature Comparison

| Capability | mem0 | Supermemory | Aegis Memory |
|------------|------|-------------|--------------|
| **Primary Focus** | User personalization | Knowledge management | Multi-agent coordination |
| **Open Source** | ✓ | ✓ | ✓ |
| **Self-Hostable** | ✓ | ✓ | ✓ |
| **Memory Scopes** | User, Session, Agent | Containers, Profiles | Private, Shared, Global + ACL |
| **Cross-Agent Queries** | — | — | ✓ With access control |
| **Agent Handoffs** | — | — | ✓ Structured state transfer |
| **Document Sync** | — | ✓ (Drive, Notion) | — |
| **Graph Memory** | ✓ (Neo4j) | — | — |
| **Memory Voting** | — | — | ✓ ACE patterns |
| **Session Progress** | — | — | ✓ Survives context resets |
| **Managed Platform** | ✓ | ✓ | Self-host only |
| **Framework Support** | LangChain, CrewAI, AutoGen | MCP, Various | LangChain, CrewAI, LangGraph |

> **Bottom line:** Choose mem0 for personalization, Supermemory for knowledge bases, Aegis for multi-agent systems.

## 15-Second Demo

See Aegis Memory in action with our interactive demo:

```bash
# Start the server
docker compose up -d

# Run the demo
pip install aegis-memory
aegis demo
```

The demo walks through 5 acts showing:
1. **The Problem** — Agents forget everything between sessions
2. **Aegis Memory** — Persistent memory that survives context resets
3. **Smart Extraction** — Automatic extraction of valuable information
4. **Multi-Agent** — Agents share knowledge with scope control
5. **Self-Improvement** — Agents learn what works over time

```bash
# Save demo output to share on social media
aegis demo --log
# Creates demo.log file
```

> **Tip:** Set `OPENAI_API_KEY` for live Smart Extraction, or see simulated output without it.

## Features

### Core Memory
- **Semantic Search** — pgvector HNSW index for O(log n) queries at scale
- **Scope-Aware Access** — `agent-private`, `agent-shared`, `global` with automatic ACL
- **Multi-Agent Handoffs** — Structured state transfer between agents
- **Auto-Deduplication** — Hash-based O(1) duplicate detection

### ACE Patterns
- **Memory Voting** — Track which memories help vs harm task completion
- **Delta Updates** — Incremental changes that prevent context collapse
- **Reflections** — Store insights from failures for future reference
- **Session Progress** — Track work across context windows
- **Feature Tracking** — Prevent premature task completion

### Production Ready
- **Self-Hostable** — Docker, Kubernetes, any cloud
- **Observable** — Prometheus metrics, structured logging
- **Fast** — 30-80ms queries on 1M+ memories
- **Safe** — Data export, migrations, no vendor lock-in

## Quick Start

### 1. Start the Server (2 min)

```bash
git clone https://github.com/quantifylabs/aegis-memory.git
cd aegis-memory

export OPENAI_API_KEY=sk-...
docker-compose up -d

curl http://localhost:8000/health
# {"status": "healthy"}
```

### 2. Install the SDK

```bash
pip install aegis-memory
```

### 3. Use It

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="dev-key", base_url="http://localhost:8000")

# Planner agent stores task breakdown
client.add(
    content="Task: Build login. Steps: 1) Form, 2) Validation, 3) API",
    agent_id="planner",
    scope="agent-shared",
    shared_with_agents=["executor"]
)

# Executor queries planner's memories
memories = client.query_cross_agent(
    query="current task",
    requesting_agent_id="executor",
    target_agent_ids=["planner"]
)
print(memories[0].content)
```

**[→ Full Quickstart Guide](QUICKSTART.md)**

## Framework Integrations

Drop-in support for popular agent frameworks:

```python
# LangChain
from aegis_memory.integrations.langchain import AegisMemory
chain = ConversationChain(llm=llm, memory=AegisMemory(agent_id="assistant"))

# LangGraph
from aegis_memory.integrations.langgraph import AegisCheckpointer
app = workflow.compile(checkpointer=AegisCheckpointer())

# CrewAI
from aegis_memory.integrations.crewai import AegisCrewMemory
crew = Crew(agents=[...], memory=AegisCrewMemory())
```

**[→ Integration Guides](integrations/)**

## ACE Patterns

Aegis implements patterns from recent research on self-improving agents:

### Memory Voting
```python
# After a memory helped complete a task
client.vote(memory.id, "helpful", voter_agent_id="executor")

# Query only effective strategies
strategies = client.playbook("API pagination", agent_id="executor", min_effectiveness=0.3)
```

### Session Progress
```python
# Track work across context windows
client.progress.update(
    session_id="build-dashboard",
    completed=["auth", "routing"],
    in_progress="api-client",
    blocked=[{"item": "payments", "reason": "Waiting for API keys"}]
)
```

### Reflections
```python
# Store lessons from failures
client.reflection(
    content="Always use while True for pagination, not range(n)",
    agent_id="reflector",
    error_pattern="pagination_incomplete"
)
```

**[→ ACE Patterns Guide](docs/ACE-PATTERNS.md)**

## Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Query (1M memories) | 30-80ms | HNSW index |
| Add single | ~100ms | Includes embedding |
| Add batch (50) | ~300ms | Batched embedding |
| Deduplication | <1ms | Hash lookup |

## Documentation

- **[Quickstart](QUICKSTART.md)** — Get running in 15 minutes
- **[ACE Patterns](docs/ACE-PATTERNS.md)** — Self-improving agent patterns
- **[Operations](docs/OPERATIONS.md)** — Backup, monitoring, upgrades
- **[Design](docs/DESIGN.md)** — Technical deep-dive
- **[API Reference](http://localhost:8000/docs)** — OpenAPI docs (when running)

## Deployment

### Docker Compose

```bash
docker-compose up -d
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `OPENAI_API_KEY` | — | For embeddings |
| `AEGIS_API_KEY` | `dev-key` | API authentication |

**[→ Full Configuration](docs/OPERATIONS.md#configuration)**

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Run tests
pytest tests/ -v

# Run linting
ruff check server/
```

## License

Apache 2.0 — Use it however you want. See [LICENSE](LICENSE).

## Links

- [GitHub Discussions](https://github.com/quantifylabs/aegis-memory/discussions)
- [Issue Tracker](https://github.com/quantifylabs/aegis-memory/issues)
- [Changelog](CHANGELOG.md)

---

Built with ❤️ for the agent community