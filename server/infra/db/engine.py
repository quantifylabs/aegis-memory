"""Database engine creation and management.

Re-exports from the existing database module for the new package structure.
"""
from database import (
    _create_engine,
    primary_engine,
    replica_engine,
    init_db,
    check_db_health,
)

__all__ = [
    "_create_engine",
    "primary_engine",
    "replica_engine",
    "init_db",
    "check_db_health",
]
