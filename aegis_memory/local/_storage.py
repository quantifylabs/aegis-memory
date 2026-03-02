"""
Local storage engine for Aegis Memory.

SQLite + numpy cosine similarity. Thread-safe writes via Lock.
WAL mode for concurrent reads.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import numpy as np

from ._integrity import compute_integrity_hash
from ._schema import ensure_schema
from ._scope import infer_scope
from ._temporal import rerank_with_decay


def _uid() -> str:
    return uuid.uuid4().hex[:32]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def _json_loads(s: str | None) -> Any:
    if s is None:
        return None
    return json.loads(s)


def _cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Batch cosine similarity between a query vector and a matrix of vectors."""
    if matrix.shape[0] == 0:
        return np.array([], dtype=np.float32)
    # Normalize
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    matrix_norm = matrix / norms
    return matrix_norm @ query_norm


def _embedding_to_blob(emb: np.ndarray) -> bytes:
    return emb.astype(np.float32).tobytes()


def _blob_to_embedding(blob: bytes, dims: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).copy()


def _row_to_memory_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a SQLite row to a memory dict matching client model fields."""
    d = dict(row)
    d["metadata"] = _json_loads(d.get("metadata", "{}")) or {}
    d["shared_with_agents"] = _json_loads(d.get("shared_with_agents", "[]")) or []
    d["derived_from_agents"] = _json_loads(d.get("derived_from_agents", "[]")) or []
    d["coordination_metadata"] = _json_loads(d.get("coordination_metadata", "{}")) or {}
    d["content_flags"] = _json_loads(d.get("content_flags", "[]")) or []
    d.pop("embedding", None)
    d.pop("is_deprecated", None)
    return d


class LocalStorage:
    """
    Core local storage engine: SQLite + numpy vector search.

    Thread-safe: writes protected by Lock, reads are concurrent (WAL mode).
    """

    def __init__(
        self,
        db_path: str | Path,
        signing_key: str = "aegis-local-default-key",
        embedding_dims: int = 384,
    ):
        self.db_path = str(db_path)
        self.signing_key = signing_key
        self.embedding_dims = embedding_dims
        self._write_lock = threading.Lock()

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    # ========================================================================
    # Embedding Cache
    # ========================================================================

    def get_cached_embedding(self, content: str, model: str) -> Optional[np.ndarray]:
        ch = _content_hash(content)
        row = self._conn.execute(
            "SELECT embedding, dimensions FROM embedding_cache WHERE content_hash = ? AND model = ?",
            (ch, model),
        ).fetchone()
        if row:
            self._conn.execute(
                "UPDATE embedding_cache SET hit_count = hit_count + 1 WHERE content_hash = ?",
                (ch,),
            )
            self._conn.commit()
            return _blob_to_embedding(row["embedding"], row["dimensions"])
        return None

    def cache_embedding(self, content: str, embedding: np.ndarray, model: str) -> None:
        ch = _content_hash(content)
        with self._write_lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO embedding_cache (content_hash, embedding, model, dimensions) "
                "VALUES (?, ?, ?, ?)",
                (ch, _embedding_to_blob(embedding), model, len(embedding)),
            )
            self._conn.commit()

    # ========================================================================
    # Core Memory Operations
    # ========================================================================

    def add_memory(
        self,
        content: str,
        embedding: np.ndarray,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        scope: Optional[str] = None,
        shared_with_agents: Optional[List[str]] = None,
        derived_from_agents: Optional[List[str]] = None,
        coordination_metadata: Optional[Dict[str, Any]] = None,
        memory_type: str = "standard",
    ) -> Dict[str, Any]:
        """Add a single memory. Returns dict with id, deduped_from, inferred_scope."""
        ch = _content_hash(content)
        metadata = metadata or {}

        # Dedup check
        existing = self._conn.execute(
            "SELECT id FROM memories WHERE content_hash = ? AND namespace = ? AND is_deprecated = 0",
            (ch, namespace),
        ).fetchone()
        if existing:
            return {
                "id": existing["id"],
                "deduped_from": existing["id"],
                "inferred_scope": scope,
            }

        # Scope inference
        inferred = infer_scope(
            content,
            explicit_scope=scope,
            agent_id=agent_id,
            metadata=metadata,
        )

        # Integrity hash
        integrity = compute_integrity_hash(content, agent_id, self.signing_key)

        # TTL
        expires_at = None
        if ttl_seconds:
            from datetime import timedelta
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()

        mem_id = _uid()
        now = _now_iso()

        with self._write_lock:
            self._conn.execute(
                """INSERT INTO memories (
                    id, user_id, agent_id, namespace, memory_type, content, content_hash,
                    embedding, metadata, scope, shared_with_agents, derived_from_agents,
                    coordination_metadata, created_at, updated_at, expires_at,
                    integrity_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mem_id, user_id, agent_id, namespace, memory_type, content, ch,
                    _embedding_to_blob(embedding),
                    _json_dumps(metadata), inferred,
                    _json_dumps(shared_with_agents or []),
                    _json_dumps(derived_from_agents or []),
                    _json_dumps(coordination_metadata or {}),
                    now, now, expires_at, integrity,
                ),
            )
            self._conn.commit()

        return {"id": mem_id, "deduped_from": None, "inferred_scope": inferred}

    def add_batch(
        self,
        items: List[Dict[str, Any]],
        embeddings: List[np.ndarray],
    ) -> List[Dict[str, Any]]:
        """Add multiple memories. Returns list of add results."""
        results = []
        for item, emb in zip(items, embeddings):
            r = self.add_memory(
                content=item["content"],
                embedding=emb,
                user_id=item.get("user_id"),
                agent_id=item.get("agent_id"),
                namespace=item.get("namespace", "default"),
                metadata=item.get("metadata"),
                ttl_seconds=item.get("ttl_seconds"),
                scope=item.get("scope"),
                shared_with_agents=item.get("shared_with_agents"),
                derived_from_agents=item.get("derived_from_agents"),
                coordination_metadata=item.get("coordination_metadata"),
            )
            results.append(r)
        return results

    def semantic_search(
        self,
        query_embedding: np.ndarray,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        namespace: str = "default",
        top_k: int = 10,
        min_score: float = 0.0,
        apply_decay: bool = False,
        memory_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search via numpy cosine similarity.

        Returns list of memory dicts with 'score' field added.
        """
        # Build filter query
        conditions = ["namespace = ?", "is_deprecated = 0"]
        params: list = [namespace]

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if agent_id:
            conditions.append("(agent_id = ? OR scope = 'global')")
            params.append(agent_id)
        if memory_types:
            placeholders = ",".join("?" * len(memory_types))
            conditions.append(f"memory_type IN ({placeholders})")
            params.extend(memory_types)

        where = " AND ".join(conditions)

        rows = self._conn.execute(
            f"SELECT *, embedding FROM memories WHERE {where}",
            params,
        ).fetchall()

        if not rows:
            return []

        # Build embedding matrix
        ids_and_rows = []
        emb_list = []
        for row in rows:
            if row["embedding"] is None:
                continue
            ids_and_rows.append(row)
            emb_list.append(_blob_to_embedding(row["embedding"], self.embedding_dims))

        if not emb_list:
            return []

        matrix = np.vstack(emb_list)
        scores = _cosine_similarity(query_embedding, matrix)

        # Filter by min_score and sort
        results = []
        for i, score in enumerate(scores):
            if score >= min_score:
                mem_dict = _row_to_memory_dict(ids_and_rows[i])
                mem_dict["score"] = float(score)
                results.append(mem_dict)

        if apply_decay and results:
            pairs = [(m, m["score"]) for m in results]
            reranked = rerank_with_decay(pairs)
            results = []
            for mem, sem_score, decay in reranked:
                mem["score"] = sem_score * decay
                results.append(mem)
        else:
            results.sort(key=lambda m: m["score"], reverse=True)

        # Update access tracking for returned results
        returned_ids = [r["id"] for r in results[:top_k]]
        if returned_ids:
            now = _now_iso()
            placeholders = ",".join("?" * len(returned_ids))
            with self._write_lock:
                self._conn.execute(
                    f"UPDATE memories SET last_accessed_at = ?, access_count = access_count + 1 "
                    f"WHERE id IN ({placeholders})",
                    [now] + returned_ids,
                )
                self._conn.commit()

        return results[:top_k]

    def cross_agent_search(
        self,
        query_embedding: np.ndarray,
        requesting_agent_id: str,
        *,
        target_agent_ids: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        namespace: str = "default",
        top_k: int = 10,
        min_score: float = 0.0,
        apply_decay: bool = False,
    ) -> List[Dict[str, Any]]:
        """Cross-agent search with scope-aware ACL filtering."""
        conditions = ["namespace = ?", "is_deprecated = 0"]
        params: list = [namespace]

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if target_agent_ids:
            placeholders = ",".join("?" * len(target_agent_ids))
            conditions.append(f"agent_id IN ({placeholders})")
            params.extend(target_agent_ids)

        where = " AND ".join(conditions)

        rows = self._conn.execute(
            f"SELECT *, embedding FROM memories WHERE {where}",
            params,
        ).fetchall()

        if not rows:
            return []

        # ACL filter + build matrix
        ids_and_rows = []
        emb_list = []
        for row in rows:
            if row["embedding"] is None:
                continue
            if not self._can_access(row, requesting_agent_id):
                continue
            ids_and_rows.append(row)
            emb_list.append(_blob_to_embedding(row["embedding"], self.embedding_dims))

        if not emb_list:
            return []

        matrix = np.vstack(emb_list)
        scores = _cosine_similarity(query_embedding, matrix)

        results = []
        for i, score in enumerate(scores):
            if score >= min_score:
                mem_dict = _row_to_memory_dict(ids_and_rows[i])
                mem_dict["score"] = float(score)
                results.append(mem_dict)

        if apply_decay and results:
            pairs = [(m, m["score"]) for m in results]
            reranked = rerank_with_decay(pairs)
            results = []
            for mem, sem_score, decay in reranked:
                mem["score"] = sem_score * decay
                results.append(mem)
        else:
            results.sort(key=lambda m: m["score"], reverse=True)

        return results[:top_k]

    def _can_access(self, row: sqlite3.Row, requesting_agent_id: str) -> bool:
        """Scope-aware ACL check."""
        scope = row["scope"]
        if scope == "global":
            return True
        if scope == "agent-private":
            return row["agent_id"] == requesting_agent_id
        if scope == "agent-shared":
            if row["agent_id"] == requesting_agent_id:
                return True
            shared = _json_loads(row["shared_with_agents"]) or []
            return requesting_agent_id in shared
        return False

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a single memory by ID."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return None
        return _row_to_memory_dict(row)

    def delete_memory(self, memory_id: str) -> bool:
        """Hard delete a memory."""
        with self._write_lock:
            cursor = self._conn.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    # ========================================================================
    # ACE: Voting
    # ========================================================================

    def vote(
        self,
        memory_id: str,
        vote: Literal["helpful", "harmful"],
        voter_agent_id: str,
        *,
        context: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cast a vote on a memory."""
        with self._write_lock:
            if vote == "helpful":
                self._conn.execute(
                    "UPDATE memories SET bullet_helpful = bullet_helpful + 1, updated_at = ? WHERE id = ?",
                    (_now_iso(), memory_id),
                )
            else:
                self._conn.execute(
                    "UPDATE memories SET bullet_harmful = bullet_harmful + 1, updated_at = ? WHERE id = ?",
                    (_now_iso(), memory_id),
                )

            self._conn.execute(
                "INSERT INTO vote_history (id, memory_id, voter_agent_id, vote, context, task_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_uid(), memory_id, voter_agent_id, vote, context, task_id),
            )
            self._conn.commit()

        row = self._conn.execute(
            "SELECT bullet_helpful, bullet_harmful FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()

        helpful = row["bullet_helpful"]
        harmful = row["bullet_harmful"]
        total = helpful + harmful
        effectiveness = (helpful - harmful) / (total + 1) if total > 0 else 0.0

        return {
            "memory_id": memory_id,
            "bullet_helpful": helpful,
            "bullet_harmful": harmful,
            "effectiveness_score": effectiveness,
        }

    # ========================================================================
    # ACE: Delta Updates
    # ========================================================================

    def apply_delta(
        self,
        operations: List[Dict[str, Any]],
        embed_fn,
    ) -> Dict[str, Any]:
        """
        Apply delta operations (add, update, deprecate).

        embed_fn: callable that takes a string and returns np.ndarray
        """
        start = time.monotonic()
        results = []

        for op in operations:
            op_type = op.get("type")
            try:
                if op_type == "add":
                    embedding = embed_fn(op["content"])
                    r = self.add_memory(
                        content=op["content"],
                        embedding=embedding,
                        agent_id=op.get("agent_id"),
                        namespace=op.get("namespace", "default"),
                        metadata=op.get("metadata"),
                        scope=op.get("scope"),
                        memory_type=op.get("memory_type", "standard"),
                    )
                    results.append({
                        "operation": "add",
                        "success": True,
                        "memory_id": r["id"],
                    })

                elif op_type == "update":
                    mem_id = op["memory_id"]
                    patch = op.get("metadata_patch", {})
                    with self._write_lock:
                        row = self._conn.execute(
                            "SELECT metadata FROM memories WHERE id = ?", (mem_id,)
                        ).fetchone()
                        if row:
                            existing = _json_loads(row["metadata"]) or {}
                            existing.update(patch)
                            self._conn.execute(
                                "UPDATE memories SET metadata = ?, updated_at = ? WHERE id = ?",
                                (_json_dumps(existing), _now_iso(), mem_id),
                            )
                            self._conn.commit()
                    results.append({
                        "operation": "update",
                        "success": True,
                        "memory_id": mem_id,
                    })

                elif op_type == "deprecate":
                    mem_id = op["memory_id"]
                    now = _now_iso()
                    with self._write_lock:
                        self._conn.execute(
                            "UPDATE memories SET is_deprecated = 1, deprecated_at = ?, "
                            "deprecated_by = ?, superseded_by = ?, updated_at = ? WHERE id = ?",
                            (
                                now,
                                op.get("agent_id"),
                                op.get("superseded_by"),
                                now,
                                mem_id,
                            ),
                        )
                        self._conn.commit()
                    results.append({
                        "operation": "deprecate",
                        "success": True,
                        "memory_id": mem_id,
                    })
                else:
                    results.append({
                        "operation": str(op_type),
                        "success": False,
                        "error": f"Unknown operation type: {op_type}",
                    })

            except Exception as e:
                results.append({
                    "operation": str(op_type),
                    "success": False,
                    "error": str(e),
                })

        elapsed = (time.monotonic() - start) * 1000
        return {"results": results, "total_time_ms": elapsed}

    # ========================================================================
    # ACE: Reflections
    # ========================================================================

    def add_reflection(
        self,
        content: str,
        embedding: np.ndarray,
        agent_id: str,
        *,
        user_id: Optional[str] = None,
        namespace: str = "default",
        source_trajectory_id: Optional[str] = None,
        error_pattern: Optional[str] = None,
        correct_approach: Optional[str] = None,
        applicable_contexts: Optional[List[str]] = None,
        scope: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a reflection memory."""
        meta = metadata or {}
        if correct_approach:
            meta["correct_approach"] = correct_approach
        if applicable_contexts:
            meta["applicable_contexts"] = applicable_contexts

        result = self.add_memory(
            content=content,
            embedding=embedding,
            user_id=user_id,
            agent_id=agent_id,
            namespace=namespace,
            metadata=meta,
            scope=scope or "global",
            memory_type="reflection",
        )

        # Update reflection-specific fields
        if source_trajectory_id or error_pattern:
            with self._write_lock:
                self._conn.execute(
                    "UPDATE memories SET source_trajectory_id = ?, error_pattern = ? WHERE id = ?",
                    (source_trajectory_id, error_pattern, result["id"]),
                )
                self._conn.commit()

        return result["id"]

    # ========================================================================
    # ACE: Playbook
    # ========================================================================

    def query_playbook(
        self,
        query_embedding: np.ndarray,
        agent_id: str,
        *,
        namespace: str = "default",
        include_types: Optional[List[str]] = None,
        top_k: int = 20,
        min_effectiveness: float = -1.0,
    ) -> Dict[str, Any]:
        """Query playbook for strategies and reflections."""
        start = time.monotonic()
        types = include_types or ["strategy", "reflection"]

        results = self.semantic_search(
            query_embedding,
            agent_id=agent_id,
            namespace=namespace,
            top_k=top_k * 2,  # Over-fetch for filtering
            min_score=0.0,
            memory_types=types,
        )

        entries = []
        for m in results:
            helpful = m.get("bullet_helpful", 0)
            harmful = m.get("bullet_harmful", 0)
            total = helpful + harmful
            effectiveness = (helpful - harmful) / (total + 1) if total > 0 else 0.0

            if effectiveness >= min_effectiveness:
                entries.append({
                    "id": m["id"],
                    "content": m["content"],
                    "memory_type": m.get("memory_type", "standard"),
                    "effectiveness_score": effectiveness,
                    "bullet_helpful": helpful,
                    "bullet_harmful": harmful,
                    "error_pattern": m.get("error_pattern"),
                    "created_at": m["created_at"],
                })

        elapsed = (time.monotonic() - start) * 1000
        return {"entries": entries[:top_k], "query_time_ms": elapsed}

    # ========================================================================
    # Session Progress
    # ========================================================================

    def create_session(
        self,
        session_id: str,
        *,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Create a new session."""
        sid = _uid()
        now = _now_iso()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO session_progress
                (id, session_id, agent_id, user_id, namespace, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid, session_id, agent_id, user_id, namespace, now, now),
            )
            self._conn.commit()
        return self._get_session_dict(session_id)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by session_id."""
        return self._get_session_dict(session_id)

    def update_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """Update session fields."""
        row = self._conn.execute(
            "SELECT * FROM session_progress WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Session not found: {session_id}")

        updates = []
        params = []

        simple_fields = ["in_progress_item", "summary", "last_action", "status", "total_items"]
        for field in simple_fields:
            if field in kwargs and kwargs[field] is not None:
                updates.append(f"{field} = ?")
                params.append(kwargs[field])

        # JSON array fields - merge
        if kwargs.get("completed_items"):
            existing = _json_loads(row["completed_items"]) or []
            merged = list(set(existing + kwargs["completed_items"]))
            updates.append("completed_items = ?")
            params.append(_json_dumps(merged))
            updates.append("completed_count = ?")
            params.append(len(merged))

        if kwargs.get("next_items") is not None:
            updates.append("next_items = ?")
            params.append(_json_dumps(kwargs["next_items"]))

        if kwargs.get("blocked_items") is not None:
            updates.append("blocked_items = ?")
            params.append(_json_dumps(kwargs["blocked_items"]))

        updates.append("updated_at = ?")
        params.append(_now_iso())
        params.append(session_id)

        with self._write_lock:
            self._conn.execute(
                f"UPDATE session_progress SET {', '.join(updates)} WHERE session_id = ?",
                params,
            )
            self._conn.commit()

        return self._get_session_dict(session_id)

    def _get_session_dict(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM session_progress WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None

        d = dict(row)
        completed_items = _json_loads(d.get("completed_items", "[]")) or []
        total = d.get("total_items", 0) or 0
        completed_count = len(completed_items)
        progress = (completed_count / total * 100) if total > 0 else 0.0

        return {
            "id": d["id"],
            "session_id": d["session_id"],
            "status": d.get("status", "active"),
            "completed_count": completed_count,
            "total_items": total,
            "progress_percent": round(progress, 1),
            "completed_items": completed_items,
            "in_progress_item": d.get("in_progress_item"),
            "next_items": _json_loads(d.get("next_items", "[]")) or [],
            "blocked_items": _json_loads(d.get("blocked_items", "[]")) or [],
            "summary": d.get("summary"),
            "last_action": d.get("last_action"),
            "updated_at": d.get("updated_at", d.get("created_at")),
        }

    # ========================================================================
    # Feature Tracking
    # ========================================================================

    def create_feature(
        self,
        feature_id: str,
        description: str,
        *,
        session_id: Optional[str] = None,
        namespace: str = "default",
        category: Optional[str] = None,
        test_steps: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        fid = _uid()
        now = _now_iso()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO feature_tracker
                (id, session_id, namespace, feature_id, category, description,
                 test_steps, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fid, session_id, namespace, feature_id, category, description,
                 _json_dumps(test_steps or []), now, now),
            )
            self._conn.commit()
        return self._get_feature_dict(feature_id, namespace)

    def get_feature(self, feature_id: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        return self._get_feature_dict(feature_id, namespace)

    def update_feature(
        self, feature_id: str, namespace: str = "default", **kwargs
    ) -> Dict[str, Any]:
        updates = []
        params = []

        for field in ["status", "passes", "implemented_by", "verified_by",
                       "implementation_notes", "failure_reason"]:
            if field in kwargs and kwargs[field] is not None:
                updates.append(f"{field} = ?")
                if field == "passes":
                    params.append(1 if kwargs[field] else 0)
                else:
                    params.append(kwargs[field])

        updates.append("updated_at = ?")
        params.append(_now_iso())
        params.extend([feature_id, namespace])

        with self._write_lock:
            self._conn.execute(
                f"UPDATE feature_tracker SET {', '.join(updates)} "
                f"WHERE feature_id = ? AND namespace = ?",
                params,
            )
            self._conn.commit()

        return self._get_feature_dict(feature_id, namespace)

    def list_features(
        self,
        *,
        namespace: str = "default",
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        conditions = ["namespace = ?"]
        params: list = [namespace]
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM feature_tracker WHERE {where}", params
        ).fetchall()

        features = [self._feature_row_to_dict(r) for r in rows]
        passing = sum(1 for f in features if f["passes"])
        failing = sum(1 for f in features if f["status"] == "failed")
        in_progress = sum(1 for f in features if f["status"] == "in_progress")

        return {
            "features": features,
            "total": len(features),
            "passing": passing,
            "failing": failing,
            "in_progress": in_progress,
        }

    def _get_feature_dict(self, feature_id: str, namespace: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM feature_tracker WHERE feature_id = ? AND namespace = ?",
            (feature_id, namespace),
        ).fetchone()
        if not row:
            return None
        return self._feature_row_to_dict(row)

    def _feature_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        return {
            "id": d["id"],
            "feature_id": d["feature_id"],
            "description": d["description"],
            "category": d.get("category"),
            "status": d.get("status", "not_started"),
            "passes": bool(d.get("passes", 0)),
            "test_steps": _json_loads(d.get("test_steps", "[]")) or [],
            "implemented_by": d.get("implemented_by"),
            "verified_by": d.get("verified_by"),
            "updated_at": d.get("updated_at", d.get("created_at")),
        }

    # ========================================================================
    # ACE: Run Tracking
    # ========================================================================

    def start_run(
        self,
        run_id: str,
        agent_id: Optional[str] = None,
        *,
        task_type: Optional[str] = None,
        namespace: str = "default",
        memory_ids_used: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        rid = _uid()
        now = _now_iso()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO ace_runs
                (id, run_id, agent_id, task_type, namespace, memory_ids_used,
                 started_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, run_id, agent_id, task_type, namespace,
                 _json_dumps(memory_ids_used or []), now, now, now),
            )
            self._conn.commit()
        return self._get_run_dict(run_id)

    def complete_run(
        self,
        run_id: str,
        *,
        success: bool,
        evaluation: Optional[Dict[str, Any]] = None,
        logs: Optional[Dict[str, Any]] = None,
        auto_vote: bool = True,
        auto_reflect: bool = True,
        embed_fn=None,
    ) -> Dict[str, Any]:
        now = _now_iso()
        with self._write_lock:
            self._conn.execute(
                """UPDATE ace_runs SET
                    status = 'completed', success = ?, evaluation = ?, logs = ?,
                    completed_at = ?, updated_at = ?
                WHERE run_id = ?""",
                (
                    1 if success else 0,
                    _json_dumps(evaluation or {}),
                    _json_dumps(logs or {}),
                    now, now, run_id,
                ),
            )
            self._conn.commit()

        # Auto-vote on memories used
        if auto_vote:
            run = self._get_run_dict(run_id)
            if run:
                vote_type = "helpful" if success else "harmful"
                for mem_id in run.get("memory_ids_used", []):
                    try:
                        self.vote(mem_id, vote_type, run.get("agent_id") or "system")
                    except Exception:
                        pass

        # Auto-reflect on failure
        if auto_reflect and not success and embed_fn:
            run = self._get_run_dict(run_id)
            if run:
                reflection = (
                    f"Run {run_id} failed. Task type: {run.get('task_type', 'unknown')}. "
                    f"Evaluation: {json.dumps(evaluation or {})}."
                )
                emb = embed_fn(reflection)
                self.add_reflection(
                    content=reflection,
                    embedding=emb,
                    agent_id=run.get("agent_id") or "system",
                    namespace=run.get("namespace", "default"),
                    error_pattern="run_failure",
                )

        return self._get_run_dict(run_id)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._get_run_dict(run_id)

    def _get_run_dict(self, run_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM ace_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        return {
            "run_id": d["run_id"],
            "status": d.get("status", "running"),
            "success": bool(d["success"]) if d["success"] is not None else None,
            "agent_id": d.get("agent_id"),
            "task_type": d.get("task_type"),
            "namespace": d.get("namespace", "default"),
            "evaluation": _json_loads(d.get("evaluation", "{}")) or {},
            "logs": _json_loads(d.get("logs", "{}")) or {},
            "memory_ids_used": _json_loads(d.get("memory_ids_used", "[]")) or [],
            "reflection_ids": _json_loads(d.get("reflection_ids", "[]")) or [],
            "started_at": d.get("started_at"),
            "completed_at": d.get("completed_at"),
            "created_at": d.get("created_at"),
            "updated_at": d.get("updated_at"),
        }

    # ========================================================================
    # Curation
    # ========================================================================

    def curate(
        self,
        *,
        namespace: str = "default",
        agent_id: Optional[str] = None,
        top_k: int = 10,
        min_effectiveness_threshold: float = -0.3,
    ) -> Dict[str, Any]:
        """Identify promoted, flagged, and consolidation candidates."""
        conditions = ["namespace = ?", "is_deprecated = 0"]
        params: list = [namespace]
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM memories WHERE {where}", params
        ).fetchall()

        promoted = []
        flagged = []
        for row in rows:
            d = _row_to_memory_dict(row)
            helpful = d.get("bullet_helpful", 0)
            harmful = d.get("bullet_harmful", 0)
            total = helpful + harmful
            if total == 0:
                continue
            effectiveness = (helpful - harmful) / (total + 1)
            entry = {
                "id": d["id"],
                "content": d["content"],
                "memory_type": d.get("memory_type", "standard"),
                "effectiveness_score": effectiveness,
                "bullet_helpful": helpful,
                "bullet_harmful": harmful,
                "total_votes": total,
            }
            if effectiveness >= 0.3:
                promoted.append(entry)
            elif effectiveness < min_effectiveness_threshold:
                flagged.append(entry)

        promoted.sort(key=lambda x: x["effectiveness_score"], reverse=True)
        flagged.sort(key=lambda x: x["effectiveness_score"])

        return {
            "promoted": promoted[:top_k],
            "flagged": flagged[:top_k],
            "consolidation_candidates": [],
        }

    # ========================================================================
    # Handoff
    # ========================================================================

    def handoff(
        self,
        source_agent_id: str,
        target_agent_id: str,
        *,
        namespace: str = "default",
        user_id: Optional[str] = None,
        task_context: Optional[str] = None,
        max_memories: int = 20,
        query_embedding: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Generate handoff baton."""
        conditions = ["namespace = ?", "is_deprecated = 0", "agent_id = ?"]
        params: list = [namespace, source_agent_id]
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM memories WHERE {where} ORDER BY updated_at DESC LIMIT ?",
            params + [max_memories * 2],
        ).fetchall()

        memories = [_row_to_memory_dict(r) for r in rows]

        # If we have a task_context embedding, rank by relevance
        if query_embedding is not None and rows:
            emb_list = []
            valid_rows = []
            for row in rows:
                if row["embedding"]:
                    emb_list.append(_blob_to_embedding(row["embedding"], self.embedding_dims))
                    valid_rows.append(row)

            if emb_list:
                matrix = np.vstack(emb_list)
                scores = _cosine_similarity(query_embedding, matrix)
                scored = [(_row_to_memory_dict(valid_rows[i]), float(scores[i]))
                          for i in range(len(valid_rows))]
                scored.sort(key=lambda x: x[1], reverse=True)
                memories = [m for m, _ in scored]

        memories = memories[:max_memories]

        key_facts = [m["content"] for m in memories if m.get("memory_type") == "standard"][:5]
        recent_decisions = [m["content"] for m in memories
                          if m.get("memory_type") in ("strategy", "reflection")][:5]

        return {
            "source_agent_id": source_agent_id,
            "target_agent_id": target_agent_id,
            "namespace": namespace,
            "user_id": user_id,
            "task_context": task_context,
            "summary": f"Handoff from {source_agent_id} to {target_agent_id} with {len(memories)} memories",
            "active_tasks": [],
            "blocked_on": [],
            "recent_decisions": recent_decisions,
            "key_facts": key_facts,
            "memory_ids": [m["id"] for m in memories],
        }

    # ========================================================================
    # Interaction Events
    # ========================================================================

    def record_interaction(
        self,
        session_id: str,
        content: str,
        *,
        agent_id: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        parent_event_id: Optional[str] = None,
        namespace: str = "default",
        extra_metadata: Optional[Dict[str, Any]] = None,
        embed: bool = False,
        embedding: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        eid = _uid()
        now = _now_iso()
        emb_blob = _embedding_to_blob(embedding) if embedding is not None else None

        with self._write_lock:
            self._conn.execute(
                """INSERT INTO interaction_events
                (event_id, session_id, agent_id, content, timestamp, tool_calls,
                 parent_event_id, namespace, extra_metadata, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eid, session_id, agent_id, content, now,
                    _json_dumps(tool_calls or []),
                    parent_event_id, namespace,
                    _json_dumps(extra_metadata) if extra_metadata else None,
                    emb_blob,
                ),
            )
            self._conn.commit()

        return {
            "event_id": eid,
            "session_id": session_id,
            "namespace": namespace,
            "has_embedding": embedding is not None,
        }

    def get_session_interactions(
        self,
        session_id: str,
        *,
        namespace: str = "default",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        rows = self._conn.execute(
            """SELECT * FROM interaction_events
            WHERE session_id = ? AND namespace = ?
            ORDER BY timestamp ASC LIMIT ? OFFSET ?""",
            (session_id, namespace, limit, offset),
        ).fetchall()

        events = [self._interaction_row_to_dict(r) for r in rows]
        return {
            "session_id": session_id,
            "namespace": namespace,
            "events": events,
            "count": len(events),
        }

    def get_agent_interactions(
        self,
        agent_id: str,
        *,
        namespace: str = "default",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        rows = self._conn.execute(
            """SELECT * FROM interaction_events
            WHERE agent_id = ? AND namespace = ?
            ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
            (agent_id, namespace, limit, offset),
        ).fetchall()

        events = [self._interaction_row_to_dict(r) for r in rows]
        return {
            "agent_id": agent_id,
            "namespace": namespace,
            "events": events,
            "count": len(events),
        }

    def search_interactions(
        self,
        query_embedding: np.ndarray,
        *,
        namespace: str = "default",
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        start = time.monotonic()
        conditions = ["namespace = ?", "embedding IS NOT NULL"]
        params: list = [namespace]
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"SELECT * FROM interaction_events WHERE {where}", params
        ).fetchall()

        if not rows:
            return {"results": [], "query_time_ms": 0}

        emb_list = []
        valid_rows = []
        for row in rows:
            if row["embedding"]:
                emb_list.append(_blob_to_embedding(row["embedding"], self.embedding_dims))
                valid_rows.append(row)

        if not emb_list:
            return {"results": [], "query_time_ms": 0}

        matrix = np.vstack(emb_list)
        scores = _cosine_similarity(query_embedding, matrix)

        results = []
        for i, score in enumerate(scores):
            if score >= min_score:
                results.append({
                    "event": self._interaction_row_to_dict(valid_rows[i]),
                    "score": float(score),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        elapsed = (time.monotonic() - start) * 1000
        return {"results": results[:top_k], "query_time_ms": elapsed}

    def get_interaction_chain(self, event_id: str) -> Dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM interaction_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if not row:
            return {"event": None, "chain": [], "chain_depth": 0}

        event = self._interaction_row_to_dict(row)

        # Walk up the chain
        chain = []
        current_id = row["parent_event_id"]
        depth = 0
        while current_id and depth < 100:
            parent = self._conn.execute(
                "SELECT * FROM interaction_events WHERE event_id = ?", (current_id,)
            ).fetchone()
            if not parent:
                break
            chain.insert(0, self._interaction_row_to_dict(parent))
            current_id = parent["parent_event_id"]
            depth += 1

        chain.append(event)
        return {"event": event, "chain": chain, "chain_depth": len(chain)}

    def _interaction_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        return {
            "event_id": d["event_id"],
            "project_id": "local",
            "session_id": d["session_id"],
            "agent_id": d.get("agent_id"),
            "content": d.get("content"),
            "timestamp": d.get("timestamp"),
            "tool_calls": _json_loads(d.get("tool_calls", "[]")) or [],
            "parent_event_id": d.get("parent_event_id"),
            "namespace": d.get("namespace", "default"),
            "extra_metadata": _json_loads(d.get("extra_metadata")) if d.get("extra_metadata") else None,
            "has_embedding": d.get("embedding") is not None,
        }

    # ========================================================================
    # Export
    # ========================================================================

    def export_json(
        self,
        *,
        namespace: Optional[str] = None,
        agent_id: Optional[str] = None,
        include_embeddings: bool = False,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Export memories as a dict (caller writes to file)."""
        conditions = ["is_deprecated = 0"]
        params: list = []
        if namespace:
            conditions.append("namespace = ?")
            params.append(namespace)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM memories WHERE {where} ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {int(limit)}"

        rows = self._conn.execute(query, params).fetchall()

        memories = []
        namespaces = set()
        agents = set()
        for row in rows:
            m = _row_to_memory_dict(row)
            if not include_embeddings:
                m.pop("embedding", None)
            memories.append(m)
            namespaces.add(m.get("namespace", "default"))
            if m.get("agent_id"):
                agents.add(m["agent_id"])

        return {
            "memories": memories,
            "stats": {
                "total_exported": len(memories),
                "namespaces": list(namespaces),
                "agents": list(agents),
            },
        }
