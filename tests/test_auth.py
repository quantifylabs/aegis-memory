"""
Aegis Auth Test Suite

Tests for project-scoped API key authentication (Phase 1).
Covers: legacy fallback, project keys, token verification,
auth policy, expired keys, audit logging.

Run with: pytest tests/test_auth.py -v
"""

import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Ensure server directory is on path
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))


# ---------- Fixtures ----------

@pytest.fixture
def mock_settings_legacy():
    """Settings with ENABLE_PROJECT_AUTH=False (legacy mode)."""
    settings = MagicMock()
    settings.enable_project_auth = False
    settings.aegis_api_key = "test-secret-key"
    settings.default_project_id = "default-project"
    settings.aegis_env = "development"
    return settings


@pytest.fixture
def mock_settings_project_auth():
    """Settings with ENABLE_PROJECT_AUTH=True."""
    settings = MagicMock()
    settings.enable_project_auth = True
    settings.aegis_api_key = "test-secret-key"
    settings.default_project_id = "default-project"
    settings.aegis_env = "development"
    return settings


def _make_api_key_row(
    project_id="proj-123",
    key_hash=None,
    name="test-key",
    is_active=True,
    expires_at=None,
):
    """Create a mock ApiKey row."""
    row = MagicMock()
    row.id = "key-abc123"
    row.project_id = project_id
    row.key_hash = key_hash or hashlib.sha256(b"raw-key-value").hexdigest()
    row.name = name
    row.is_active = is_active
    row.expires_at = expires_at
    return row


# ---------- Token Verifier Tests ----------


class TestTokenVerifierLegacy:
    """Tests for legacy (single key) auth mode."""

    @pytest.mark.asyncio
    async def test_legacy_auth_still_works_when_feature_flag_off(self, mock_settings_legacy):
        """Legacy auth should accept correct AEGIS_API_KEY when flag is off."""
        with patch("auth.settings", mock_settings_legacy):
            from auth import TokenVerifier

            result = TokenVerifier._verify_legacy_key("test-secret-key")
            assert result["project_id"] == "default-project"
            assert result["auth_method"] == "legacy"

    @pytest.mark.asyncio
    async def test_legacy_auth_rejects_wrong_key(self, mock_settings_legacy):
        """Legacy auth should reject incorrect keys with 401."""
        with patch("auth.settings", mock_settings_legacy):
            from auth import TokenVerifier
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                TokenVerifier._verify_legacy_key("wrong-key")
            assert exc_info.value.status_code == 401


class TestTokenVerifierProjectKey:
    """Tests for project-scoped key auth mode."""

    @pytest.mark.asyncio
    async def test_project_key_auth_resolves_correct_project_id(self, mock_settings_project_auth):
        """Valid project key should resolve to correct project_id."""
        raw_key = "raw-key-value"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        mock_api_key = _make_api_key_row(
            project_id="proj-123",
            key_hash=key_hash,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key
        mock_db.execute.return_value = mock_result

        with patch("auth.settings", mock_settings_project_auth):
            from auth import TokenVerifier

            result = await TokenVerifier._verify_project_key(raw_key, mock_db)
            assert result["project_id"] == "proj-123"
            assert result["auth_method"] == "project_key"
            assert result["key_id"] == "key-abc123"

    @pytest.mark.asyncio
    async def test_invalid_key_returns_401(self, mock_settings_project_auth):
        """Unknown key should return 401."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("auth.settings", mock_settings_project_auth):
            from auth import TokenVerifier
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await TokenVerifier._verify_project_key("bad-key", mock_db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_key_returns_401(self, mock_settings_project_auth):
        """Expired key should return 401."""
        raw_key = "expired-key"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        expired_api_key = _make_api_key_row(
            key_hash=key_hash,
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expired_api_key
        mock_db.execute.return_value = mock_result

        with patch("auth.settings", mock_settings_project_auth):
            from auth import TokenVerifier
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await TokenVerifier._verify_project_key(raw_key, mock_db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_key_returns_401(self, mock_settings_project_auth):
        """Inactive key should return 401."""
        raw_key = "inactive-key"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        inactive_api_key = _make_api_key_row(
            key_hash=key_hash,
            is_active=False,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inactive_api_key
        mock_db.execute.return_value = mock_result

        with patch("auth.settings", mock_settings_project_auth):
            from auth import TokenVerifier
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await TokenVerifier._verify_project_key(raw_key, mock_db)
            assert exc_info.value.status_code == 401


# ---------- Auth Policy Tests ----------


class TestAuthPolicy:
    """Tests for authorization policy decisions."""

    def test_auth_policy_can_write_memory_same_project(self):
        """Principal with matching project can write."""
        from auth import AuthPolicy

        principal = {"project_id": "proj-123", "auth_method": "project_key"}
        assert AuthPolicy.can_write_memory(principal, "proj-123") is True

    def test_auth_policy_can_write_memory_wrong_project(self):
        """Principal cannot write to a different project."""
        from auth import AuthPolicy

        principal = {"project_id": "proj-123", "auth_method": "project_key"}
        assert AuthPolicy.can_write_memory(principal, "proj-456") is False

    def test_auth_policy_can_query_memory_same_project(self):
        """Principal with matching project can query."""
        from auth import AuthPolicy

        principal = {"project_id": "proj-123", "auth_method": "project_key"}
        assert AuthPolicy.can_query_memory(principal, "proj-123") is True

    def test_auth_policy_can_query_memory_wrong_project(self):
        """Principal cannot query a different project."""
        from auth import AuthPolicy

        principal = {"project_id": "proj-123", "auth_method": "project_key"}
        assert AuthPolicy.can_query_memory(principal, "proj-456") is False


# ---------- Audit Logging Tests ----------


class TestAuditLogging:
    """Tests for auth audit log emission."""

    @pytest.mark.asyncio
    async def test_audit_log_emitted_on_successful_auth(self, mock_settings_legacy):
        """Successful auth should emit an audit log."""
        with patch("auth.settings", mock_settings_legacy):
            with patch("auth.logger") as mock_logger:
                from auth import TokenVerifier

                TokenVerifier._verify_legacy_key("test-secret-key")
                mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_audit_log_emitted_on_failed_auth(self, mock_settings_legacy):
        """Failed auth should emit a warning log."""
        with patch("auth.settings", mock_settings_legacy):
            with patch("auth.logger") as mock_logger:
                from auth import TokenVerifier
                from fastapi import HTTPException

                with pytest.raises(HTTPException):
                    TokenVerifier._verify_legacy_key("wrong-key")
                mock_logger.warning.assert_called()


# ---------- Hash Key Tests ----------


class TestHashKey:
    """Tests for key hashing utility."""

    def test_hash_key_produces_consistent_sha256(self):
        """hash_key should produce deterministic SHA-256 output."""
        from auth import hash_key

        raw = "my-api-key"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert hash_key(raw) == expected
        assert len(hash_key(raw)) == 64

    def test_hash_key_different_inputs_produce_different_hashes(self):
        """Different keys should hash differently."""
        from auth import hash_key

        assert hash_key("key-a") != hash_key("key-b")
