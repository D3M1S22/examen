"""Storage factory module for EXAMEN.

``get_storage_store()`` returns the store of the current tenant (src/core/tenancy.py): each user has
a private SQLite file under ``EXAMEN_DATA_DIR/users/<user_id>/examen.db`` or, with
``STORAGE_BACKEND=dynamo``, a private DynamoDB partition (docs/next_steps/dynamodb_storage/). With no
tenant (CLI scripts, tests, ``AUTH_ENABLED=false``) it returns the legacy single-user store.
"""

import threading
from typing import Dict, Optional

from src.core.config import Settings, settings
from src.core.storage.base import AbstractContextStore
from src.core.storage.sqlite_store import SQLiteContextStore
from src.core.tenancy import resolve_tenant, tenant_db_path

_store_instance: Optional[AbstractContextStore] = None
_tenant_stores: Dict[str, AbstractContextStore] = {}
_tenant_lock = threading.Lock()


def cfg_backend() -> str:
    return settings.storage_backend.lower()


def _build_store(cfg: Settings, user_id: Optional[str]) -> AbstractContextStore:
    """``user_id`` None: the legacy single-user store (``SQLITE_DB_PATH`` / DynamoDB partition ``_local``)."""
    backend = cfg.storage_backend.lower()
    if backend == "dynamo":
        from src.core.storage.dynamo_store import DynamoContextStore

        return DynamoContextStore(user_id=user_id)
    if backend == "agentcore_memory":
        # Placeholder for AgentCoreMemoryStore (Stage 2 Cloud): actorId = user_id
        raise NotImplementedError("AgentCore Memory storage backend will be activated in Stage 2 Cloud.")
    return SQLiteContextStore(db_path=tenant_db_path(user_id) if user_id else cfg.sqlite_db_path)


def get_tenant_store(user_id: str, custom_settings: Optional[Settings] = None) -> AbstractContextStore:
    """The private store of ``user_id`` (created on first use)."""
    with _tenant_lock:
        store = _tenant_stores.get(user_id)
        if store is None:
            store = _build_store(custom_settings or settings, user_id)
            _tenant_stores[user_id] = store
        return store


def drop_tenant_store(user_id: str) -> None:
    """Forgets a cached tenant store (before its folder is deleted)."""
    with _tenant_lock:
        store = _tenant_stores.pop(user_id, None)
    if cfg_backend() == "dynamo":
        from src.core.storage.dynamo_client import drop_tenant_client

        drop_tenant_client(user_id)
    close = getattr(store, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def get_storage_store(custom_settings: Optional[Settings] = None) -> AbstractContextStore:
    """Return the store of the current tenant, or the legacy singleton in single-user mode.

    With accounts enabled and no tenant in context it raises ``MissingTenant`` (fail-closed)."""
    tenant = resolve_tenant()
    if tenant is not None:
        return get_tenant_store(tenant, custom_settings)

    global _store_instance
    if _store_instance is not None:
        return _store_instance
    cfg = custom_settings or settings
    _store_instance = _build_store(cfg, None)
    return _store_instance


__all__ = ["AbstractContextStore", "SQLiteContextStore", "get_storage_store", "get_tenant_store", "drop_tenant_store"]
