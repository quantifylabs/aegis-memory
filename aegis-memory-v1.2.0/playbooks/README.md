# Aegis Playbooks

Pre-seeded strategies and reflections that make Aegis smarter out of the box.

## 🎯 Purpose

The "cold start" problem kills adoption. If a user's first query returns empty results, they assume the tool is broken. Playbooks solve this by shipping high-quality strategies that provide immediate value.

When a user asks their agent to "write a FastAPI route" and Aegis immediately returns a battle-tested strategy, that's when they think: "Wow, this actually works."

## 📚 Genesis Playbook

The `genesis.json` file contains ~50 curated entries covering common development tasks:

### Categories

| Category | Topics |
|----------|--------|
| **Python** | async/await, httpx, dataclasses, error handling |
| **API Design** | FastAPI, validation, idempotency, rate limiting |
| **Docker** | multi-stage builds, compose, healthchecks |
| **React** | state management, forms, hooks |
| **Database** | PostgreSQL, indexing, migrations, connection pooling |
| **Testing** | pytest, fixtures, API testing, isolation |
| **Debugging** | logging, structured logs, workflow |
| **Security** | authentication, input validation, token storage |
| **Architecture** | microservices, circuit breakers, graceful shutdown |

### Entry Types

- **Strategy**: Proven patterns and best practices
- **Reflection**: Lessons learned from mistakes (with error patterns)

## 🔧 How It Works

1. On startup, Aegis checks if the database is empty
2. If empty, loads `genesis.json` automatically
3. Entries are created with `project_id: "__aegis_genesis__"`
4. All genesis entries have `scope: "global"` (accessible to all agents)
5. Each entry starts with `bullet_helpful: 3` (pre-seeded credibility)

## 📁 File Structure

```
playbooks/
├── genesis.json          # Core playbook (auto-loaded)
├── README.md            # This file
└── community/           # Community-contributed playbooks
    ├── README.md
    └── [your-playbook].json
```

## 🤝 Contributing

See [community/README.md](./community/README.md) for contribution guidelines.

### Quick Contribution

1. Fork the repository
2. Create a new file: `playbooks/community/[topic].json`
3. Follow the entry schema (see below)
4. Submit a PR

### Entry Schema

```json
{
  "content": "Strategy or reflection content",
  "memory_type": "strategy|reflection",
  "namespace": "aegis/[category]/[subcategory]",
  "metadata": {
    "category": "python|api|docker|react|...",
    "tags": ["tag1", "tag2"],
    "applicable_contexts": ["context1", "context2"]
  },
  "error_pattern": "only-for-reflections"
}
```

### Quality Guidelines

**Good Entry:**
```json
{
  "content": "Use Pydantic models for all API request/response validation. Define strict types with Field() constraints. This catches bugs at the API boundary before they propagate into business logic.",
  "memory_type": "strategy",
  "namespace": "aegis/python/api"
}
```

**Bad Entry:**
```json
{
  "content": "Use pydantic",
  "memory_type": "strategy"
}
```

Entries should be:
- **Specific**: Concrete advice, not vague tips
- **Actionable**: Clear what to do
- **Reasoned**: Explain *why*, not just *what*
- **Namespaced**: Properly categorized for discoverability

## 🔄 Loading Playbooks Manually

```bash
# Force reload genesis (even if already loaded)
cd server
python -c "
import asyncio
from playbook_loader import load_genesis_playbook
from database import init_db, async_session_factory

async def main():
    await init_db()
    async with async_session_factory() as db:
        stats = await load_genesis_playbook(db, force=True)
        print(stats)

asyncio.run(main())
"
```

## 🔍 Querying Genesis Entries

```python
from aegis_memory import AegisClient

client = AegisClient()

# Query playbook for strategies
results = client.query_playbook(
    query="how to handle HTTP requests in Python",
    agent_id="my-agent",
    include_types=["strategy", "reflection"],
    min_effectiveness=0.0
)

for entry in results:
    print(f"[{entry['memory_type']}] {entry['content'][:100]}...")
```

## 📝 License

Apache 2.0 - Same as Aegis Memory
