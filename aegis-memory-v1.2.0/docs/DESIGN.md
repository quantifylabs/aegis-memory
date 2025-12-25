# Aegis Memory Design Document

This document explains the architectural decisions behind Aegis Memory and how to tune it for production workloads.

## Performance Characteristics

| Operation | Latency | Complexity | Notes |
|-----------|---------|------------|-------|
| Vector Search | 30-80ms | O(log n) | HNSW index |
| Batch Insert (50 items) | ~300ms | O(n) | Single API call |
| Deduplication | <1ms | O(1) | Hash lookup |
| Cross-agent query | 50-100ms | O(log n) | With ACL filtering |

---

## Vector Search with pgvector HNSW

### Why HNSW?

Aegis uses PostgreSQL with pgvector's HNSW (Hierarchical Navigable Small World) index for approximate nearest neighbor search. This provides O(log n) query performance compared to O(n) for brute-force similarity search.

At 1 million memories, HNSW delivers 30-80ms queries vs 5-10 seconds for naive approaches.

### How It Works

```python
# Vector search pushes similarity computation to the database
distance_expr = Memory.embedding.cosine_distance(query_embedding)
stmt = (
    select(Memory, distance_expr.label("distance"))
    .where(and_(*conditions))  # Filters apply BEFORE ANN search
    .order_by(distance_expr)   # Uses HNSW index
    .limit(top_k)
)
```

### Index Configuration

```sql
CREATE INDEX ix_memories_embedding_hnsw 
ON memories USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Query-time parameter (higher = more accurate, slower)
SET hnsw.ef_search = 100;
```

**Tuning Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `m` | 16 | Connections per node. Higher = better recall, more memory. Range: 16-64 |
| `ef_construction` | 64 | Build-time search width. Higher = better index quality, slower builds |
| `ef_search` | 100 | Query-time search width. Tune per-query for accuracy/speed tradeoff |

**Recommendations:**
- Start with defaults for <100k memories
- Increase `m` to 32 and `ef_construction` to 128 for >1M memories
- Tune `ef_search` based on recall requirements (100-200 for most use cases)

---

## Embedding Service

### Batching Strategy

Aegis batches embedding requests to minimize API calls:

```python
# All texts embedded in a single API call
texts = [item.content for item in body.items]
embeddings = await embed_service.embed_batch(texts)

# OpenAI supports up to 2048 texts per batch
response = await client.embeddings.create(
    model="text-embedding-3-small",
    input=texts,
)
```

### Caching Architecture

Two-tier caching reduces redundant embedding API calls:

```
Request → In-Memory LRU (10k items) → DB Cache → Embedding API
              ↓ hit                      ↓ hit        ↓ miss
           Return                     Return      Embed + Cache
```

Cache key is based on content hash:

```python
hash_key = sha256(text.strip().lower())
```

**Cache hit rates of 80%+ are typical** for applications with repeated or similar content.

---

## Connection Pooling

### Configuration

Aegis uses SQLAlchemy's async engine with connection pooling:

```python
engine = create_async_engine(
    url,
    pool_size=20,        # Persistent connections
    max_overflow=10,     # Burst capacity
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,   # Refresh connections after 1 hour
)
```

### Sizing Guidelines

- `pool_size` × workers < PostgreSQL `max_connections`
- Example: 2 uvicorn workers × 20 pool = 40 connections
- Leave headroom for migrations, monitoring, and admin tools
- Default PostgreSQL `max_connections` is 100

---

## Deduplication

Aegis uses content-hash based deduplication with a B-tree index for O(1) lookups:

```python
content_hash = sha256(text.strip().lower())
stmt = select(Memory).where(Memory.content_hash == content_hash)
existing = await db.execute(stmt)
```

This is significantly faster than semantic similarity-based deduplication, which requires embedding generation and vector comparison.

---

## Multi-Agent Access Control

### Scope-Aware Indexing

Composite indexes enable efficient cross-agent queries:

