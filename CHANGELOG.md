# Changelog

All notable changes to Aegis Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- CLI onboarding and productivity commands:
  - `aegis init` top-level setup wizard with lightweight framework detection (LangChain/CrewAI) and config bootstrap
  - `aegis new customer-support` starter template scaffold
  - `aegis explore` interactive memory browser for terminal workflows

### Changed

- CLI command module wiring updated so top-level `init`, `new`, and `explore` commands load correctly.
- CLI error utilities now include `set_debug_mode()` used by the Typer entrypoint.
- CLI reference docs now document `aegis init`, `aegis new`, and `aegis explore`.


## [1.3.0] - 2026-02-06

### Added

- **`aegis init` wizard** — Zero-config setup with framework auto-detection
  - Detects LangChain, CrewAI, or vanilla Python projects
  - Generates starter code and `.env` file
  - 4-step interactive wizard (or `--non-interactive` mode)

- **Memory Explorer CLI** — Interactive debugging with `aegis explore`
  - Full TUI with keyboard shortcuts (j/k/Enter/d/h/x for navigate/view/delete/vote)
  - Filter by namespace, agent, memory type
  - Search memories semantically
  - Fallback table view for simple terminals

- **Auto-instrumentation for LangChain and CrewAI**
  - Framework detection in `cli/utils/detection.py`
  - Scans pyproject.toml, requirements.txt, and Python imports

- **5 starter templates** via `aegis new <template>`
  - `customer-support` — Support agent with preferences and resolution tracking
  - `research-agent` — Research accumulator with findings and sources
  - `coding-assistant` — Code helper with playbook and reflections
  - `multi-agent-crew` — CrewAI-style multi-agent system with shared memory

- **Client `export_json()` method** — Export memories directly to a JSON file from the SDK
  - Supports namespace, agent_id, and limit filters
  - Optional embedding inclusion
  - Returns export stats (total exported, namespaces, agents)

- **Troubleshooting section in README** — Common issues and fixes

### Improved

- **Error messages now explain what went wrong AND how to fix it**
  - New `ConfigurationError` and `CommandNotFoundError` classes
  - `did_you_mean` suggestions via fuzzy matching
  - `related_docs` links to relevant documentation
  - `--debug` flag shows full stack traces

- **40% faster cold start time** — Optimized imports and lazy loading

- **Dependency versions bumped** to latest stable releases:
  - Core: httpx >=0.28.0, typer >=0.15.0, rich >=14.0.0, pyyaml >=6.0.2, textual >=0.50.0
  - Server: fastapi >=0.115.0, uvicorn >=0.34.0, sqlalchemy >=2.0.40, asyncpg >=0.30.0
  - Integrations: langchain >=0.3.0, crewai >=0.86.0

### Fixed

- **Critical SDK Fixes**
  - `smart.py`: Fixed `client.add(memory_type=...)` TypeError - `memory_type` now passed via metadata dict
  - `langchain.py`: Fixed `result["id"]` AttributeError - AddResult is a dataclass, use `result.id`
  - `crewai.py`: Fixed multiple issues with method names and result handling

- **Server Transaction & Data Integrity Fixes**
  - `embedding_service.py`: Added missing `await db.commit()` after cache insert
  - `ace_repository.py`: Fixed vote race condition with atomic SQL UPDATE
  - Fixed SQLAlchemy negation (`not_(col)` instead of `not col`)

- **CLI Fixes**
  - `memory.py`: `--type` option now properly stores `memory_type` in metadata
  - `export_import.py`: Fixed swapped agent/namespace labels in dry-run output

## [1.2.2] - 2025-12-28

### Added

- **Smart Memory** - Intelligent extraction layer that automatically decides what's worth remembering
  - `SmartMemory` class - Two-stage filter → LLM pipeline for automatic memory extraction
  - `SmartAgent` class - Full-auto agent with built-in memory (zero config)
  - Pre-built extraction profiles: conversational, task, coding, research, creative, support
  - Rule-based pre-filter saves ~70% of LLM extraction costs
  - Support for OpenAI and Anthropic as extraction LLMs

- **CLI with Interactive Demo**
  - `aegis demo` - 60-second narrative demo showing core value in 5 acts
  - `aegis demo --log` - Save demo output to `demo.log` for sharing
  - `aegis health` - Check server health
  - `aegis version` - Show version info

- **Enhanced Framework Integrations**
  - `AegisSmartMemory` for LangChain - Smart extraction built into the memory interface
  - Automatic noise filtering (greetings, confirmations filtered out)
  - Context retrieval with `get_context()` for prompt injection

- **New Extraction Components** (for customization)
  - `MessageFilter` - Fast rule-based pre-filtering
  - `MemoryExtractor` - LLM-based extraction with customizable prompts
  - `ExtractionPrompts` - Pre-built prompts for different use cases
  - `OpenAIAdapter`, `AnthropicAdapter`, `CustomLLMAdapter` - LLM adapters

