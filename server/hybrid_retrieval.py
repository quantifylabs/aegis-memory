"""
Hybrid Retrieval (v2.4.0).

Two-channel: dense (pgvector cosine, existing HNSW) + sparse (PostgreSQL
tsvector + ts_rank_cd over GIN index, added in migration 0009).

Fusion: Reciprocal Rank Fusion (Cormack et al. 2009), k=60.

Why tsvector and not Elasticsearch:
- Zero new infra dependency
- ts_rank_cd uses cover-density, a BM25-flavored ranking
- GIN index gives sub-ms lookups on the corpus sizes we target (<10M memories)
- If you need true BM25 later, the HybridRetriever interface stays the
  same -- swap the sparse channel impl.
"""

from collections import defaultdict

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Memory


DEFAULT_RRF_K = 60   # Cormack et al. 2009 default


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = DEFAULT_RRF_K) -> dict[str, float]:
    """
    Combine multiple rankings into a single score per item.
    Each input is a list of item IDs in rank order (best first).
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return dict(scores)


class HybridRetriever:
    """Dense + sparse retrieval with RRF fusion."""

    @staticmethod
    async def search(
        db: AsyncSession,
        *,
        query: str,
        query_embedding: list[float],
        project_id: str,
        namespace: str = "default",
        top_k: int = 10,
        candidate_pool: int = 40,
        rrf_k: int = DEFAULT_RRF_K,
        dense_weight: int = 1,
        sparse_weight: int = 1,
    ) -> list[tuple[Memory, float]]:
        """
        Returns top_k memories ranked by hybrid score.

        candidate_pool: how many to fetch from each channel before fusion.
                       Default 40 = 4xtop_k (standard practice).
        dense_weight / sparse_weight: integer multipliers on contribution to RRF.
                                       Default 1:1 (equal weighting).
        """
        # ---------- Dense channel ----------
        dense_distance = Memory.embedding.cosine_distance(query_embedding)
        dense_stmt = (
            select(Memory.id, dense_distance.label("d"))
            .where(and_(
                Memory.project_id == project_id,
                Memory.namespace == namespace,
                Memory.embedding.is_not(None),
            ))
            .order_by(dense_distance)
            .limit(candidate_pool)
        )
        dense_result = await db.execute(dense_stmt)
        dense_ranking = [row.id for row in dense_result]

        # ---------- Sparse channel (tsvector with OR-semantics for natural-language queries) ----------
        # plainto_tsquery defaults to AND between lexemes, which fails for queries
        # like "how do I fix error PG-2087" because 'fix' describes user intent, not
        # document content. We convert AND -> OR so the channel ranks by overlap
        # via ts_rank_cd rather than filtering by completeness. The dense channel
        # carries semantic match; sparse is for lexical/identifier anchoring.
        sparse_stmt = text("""
            WITH q AS (
                SELECT NULLIF(
                    regexp_replace(plainto_tsquery('english', :q)::text, ' & ', ' | ', 'g'),
                    ''
                )::tsquery AS tsq
            )
            SELECT m.id
            FROM memories m, q
            WHERE q.tsq IS NOT NULL
              AND m.project_id = :pid
              AND m.namespace = :ns
              AND m.content_tsv @@ q.tsq
            ORDER BY ts_rank_cd(m.content_tsv, q.tsq) DESC
            LIMIT :pool
        """).bindparams(q=query, pid=project_id, ns=namespace, pool=candidate_pool)
        sparse_result = await db.execute(sparse_stmt)
        sparse_ranking = [row.id for row in sparse_result]

        # ---------- RRF fusion (channel weights = integer copies) ----------
        rankings = (
            [dense_ranking] * max(1, dense_weight)
            + [sparse_ranking] * max(1, sparse_weight)
        )
        scores = reciprocal_rank_fusion(rankings, k=rrf_k)

        # ---------- Hydrate top_k ----------
        top_ids = [
            mid for mid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        ]
        if not top_ids:
            return []
        hydrate = await db.execute(select(Memory).where(Memory.id.in_(top_ids)))
        by_id = {m.id: m for m in hydrate.scalars()}
        return [(by_id[mid], scores[mid]) for mid in top_ids if mid in by_id]
