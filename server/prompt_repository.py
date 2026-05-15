"""Prompt Repository (Context Hub v2.3.0) — versioned prompt CRUD."""

import re
from uuid import uuid4

from event_repository import EventRepository
from models import MemoryEventType, Prompt
from observability import OperationNames, record_operation, track_latency
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def extract_variables(content: str) -> list[str]:
    """Extract {{variable}} names from prompt template, preserving first occurrence order."""
    seen: list[str] = []
    for m in _VAR_RE.finditer(content):
        v = m.group(1)
        if v not in seen:
            seen.append(v)
    return seen


class PromptRepository:

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        project_id: str,
        name: str,
        content: str,
        namespace: str = "default",
        description: str | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        integrity_hash: str | None = None,
        content_flags: list[str] | None = None,
        trust_level: str = "internal",
        activate: bool = True,
    ) -> Prompt:
        """Create a new version. If activate=True, deactivates prior versions."""
        with track_latency(OperationNames.MEMORY_ADD):
            # Determine next version number
            result = await db.execute(
                select(Prompt.version)
                .where(and_(
                    Prompt.project_id == project_id,
                    Prompt.namespace == namespace,
                    Prompt.name == name,
                ))
                .order_by(Prompt.version.desc())
                .limit(1)
            )
            prev = result.scalar_one_or_none()
            next_version = (prev or 0) + 1

            if activate:
                await db.execute(
                    update(Prompt)
                    .where(and_(
                        Prompt.project_id == project_id,
                        Prompt.namespace == namespace,
                        Prompt.name == name,
                        Prompt.is_active == True,  # noqa: E712
                    ))
                    .values(is_active=False)
                )

            prompt = Prompt(
                id=uuid4().hex,
                project_id=project_id,
                namespace=namespace,
                name=name,
                version=next_version,
                content=content,
                description=description,
                variables=extract_variables(content),
                tags=tags or [],
                is_active=activate,
                created_by_agent_id=agent_id,
                integrity_hash=integrity_hash,
                content_flags=content_flags or [],
                trust_level=trust_level,
            )
            db.add(prompt)
            await db.flush()

            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=agent_id,
                event_type=MemoryEventType.PROMPT_CREATED.value,
                event_payload={"name": name, "version": next_version, "activated": activate},
            )
            record_operation(OperationNames.MEMORY_ADD, "success")
            return prompt

    @staticmethod
    async def get_active(
        db: AsyncSession, project_id: str, name: str, namespace: str = "default"
    ) -> Prompt | None:
        result = await db.execute(
            select(Prompt).where(and_(
                Prompt.project_id == project_id,
                Prompt.namespace == namespace,
                Prompt.name == name,
                Prompt.is_active == True,  # noqa: E712
            ))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_versions(
        db: AsyncSession, project_id: str, name: str, namespace: str = "default"
    ) -> list[Prompt]:
        result = await db.execute(
            select(Prompt).where(and_(
                Prompt.project_id == project_id,
                Prompt.namespace == namespace,
                Prompt.name == name,
            )).order_by(Prompt.version.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def activate(
        db: AsyncSession, project_id: str, name: str, version: int, namespace: str = "default"
    ) -> Prompt | None:
        # Deactivate all
        await db.execute(
            update(Prompt)
            .where(and_(
                Prompt.project_id == project_id,
                Prompt.namespace == namespace,
                Prompt.name == name,
            ))
            .values(is_active=False)
        )
        # Activate target
        await db.execute(
            update(Prompt)
            .where(and_(
                Prompt.project_id == project_id,
                Prompt.namespace == namespace,
                Prompt.name == name,
                Prompt.version == version,
            ))
            .values(is_active=True)
        )
        return await PromptRepository.get_active(db, project_id, name, namespace)
