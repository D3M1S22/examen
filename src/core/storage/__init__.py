"""Storage factory module for EXAMEN."""

from typing import Optional
from src.core.config import Settings, settings
from src.core.storage.base import AbstractContextStore
from src.core.storage.sqlite_store import SQLiteContextStore

_store_instance: Optional[AbstractContextStore] = None


def get_storage_store(custom_settings: Optional[Settings] = None) -> AbstractContextStore:
    """Return a singleton instance of the configured context store."""
    global _store_instance
    if _store_instance is not None:
        return _store_instance

    cfg = custom_settings or settings
    backend = cfg.storage_backend.lower()

    if backend == "sqlite":
        _store_instance = SQLiteContextStore(db_path=cfg.sqlite_db_path)
    elif backend == "dynamo":
        # Placeholder per DynamoDBContextStore (Fase 2 Cloud)
        raise NotImplementedError("DynamoDB storage backend verrà attivato in Fase 2 Cloud.")
    elif backend == "agentcore_memory":
        # Placeholder per AgentCoreMemoryStore (Fase 2 Cloud)
        raise NotImplementedError("AgentCore Memory storage backend verrà attivato in Fase 2 Cloud.")
    else:
        # Default di fallback su SQLite
        _store_instance = SQLiteContextStore(db_path=cfg.sqlite_db_path)

    return _store_instance


__all__ = ["AbstractContextStore", "SQLiteContextStore", "get_storage_store"]
