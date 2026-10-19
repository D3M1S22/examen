"""Storage factory: scoped per-user stores and the System DB (docs/next_steps/multi_user/03 §2).

Every user has their own store; ``get_storage_store()`` returns the store of the user in the current
``UserContext`` (request or per-user runtime) and fails closed without one. User-agnostic records
(users, sessions, tokens, Bee links, audit) live in ``StoreRegistry.system()``.

Layout (SQLite): ``<EXAMEN_DATA_DIR>/system.db`` and ``<EXAMEN_DATA_DIR>/users/<user_id>/{examen.db, bee/}``.
"""

import os
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional

from src.core.config import Settings, settings
from src.core.identity import MissingUserContext, get_current_user, is_valid_user_id
from src.core.storage.base import AbstractContextStore
from src.core.storage.sqlite_store import SQLiteContextStore
from src.core.storage.system_store import SystemStore

# Test seam only: a store pinned here is returned for every user (tests that predate multi-user).
_store_instance: Optional[AbstractContextStore] = None


class StoreRegistry:
    def __init__(self, data_dir: str, backend: str = "sqlite"):
        self.data_dir = Path(data_dir)
        self.backend = backend.lower()
        if self.backend in ("dynamo", "agentcore_memory"):
            raise NotImplementedError(f"{self.backend} storage backend will be activated in Stage 2 Cloud.")
        self._lock = threading.RLock()
        self._stores: Dict[str, AbstractContextStore] = {}
        self._system: Optional[SystemStore] = None

    def system(self) -> SystemStore:
        with self._lock:
            if self._system is None:
                self._system = SystemStore(str(self.data_dir / "system.db"))
            return self._system

    def user_dir(self, user_id: str) -> Path:
        if not is_valid_user_id(user_id):
            raise ValueError(f"Invalid user id: {user_id!r}")
        return self.data_dir / "users" / user_id

    def bee_config_dir(self, user_id: str) -> Path:
        """Per-user BEE_CONFIG_DIR (mode 0700): the user's Bee token and pairing state."""
        path = self.user_dir(user_id) / "bee"
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        return path

    def for_user(self, user_id: str) -> AbstractContextStore:
        with self._lock:
            store = self._stores.get(user_id)
            if store is None:
                directory = self.user_dir(user_id)
                directory.mkdir(parents=True, exist_ok=True)
                store = SQLiteContextStore(db_path=str(directory / "examen.db"))
                self._stores[user_id] = store
            return store

    def drop_user(self, user_id: str) -> None:
        """Deletes every file of a user (GDPR erasure). The user's runtime must be stopped first."""
        with self._lock:
            self._stores.pop(user_id, None)
            directory = self.user_dir(user_id)
            if directory.exists():
                shutil.rmtree(directory)


_registry: Optional[StoreRegistry] = None
_registry_lock = threading.Lock()


def get_store_registry(custom_settings: Optional[Settings] = None) -> StoreRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            cfg = custom_settings or settings
            _registry = StoreRegistry(cfg.examen_data_dir, cfg.storage_backend)
        return _registry


def reset_store_registry(registry: Optional[StoreRegistry] = None) -> None:
    """Replaces the process registry (tests, data-dir changes)."""
    global _registry
    with _registry_lock:
        _registry = registry


def get_system_store() -> SystemStore:
    return get_store_registry().system()


def get_storage_store(custom_settings: Optional[Settings] = None, user_id: Optional[str] = None) -> AbstractContextStore:
    """The scoped store of ``user_id`` or, by default, of the user in the current context."""
    if _store_instance is not None:
        return _store_instance
    uid = user_id
    if uid is None:
        ctx = get_current_user()
        if ctx is None:
            raise MissingUserContext("No user context: user data cannot be accessed")
        uid = ctx.user_id
    return get_store_registry(custom_settings).for_user(uid)


__all__ = [
    "AbstractContextStore", "SQLiteContextStore", "StoreRegistry", "SystemStore",
    "get_storage_store", "get_store_registry", "get_system_store", "reset_store_registry",
]
