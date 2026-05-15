"""
Context Bundle Service (Context Hub v2.3.0).

The unifying primitive: assemble an agent's full context window in one call,
token-budgeted across prompts, memories, skills, and subagents.

This is what makes Aegis a Context Hub, not just a memory layer.
"""

from dataclasses import dataclass
from typing import Any

from config import get_settings
from embedding_service import get_embedding_service
from integrity import verify_integrity
from memory_repository import MemoryRepository
from models import Prompt
from observability import OperationNames, track_latency
from prompt_repository import PromptRepository
from skill_repository import SkillRepository
from sqlalchemy.ext.asyncio import AsyncSession
from subagent_repository import SubagentRepository


# Rough char→token approximation (3.5 chars/token average for English+code mix).
# For exact counting, swap with tiktoken at call site.
CHARS_PER_TOKEN = 3.5

DEFAULT_BUDGET_SPLIT = {
    "prompt": 0.15,      # system prompt
    "memories": 0.55,    # ranked relevant memories
    "skills": 0.25,      # skill descriptions only (full SKILL.md loads on-demand)
    "subagents": 0.05,   # delegation surface
}


@dataclass
class BundleItem:
    kind: str        # "prompt" | "memory" | "skill" | "subagent"
    id: str
    name: str | None
    content: str
    score: float | None
    integrity_verified: bool
    tokens_estimated: int
    metadata: dict[str, Any]


@dataclass
class ContextBundle:
    agent_id: str
    task_type: str | None
    query: str | None
    items: list[BundleItem]
    tokens_used: dict[str, int]
    tokens_budget: int
    integrity_all_verified: bool


def _est_tokens(text: str) -> int:
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    return text if len(text) <= max_chars else text[:max_chars] + "..."


class ContextBundleService:
    """Assembles a token-budgeted context bundle for an agent."""

    @staticmethod
    async def load(
        db: AsyncSession,
        *,
        project_id: str,
        agent_id: str,
        query: str | None = None,
        task_type: str | None = None,
        namespace: str = "default",
        token_budget: int = 8000,
        prompt_name: str | None = None,
        include_skills: bool = True,
        include_subagents: bool = True,
        memory_top_k: int = 10,
        skill_top_k: int = 3,
        apply_decay: bool = True,
        budget_split: dict[str, float] | None = None,
    ) -> ContextBundle:
        """
        Returns a fully assembled, token-budgeted, integrity-verified
        context bundle for an agent.

        prompt_name defaults to "{agent_id}_system" if not provided.
        """
        with track_latency(OperationNames.MEMORY_QUERY):
            settings = get_settings()
            split = budget_split or DEFAULT_BUDGET_SPLIT
            budgets = {k: int(token_budget * v) for k, v in split.items()}

            items: list[BundleItem] = []
            integrity_all = True
            tokens_used = {"prompt": 0, "memories": 0, "skills": 0, "subagents": 0}

            embedding_service = get_embedding_service()
            query_embedding: list[float] | None = None
            if query:
                query_embedding = await embedding_service.embed_single(query, db)

            # ---------- 1) Prompt ----------
            pname = prompt_name or f"{agent_id}_system"
            prompt: Prompt | None = await PromptRepository.get_active(db, project_id, pname, namespace)
            if prompt:
                ok = True
                if prompt.integrity_hash:
                    # Reuse memory verifier by adapting signature
                    expected_msg_obj = type("M", (), {
                        "content": prompt.content,
                        "agent_id": prompt.created_by_agent_id,
                        "project_id": prompt.project_id,
                        "integrity_hash": prompt.integrity_hash,
                    })
                    ok = verify_integrity(expected_msg_obj, settings.get_integrity_key())
                integrity_all = integrity_all and ok
                content = _truncate_to_tokens(prompt.content, budgets["prompt"])
                t = _est_tokens(content)
                tokens_used["prompt"] = t
                items.append(BundleItem(
                    kind="prompt", id=prompt.id, name=prompt.name, content=content,
                    score=None, integrity_verified=ok, tokens_estimated=t,
                    metadata={"version": prompt.version, "variables": prompt.variables},
                ))

            # ---------- 2) Memories ----------
            if query and query_embedding is not None:
                mem_results, _ = await MemoryRepository.semantic_search(
                    db,
                    query_embedding=query_embedding,
                    project_id=project_id,
                    namespace=namespace,
                    requesting_agent_id=agent_id,
                    top_k=memory_top_k,
                    apply_decay=apply_decay,
                )
                mem_budget_left = budgets["memories"]
                for mem, score in mem_results:
                    mok = True
                    if mem.integrity_hash:
                        mok = verify_integrity(mem, settings.get_integrity_key())
                    integrity_all = integrity_all and mok
                    mt = _est_tokens(mem.content)
                    if mt > mem_budget_left:
                        if mem_budget_left < 80:
                            break
                        content = _truncate_to_tokens(mem.content, mem_budget_left)
                        mt = _est_tokens(content)
                    else:
                        content = mem.content
                    mem_budget_left -= mt
                    tokens_used["memories"] += mt
                    items.append(BundleItem(
                        kind="memory", id=mem.id, name=None, content=content,
                        score=score, integrity_verified=mok, tokens_estimated=mt,
                        metadata={"memory_type": mem.memory_type, "scope": mem.scope,
                                  "effectiveness": mem.get_effectiveness_score()},
                    ))

            # ---------- 3) Skills (descriptions only — full SKILL.md is loaded on demand) ----------
            if include_skills and query and query_embedding is not None:
                skill_matches = await SkillRepository.match(
                    db, project_id=project_id, namespace=namespace,
                    query_embedding=query_embedding, top_k=skill_top_k,
                )
                sk_budget_left = budgets["skills"]
                for sk, sscore in skill_matches:
                    line = f"[skill:{sk.name}] {sk.description}"
                    st = _est_tokens(line)
                    if st > sk_budget_left:
                        break
                    sk_budget_left -= st
                    tokens_used["skills"] += st
                    items.append(BundleItem(
                        kind="skill", id=sk.id, name=sk.name, content=line,
                        score=sscore, integrity_verified=True, tokens_estimated=st,
                        metadata={"version": sk.version, "files": list(sk.bundled_files.keys())},
                    ))

            # ---------- 4) Subagents ----------
            if include_subagents:
                subs = await SubagentRepository.list_for_parent(
                    db, project_id=project_id, parent_agent_id=agent_id, namespace=namespace,
                )
                sa_budget_left = budgets["subagents"]
                for sa in subs:
                    line = f"[subagent:{sa.name}] {sa.description} (tools: {', '.join(sa.tools[:5])})"
                    sat = _est_tokens(line)
                    if sat > sa_budget_left:
                        break
                    sa_budget_left -= sat
                    tokens_used["subagents"] += sat
                    items.append(BundleItem(
                        kind="subagent", id=sa.id, name=sa.name, content=line,
                        score=None, integrity_verified=True, tokens_estimated=sat,
                        metadata={"model": sa.model, "tools": sa.tools},
                    ))

            return ContextBundle(
                agent_id=agent_id,
                task_type=task_type,
                query=query,
                items=items,
                tokens_used=tokens_used,
                tokens_budget=token_budget,
                integrity_all_verified=integrity_all,
            )
