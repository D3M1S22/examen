"""Storage factory module for EXAMEN.

``get_storage_store()`` returns the store of the current tenant (src/core/tenancy.py): each user has
a private SQLite file under ``EXAMEN_DATA_DIR/users/<user_id>/examen.db``. With no tenant (CLI
scripts, tests, ``AUTH_ENABLED=false``) it returns the legacy single-user store at ``SQLITE_DB_PATH``.
"""

import threading
from typing import Dict, Optional

from src.core.config import Settings, settings
from src.core.storage.base import AbstractContextStore
from src.core.storage.sqlite_store import SQLiteContextStore
from src.core.tenancy import get_tenant_id, tenant_db_path

_store_instance: Optional[AbstractContextStore] = None
_tenant_stores: Dict[str, AbstractContextStore] = {}
_tenant_lock = threading.Lock()


def _build_store(cfg: Settings, db_path: str) -> AbstractContextStore:
    backend = cfg.storage_backend.lower()
    if backend == "dynamo":
        # Placeholder for DynamoDBContextStore (Stage 2 Cloud): partition key = user_id
        raise NotImplementedError("DynamoDB storage backend will be activated in Stage 2 Cloud.")
    if backend == "agentcore_memory":
        # Placeholder for AgentCoreMemoryStore (Stage 2 Cloud): actorId = user_id
        raise NotImplementedError("AgentCore Memory storage backend will be activated in Stage 2 Cloud.")
    return SQLiteContextStore(db_path=db_path)


def get_tenant_store(user_id: str, custom_settings: Optional[Settings] = None) -> AbstractContextStore:
    """The private store of ``user_id`` (created on first use)."""
    with _tenant_lock:
        store = _tenant_stores.get(user_id)
        if store is None:
            store = _build_store(custom_settings or settings, tenant_db_path(user_id))
            _tenant_stores[user_id] = store
        return store


def drop_tenant_store(user_id: str) -> None:
    """Forgets a cached tenant store (before its folder is deleted)."""
    with _tenant_lock:
        store = _tenant_stores.pop(user_id, None)
    close = getattr(store, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def get_storage_store(custom_settings: Optional[Settings] = None) -> AbstractContextStore:
    """Return the store of the current tenant, or the legacy singleton when there is none."""
    tenant = get_tenant_id()
    if tenant is not None:
        return get_tenant_store(tenant, custom_settings)

    global _store_instance
    if _store_instance is not None:
        return _store_instance
    cfg = custom_settings or settings
    _store_instance = _build_store(cfg, cfg.sqlite_db_path)
    return _store_instance


__all__ = ["AbstractContextStore", "SQLiteContextStore", "get_storage_store", "get_tenant_store", "drop_tenant_store"]