```sql
-- Project + namespace + scope (for cross-agent queries)
CREATE INDEX ix_memories_project_ns_scope 
ON memories (project_id, namespace, scope);

-- GIN index for shared_with_agents array
CREATE INDEX ix_memories_shared_agents 
ON memories USING gin (shared_with_agents);
```

### Access Control Query Pattern

Access control is expressed as WHERE clauses that the query planner can optimize:

```python
scope_filter = or_(
    Memory.scope == 'global',
    and_(
        Memory.scope == 'agent-private',
        Memory.agent_id == requesting_agent_id
    ),
    and_(
        Memory.scope == 'agent-shared',
        or_(
            Memory.agent_id == requesting_agent_id,
            Memory.shared_with_agents.contains([requesting_agent_id])
        )
    ),
)
```

---

## Horizontal Scaling

### Read Replica Pattern

For read-heavy workloads, configure a read replica:

```
┌─────────────┐     ┌─────────────┐
│   Writes    │     │   Reads     │
│  (Primary)  │────▶│  (Replica)  │
└─────────────┘     └─────────────┘
       │                  │
       ▼                  ▼
   /memories/add      /memories/query
   /memories/delete   /memories/query_cross_agent
```

Configuration:

```env
DATABASE_URL=postgresql://primary:5432/aegis
DATABASE_READ_REPLICA_URL=postgresql://replica:5432/aegis
```

### Multi-Region Deployment

```
┌──────────────────────────────────────────────────────┐
│                    Load Balancer                      │
└──────────────────────────────────────────────────────┘
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ US-East │      │ EU-West │      │ APAC    │
    │ Aegis   │      │ Aegis   │      │ Aegis   │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ US-East │◀────▶│ EU-West │◀────▶│ APAC    │
    │ Primary │      │ Replica │      │ Replica │
    └─────────┘      └─────────┘      └─────────┘
```

### Partitioning (>10M memories)

For very large deployments, partition by project_id:

```sql
CREATE TABLE memories (
    id VARCHAR(32),
    project_id VARCHAR(64),
    ...
) PARTITION BY HASH (project_id);

CREATE TABLE memories_p0 PARTITION OF memories
    FOR VALUES WITH (MODULUS 16, REMAINDER 0);
-- Create 16 partitions total
```

---

## Rate Limiting

### Per-Project Limits

Default configuration:

```python
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10
```

### Distributed Rate Limiting

For multi-instance deployments, use Redis:

```python
# Redis sorted set sliding window
pipe.zadd(f"ratelimit:minute:{project_id}", {timestamp: timestamp})
pipe.zremrangebyscore(key, 0, now - 60)
count = pipe.zcard(key)
```

---

## Deployment Configuration

### Environment Variables

```env
# Required
DATABASE_URL=postgresql://user:pass@host:5432/aegis
OPENAI_API_KEY=sk-...
AEGIS_API_KEY=your-production-key

# Recommended
DATABASE_READ_REPLICA_URL=postgresql://user:pass@replica:5432/aegis
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
CORS_ORIGINS=https://your-app.com
```

### Docker Compose (Production)

```yaml
version: '3.9'

services:
  aegis:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '2'
          memory: 4G

  postgres:
    image: pgvector/pgvector:pg16
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: aegis
      POSTGRES_USER: aegis
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    command:
      - "postgres"
      - "-c"
      - "max_connections=200"
      - "-c"
      - "shared_buffers=1GB"
      - "-c"
      - "work_mem=256MB"
```

### Kubernetes (High Scale)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aegis
spec:
  replicas: 3
  selector:
    matchLabels:
      app: aegis
  template:
    spec:
      containers:
      - name: aegis
        image: aegis:latest
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: aegis
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: aegis
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## Monitoring

### Key Metrics to Track

1. **Vector search latency** (p50, p95, p99)
2. **Embedding cache hit rate** (target: >80%)
3. **Database connection pool utilization**
4. **Rate limit rejections per project**
5. **Memory count per project/agent**

### Health Endpoints

- `GET /health` — Overall system health
- `GET /ready` — Readiness probe (includes DB connectivity)

---

## ACE Pattern Implementation

