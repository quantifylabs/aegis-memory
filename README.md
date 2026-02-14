<p align="center">
  <img src=".github/banner.svg" alt="Aegis Memory" width="400"/>
</p>

<p align="center">
  <strong>The Memory Layer for Multi-Agent Systems</strong>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://docs.aegismemory.com"><img src="https://img.shields.io/badge/docs-aegismemory.com-6366F1" alt="Docs"></a>
</p>

<p align="center">
  <a href="https://www.aegismemory.com/">Website</a> •
  <a href="https://docs.aegismemory.com/introduction/overview">Docs</a> •
  <a href="https://www.aegismemory.com/blog/">Blog</a> •
  <a href="https://docs.aegismemory.com/quickstart/installation">Quickstart</a> •
  <a href="https://docs.aegismemory.com/integrations/crewai">Integrations</a> •
  <a href="https://docs.aegismemory.com/guides/observability">Observability</a>
</p>

---

Aegis Memory is a production-ready, self-hostable memory engine designed for multi-agent systems. It provides semantic search, scope-aware access control, and ACE (Agentic Context Engineering) patterns that help agents learn and improve over time.

## Get productive in 2 minutes

For first-time setup, starter scaffolding, and debugging memory quality, start with the CLI flow:

1. `aegis init`
2. `aegis new <template>`
3. `aegis explore`

See the [CLI API reference](docs/api-reference/cli.mdx) for command details.

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
#         "User is based in Manchester", "User prefers dark mode"

# Get relevant context for any query
context = memory.get_context("What theme should I use?", user_id="user_123")
print(context.context_string)
# "- User prefers dark mode"
```

**Smart Memory handles the hard part:** deciding what's worth remembering. It filters out greetings and noise, extracts atomic facts, and stores them with proper categorization.

[📚 Full Smart Memory Guide](https://docs.aegismemory.com/guides/smart-memory)

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
| Multi-agent memory sharing | Custom access control | Built-in scopes (`agent-private`/`agent-shared`/`global`) |
| Long-running agent state | File-based progress tracking | Structured session & feature tracking |
| Context window limits | Dump everything in prompt | Semantic search + effectiveness scoring |
| Learning from mistakes | Manual prompt tuning | Memory voting + reflection patterns |
| Typed cognitive memory (episodic/semantic/procedural/control) | Custom schema per type | Built-in typed memory API with session timelines & entity facts |

**Aegis Memory is not another vector database.** It's an *agent-native memory fabric* with primitives designed for how AI agents actually work.

## Choosing the Right Memory Solution

Different memory tools solve different memory problems. This comparison stays focused on capabilities that are clearly documented in public docs/repos.[^comparison]

| If you need... | Usually pick | Reason |
|---|---|---|
| Personalized assistant memory (user/profile facts, retrieval) | **mem0** | Designed around persistent user/agent memory for assistants and copilots |
| Personal/team "second brain" with ingestion + retrieval | **Supermemory** | Knowledge-base style memory with connectors and retrieval workflows |
| Graph-native episodic memory over agent events | **Graphiti / Zep** | Focused on temporal + knowledge graph memory models |
| Stateful agent runtime + built-in memory blocks | **Letta** | Agent framework centered on durable state and memory editing |
| Multi-agent coordination with explicit access boundaries | **Aegis Memory** | Scope-aware ACLs (`agent-private` / `agent-shared` / `global`) plus cross-agent query APIs |
| Cross-agent handoffs that preserve task context | **Aegis Memory** | Handoff baton primitives for structured state transfer between agents |
| Self-improving memory loops (what worked / failed) | **Aegis Memory** | ACE patterns: vote, reflection, playbook |

### Quick Feature Comparison

| Capability | mem0 | Supermemory | Graphiti / Zep | Letta | Aegis Memory |
|---|---|---|---|---|---|
| **Primary focus** | Assistant personalization memory | Knowledge retrieval + synced context | Graph-based episodic/relational memory | Stateful agents with editable memory | Multi-agent memory coordination |
| **Open source** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Self-host posture** | Self-host options available | Self-host options available | Self-host options available | Self-host options available | Self-host-first |
| **Graph-native memory model** | Partial / optional | — | ✓ | — | — |
| **Built for multi-agent ACL/scopes** | — | — | — | — | ✓ |
| **Cross-agent query with policy boundaries** | — | — | — | — | ✓ |
| **Handoff baton / structured handoff state** | — | — | — | — | ✓ |
| **ACE loop (vote / reflection / playbook)** | — | — | — | — | ✓ |
| **Typed memory model** | — | — | — | — | ✓ |

### When to pick Aegis (quick checklist)

Pick **Aegis Memory** when most of these are true:

- You need **multiple agents** to share memory safely with explicit ACL/scopes.
- You need **handoffs** where one agent passes a reliable baton/state bundle to another.
- You want **ACE patterns** (vote/reflection/playbook) to continuously improve memory quality.
- You prefer a **self-host posture** with operational control over storage and deployment.

> Compliance, pricing, and managed-service nuances are intentionally omitted from the main table; keep those in footnotes/docs so the core comparison remains verifiable.[^comparison]

## 15-Second Demo

See Aegis Memory in action with built-in CLI commands:

```bash
# Start the server
docker compose up -d

