"""Subagent Repository (Context Hub v2.3.0)."""

from uuid import uuid4

from event_repository import EventRepository
from models import MemoryEventType, Subagent
from observability import OperationNames, record_operation, track_latency
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


class SubagentRepository:

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        project_id: str,
        name: str,
        description: str,
        system_prompt: str | None = None,
        system_prompt_ref: str | None = None,
        model: str | None = None,
        tools: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        allowed_skills: list[str] | None = None,
        parent_agent_id: str | None = None,
        namespace: str = "default",
        integrity_hash: str | None = None,
        trust_level: str = "internal",
    ) -> Subagent:
        # Contract: must have either inline prompt or a reference
        if not system_prompt and not system_prompt_ref:
            raise ValueError("subagent requires either system_prompt or system_prompt_ref")

        with track_latency(OperationNames.MEMORY_ADD):
            sub = Subagent(
                id=uuid4().hex,
                project_id=project_id,
                namespace=namespace,
                name=name,
                description=description,
                system_prompt=system_prompt,
                system_prompt_ref=system_prompt_ref,
                model=model,
                tools=tools or [],
                allowed_scopes=allowed_scopes or [],
                allowed_skills=allowed_skills or [],
                parent_agent_id=parent_agent_id,
                integrity_hash=integrity_hash,
                trust_level=trust_level,
            )
            db.add(sub)
            await db.flush()

            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=parent_agent_id,
                event_type=MemoryEventType.SUBAGENT_CREATED.value,
                event_payload={"name": name, "parent": parent_agent_id},
            )
            record_operation(OperationNames.MEMORY_ADD, "success")
            return sub

    @staticmethod
    async def get(
        db: AsyncSession, project_id: str, name: str, namespace: str = "default"
    ) -> Subagent | None:
        result = await db.execute(
            select(Subagent).where(and_(
                Subagent.project_id == project_id,
                Subagent.namespace == namespace,
                Subagent.name == name,
            ))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_parent(
        db: AsyncSession,
        project_id: str,
        parent_agent_id: str | None = None,
        namespace: str = "default",
    ) -> list[Subagent]:
        conditions = [
            Subagent.project_id == project_id,
            Subagent.namespace == namespace,
            Subagent.is_active == True,  # noqa: E712
        ]
        if parent_agent_id is not None:
            conditions.append(Subagent.parent_agent_id == parent_agent_id)
        result = await db.execute(select(Subagent).where(and_(*conditions)).order_by(Subagent.name))
        return list(result.scalars().all())
