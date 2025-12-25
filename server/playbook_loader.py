"""
Aegis Playbook Loader

Auto-loads pre-seeded strategies and reflections from genesis.json
when the database is empty. This solves the "cold start" problem.

Usage:
    from playbook_loader import load_genesis_playbook
    
    # In startup
    await load_genesis_playbook(db)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import Memory, MemoryType, MemoryScope
from embedding_service import get_embedding_service, content_hash

logger = logging.getLogger("aegis.playbook_loader")

# Default paths to check for genesis.json
GENESIS_PATHS = [
    Path("/app/playbooks/genesis.json"),      # Docker mounted
    Path("./playbooks/genesis.json"),          # Local dev
    Path("../playbooks/genesis.json"),         # From server dir
]

# System project ID for genesis entries
GENESIS_PROJECT_ID = "__aegis_genesis__"


async def count_memories(db: AsyncSession) -> int:
    """Count total memories in database."""
    result = await db.execute(select(func.count(Memory.id)))
    return result.scalar() or 0


async def count_genesis_memories(db: AsyncSession) -> int:
    """Count memories from genesis playbook."""
    result = await db.execute(
        select(func.count(Memory.id)).where(
            Memory.project_id == GENESIS_PROJECT_ID
        )
    )
    return result.scalar() or 0


def find_genesis_file() -> Optional[Path]:
    """Find the genesis.json file."""
    for path in GENESIS_PATHS:
        if path.exists():
            return path
    return None


async def load_genesis_playbook(
    db: AsyncSession,
    force: bool = False,
    genesis_path: Optional[Path] = None
) -> dict:
    """
    Load genesis playbook entries into the database.
    
    Args:
        db: Database session
        force: If True, load even if genesis entries already exist
        genesis_path: Optional explicit path to genesis.json
    
    Returns:
        Dict with loading statistics
    """
    stats = {
        "loaded": 0,
        "skipped": 0,
        "errors": 0,
        "already_exists": False
    }
    
    # Check if genesis already loaded
    existing_count = await count_genesis_memories(db)
    if existing_count > 0 and not force:
        logger.info(f"Genesis playbook already loaded ({existing_count} entries). Skipping.")
        stats["already_exists"] = True
        stats["skipped"] = existing_count
        return stats
    
    # Find genesis file
    genesis_file = genesis_path or find_genesis_file()
    if not genesis_file or not genesis_file.exists():
        logger.warning("Genesis playbook not found. Skipping preload.")
        return stats
    
    logger.info(f"Loading genesis playbook from {genesis_file}")
    
    # Parse genesis file
    try:
        with open(genesis_file, "r") as f:
            genesis_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse genesis.json: {e}")
        stats["errors"] = 1
        return stats
    
    entries = genesis_data.get("entries", [])
    if not entries:
        logger.warning("Genesis playbook has no entries")
        return stats
    
    logger.info(f"Found {len(entries)} genesis entries to load")
    
    # Get embedding service
    embed_service = get_embedding_service()
    
    # Load entries in batches
    batch_size = 10
    for i in range(0, len(entries), batch_size):
        batch = entries[i:i + batch_size]
        
        # Batch embed
        contents = [e["content"] for e in batch]
        try:
            embeddings = await embed_service.embed_batch(contents, db)
        except Exception as e:
            logger.error(f"Failed to embed batch: {e}")
            stats["errors"] += len(batch)
            continue
        
        # Create memories
        for j, entry in enumerate(batch):
            try:
                content = entry["content"]
                memory_type = entry.get("memory_type", MemoryType.STRATEGY.value)
                namespace = entry.get("namespace", "aegis/genesis")
                metadata = entry.get("metadata", {})
                error_pattern = entry.get("error_pattern")
                
                # Add genesis marker to metadata
                metadata["_genesis"] = True
                metadata["_genesis_version"] = genesis_data.get("metadata", {}).get("version", "1.0.0")
                
                # Check for duplicate content
                c_hash = content_hash(content)
                existing = await db.execute(
                    select(Memory).where(
                        Memory.content_hash == c_hash,
                        Memory.project_id == GENESIS_PROJECT_ID
                    )
                )
                if existing.scalar_one_or_none():
                    stats["skipped"] += 1
                    continue
                
                # Create memory
                from ace_repository import generate_id
                memory = Memory(
                    id=generate_id(),
                    project_id=GENESIS_PROJECT_ID,
                    content=content,
                    content_hash=c_hash,
                    embedding=embeddings[j],
                    namespace=namespace,
                    scope=MemoryScope.GLOBAL.value,  # Genesis entries are always global
                    memory_type=memory_type,
                    metadata_json=metadata,
                    error_pattern=error_pattern,
                    # Genesis entries start with credibility
                    bullet_helpful=3,
                    bullet_harmful=0,
                )
                
                db.add(memory)
                stats["loaded"] += 1
                
            except Exception as e:
                logger.error(f"Failed to load genesis entry: {e}")
                stats["errors"] += 1
        
        # Commit batch
        try:
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to commit batch: {e}")
            await db.rollback()
            stats["errors"] += len(batch)
            stats["loaded"] -= len(batch)
    
    logger.info(
        f"Genesis playbook loaded: {stats['loaded']} entries, "
        f"{stats['skipped']} skipped, {stats['errors']} errors"
    )
    
    return stats


async def get_genesis_entries(
    db: AsyncSession,
    memory_type: Optional[str] = None,
    namespace_prefix: Optional[str] = None,
    limit: int = 100
) -> list:
    """
    Query genesis entries.
    
    Useful for debugging and verifying genesis content.
    """
    from sqlalchemy import and_
    
    conditions = [Memory.project_id == GENESIS_PROJECT_ID]
    
    if memory_type:
        conditions.append(Memory.memory_type == memory_type)
    
    if namespace_prefix:
        conditions.append(Memory.namespace.startswith(namespace_prefix))
    
    result = await db.execute(
        select(Memory)
        .where(and_(*conditions))
        .order_by(Memory.namespace, Memory.created_at)
        .limit(limit)
    )
    
    return list(result.scalars().all())


# CLI for manual loading
if __name__ == "__main__":
    import asyncio
    import sys
    
    async def main():
        from database import init_db, async_session_factory
        
        print("Initializing database...")
        await init_db()
        
        async with async_session_factory() as db:
            force = "--force" in sys.argv
            stats = await load_genesis_playbook(db, force=force)
            print(f"Results: {stats}")
    
    asyncio.run(main())
