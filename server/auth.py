"""
Aegis Project-Scoped Authentication

Provides project-scoped API key authentication behind a feature flag.
When ENABLE_PROJECT_AUTH is false, falls back to legacy single-key auth.
When true, resolves project_id from the api_keys table.
"""

import hashlib
import logging
from datetime import datetime, timezone

from config import get_settings
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("aegis.auth")
settings = get_settings()


def hash_key(raw_key: str) -> str:
    """SHA-256 hash of an API key for secure storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class TokenVerifier:
    """
    Verifies bearer tokens against the api_keys table or legacy config.

    When ENABLE_PROJECT_AUTH is True:
      - Hashes the bearer token and looks it up in api_keys
      - Checks expiration and active status
      - Returns the associated project_id

    When ENABLE_PROJECT_AUTH is False:
      - Compares token against AEGIS_API_KEY config
      - Returns default_project_id
    """

    @staticmethod
    async def verify(token: str, db: AsyncSession | None = None) -> dict:
        """
        Verify a bearer token and return auth context.

        Returns:
            dict with keys: project_id, key_id (optional), principal (optional)

        Raises:
            HTTPException 401 on invalid/expired/missing key
        """
        if settings.enable_project_auth and db is not None:
            return await TokenVerifier._verify_project_key(token, db)
        return TokenVerifier._verify_legacy_key(token)

    @staticmethod
    def _verify_legacy_key(token: str) -> dict:
        """Legacy single API key verification."""
        if token != settings.aegis_api_key:
            logger.warning("auth.legacy.invalid_key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key. Check AEGIS_API_KEY environment variable on the server.",
            )
        logger.debug("auth.legacy.success", extra={"project_id": settings.default_project_id})
        return {
            "project_id": settings.default_project_id,
            "auth_method": "legacy",
        }

    @staticmethod
    async def _verify_project_key(token: str, db: AsyncSession) -> dict:
        """Project-scoped API key verification against api_keys table."""
        from models import ApiKey

        key_hash = hash_key(token)
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            logger.warning("auth.project.key_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
            )

        if not api_key.is_active:
            logger.warning(
                "auth.project.key_inactive",
                extra={"key_id": api_key.id, "project_id": api_key.project_id},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is inactive.",
            )

        if api_key.expires_at is not None and api_key.expires_at < datetime.now(timezone.utc):
            logger.warning(
                "auth.project.key_expired",
                extra={"key_id": api_key.id, "project_id": api_key.project_id},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired.",
            )

        logger.info(
            "auth.project.success",
            extra={
                "key_id": api_key.id,
                "project_id": api_key.project_id,
                "principal": api_key.name,
            },
        )
        return {
            "project_id": api_key.project_id,
            "key_id": api_key.id,
            "principal": api_key.name,
            "auth_method": "project_key",
        }


class AuthPolicy:
    """
    Authorization policy for memory operations.

    Determines whether a principal can read/write memory
    for a given project, scope, and agent.
    """

    @staticmethod
    def can_write_memory(
        principal: dict,
        project_id: str,
        scope: str | None = None,
        agent_id: str | None = None,
    ) -> bool:
        """Check if the authenticated principal can write to this project."""
        auth_project = principal.get("project_id")
        allowed = auth_project == project_id
        logger.debug(
            "auth.policy.can_write_memory",
            extra={
                "allowed": allowed,
                "auth_project": auth_project,
                "target_project": project_id,
                "scope": scope,
                "agent_id": agent_id,
            },
        )
        return allowed

    @staticmethod
    def can_query_memory(
        principal: dict,
        project_id: str,
        scope: str | None = None,
        agents: list[str] | None = None,
    ) -> bool:
        """Check if the authenticated principal can query this project."""
        auth_project = principal.get("project_id")
        allowed = auth_project == project_id
        logger.debug(
            "auth.policy.can_query_memory",
            extra={
                "allowed": allowed,
                "auth_project": auth_project,
                "target_project": project_id,
                "scope": scope,
                "agents": agents,
            },
        )
        return allowed


async def get_project_id(request: Request) -> str:
    """
    FastAPI dependency: extract and validate project ID from bearer token.

    Replaces the inline get_project_id in routes.py.
    When ENABLE_PROJECT_AUTH is on, looks up the key in the database.
    When off, falls back to legacy single-key logic.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: 'Bearer <api_key>'",
        )

    token = auth[7:].strip()

    if settings.enable_project_auth:
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await TokenVerifier.verify(token, db)
            return result["project_id"]

    result = TokenVerifier._verify_legacy_key(token)
    return result["project_id"]
