"""
Aegis Migration Test Suite

Tests for Alembic migration round-trips and environment gating.

Run with: pytest tests/test_migrations.py -v

Note: Full upgrade/downgrade tests require a live PostgreSQL database.
      These tests verify the migration configuration and environment gating.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure server directory is on path
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))


class TestAlembicConfiguration:
    """Tests for Alembic configuration correctness."""

    def test_alembic_ini_exists(self):
        """alembic.ini should exist at repo root."""
        ini_path = Path(__file__).parent.parent / "alembic.ini"
        assert ini_path.exists(), "alembic.ini not found at repo root"

    def test_alembic_env_exists(self):
        """alembic/env.py should exist."""
        env_path = Path(__file__).parent.parent / "alembic" / "env.py"
        assert env_path.exists(), "alembic/env.py not found"

    def test_baseline_migration_exists(self):
        """Baseline migration 0001 should exist."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"
        migrations = list(versions_dir.glob("0001_*.py"))
        assert len(migrations) == 1, "Expected exactly one baseline migration"

    def test_migration_template_exists(self):
        """script.py.mako template should exist."""
        template = Path(__file__).parent.parent / "alembic" / "script.py.mako"
        assert template.exists(), "script.py.mako not found"


class TestDatabaseInitGating:
    """Tests for environment-aware database initialization."""

    @pytest.mark.asyncio
    async def test_development_mode_still_uses_create_all(self):
        """In development mode, init_db should use create_all."""
        mock_settings = MagicMock()
        mock_settings.aegis_env = "development"
        mock_settings.database_url = "postgresql://test:test@localhost/test"
        mock_settings.sql_echo = False
        mock_settings.db_pool_size = 5
        mock_settings.db_max_overflow = 2
        mock_settings.database_read_replica_url = None

        with patch("database.settings", mock_settings):
            with patch("database.primary_engine") as mock_engine:
                mock_conn = AsyncMock()
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_engine.begin.return_value = mock_ctx

                from database import init_db
                await init_db()

                # Should have called execute for pgvector and run_sync for create_all
                assert mock_conn.execute.called or mock_conn.run_sync.called

    @pytest.mark.asyncio
    async def test_production_startup_without_alembic_version_raises(self):
        """In production mode, init_db should verify alembic_version table exists."""
        mock_settings = MagicMock()
        mock_settings.aegis_env = "production"

        with patch("database.settings", mock_settings):
            with patch("database.primary_engine") as mock_engine:
                mock_conn = AsyncMock()
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_engine.begin.return_value = mock_ctx

                # Simulate alembic_version table not existing
                mock_conn.execute.side_effect = Exception("relation \"alembic_version\" does not exist")

                from database import init_db
                with pytest.raises(RuntimeError, match="alembic"):
                    await init_db()


class TestMigrationFiles:
    """Tests for migration file integrity."""

    def test_baseline_migration_has_upgrade_and_downgrade(self):
        """Baseline migration must define both upgrade() and downgrade()."""
        import importlib.util

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0001_baseline.py"
        spec = importlib.util.spec_from_file_location("baseline", migration_path)
        module = importlib.util.module_from_spec(spec)

        # Need alembic and sqlalchemy available
        try:
            spec.loader.exec_module(module)
            assert hasattr(module, "upgrade"), "Missing upgrade() function"
            assert hasattr(module, "downgrade"), "Missing downgrade() function"
            assert callable(module.upgrade)
            assert callable(module.downgrade)
        except ImportError:
            pytest.skip("alembic or sqlalchemy not installed")

    def test_baseline_revision_id_is_0001(self):
        """Baseline migration should have revision '0001'."""
        import importlib.util

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "0001_baseline.py"
        spec = importlib.util.spec_from_file_location("baseline", migration_path)
        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
            assert module.revision == "0001"
            assert module.down_revision is None
        except ImportError:
            pytest.skip("alembic or sqlalchemy not installed")