# Configure defaults (creates local profile)
pip install aegis-memory
aegis init --non-interactive

# Check connectivity
aegis status

# Add and retrieve a memory
aegis add "User prefers dark mode"
aegis query "What does the user prefer?" --top-k 3

# Optionally browse results interactively
aegis explore --query "user preferences" --top-k 5
```

This quick flow shows:
1. **Initialization** — Configure CLI defaults for your environment
2. **Connectivity** — Verify server health before writing memories
3. **Persistence** — Add a memory that survives agent context resets
4. **Retrieval** — Semantically query what was stored
5. **Exploration** — Iterate on results from an interactive terminal explorer

```bash
# JSON output for scripting / logs
aegis status --json
aegis query "What does the user prefer?" --json
```

> **Tip:** Set `OPENAI_API_KEY` to enable embedding-backed semantic retrieval on the server.

## Features

### Core Memory
- **Semantic Search** — pgvector HNSW index for O(log n) queries at scale
- **Scope-Aware Access** — `agent-private`, `agent-shared`, `global` with automatic ACL
- **Multi-Agent Handoffs** — Structured state transfer between agents
- **Auto-Deduplication** — Hash-based O(1) duplicate detection
- **Typed Memory** — Cognitive memory types: episodic, semantic, procedural, control

### ACE Patterns
- **Memory Voting** — Track which memories help vs harm task completion
- **Delta Updates** — Incremental changes that prevent context collapse
- **Reflections** — Store insights from failures for future reference
- **Session Progress** — Track work across context windows
- **Feature Tracking** — Prevent premature task completion

### Production Ready
- **Self-Hostable** — Docker, Kubernetes, any cloud
- **Observable** — Prometheus metrics, structured logging
- **Fast** — Sub-100ms writes, 85 ops/s concurrent throughput
- **Safe** — Data export, migrations, no vendor lock-in

### Observability & Evaluation
- **Metrics endpoint** — `/metrics` for Prometheus scraping (request, operation, cache, and ACE counters)
- **Evaluation harness APIs** — `/memories/ace/eval/metrics` and `/memories/ace/eval/correlation`
- **Dashboard APIs** — `/memories/ace/dashboard/stats`, `/activity`, `/sessions`
- **Design roadmap** — Memory analytics, timeline events, effectiveness attribution, and Langfuse/LangSmith export plan

**[→ Observability Guide](https://docs.aegismemory.com/guides/observability)**

## Quick Start

### 1. Start the Server (2 min)

Requires **Python 3.10+** (matches `pyproject.toml`).

```bash
git clone https://github.com/quantifylabs/aegis-memory.git
cd aegis-memory

export OPENAI_API_KEY=sk-...
docker compose up -d

curl http://localhost:8000/health
# {"status": "healthy"}
```

### 2. Install the SDK

```bash
# Python 3.10+
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

