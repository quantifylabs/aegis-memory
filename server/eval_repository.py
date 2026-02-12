"""Evaluation and effectiveness analytics repository."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EvalRepository:
    """Repository for evaluation and memory effectiveness metrics."""

    @staticmethod
    def _get_window_start(window: str) -> datetime | None:
        now = datetime.now(timezone.utc)
        if window == "24h":
            return now - timedelta(days=1)
        if window == "7d":
            return now - timedelta(days=7)
        if window == "30d":
            return now - timedelta(days=30)
        return None

    @staticmethod
    async def _linked_memory_outcomes(
        db: AsyncSession,
        project_id: str,
        namespace: str | None,
        window: str,
    ) -> list[dict[str, Any]]:
        start_time = EvalRepository._get_window_start(window)
        sql = """
        SELECT DISTINCT
            COALESCE(o.task_id, o.event_payload->>'feature_id') AS task_id,
            ft.passes AS passes,
            m.id AS memory_id,
            m.memory_type AS memory_type,
            m.agent_id AS memory_agent_id,
            m.scope AS memory_scope,
            o.created_at AS outcome_created_at
        FROM memory_events r
        JOIN memory_events o
          ON o.project_id = r.project_id
         AND o.retrieval_event_id = r.event_id
         AND o.event_type = 'delta_updated'
        JOIN feature_tracker ft
          ON ft.project_id = o.project_id
         AND ft.namespace = o.namespace
         AND ft.feature_id = COALESCE(o.task_id, o.event_payload->>'feature_id')
        JOIN LATERAL jsonb_array_elements_text(
          COALESCE(NULLIF(o.selected_memory_ids::jsonb, 'null'::jsonb), r.selected_memory_ids::jsonb, '[]'::jsonb)
        ) sid(memory_id)
          ON TRUE
        JOIN memories m
          ON m.id = sid.memory_id
         AND m.project_id = r.project_id
        WHERE r.project_id = :project_id
          AND r.event_type = 'queried'
          AND COALESCE(o.task_id, o.event_payload->>'feature_id') IS NOT NULL
          AND (:namespace IS NULL OR r.namespace = :namespace)
          AND (:start_time IS NULL OR o.created_at >= :start_time)
        """
        result = await db.execute(
            text(sql),
            {
                "project_id": project_id,
                "namespace": namespace,
                "start_time": start_time,
            },
        )
        return [dict(row._mapping) for row in result.fetchall()]

    @staticmethod
    def _compute_group_metrics(
        rows: list[dict[str, Any]],
        group_key: str,
        min_samples: int,
        alpha: float,
        beta: float,
    ) -> list[dict[str, Any]]:
        task_outcomes = {}
        for row in rows:
            task_outcomes[row["task_id"]] = bool(row["passes"])

        total_tasks = len(task_outcomes)
        total_pass = sum(1 for p in task_outcomes.values() if p)
        global_pass_rate = total_pass / total_tasks if total_tasks else 0.0
        global_smoothed = (total_pass + alpha) / (total_tasks + alpha + beta) if total_tasks else 0.0

        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "tasks": set(),
                "pass_count": 0,
                "memory_ids": set(),
            }
        )

        for row in rows:
            key = row[group_key]
            if key is None:
                key = "unknown"
            bucket = grouped[str(key)]
            task_id = row["task_id"]
            if task_id not in bucket["tasks"]:
                bucket["tasks"].add(task_id)
                if row["passes"]:
                    bucket["pass_count"] += 1
            bucket["memory_ids"].add(row["memory_id"])

        output = []
        for key, bucket in grouped.items():
            n = len(bucket["tasks"])
            if n < min_samples:
                continue
            passes = bucket["pass_count"]
            pass_rate = passes / n if n else 0.0
            smoothed_pass_rate = (passes + alpha) / (n + alpha + beta)
            uplift = pass_rate - global_pass_rate
            smoothed_uplift = smoothed_pass_rate - global_smoothed
            output.append(
                {
                    "segment": key,
                    "sample_size": n,
                    "pass_count": passes,
                    "pass_rate": round(pass_rate, 4),
                    "smoothed_pass_rate": round(smoothed_pass_rate, 4),
                    "pass_rate_delta": round(uplift, 4),
                    "uplift_score": round(smoothed_uplift, 4),
                    "memory_count": len(bucket["memory_ids"]),
                }
            )

        output.sort(key=lambda item: item["uplift_score"], reverse=True)
        return output

    @staticmethod
    def _compute_trends(
        rows: list[dict[str, Any]],
        group_key: str,
        min_samples: int,
        alpha: float,
        beta: float,
    ) -> dict[str, list[dict[str, Any]]]:
        slices = {"24h": [], "7d": [], "30d": []}
        now = datetime.now(timezone.utc)
        for window, days in (("24h", 1), ("7d", 7), ("30d", 30)):
            window_rows = [
                row for row in rows
                if row["outcome_created_at"] and row["outcome_created_at"] >= now - timedelta(days=days)
            ]
            slices[window] = EvalRepository._compute_group_metrics(
                window_rows,
                group_key=group_key,
                min_samples=min_samples,
                alpha=alpha,
                beta=beta,
            )
        return slices

    @staticmethod
    async def get_effectiveness_overview(
        db: AsyncSession,
        project_id: str,
        namespace: str | None = None,
        window: str = "global",
        min_samples: int = 5,
        alpha: float = 1.0,
        beta: float = 1.0,
    ) -> dict[str, Any]:
        rows = await EvalRepository._linked_memory_outcomes(db, project_id, namespace, window)
        by_memory = EvalRepository._compute_group_metrics(rows, "memory_id", min_samples, alpha, beta)

        task_ids = {row["task_id"] for row in rows}
        pass_count = sum(1 for row in {r["task_id"]: bool(r["passes"]) for r in rows}.values() if row)
        total_tasks = len(task_ids)
        overall_pass_rate = pass_count / total_tasks if total_tasks else 0.0

        return {
            "window": window,
            "total_linked_rows": len(rows),
            "total_tasks": total_tasks,
            "overall_pass_rate": round(overall_pass_rate, 4),
            "top_helpful": by_memory[:10],
            "top_harmful": list(reversed(by_memory[-10:])),
            "trends": {
                trend: {
                    "top_helpful": vals[:5],
                    "top_harmful": list(reversed(vals[-5:])),
                }
                for trend, vals in EvalRepository._compute_trends(rows, "memory_id", min_samples, alpha, beta).items()
            },
            "controls": {
                "min_samples": min_samples,
                "bayesian_alpha": alpha,
                "bayesian_beta": beta,
            },
        }

    @staticmethod
    async def get_effectiveness_memories(
        db: AsyncSession,
        project_id: str,
        namespace: str | None = None,
        window: str = "global",
        min_samples: int = 5,
        alpha: float = 1.0,
        beta: float = 1.0,
    ) -> dict[str, Any]:
        rows = await EvalRepository._linked_memory_outcomes(db, project_id, namespace, window)
        by_memory = EvalRepository._compute_group_metrics(rows, "memory_id", min_samples, alpha, beta)
        trends = EvalRepository._compute_trends(rows, "memory_id", min_samples, alpha, beta)
        return {
            "window": window,
            "leaderboard": {
                "top_helpful": by_memory[:20],
                "top_harmful": list(reversed(by_memory[-20:])),
            },
            "trends": trends,
            "controls": {"min_samples": min_samples, "bayesian_alpha": alpha, "bayesian_beta": beta},
        }

    @staticmethod
    async def get_effectiveness_segments(
        db: AsyncSession,
        project_id: str,
        namespace: str | None = None,
        window: str = "global",
        min_samples: int = 5,
        alpha: float = 1.0,
        beta: float = 1.0,
    ) -> dict[str, Any]:
        rows = await EvalRepository._linked_memory_outcomes(db, project_id, namespace, window)
        by_type = EvalRepository._compute_group_metrics(rows, "memory_type", min_samples, alpha, beta)
        by_agent = EvalRepository._compute_group_metrics(rows, "memory_agent_id", min_samples, alpha, beta)
        by_scope = EvalRepository._compute_group_metrics(rows, "memory_scope", min_samples, alpha, beta)

        trend_type = EvalRepository._compute_trends(rows, "memory_type", min_samples, alpha, beta)
        trend_agent = EvalRepository._compute_trends(rows, "memory_agent_id", min_samples, alpha, beta)
        trend_scope = EvalRepository._compute_trends(rows, "memory_scope", min_samples, alpha, beta)

        return {
            "window": window,
            "segments": {
                "memory_type": {
                    "top_helpful": by_type[:10],
                    "top_harmful": list(reversed(by_type[-10:])),
                    "trends": trend_type,
                },
                "agent_id": {
                    "top_helpful": by_agent[:10],
                    "top_harmful": list(reversed(by_agent[-10:])),
                    "trends": trend_agent,
                },
                "scope": {
                    "top_helpful": by_scope[:10],
                    "top_harmful": list(reversed(by_scope[-10:])),
                    "trends": trend_scope,
                },
            },
            "controls": {"min_samples": min_samples, "bayesian_alpha": alpha, "bayesian_beta": beta},
        }

    @staticmethod
    async def get_metrics(
        db: AsyncSession,
        project_id: str,
        namespace: str | None = None,
        agent_id: str | None = None,
        window: str = "global",
    ) -> dict[str, Any]:
        start_time = EvalRepository._get_window_start(window)
        ft_sql = """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE passes) AS passing,
          AVG(EXTRACT(EPOCH FROM completed_at) - EXTRACT(EPOCH FROM created_at)) FILTER (WHERE completed_at IS NOT NULL) AS avg_mttr_sec
        FROM feature_tracker
        WHERE project_id = :project_id
          AND (:namespace IS NULL OR namespace = :namespace)
          AND (:start_time IS NULL OR created_at >= :start_time)
        """
        mem_sql = """
        SELECT
          COUNT(*) AS total,
          COALESCE(SUM(bullet_helpful), 0) AS helpful,
          COALESCE(SUM(bullet_harmful), 0) AS harmful,
          COUNT(*) FILTER (WHERE bullet_harmful > 0) AS polluted
        FROM memories
        WHERE project_id = :project_id
          AND (:namespace IS NULL OR namespace = :namespace)
          AND (:agent_id IS NULL OR agent_id = :agent_id)
          AND (:start_time IS NULL OR created_at >= :start_time)
        """
        params={"project_id":project_id,"namespace":namespace,"agent_id":agent_id,"start_time":start_time}
        ft=(await db.execute(text(ft_sql),params)).one()
        mem=(await db.execute(text(mem_sql),params)).one()
        total_votes=(mem.helpful or 0)+(mem.harmful or 0)
        return {
            "success_rate": round((ft.passing / ft.total) if ft.total else 0.0, 4),
            "retrieval_precision": round((mem.helpful or 0) / (total_votes + 1), 4),
            "pollution_rate": round((mem.polluted / mem.total) if mem.total else 0.0, 4),
            "mttr_seconds": round(ft.avg_mttr_sec or 0.0, 2),
            "total_tasks": ft.total,
            "passing_tasks": ft.passing,
            "total_memories": mem.total,
            "helpful_votes": mem.helpful or 0,
            "harmful_votes": mem.harmful or 0,
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
        start_time = EvalRepository._get_window_start(window)
        sql = """
        SELECT vh.vote, ft.passes
        FROM vote_history vh
        JOIN feature_tracker ft
          ON ft.project_id = vh.project_id
         AND ft.feature_id = vh.task_id
        WHERE vh.project_id = :project_id
          AND (:namespace IS NULL OR ft.namespace = :namespace)
          AND (:agent_id IS NULL OR vh.voter_agent_id = :agent_id)
          AND (:start_time IS NULL OR vh.created_at >= :start_time)
        """
        rows=(await db.execute(text(sql),{"project_id":project_id,"namespace":namespace,"agent_id":agent_id,"start_time":start_time})).fetchall()
        helpful_total=helpful_pass=harmful_total=harmful_pass=0
        for vote, passes in rows:
            if vote=="helpful":
                helpful_total +=1
                if passes: helpful_pass +=1
            elif vote=="harmful":
                harmful_total +=1
                if passes: harmful_pass +=1
        prob_help=helpful_pass/helpful_total if helpful_total else 0.0
        prob_harm=harmful_pass/harmful_total if harmful_total else 0.0
        return {
            "correlation_score": round(prob_help-prob_harm,4),
            "prob_pass_given_helpful": round(prob_help,4),
            "prob_pass_given_harmful": round(prob_harm,4),
            "sample_size": len(rows),
            "helpful_count": helpful_total,
            "harmful_count": harmful_total,
        }