Version 1.1 adds ACE (Agentic Context Engineering) features based on research from:
- [ACE Paper](https://arxiv.org/pdf/2510.04618) (Stanford/SambaNova)
- [Anthropic's Long-Running Agent Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

### Design Rationale

Both papers address the same problem: agents working across multiple context windows lose track of prior work. Aegis implements their solutions as memory primitives:

| Research Insight | Aegis Implementation |
|-----------------|---------------------|
| Context collapse prevention | Incremental delta updates, not full rewrites |
| Brevity bias avoidance | Memory types preserve detailed strategies |
| Session state tracking | SessionProgress table + endpoints |
| Feature verification | FeatureTracker prevents premature completion |
| Self-improvement via feedback | VoteHistory enables playbook curation |

### Memory Types

```python
class MemoryType(str, Enum):
    STANDARD = "standard"     # Regular memories
    REFLECTION = "reflection" # Insights from failures
    PROGRESS = "progress"     # Session progress tracking
    FEATURE = "feature"       # Feature status tracking
    STRATEGY = "strategy"     # Reusable strategies
```

### Effectiveness Scoring

Memories are ranked by accumulated votes:

```python
effectiveness = (helpful - harmful) / (helpful + harmful + 1)
# Range: -1.0 to 1.0
```

Playbook queries filter by minimum effectiveness, ensuring frequently-harmful memories are excluded from agent context.

### ACE Database Schema

```sql
-- Vote history for audit and analysis
CREATE TABLE vote_history (
    id VARCHAR(32) PRIMARY KEY,
    memory_id VARCHAR(32) REFERENCES memories(id),
    voter_agent_id VARCHAR(64),
    vote VARCHAR(8),  -- 'helpful' or 'harmful'
    context TEXT,
    task_id VARCHAR(64),
    created_at TIMESTAMPTZ
);

-- Session progress tracking
CREATE TABLE session_progress (
    session_id VARCHAR(64) UNIQUE,
    completed_items JSONB,
    in_progress_item VARCHAR(256),
    next_items JSONB,
    blocked_items JSONB,
    summary TEXT,
    status VARCHAR(16)  -- active, paused, completed, failed
);

-- Feature tracking (prevents premature completion)
CREATE TABLE feature_tracker (
    feature_id VARCHAR(128),
    description TEXT,
    test_steps JSONB,
    status VARCHAR(16),  -- not_started, in_progress, complete, failed
    passes BOOLEAN,
    verified_by VARCHAR(64)
);
```

### ACE Performance Impact

ACE features add minimal overhead:

| Operation | Latency Impact |
|-----------|---------------|
| Memory with votes | +0ms (same table) |
| Playbook query | +5ms (effectiveness filter) |
| Delta update (batch) | ~50ms per operation |
| Session get/update | ~5ms (simple CRUD) |
| Feature list | ~10ms (indexed query) |

---

## Database Schema

### Core Tables

```sql
CREATE TABLE memories (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    namespace VARCHAR(64) DEFAULT 'default',
    agent_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64),
    embedding vector(1536),
    scope VARCHAR(16) DEFAULT 'agent-private',
    shared_with_agents JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    memory_type VARCHAR(16) DEFAULT 'standard',
    is_deprecated BOOLEAN DEFAULT false,
    helpful_votes INTEGER DEFAULT 0,
    harmful_votes INTEGER DEFAULT 0,
    ttl_seconds INTEGER,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX ix_memories_embedding_hnsw 
ON memories USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX ix_memories_project_ns_scope 
ON memories (project_id, namespace, scope);

CREATE INDEX ix_memories_content_hash 
ON memories (content_hash);

CREATE INDEX ix_memories_shared_agents 
ON memories USING gin (shared_with_agents);

CREATE INDEX ix_memories_expires 
ON memories (expires_at) WHERE expires_at IS NOT NULL;
```

---

## Further Reading

- [QUICKSTART.md](../QUICKSTART.md) — Get running in 15 minutes
- [ACE-PATTERNS.md](ACE-PATTERNS.md) — Self-improving agent patterns
- [OPERATIONS.md](OPERATIONS.md) — Backup, monitoring, upgrades