**[→ Full Quickstart Guide](https://docs.aegismemory.com/quickstart/installation)**

## Async Usage (FastAPI / LangGraph / CrewAI)

`AsyncAegisClient` mirrors the core `AegisClient` APIs for async applications.

```python
from aegis_memory import AsyncAegisClient

async def handle_turn(user_id: str, text: str):
    async with AsyncAegisClient(api_key="dev-key", base_url="http://localhost:8000") as client:
        await client.add(text, user_id=user_id, agent_id="assistant")
        memories = await client.query("user preferences", user_id=user_id)
        return memories
```

Use this pattern in:
- **FastAPI** request handlers (`async def` endpoints)
- **LangGraph** async nodes (`await client.query(...)`)
- **CrewAI** async tools/callbacks that run in event loops

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

**[→ Integration Guides](https://docs.aegismemory.com/integrations/crewai)**

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

**[→ ACE Patterns Guide](https://docs.aegismemory.com/guides/ace-patterns)**

## Typed Memory API

Aegis supports 4 cognitive memory types inspired by research SOTA systems for multi-layered agent memory:

```python
# Episodic — record interaction trace
client.post("/memories/typed/episodic", json={
    "content": "User asked about pricing",
    "agent_id": "sales",
    "session_id": "conv-42",
    "sequence_number": 1,
})

# Semantic — store extracted fact
client.post("/memories/typed/semantic", json={
    "content": "User is a Python developer",
    "entity_id": "user_123",
})

# Procedural — save reusable strategy
client.post("/memories/typed/procedural", json={
    "content": "For API pagination, use cursor-based approach",
    "agent_id": "executor",
    "steps": ["Init cursor", "Fetch page", "Check has_more"],
})

# Control — record meta-rule
client.post("/memories/typed/control", json={
    "content": "Never use range() for unknown-length pagination",
    "agent_id": "reflector",
    "error_pattern": "pagination_incomplete",
})

# Query by type
client.post("/memories/typed/query", json={
    "query": "pagination strategies",
    "memory_types": ["procedural", "control"],
})

# Session timeline
client.get("/memories/typed/episodic/session/conv-42")

# Entity facts
client.get("/memories/typed/semantic/entity/user_123")
```

**[→ Typed Memory Guide](https://docs.aegismemory.com/guides/typed-memory)**

## Performance

Benchmarked on 8 vCPU / 7.6 GB RAM (Intel 13th Gen), 1000 memories, Docker Compose (PostgreSQL 16 + pgvector), concurrency=10. Queries include OpenAI embedding latency. Reproduce with `cd benchmarks && bash run_benchmark.sh`.

| Operation | p50 | p95 | p99 | Throughput |
|-----------|-----|-----|-----|------------|
| Sequential add | 72ms | 89ms | 97ms | 14.1 ops/s |
| Batch add (5x20) | 216ms | 292ms | 292ms | 4.6 ops/s |
| Concurrent add (c=10) | 100ms | 193ms | 511ms | 85.1 ops/s |
| Sequential query | 282ms | 411ms | 1502ms | 3.8 ops/s |
| Concurrent query (c=10) | 413ms | 1832ms | 1897ms | 18.6 ops/s |
| Cross-agent query | 304ms | 380ms | 380ms | 3.3 ops/s |
| Vote | 64ms | 176ms | 176ms | 14.1 ops/s |
| Deduplication | 75ms | 112ms | 112ms | 13.6 ops/s |

> **Note:** Query tail latency (p95/p99) is dominated by the external OpenAI embedding call, not Aegis or PostgreSQL. Write and vote operations that skip embedding are consistently under 100ms at p50.

## Documentation

**📚 [docs.aegismemory.com](https://docs.aegismemory.com)** — Full documentation

- **[Quickstart](https://docs.aegismemory.com/quickstart/installation)** — Get running in 5 minutes
- **[Smart Memory](https://docs.aegismemory.com/guides/smart-memory)** — Zero-config memory extraction
- **[ACE Patterns](https://docs.aegismemory.com/guides/ace-patterns)** — Self-improving agent patterns
- **[Integrations](https://docs.aegismemory.com/integrations/crewai)** — CrewAI, LangChain guides
- **[CLI Reference](https://docs.aegismemory.com/api-reference/cli)** — Command-line tools

## Deployment

### Docker Compose

```bash
docker compose up -d
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

**[→ Full Configuration](https://docs.aegismemory.com/guides/production-deployment)**

## Troubleshooting

### Connection Refused / Cannot Connect to Server

```
Cannot connect to Aegis server
  URL: http://localhost:8000
```

**Fix:**
1. Verify the server is running: `docker compose ps`
2. Check the server URL in your config: `aegis config show`
3. Ensure the port is not blocked by a firewall
4. If using a custom URL, pass it explicitly: `AegisClient(api_key="...", base_url="http://your-host:8000")`

### Authentication Failed / Invalid API Key

```
Authentication failed: Invalid API key
```

**Fix:**
1. Check your configured key: `aegis config show`
2. Reconfigure: `aegis config init`
3. Or set via environment variable: `export AEGIS_API_KEY=your-key`
4. The default development key is `dev-key`

### Missing OPENAI_API_KEY

```
RuntimeError: OPENAI_API_KEY is required for embeddings
```

**Fix:**
1. Set the environment variable: `export OPENAI_API_KEY=sk-...`
2. Or pass it in your `docker-compose.yml` under the server service environment

### Database Connection Errors

```
asyncpg.exceptions: could not connect to server
```

**Fix:**
1. Ensure PostgreSQL is running: `docker compose ps`
2. Check `DATABASE_URL` in your environment matches the running database
3. Verify pgvector extension is installed: `CREATE EXTENSION IF NOT EXISTS vector;`
4. Run migrations if upgrading: `psql -f migrations/002_ace_tables.sql`

### Smart Memory Returns No Extractions

If `process_turn()` always returns empty results:

1. **Check the filter** — Short or generic messages are filtered out by design. Use `force_extract=True` to bypass:
   ```python
   result = memory.process_turn(user_input="...", ai_response="...", force_extract=True)
   ```
2. **Check the LLM key** — Extraction requires a valid OpenAI or Anthropic API key
3. **Lower the sensitivity** — `SmartMemory(..., sensitivity="high")` passes more messages to the LLM

### Import Errors (ModuleNotFoundError)

```
ModuleNotFoundError: No module named 'aegis_memory.integrations.langchain'
```

**Fix:** Install the optional dependency group:
```bash
# Python 3.10+
pip install aegis-memory[langchain]   # For LangChain
pip install aegis-memory[crewai]      # For CrewAI
pip install aegis-memory[server]      # For server components
pip install aegis-memory[all]         # Everything
```

### Rate Limit Exceeded (429)

**Fix:**
1. Wait and retry — the `Retry-After` header indicates how long
2. Reduce request frequency or batch operations with `add_batch()`
3. Adjust server-side limits via `RATE_LIMIT_*` environment variables

### Slow Queries on Large Datasets

If queries take longer than expected on 100K+ memories:

1. Verify the HNSW index exists: check `migrations/` scripts were applied
2. Increase `DB_POOL_SIZE` for concurrent workloads
3. Use a read replica via `DATABASE_READ_REPLICA_URL` for query-heavy traffic
4. Filter by `namespace` or `agent_id` to narrow the search space

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

- [Documentation](https://docs.aegismemory.com)
- [GitHub Discussions](https://github.com/quantifylabs/aegis-memory/discussions)
- [Issue Tracker](https://github.com/quantifylabs/aegis-memory/issues)
- [Changelog](CHANGELOG.md)

---

Built with ❤️ for the agent community

[^comparison]: Sources: [mem0 docs/repo](https://docs.mem0.ai/) · [Supermemory repo/docs](https://github.com/supermemoryai/supermemory) · [Graphiti repo](https://github.com/getzep/graphiti) and [Zep docs](https://help.getzep.com/) · [Letta docs/repo](https://github.com/letta-ai/letta) · [Aegis Memory docs](https://docs.aegismemory.com/).
