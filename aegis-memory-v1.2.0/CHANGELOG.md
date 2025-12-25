# Changelog

All notable changes to Aegis Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2025-12-20

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

## [1.0.0] - 2024-11-01

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

## [0.1.0] - 2024-09-01

### Added

- Initial prototype
- Basic CRUD operations
- Simple vector similarity search

---

## Upgrade Notes

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
