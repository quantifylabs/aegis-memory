"""API key storage operations.

Provides helpers for creating and managing API keys in the database.
"""
import secrets
from datetime import datetime, timezone

from auth import hash_key
from models import ApiKey, Project
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class KeyStore:
    """Manages API key lifecycle in the database."""

    @staticmethod
    async def create_project(
        db: AsyncSession,
        project_id: str,
        name: str,
        description: str | None = None,
    ) -> Project:
        """Create a new project."""
        project = Project(
            id=project_id,
            name=name,
            description=description,
        )
        db.add(project)
        await db.flush()
        return project

    @staticmethod
    async def create_api_key(
        db: AsyncSession,
        project_id: str,
        name: str = "default",
        expires_at: datetime | None = None,
    ) -> tuple[ApiKey, str]:
        """
        Create a new API key for a project.

        Returns (ApiKey, raw_key) -- the raw key is only available at creation time.
        """
        raw_key = f"aegis_{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(16)

        api_key = ApiKey(
            id=key_id,
            project_id=project_id,
            key_hash=hash_key(raw_key),
            name=name,
            expires_at=expires_at,
        )
        db.add(api_key)
        await db.flush()
        return api_key, raw_key

    @staticmethod
    async def revoke_key(db: AsyncSession, key_id: str) -> bool:
        """Deactivate an API key. Returns True if found."""
        result = await db.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        if key is None:
            return False
        key.is_active = False
        await db.flush()
        return True
