# Aegis Memory - Database Management
#
# Usage:
#   make db-upgrade      - Apply all pending migrations
#   make db-downgrade    - Revert last migration
#   make db-migrate MSG="description"  - Generate new migration
#   make db-check        - Verify migration round-trip (upgrade + downgrade + upgrade)
#   make db-current      - Show current migration revision
#   make db-history      - Show migration history
#   make test            - Run all tests
#   make lint            - Run linter

.PHONY: db-upgrade db-downgrade db-migrate db-check db-current db-history test lint

db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

db-migrate:
	alembic revision --autogenerate -m "$(MSG)"

db-check:
	@echo "=== Migration round-trip check ==="
	@echo "Step 1: Upgrade to head..."
	alembic upgrade head
	@echo "Step 2: Downgrade to base..."
	alembic downgrade base
	@echo "Step 3: Upgrade to head again..."
	alembic upgrade head
	@echo "=== Round-trip check passed ==="

db-current:
	alembic current

db-history:
	alembic history --verbose

test:
	pytest tests/ -v

lint:
	ruff check server/ tests/
