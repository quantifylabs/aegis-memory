# Changelog

All notable changes to Aegis Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.9.11] - 2026-02-21

### Added

- **Interaction Events** — lightweight multi-agent collaboration history (Priority 3)
  - `interaction_events` table with temporal + causal chain support
  - `POST /interaction-events/` — create event (201); optional `embed=True` for semantic search
  - `GET /interaction-events/session/{session_id}` — session timeline ordered ASC
  - `GET /interaction-events/agent/{agent_id}` — agent history ordered DESC
  - `POST /interaction-events/search` — embed query → cosine similarity search
  - `GET /interaction-events/{event_id}` — event + full causal chain (root → leaf)
  - Two composite B-tree indexes: `(project_id, session_id, timestamp)` and `(project_id, agent_id, timestamp)`
  - Partial index on `parent_event_id` for causal chain traversal
  - HNSW index on `embedding` for vector search (pgvector >= 0.5.0, skips NULLs automatically)
  - `INTERACTION_CREATED = "interaction_created"` added to `MemoryEventType` enum (now 11 members)
  - **SDK methods** (sync + async): `record_interaction()`, `get_session_interactions()`, `get_agent_interactions()`, `search_interactions()`, `get_interaction_chain()`
  - **Alembic migration** `0005_interaction_events` (down_revision="0004")
  - **Test suite**: `tests/test_interaction_events.py` (~400 lines, 10 test classes)
  - **Docs**: `docs/guides/interaction-events.mdx`

## [1.9.1] - 2026-02-20

### Added

- **Formalized ACE Loop** -- full Generation -> Reflection -> Curation cycle as native memory operations
  - `ace_runs` table for tracking agent execution runs with outcomes
  - `POST /ace/run` -- start tracking an agent run
  - `POST /ace/run/{run_id}/complete` -- complete run with auto-feedback:
    - Auto-votes memories used (helpful on success, harmful on failure)
    - Auto-creates reflection memories on failure
    - Links run results to playbook entries
  - `GET /ace/run/{run_id}` -- retrieve run details
  - `POST /ace/playbook/agent` -- agent-specific playbook retrieval with optional task_type filter
  - `POST /ace/curate` -- trigger curation cycle (identify effective, flag ineffective, suggest consolidations)
- **SDK methods**: `start_run()`, `complete_run()`, `get_run()`, `get_playbook_for_agent()`, `curate()`
- **Alembic migration** `0004_ace_runs`
- **Test suite**: `tests/test_ace_loop.py`

### Changed

- Version bumped to `1.9.1`

## [1.9.0] - 2026-02-14

### Added

- **Typed Memory API** — 4 cognitive memory types inspired by research SOTA systems (MIRIX, G-Memory, BMAM):
  - `episodic` — Time-ordered interaction traces linked to sessions
  - `semantic` — Facts, preferences, knowledge linked to entities
  - `procedural` — Workflows, strategies, reusable patterns
  - `control` — Meta-rules, error patterns, constraints
- **7 new API endpoints** under `/memories/typed/`:
  - `POST /memories/typed/episodic` — Store episodic memory
  - `POST /memories/typed/semantic` — Store semantic memory
  - `POST /memories/typed/procedural` — Store procedural memory
  - `POST /memories/typed/control` — Store control memory
  - `POST /memories/typed/query` — Type-filtered semantic search
  - `GET /memories/typed/episodic/session/{session_id}` — Session timeline
  - `GET /memories/typed/semantic/entity/{entity_id}` — Entity facts
- **3 new indexed columns** on Memory table: `session_id`, `entity_id`, `sequence_number`
- **2 partial indexes**: `ix_memories_session`, `ix_memories_entity`
- **Alembic migration** `0003_typed_memory` (upgrade + downgrade)
- **Repository methods**: `get_session_timeline()`, `get_entity_facts()`
- **Test suite**: `tests/test_typed_memory.py`

### Changed

- `MemoryOut` response model extended with `memory_type`, `session_id`, `entity_id`, `sequence_number` fields (both modular and legacy routes)
- `MemoryQuery` now accepts optional `memory_types` filter list
- `memory_type` column widened from `String(16)` to `String(32)` for extensibility
- Version bumped to `1.9.0`

## [1.8.0] - 2026-02-14

### Added

- **`RateLimiterProtocol`** (`runtime_checkable`) -- shared interface for all rate limiter implementations with `check()` and `get_remaining()` methods
- **`get_remaining()`** on `RedisRateLimiter` -- synchronous approximation + async-precise variant (`get_remaining_async()`)
- **`create_rate_limiter()` factory** -- auto-detects Redis from `REDIS_URL`, falls back to in-memory
- **`X-RateLimit-*` response headers** on every API response:
  - `X-RateLimit-Limit-Minute`, `X-RateLimit-Remaining-Minute`
  - `X-RateLimit-Limit-Hour`, `X-RateLimit-Remaining-Hour`
- **Reproducible benchmark harness** (`benchmarks/`):
  - `generate_dataset.py` -- seeded JSONL dataset generator
  - `query_workload.py` -- async workload runner with latency percentiles
  - `run_benchmark.sh` -- end-to-end benchmark script
  - `machine_profile.py` -- capture hardware profile for reproducibility
