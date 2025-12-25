# Database Migrations

This directory contains SQL migration files for Aegis Memory.

## Migration Files

| File | Description | Version |
|------|-------------|---------|
| `001_initial.sql` | Initial schema with memories table and pgvector | 1.0.0 |
| `002_ace_tables.sql` | ACE pattern tables (voting, sessions, features) | 1.1.0 |

## Running Migrations

### Manual Execution

```bash
# Connect to your PostgreSQL instance
psql -h localhost -U aegis -d aegis

# Run a specific migration
\i migrations/001_initial.sql
\i migrations/002_ace_tables.sql
```

### Using Docker

```bash
# Copy migration file into container
docker cp migrations/002_ace_tables.sql aegis-postgres:/tmp/

# Execute migration
docker exec -it aegis-postgres psql -U aegis -d aegis -f /tmp/002_ace_tables.sql
```

## Migration Strategy

1. **Always backup before migrating**
   ```bash
   pg_dump -h localhost -U aegis -d aegis -F c -f backup_before_migration.dump
   ```

2. **Run migrations in order** - Each migration depends on previous ones

3. **Test in staging first** - Never run untested migrations in production

4. **Migrations are idempotent** - Use `IF NOT EXISTS` to allow re-running

## Rollback

Each migration should have a corresponding rollback section commented at the bottom. Uncomment and run if needed.

## Future: Alembic

We plan to migrate to Alembic for automated migrations in a future release. For now, manual SQL migrations provide more control and visibility.

