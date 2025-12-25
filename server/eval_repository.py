"""
Aegis Evaluation Repository

Aggregation logic for 'Confidence Metrics' and 'Evaluation Harness':
- Task Success Rate
- Retrieval Precision
- Pollution Rate
- MTTR (Mean Time to Resolution)
- Vote-Utility Correlation
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from models import FeatureTracker, Memory, VoteHistory
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class EvalRepository:
    """Repository for evaluation and confidence metrics."""

    @staticmethod
    def _get_window_start(window: str) -> datetime | None:
        """Convert window string to start datetime."""
        now = datetime.now(timezone.utc)
        if window == "24h":
            return now - timedelta(days=1)
        elif window == "7d":
            return now - timedelta(days=7)
        elif window == "30d":
            return now - timedelta(days=30)
        return None

    @staticmethod
    async def get_metrics(
        db: AsyncSession,
        project_id: str,
        namespace: str | None = None,
        agent_id: str | None = None,
        window: str = "global",
    ) -> dict[str, Any]:
        """
        Aggregate high-level KPIs for the Evaluation Harness.
        """
        start_time = EvalRepository._get_window_start(window)

        # 1. Task Success Rate (from FeatureTracker)
        ft_conditions = [FeatureTracker.project_id == project_id]
        if namespace:
            ft_conditions.append(FeatureTracker.namespace == namespace)
        if start_time:
            ft_conditions.append(FeatureTracker.created_at >= start_time)

        ft_query = select(
            func.count(FeatureTracker.id).label("total"),
            func.count(FeatureTracker.id).filter(FeatureTracker.passes).label("passing"),
            func.avg(
                func.extract("epoch", FeatureTracker.completed_at) -
                func.extract("epoch", FeatureTracker.created_at)
            ).filter(FeatureTracker.completed_at.isnot(None)).label("avg_mttr_sec")
        ).where(and_(*ft_conditions))

        ft_result = await db.execute(ft_query)
        ft_stats = ft_result.one()

        success_rate = ft_stats.passing / ft_stats.total if ft_stats.total > 0 else 0.0
        mttr = ft_stats.avg_mttr_sec if ft_stats.avg_mttr_sec else 0.0

        # 2. Retrieval Precision & Pollution Rate (from Memory)
        mem_conditions = [Memory.project_id == project_id]
        if namespace:
            mem_conditions.append(Memory.namespace == namespace)
        if agent_id:
            mem_conditions.append(Memory.agent_id == agent_id)
        if start_time:
            mem_conditions.append(Memory.created_at >= start_time)

        mem_query = select(
            func.count(Memory.id).label("total"),
            func.sum(Memory.bullet_helpful).label("helpful"),
            func.sum(Memory.bullet_harmful).label("harmful"),
            func.count(Memory.id).filter(Memory.bullet_harmful > 0).label("polluted")
        ).where(and_(*mem_conditions))

        mem_result = await db.execute(mem_query)
        mem_stats = mem_result.one()

        total_votes = (mem_stats.helpful or 0) + (mem_stats.harmful or 0)
        # Formula: Helpful / (Helpful + Harmful + 1)
        precision = (mem_stats.helpful or 0) / (total_votes + 1)
        pollution_rate = mem_stats.polluted / mem_stats.total if mem_stats.total > 0 else 0.0

        return {
            "success_rate": round(success_rate, 4),
            "retrieval_precision": round(precision, 4),
            "pollution_rate": round(pollution_rate, 4),
            "mttr_seconds": round(mttr, 2),
            "total_tasks": ft_stats.total,
            "passing_tasks": ft_stats.passing,
            "total_memories": mem_stats.total,
            "helpful_votes": mem_stats.helpful or 0,
            "harmful_votes": mem_stats.harmful or 0,
            "window": window,
        }

    @staticmethod
    async def get_vote_utility_correlation(
        db: AsyncSession,
        project_id: str,
        namespace: str | None = None,
        agent_id: str | None = None,
        window: str = "global",
    ) -> dict[str, Any]:
        """
        Calculate correlation between memory votes and task success.
        Answers: 'Do votes predict actual usefulness?'
        """
        start_time = EvalRepository._get_window_start(window)

        # We join VoteHistory with FeatureTracker on task_id
        # Note: This assumes agents pass task_id when voting
        conditions = [
            VoteHistory.project_id == project_id,
            FeatureTracker.project_id == project_id,
            VoteHistory.task_id == FeatureTracker.feature_id,
        ]
        if namespace:
            conditions.append(FeatureTracker.namespace == namespace)
        if start_time:
            conditions.append(VoteHistory.created_at >= start_time)

        query = select(
            VoteHistory.vote,
            FeatureTracker.passes
        ).where(and_(*conditions))

        result = await db.execute(query)
        rows = result.all()

        if not rows:
            return {
                "correlation_score": 0.0,
                "prob_pass_given_helpful": 0.0,
                "prob_pass_given_harmful": 0.0,
                "sample_size": 0,
                "helpful_count": 0,
                "harmful_count": 0,
                "message": "No linked vote/task data found."
            }

        # Simple correlation: P(Pass | Helpful) vs P(Pass | Harmful)
        helpful_pass = 0
        helpful_total = 0
        harmful_pass = 0
        harmful_total = 0

        for vote, passes in rows:
            if vote == "helpful":
                helpful_total += 1
                if passes:
                    helpful_pass += 1
            elif vote == "harmful":
                harmful_total += 1
                if passes:
                    harmful_pass += 1

        prob_pass_helpful = helpful_pass / helpful_total if helpful_total > 0 else 0.0
        prob_pass_harmful = harmful_pass / harmful_total if harmful_total > 0 else 0.0

        # Correlation score is the gap between probability of success when memory is helpful vs harmful
        correlation_score = prob_pass_helpful - prob_pass_harmful

        return {
            "correlation_score": round(correlation_score, 4),
            "prob_pass_given_helpful": round(prob_pass_helpful, 4),
            "prob_pass_given_harmful": round(prob_pass_harmful, 4),
            "sample_size": len(rows),
            "helpful_count": helpful_total,
            "harmful_count": harmful_total,
        }

