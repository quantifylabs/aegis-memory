"""
Backfill script: migrate shared_with_agents JSON → memory_shared_agents join table.

Idempotent: uses INSERT ... ON CONFLICT DO NOTHING.
Safe to run multiple times or interrupt and resume.

Usage:
    python server/backfill_acl.py

Requires DATABASE_URL environment variable.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add server directory to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_acl")

BATCH_SIZE = 500


async def backfill():
    """Backfill memory_shared_agents from shared_with_agents JSON column."""
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    database_url = os.environ.get("DATABASE_URL", "postgresql://aegis:aegis@localhost:5432/aegis")
    url = database_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Count memories with shared_with_agents
        result = await db.execute(text(
            "SELECT COUNT(*) FROM memories WHERE shared_with_agents::text != '[]' AND shared_with_agents::text != 'null'"
        ))
        total = result.scalar()
        logger.info(f"Found {total} memories with shared_with_agents to backfill")

        if total == 0:
            logger.info("Nothing to backfill")
            return {"total": 0, "inserted": 0}

        # Process in batches
        offset = 0
        total_inserted = 0

        while offset < total:
            result = await db.execute(text("""
                SELECT id, project_id, namespace, shared_with_agents
                FROM memories
                WHERE shared_with_agents::text != '[]' AND shared_with_agents::text != 'null'
                ORDER BY id
                LIMIT :limit OFFSET :offset
            """), {"limit": BATCH_SIZE, "offset": offset})

            rows = result.fetchall()
            if not rows:
                break

            batch_inserted = 0
            for row in rows:
                memory_id, project_id, namespace, shared_agents = row
                if not shared_agents or not isinstance(shared_agents, list):
                    continue

                for agent_id in shared_agents:
                    if not agent_id:
                        continue
                    try:
                        await db.execute(text("""
                            INSERT INTO memory_shared_agents (memory_id, shared_agent_id, project_id, namespace)
                            VALUES (:memory_id, :shared_agent_id, :project_id, :namespace)
                            ON CONFLICT DO NOTHING
                        """), {
                            "memory_id": memory_id,
                            "shared_agent_id": agent_id,
                            "project_id": project_id,
                            "namespace": namespace,
                        })
                        batch_inserted += 1
                    except Exception as e:
                        logger.warning(f"Error backfilling memory {memory_id} agent {agent_id}: {e}")

            await db.commit()
            total_inserted += batch_inserted
            offset += BATCH_SIZE
            logger.info(f"Processed {min(offset, total)}/{total} memories ({total_inserted} rows inserted)")

    await engine.dispose()
    logger.info(f"Backfill complete: {total_inserted} rows inserted from {total} memories")
    return {"total": total, "inserted": total_inserted}


if __name__ == "__main__":
    asyncio.run(backfill())