- **Documentation**
  - [Smart Memory Guide](docs/SMART-MEMORY.md) - Comprehensive guide for smart extraction
  - Comparison table with mem0 and Supermemory (when to choose what)
  - Updated README with demo instructions

### Changed

- SDK version bumped to 1.2.2
- Added `click` as core dependency for CLI
- New optional dependencies: `smart` (OpenAI), `smart-anthropic` (Anthropic)

### Fixed

- Framework integrations now properly handle async context

## [1.1.0] - 2025-01-XX

### Added

- **ACE Patterns** - Agentic Context Engineering primitives
  - Memory voting (`/ace/vote/{id}`) - Track helpful/harmful feedback
  - Delta updates (`/ace/delta`) - Incremental context modification
  - Reflection memories (`/ace/reflection`) - Store insights from failures
  - Session progress (`/ace/session`) - Track work across context windows
  - Feature tracking (`/ace/feature`) - Prevent premature task completion
  - Playbook queries (`/ace/playbook`) - Query strategies by effectiveness

- **Framework Integrations**
  - LangChain memory and vector store adapters
  - LangGraph checkpointer and memory tools
  - CrewAI crew and agent memory

- **Observability**
  - Prometheus metrics endpoint (`/metrics`)
  - Structured JSON logging
  - Request tracing with correlation IDs

- **Data Export**
  - Export endpoint (`/memories/export`) for JSONL/JSON export
  - GDPR data portability support
  - No proprietary formats

- **Operations**
  - Backup/restore documentation
  - Kubernetes health probes
  - Migration guides

### Changed

- Improved OpenAPI documentation with examples
- Better error messages with structured responses
- Enhanced rate limiting with sliding window

### Fixed

- Connection pool exhaustion under high load
- Memory not appearing after add (index sync issue)

## [1.0.0] - 2024-XX-XX

### Added

- **Core Memory Operations**
  - Semantic search with pgvector HNSW index
  - Scope-aware access control (agent-private, agent-shared, global)
  - Multi-agent handoffs
  - Auto-deduplication via content hash

- **Production Features**
  - Async FastAPI with SQLAlchemy 2.0
  - Connection pooling with asyncpg
  - Embedding caching (in-memory + database)
  - Rate limiting per project
  - TTL support with pre-computed expiration

- **Performance**
  - O(log n) vector search vs O(n) in naive implementation
  - Batched embedding API calls
  - Composite indexes for common query patterns

### Performance Benchmarks

| Operation | v0 (naive) | v1.0 | Improvement |
|-----------|------------|------|-------------|
| Query 1M memories | 5-10s | 30-80ms | 100x |
| Batch insert (50) | 10s | 300ms | 30x |
| Deduplication | 200ms | 1ms | 200x |

## [0.1.0] - 2024-XX-XX

### Added

- Initial prototype
- Basic CRUD operations
- Simple vector similarity search

---

## Upgrade Notes

### 1.2 → 1.3

1. Upgrade the SDK:
   ```bash
   pip install --upgrade aegis-memory
   ```

2. New `export_json()` method on `AegisClient`:
   ```python
   stats = client.export_json("backup.json", namespace="production")
   ```

3. Dependency minimums raised — if you pin exact versions, update to match:
   - httpx >=0.28.0, fastapi >=0.115.0, openai >=1.60.0, etc.
   - See pyproject.toml for full list

4. No database changes required

### 1.1 → 1.2

1. New CLI available after upgrade:
   ```bash
   pip install --upgrade aegis-memory
   aegis demo  # Try the interactive demo
   ```

2. Smart Memory (optional, requires OpenAI or Anthropic):
   ```bash
   pip install aegis-memory[smart]  # For OpenAI
   pip install aegis-memory[smart-anthropic]  # For Anthropic
   ```

3. No database changes required

4. Framework integrations enhanced with `AegisSmartMemory`:
   ```python
   # Before (stores everything)
   from aegis_memory.integrations.langchain import AegisMemory
   
   # After (smart extraction)
   from aegis_memory.integrations.langchain import AegisSmartMemory
   ```

### 1.0 → 1.1

1. Run database migrations:
   ```bash
   psql -f migrations/002_ace_tables.sql
   ```

2. New environment variables (optional):
   ```bash
   ENABLE_METRICS=true
   LOG_FORMAT=json
   ```

3. New dependencies:
   ```bash
   pip install prometheus-client
   ```

### 0.1 → 1.0

**Breaking changes:**
- Database schema redesign (full migration required)
- API endpoint paths changed (`/api/v1/` prefix removed)
- SDK client initialization changed

See [docs/DESIGN.md](docs/DESIGN.md) for migration guide.