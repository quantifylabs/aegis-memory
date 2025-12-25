# Aegis Memory Operations Guide

This guide covers production operations: backup, restore, export, monitoring, and upgrades.

## Table of Contents

1. [Backup & Restore](#backup--restore)
2. [Data Export](#data-export)
3. [Monitoring](#monitoring)
4. [Upgrades & Migrations](#upgrades--migrations)
5. [Troubleshooting](#troubleshooting)

---

## Backup & Restore

### PostgreSQL Backup

Aegis Memory uses PostgreSQL with pgvector. Use standard PostgreSQL backup tools.

#### Option 1: pg_dump (Recommended for < 100GB)

```bash
# Full backup
pg_dump -h localhost -U aegis -d aegis -F c -f aegis_backup_$(date +%Y%m%d).dump

# With compression
pg_dump -h localhost -U aegis -d aegis -F c -Z 9 -f aegis_backup_$(date +%Y%m%d).dump.gz

# Backup specific tables only
pg_dump -h localhost -U aegis -d aegis -t memories -t vote_history -F c -f aegis_memories_backup.dump
```

#### Option 2: pg_basebackup (For larger databases)

```bash
# Base backup for point-in-time recovery
pg_basebackup -h localhost -U aegis -D /backups/aegis_base -Fp -Xs -P
```

#### Automated Backup Script

```bash
#!/bin/bash
# /usr/local/bin/aegis-backup.sh

BACKUP_DIR="/backups/aegis"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup
pg_dump -h localhost -U aegis -d aegis -F c -Z 6 \
  -f "${BACKUP_DIR}/aegis_${DATE}.dump"

# Upload to S3 (optional)
aws s3 cp "${BACKUP_DIR}/aegis_${DATE}.dump" \
  "s3://your-bucket/aegis-backups/aegis_${DATE}.dump"

# Clean old backups
find ${BACKUP_DIR} -name "aegis_*.dump" -mtime +${RETENTION_DAYS} -delete

echo "Backup completed: aegis_${DATE}.dump"
```

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/aegis-backup.sh >> /var/log/aegis-backup.log 2>&1
```

### Restore

```bash
# Restore from dump
pg_restore -h localhost -U aegis -d aegis -c aegis_backup.dump

# Restore to a new database
createdb aegis_restored
pg_restore -h localhost -U aegis -d aegis_restored aegis_backup.dump
```

### Kubernetes Backup with Velero

```yaml
# velero-schedule.yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: aegis-daily-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"
  template:
    includedNamespaces:
      - aegis
    includedResources:
      - persistentvolumeclaims
      - persistentvolumes
    storageLocation: default
    ttl: 720h  # 30 days
```

---

## Data Export

### Export via API

Aegis provides a data export endpoint for GDPR compliance and data portability.

```bash
# Export all memories for a project
curl -X POST http://localhost:8000/memories/export \
  -H "Authorization: Bearer your-key" \
  -H "Content-Type: application/json" \
  -d '{"format": "jsonl"}' \
  -o memories_export.jsonl

# Export with filters
curl -X POST http://localhost:8000/memories/export \
  -H "Authorization: Bearer your-key" \
  -d '{
    "namespace": "production",
    "agent_id": "assistant",
    "format": "jsonl"
  }' \
  -o filtered_export.jsonl
```

### Export Format (JSONL)

```jsonl
{"id":"abc123","content":"Memory content","agent_id":"assistant","namespace":"default","scope":"agent-private","metadata":{},"created_at":"2024-01-15T10:30:00Z"}
{"id":"def456","content":"Another memory","agent_id":"planner","namespace":"default","scope":"global","metadata":{"type":"reflection"},"created_at":"2024-01-15T11:00:00Z"}
```

### Direct SQL Export

```sql
-- Export to CSV
COPY (
  SELECT id, content, agent_id, namespace, scope, 
         metadata::text, created_at, updated_at
  FROM memories 
  WHERE project_id = 'your-project'
  ORDER BY created_at
) TO '/tmp/memories_export.csv' WITH CSV HEADER;

-- Export to JSON
COPY (
  SELECT json_agg(row_to_json(m))
  FROM (
    SELECT id, content, agent_id, namespace, scope, metadata, created_at
    FROM memories
    WHERE project_id = 'your-project'
  ) m
) TO '/tmp/memories_export.json';
```

### Import Data

```bash
# Import from JSONL
curl -X POST http://localhost:8000/memories/import \
  -H "Authorization: Bearer your-key" \
  -H "Content-Type: application/json" \
  -d @memories_export.jsonl
```

---

## Monitoring

### Prometheus Metrics

Aegis exposes Prometheus metrics at `/metrics`:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'aegis-memory'
    static_configs:
      - targets: ['aegis:8000']
    metrics_path: /metrics
    scrape_interval: 15s
```

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `aegis_http_requests_total` | Counter | Total HTTP requests |
| `aegis_http_request_duration_seconds` | Histogram | Request latency |
| `aegis_memory_operations_total` | Counter | Memory operations (add, query, delete) |
| `aegis_memory_operation_duration_seconds` | Histogram | Operation latency |
| `aegis_embedding_cache_hits_total` | Counter | Embedding cache hits |
| `aegis_embedding_cache_misses_total` | Counter | Embedding cache misses |
| `aegis_db_pool_size` | Gauge | DB connection pool size |
| `aegis_db_pool_checked_out` | Gauge | DB connections in use |
| `aegis_ace_votes_total` | Counter | ACE votes by type |

### Grafana Dashboard

Key panels:
- Request rate and latency
- Memory operation throughput
- Embedding cache hit rate
- Database connection pool health
- ACE pattern usage

### Alerting Rules

```yaml
# prometheus-alerts.yml
groups:
  - name: aegis
    rules:
      - alert: AegisHighLatency
        expr: histogram_quantile(0.95, aegis_http_request_duration_seconds_bucket) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"
          
      - alert: AegisErrorRate
        expr: rate(aegis_http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate"
          
      - alert: AegisDBPoolExhausted
        expr: aegis_db_pool_checked_out / aegis_db_pool_size > 0.9
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Database connection pool nearly exhausted"
```

### Health Checks

```bash
# Liveness probe
curl http://localhost:8000/health
# {"status": "healthy"}

# Readiness probe (includes DB check)
curl http://localhost:8000/ready
# {"status": "ready", "database": "connected", "embedding_service": "healthy"}
```

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## Upgrades & Migrations

### Version Compatibility

| Aegis Version | PostgreSQL | pgvector | Breaking Changes |
|---------------|------------|----------|------------------|
| 1.0.x | 14+ | 0.5+ | - |
| 1.1.x | 15+ | 0.6+ | ACE tables added |
| 2.0.x | 16+ | 0.7+ | Schema changes (migration required) |

### Upgrade Process

1. **Backup first**
   ```bash
   pg_dump -h localhost -U aegis -d aegis -F c -f pre_upgrade_backup.dump
   ```

2. **Check migration scripts**
   ```bash
   ls migrations/
   # 001_initial.sql
   # 002_ace_tables.sql
   # 003_...
   ```

3. **Run migrations**
   ```bash
   # Using alembic
   alembic upgrade head
   
   # Or manually
   psql -h localhost -U aegis -d aegis -f migrations/002_ace_tables.sql
   ```

4. **Deploy new version**
   ```bash
   # Kubernetes rolling update
   kubectl set image deployment/aegis aegis=aegis-memory:1.1.0
   
   # Docker Compose
   docker-compose pull
   docker-compose up -d
   ```

5. **Verify**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/ready
   ```

### Rollback

```bash
# Kubernetes
kubectl rollout undo deployment/aegis

# Docker Compose
docker-compose down
docker-compose up -d aegis:1.0.0  # Previous version

# Database (if needed)
pg_restore -h localhost -U aegis -d aegis -c pre_upgrade_backup.dump
```

### Migration: v1.0 → v1.1 (ACE Tables)

```sql
-- migrations/002_ace_tables.sql

-- Add new columns to memories table
ALTER TABLE memories ADD COLUMN IF NOT EXISTS memory_type VARCHAR(16) DEFAULT 'standard';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_deprecated BOOLEAN DEFAULT false;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS bullet_helpful INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS bullet_harmful INTEGER DEFAULT 0;

-- Create vote_history table
CREATE TABLE IF NOT EXISTS vote_history (
    id VARCHAR(32) PRIMARY KEY,
    memory_id VARCHAR(32) REFERENCES memories(id) ON DELETE CASCADE,
    project_id VARCHAR(64) NOT NULL,
    voter_agent_id VARCHAR(64) NOT NULL,
    vote VARCHAR(8) NOT NULL,
    context TEXT,
    task_id VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create session_progress table
CREATE TABLE IF NOT EXISTS session_progress (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    agent_id VARCHAR(64),
    status VARCHAR(16) DEFAULT 'active',
    completed_items JSONB DEFAULT '[]',
    in_progress_item VARCHAR(256),
    next_items JSONB DEFAULT '[]',
    blocked_items JSONB DEFAULT '[]',
    summary TEXT,
    last_action TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create feature_tracker table
CREATE TABLE IF NOT EXISTS feature_tracker (
    id VARCHAR(32) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    feature_id VARCHAR(128) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(16) DEFAULT 'not_started',
    passes BOOLEAN DEFAULT false,
    test_steps JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_memories_type ON memories (project_id, memory_type);
CREATE INDEX IF NOT EXISTS ix_votes_memory ON vote_history (memory_id);
CREATE INDEX IF NOT EXISTS ix_session_project ON session_progress (project_id);
CREATE INDEX IF NOT EXISTS ix_feature_project ON feature_tracker (project_id);
```

---

## Troubleshooting

### Common Issues

#### 1. Slow Queries

**Symptom**: Query latency > 500ms

**Diagnosis**:
```sql
-- Check if HNSW index exists
SELECT indexname FROM pg_indexes WHERE tablename = 'memories';

-- Check index usage
EXPLAIN ANALYZE
SELECT * FROM memories
WHERE project_id = 'test'
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 10;
```

**Solution**:
```sql
-- Recreate HNSW index
DROP INDEX IF EXISTS ix_memories_embedding_hnsw;
CREATE INDEX ix_memories_embedding_hnsw ON memories 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Increase ef_search for better recall (at cost of speed)
SET hnsw.ef_search = 200;
```

#### 2. Connection Pool Exhausted

**Symptom**: "too many connections" errors

**Diagnosis**:
```bash
curl http://localhost:8000/metrics | grep db_pool
```

**Solution**:
```python
# Increase pool size in config
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=20
```

#### 3. Embedding Service Errors

**Symptom**: "OpenAI API error" in logs

**Diagnosis**:
```bash
# Check API key
echo $OPENAI_API_KEY

# Test directly
curl https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "text-embedding-3-small"}'
```

**Solution**:
- Check API key validity
- Check rate limits
- Enable embedding cache to reduce API calls

#### 4. Memory Not Found After Add

**Symptom**: Recently added memory not appearing in queries

**Diagnosis**:
```sql
-- Check if memory exists
SELECT id, created_at, expires_at FROM memories 
WHERE id = 'your-memory-id';

-- Check if TTL expired
SELECT * FROM memories WHERE expires_at < NOW();
```

**Solution**:
- Check TTL settings
- Verify namespace/scope filters match
- Run `VACUUM ANALYZE memories;` if index is stale

### Support

- **GitHub Issues**: [github.com/quantifylabs/aegis-memory/issues](https://github.com/quantifylabs/aegis-memory/issues)
- **Discussions**: [github.com/quantifylabs/aegis-memory/discussions](https://github.com/quantifylabs/aegis-memory/discussions)