- Rate limiter test suite (`tests/test_rate_limiter_unified.py`) -- protocol conformance, factory, headers
- Version test suite (`tests/test_version.py`) -- checks no hardcoded version strings remain
- **Baseline benchmark results** (`benchmarks/results.json`) -- 1060 ops, 0% error rate on 8 vCPU / 7.6 GB RAM; concurrent writes at 85 ops/s (p50=100ms), concurrent queries at 18.6 ops/s (p50=413ms)
- README Performance section updated with actual benchmark data, replacing provisional numbers

### Changed

- **Version synchronized from `pyproject.toml`** via `importlib.metadata.version("aegis-memory")` with `"dev"` fallback
- Removed all hardcoded `"1.2.0"` version strings from `main.py` and `api/app.py`

## [1.7.0] - 2026-02-14

### Added

- **Modular application structure** -- decomposed into `api/`, `domain/`, `infra/` bounded contexts
  - `api/app.py` -- new modular FastAPI entry point via `create_app()`
  - `api/routers/` -- 9 focused routers (memories, handoffs, ace_votes, ace_delta, ace_reflections, ace_progress, ace_features, ace_eval, dashboard), each under 300 lines
  - `api/dependencies/` -- shared auth, rate_limit, and database dependencies
- **Domain layer** (`domain/`) with service, repository, and model modules for memory, ACE, events, and eval
- **Infrastructure layer** (`infra/`) with adapters for DB, embeddings, observability, auth, and config
- `KeyStore` class (`infra/auth/key_store.py`) for API key management

### Changed

- **Unified transaction boundaries** -- all `await db.commit()` calls removed from `ace_repository.py`; commit/rollback now handled exclusively by the `get_db()` FastAPI dependency
- Original `main.py`, `routes.py`, `routes_ace.py` retained as backward-compatible entry points
- `api/app.py` version bumped to `1.7.0`

## [1.6.0] - 2026-02-14

### Added

- **Normalized `memory_shared_agents` join table** for scalable ACL lookups
  - `MemorySharedAgent` ORM model with composite PK (`memory_id`, `shared_agent_id`)
  - Indexes: `ix_msa_memory_agent` (unique), `ix_msa_query` (project + namespace + agent)
  - Alembic migration `0002_memory_shared_agents`
- **Dual-write** on `add()` and `add_batch()` -- populates both JSON and join table
- **Backfill script** (`server/backfill_acl.py`) -- idempotent migration from JSON to join table
- ACL test suite (`tests/test_acl.py`) covering dual-write, join-based read, backfill, cascade

### Changed

- `semantic_search` ACL now uses indexed join-table subquery instead of JSONB `@>` containment
- `query_playbook` ACL switched from JSONB containment to join-table subquery
- `shared_with_agents` JSON column retained for backward compatibility but no longer read for ACL decisions

## [1.5.0] - 2026-02-14

### Added

- **Alembic as canonical schema source** -- deterministic schema lifecycle
  - `alembic.ini`, `alembic/env.py` with async migration support
  - Baseline migration `0001_baseline.py` capturing full v1.3.0+ schema
  - `script.py.mako` template for new migrations
- `Makefile` with `db-upgrade`, `db-downgrade`, `db-migrate`, `db-check` targets
- CI workflow `.github/workflows/migration-check.yml` for migration round-trip testing
- Migration test suite (`tests/test_migrations.py`)

### Changed

- `init_db()` is now environment-aware:
  - `AEGIS_ENV=development` (default): uses `create_all()` as before
  - `AEGIS_ENV=production`: verifies `alembic_version` table exists; fails fast if not
- `alembic>=1.13.0` added to `[server]` dependencies in `pyproject.toml`

### Removed

- `INIT_SQL` and `MIGRATION_SQL_V1_1` raw SQL constants from `models.py` (schema now managed by Alembic)

## [1.4.0] - 2026-02-14

### Added

- **Project-scoped API key authentication** behind `ENABLE_PROJECT_AUTH` feature flag
  - `Project` and `ApiKey` ORM models for multi-tenant isolation
  - `TokenVerifier` for bearer token validation (legacy + project key modes)
  - `AuthPolicy` with `can_write_memory()` and `can_query_memory()` checks
  - SHA-256 key hashing for secure storage
  - Key expiration and active/inactive status support
  - Audit logging for every authentication decision
- `ENABLE_PROJECT_AUTH` config flag (default: `false`) -- zero behavior change when off
- `AEGIS_ENV` config flag (`development` | `production`) for environment-aware behavior
- Migration `004_project_auth.sql` with `projects` and `api_keys` tables + default project seed
- Auth test suite (`tests/test_auth.py`) covering legacy fallback, project keys, policy, audit

### Changed

- `get_project_id` dependency extracted from `routes.py` into `server/auth.py`
- `routes.py` and `routes_ace.py` import auth from centralized module

### Added (Unreleased)

- CLI onboarding and productivity commands:
  - `aegis init` top-level setup wizard with lightweight framework detection (LangChain/CrewAI) and config bootstrap
  - `aegis new customer-support` starter template scaffold
  - `aegis explore` interactive memory browser for terminal workflows
- New observability guide with architecture and phased plan for memory analytics, Prometheus expansion, memory timeline events, effectiveness dashboards, and Langfuse/LangSmith exports (`docs/guides/observability.mdx`).

### Changed

- CLI command module wiring updated so top-level `init`, `new`, and `explore` commands load correctly.
- CLI error utilities now include `set_debug_mode()` used by the Typer entrypoint.
- CLI reference docs now document `aegis init`, `aegis new`, and `aegis explore`.
- README now highlights observability surfaces (metrics, evaluation, dashboard APIs) and links directly to the new observability guide.


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