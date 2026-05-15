"""Skill Repository (Context Hub v2.3.0) — Anthropic Agent Skills spec."""

from uuid import uuid4

from event_repository import EventRepository
from models import MemoryEventType, Skill
from observability import OperationNames, record_operation, track_latency
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


class SkillRepository:

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        project_id: str,
        name: str,
        description: str,
        skill_md: str,
        description_embedding: list[float] | None = None,
        bundled_files: dict[str, str] | None = None,
        metadata: dict | None = None,
        namespace: str = "default",
        version: str = "1.0.0",
        agent_id: str | None = None,
        integrity_hash: str | None = None,
        content_flags: list[str] | None = None,
        trust_level: str = "privileged",
    ) -> Skill:
        with track_latency(OperationNames.MEMORY_ADD):
            skill = Skill(
                id=uuid4().hex,
                project_id=project_id,
                namespace=namespace,
                name=name,
                description=description,
                description_embedding=description_embedding,
                version=version,
                skill_md=skill_md,
                bundled_files=bundled_files or {},
                metadata_json=metadata or {},
                created_by_agent_id=agent_id,
                integrity_hash=integrity_hash,
                content_flags=content_flags or [],
                trust_level=trust_level,
            )
            db.add(skill)
            await db.flush()

            await EventRepository.create_event(
                db,
                memory_id=None,
                project_id=project_id,
                namespace=namespace,
                agent_id=agent_id,
                event_type=MemoryEventType.SKILL_CREATED.value,
                event_payload={"name": name, "version": version, "files": list((bundled_files or {}).keys())},
            )
            record_operation(OperationNames.MEMORY_ADD, "success")
            return skill

    @staticmethod
    async def get(
        db: AsyncSession, project_id: str, name: str, namespace: str = "default"
    ) -> Skill | None:
        result = await db.execute(
            select(Skill).where(and_(
                Skill.project_id == project_id,
                Skill.namespace == namespace,
                Skill.name == name,
            ))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession, project_id: str, namespace: str = "default", active_only: bool = True
    ) -> list[Skill]:
        conditions = [Skill.project_id == project_id, Skill.namespace == namespace]
        if active_only:
            conditions.append(Skill.is_active == True)  # noqa: E712
        result = await db.execute(select(Skill).where(and_(*conditions)).order_by(Skill.name))
        return list(result.scalars().all())

    @staticmethod
    async def match(
        db: AsyncSession,
        *,
        project_id: str,
        query_embedding: list[float],
        namespace: str = "default",
        top_k: int = 3,
        min_score: float = 0.3,
    ) -> list[tuple[Skill, float]]:
        """Semantic activation: match skills whose description is closest to the query."""
        distance_expr = Skill.description_embedding.cosine_distance(query_embedding)
        stmt = (
            select(Skill, distance_expr.label("distance"))
            .where(and_(
                Skill.project_id == project_id,
                Skill.namespace == namespace,
                Skill.is_active == True,  # noqa: E712
                Skill.description_embedding.is_not(None),
            ))
            .order_by(distance_expr)
            .limit(top_k)
        )
        result = await db.execute(stmt)
        out = []
        for sk, dist in result.all():
            score = 1.0 - dist
            if score >= min_score:
                out.append((sk, score))
        return out

    @staticmethod
    async def delete(
        db: AsyncSession, project_id: str, name: str, namespace: str = "default"
    ) -> bool:
        skill = await SkillRepository.get(db, project_id, name, namespace)
        if skill is None:
            return False
        await db.delete(skill)
        return True
