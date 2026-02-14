# Aegis Memory -- Project Guide

## Architecture

Aegis Memory is a production-grade multi-agent memory layer (FastAPI + PostgreSQL/pgvector).

### Directory Structure

```
server/
  main.py                    # Legacy entry point (backward-compatible)
  api/
    app.py                   # Modular FastAPI entry point (v1.7.0+)
    dependencies/            # Shared FastAPI dependencies (auth, db, rate_limit)
    routers/                 # Focused routers (<300 lines each)
  domain/                    # Business logic layer (services, repositories, models)
    memory/, ace/, events/, eval/
  infra/                     # Infrastructure adapters
    db/, embeddings/, observability/, auth/, config.py
  auth.py                    # Token verification and auth policy
  config.py                  # Settings (Pydantic BaseSettings)
  database.py                # Async SQLAlchemy engine, sessions, init_db
  models.py                  # ORM models (Memory, VoteHistory, etc.)
  rate_limiter.py            # Rate limiting (in-memory + Redis)
  memory_repository.py       # Memory CRUD + semantic search
  ace_repository.py          # ACE operations (voting, delta, sessions, features)
  routes.py                  # Legacy memory routes
  routes_ace.py              # Legacy ACE routes
  routes_dashboard.py        # Dashboard stats routes
tests/
benchmarks/                  # Performance benchmark harness
alembic/                     # Database migrations
migrations/                  # Raw SQL migrations (legacy)
```

### Phase Status

| Phase | Version | Status | Description |
|-------|---------|--------|-------------|
| 1 | v1.4.0 | Complete | Security Foundations -- project-scoped API key auth |
| 2 | v1.5.0 | Complete | Schema Governance -- Alembic as canonical schema source |
| 3 | v1.6.0 | Complete | ACL Scalability -- normalized join table for shared agents |
| 4 | v1.7.0 | Complete | Module Decomposition -- api/domain/infra bounded contexts |
| 5 | v1.8.0 | Complete | Operational Hardening -- unified rate limiter, version sync, benchmarks |

## Key Conventions

- **Transaction boundaries**: Only `get_db()` dependency commits/rollbacks. Repositories use `flush()`, never `commit()`.
- **Version**: Read from `importlib.metadata.version("aegis-memory")`, never hardcode.
- **Auth**: `ENABLE_PROJECT_AUTH=false` (default) uses legacy single-key; `true` uses per-project keys.
- **Schema**: `AEGIS_ENV=development` uses `create_all()`; `production` requires Alembic.
- **ACLs**: Dual-write to both `shared_with_agents` JSON and `memory_shared_agents` join table; reads use join table.

## Commands

```bash
# Run server
cd server && uvicorn main:app --reload

# Run modular server
cd server && uvicorn api.app:modular_app --reload

# Run tests
pytest tests/ -v

# Lint
ruff check server/ tests/

# Database migrations
make db-upgrade     # Apply migrations
make db-downgrade   # Rollback one migration
make db-migrate     # Generate new migration
make db-check       # Verify migration round-trip

# Benchmarks
cd benchmarks && bash run_benchmark.sh
```

## Commit Conventions

Use conventional commits: `feat(scope):`, `fix(scope):`, `chore(scope):`, `test(scope):`, `docs:`, `refactor(scope):`
