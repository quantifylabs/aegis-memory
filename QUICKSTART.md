# Aegis Memory Quickstart

**Get from zero to working agent memory in under 15 minutes.**

## Prerequisites

- Docker & Docker Compose
- Python 3.10+
- OpenAI API key (for embeddings)

## 1. Start Aegis Memory Server (2 minutes)

```bash
# Clone the repo
git clone https://github.com/quantifylabs/aegis-memory.git
cd aegis-memory

# Set your OpenAI key
export OPENAI_API_KEY=sk-...

# Start the server
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health
# → {"status": "healthy", "database": "connected"}
```

## 2. Install the CLI + SDK (30 seconds)

```bash
pip install aegis-memory
```

## 3. Configure the CLI (1 minute)

```bash
# Interactive setup
aegis config init

# Or quick setup with defaults
aegis config init -y

# Check connection
aegis status
```

You should see:
```
Aegis Memory Server
───────────────────────────────
Status:     healthy
Version:    1.2.2
Database:   connected
...
```

## 4. Add Your First Memory (1 minute)

```bash
# Add a simple memory
aegis add "User prefers dark mode and concise responses" -a assistant

# Add a strategy (shared globally)
aegis add "Always use async/await for HTTP calls" -t strategy -s global

# Add with metadata
aegis add "User's timezone is PST" -m '{"source": "onboarding"}'
```

## 5. Query Memories (1 minute)

```bash
# Semantic search
aegis query "What are the user's preferences?"

# Filter by type
aegis query "HTTP patterns" -t strategy

# Get more results
aegis query "user settings" -k 20

# JSON output for scripting
aegis query "preferences" --json
```

## 6. Multi-Agent Example (3 minutes)

```bash
# Planner agent stores a task breakdown
aegis add "Task: Build login page. Steps: 1) Create form, 2) Add validation, 3) Connect API" \
    -a planner \
    -s agent-shared \
    --share-with executor

# Executor queries planner's memories
aegis query "current task breakdown" -a executor -x planner
```

## 7. Use ACE Patterns (5 minutes)

### Vote on Memory Usefulness

```bash
# First, find a memory
aegis query "HTTP patterns" --ids-only
# → 7f3a8b2c1d4e

# Vote helpful (after it worked)
aegis vote 7f3a8b2c1d4e helpful -c "Successfully handled async requests"

# Vote harmful (if it caused issues)
aegis vote 7f3a8b2c1d4e harmful -c "Caused timeout in sync context"
```

### Track Session Progress

```bash
# Create a session for long-running work
aegis progress create build-dashboard -a coder -s "Building React dashboard"

# Update as you work
aegis progress update build-dashboard \
    -c auth \
    -c routing \
    -i api-client \
    --next "dashboard-ui,testing"

# View progress
aegis progress show build-dashboard
```

### Query the Playbook

```bash
# Get proven strategies before starting a task
aegis playbook "API pagination best practices" -e 0.3

# Only strategies (no reflections)
aegis playbook "error handling" -t strategy
```

### Track Features

```bash
# Create a feature to track
aegis features create user-auth \
    -d "User authentication with JWT" \
    -c auth \
    -t "Can login" \
    -t "Can logout" \
    -t "Token expires correctly"

# Update status
aegis features update user-auth -s in_progress --implemented-by executor

# Mark as verified
aegis features verify user-auth --by qa-agent

# List all features
aegis features list
```

## 8. Export & Backup (1 minute)

```bash
# Export all memories
aegis export -o backup.jsonl

# Export specific namespace
aegis export -n production -o prod-backup.jsonl

# Import from backup
aegis import backup.jsonl
```

## 9. View Statistics

```bash
# Namespace overview
aegis stats

# Filter by agent
aegis stats -a executor
```

---

## Using the Python SDK

All CLI commands have SDK equivalents:

```python
from aegis_memory import AegisClient

client = AegisClient(
    api_key="dev-key",
    base_url="http://localhost:8000"
)

# Add memory
result = client.add(
    content="User prefers dark mode",
    agent_id="assistant",
    scope="global"
)

# Query
memories = client.query(
    query="user preferences",
    agent_id="assistant",
    top_k=5
)

# Vote
client.vote(
    memory_id=memories[0].id,
    vote="helpful",
    voter_agent_id="assistant"
)

# Session progress
client.create_session(session_id="build-api", agent_id="coder")
client.update_session(
    session_id="build-api",
    completed_items=["auth", "routing"],
    in_progress_item="api-client"
)

# Playbook
strategies = client.query_playbook(
    query="pagination patterns",
    agent_id="executor",
    min_effectiveness=0.3
)
```

---

## What's Next?

- **[Framework Integrations](aegis_memory/integrations/)** — LangChain, CrewAI
- **[ACE Patterns Guide](docs/ACE-PATTERNS.md)** — Deep dive into self-improving agents
- **[Recipes](docs/Recipes/)** — 10 production-ready patterns
- **[Operations Guide](docs/OPERATIONS.md)** — Monitoring, backup, deployment

## Need Help?

- 📖 [Full Documentation](docs/)
- 💬 [GitHub Discussions](https://github.com/quantifylabs/aegis-memory/discussions)
- 🐛 [Report Issues](https://github.com/quantifylabs/aegis-memory/issues)
