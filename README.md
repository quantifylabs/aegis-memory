# Aegis Memory

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**The memory engine for multi-agent systems.**

Aegis Memory is a production-ready, self-hostable memory engine designed to give AI agents a **persistent learning loop**. By combining **semantic search**, **scope-aware access control**, and **ACE (Agentic Context Engineering)**, Aegis allows agents to share state, vote on strategies, and extract actionable reflections from their failures.

## Quick Start

### 1. Start the Server (2 min)

```bash
git clone https://github.com/quantifylabs/aegis-memory.git
cd aegis-memory

export OPENAI_API_KEY=sk-...
docker-compose up -d

# Verify
curl http://localhost:8000/health
```

### 2. Install the CLI + SDK

```bash
pip install aegis-memory
```

### 3. Configure & Use

```bash
# First-time setup
aegis config init

# Check connection
aegis status

# Add your first memory
aegis add "User prefers concise responses" -a assistant -s global

# Query memories
aegis query "user preferences"

# View stats
aegis stats
```

## CLI Reference

Aegis provides a powerful CLI for all memory operations:

```bash
# Core Operations
aegis add "content"              # Add a memory
aegis query "search text"        # Semantic search
aegis get <id>                   # Get single memory
aegis delete <id>                # Delete memory
aegis vote <id> helpful          # Vote on memory

# ACE Patterns
aegis playbook "error handling"  # Query proven strategies
aegis progress show <session>    # View session progress
aegis features list              # Track feature status

# Data Management
aegis export -o backup.jsonl     # Export memories
aegis import backup.jsonl        # Import memories
aegis stats                      # Namespace statistics
```

**[→ Full CLI Reference](https://github.com/quantifylabs/aegis-memory/blob/main/docs/CLI-REFERENCE.md)**

## Python SDK

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="dev-key", base_url="http://localhost:8000")

# Add a memory
client.add("User prefers concise responses", agent_id="assistant")

# Query memories
memories = client.query("user preferences", agent_id="assistant")

# Vote on usefulness (ACE pattern)
client.vote(memories[0].id, "helpful", voter_agent_id="assistant")

# Cross-agent memory sharing
client.add(
    content="Task: Build login. Steps: 1) Form, 2) Validation, 3) API",
    agent_id="planner",
    scope="agent-shared",
    shared_with_agents=["executor"]
)
```

## Why Aegis Memory?

| Challenge | DIY Solution | Aegis Memory |
|-----------|--------------|--------------|
| Multi-agent memory sharing | Custom access control | Built-in scopes (private/shared/global) |
| Long-running agent state | File-based progress tracking | Structured session & feature tracking |
| Context window limits | Dump everything in prompt | Semantic search + effectiveness scoring |
| Learning from mistakes | Manual prompt tuning | Memory voting + reflection patterns |

**Aegis Memory is not just another vector database.** It's an *active strategy engine* with primitives designed to turn agent execution into persistent organizational intelligence.

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

## Framework Integrations

Drop-in support for popular agent frameworks:

```python
# LangChain
from aegis_memory.integrations.langchain import AegisMemory
chain = ConversationChain(llm=llm, memory=AegisMemory(agent_id="assistant"))

# CrewAI
from aegis_memory.integrations.crewai import AegisCrewMemory
crew = Crew(agents=[...], memory=AegisCrewMemory())
```

**[→ Integration Guides](https://github.com/quantifylabs/aegis-memory/tree/main/aegis_memory/integrations/)**

## ACE Patterns

Aegis implements patterns from recent research on self-improving agents:

### Memory Voting
```bash
# After a memory helped complete a task
aegis vote <memory-id> helpful -c "Successfully paginated API"

# Query only effective strategies
aegis playbook "API pagination" -e 0.3
```

### Session Progress
```bash
# Track work across context windows
aegis progress create build-dashboard -a coder
aegis progress update build-dashboard -c auth -i routing
aegis progress show build-dashboard
```

**[→ ACE Patterns Guide](https://github.com/quantifylabs/aegis-memory/blob/main/docs/ACE-PATTERNS.md)**

## Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Query (1M memories) | 30-80ms | HNSW index |
| Add single | ~100ms | Includes embedding |
| Add batch (50) | ~300ms | Batched embedding |
| Deduplication | <1ms | Hash lookup |

## Documentation

- **[Quickstart](https://github.com/quantifylabs/aegis-memory/blob/main/QUICKSTART.md)** — Get running in 15 minutes
- **[ACE Patterns](https://github.com/quantifylabs/aegis-memory/blob/main/docs/ACE-PATTERNS.md)** — Self-improving agent patterns
- **[Operations](https://github.com/quantifylabs/aegis-memory/blob/main/docs/OPERATIONS.md)** — Backup, monitoring, upgrades
- **[Design](https://github.com/quantifylabs/aegis-memory/blob/main/docs/DESIGN.md)** — Technical deep-dive
- **[Recipes](https://github.com/quantifylabs/aegis-memory/tree/main/docs/Recipes/)** — 10 production-ready patterns
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

Apache 2.0 — Use it however you want. See [LICENSE](https://github.com/quantifylabs/aegis-memory/blob/main/LICENSE).

## Links

- [GitHub Discussions](https://github.com/quantifylabs/aegis-memory/discussions)
- [Issue Tracker](https://github.com/quantifylabs/aegis-memory/issues)
- [Changelog](https://github.com/quantifylabs/aegis-memory/blob/main/CHANGELOG.md)

---

Built with ❤️ for the agent community
