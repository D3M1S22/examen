"""System DB: user-agnostic records needed before a user is known (docs/next_steps/multi_user/02 §1).

Users, web sessions, personal access tokens, Bee links and the security audit log. Speech-derived
data never lives here: it is in each user's scoped store (``StoreRegistry.for_user``).
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.schemas import ApiTokenInfo, BeeLink, UserAccount

_USER_FIELDS = ("username", "display_name", "password_hash", "external_sub", "is_admin", "status",
                "timezone", "last_login_at")
_BEE_FIELDS = ("state", "bee_user_id", "bee_first_name", "pairing_url", "pairing_expires_at", "linked_at",
               "last_ok_at", "last_error")


def _now() -> str:
    return datetime.now().isoformat()


class SystemStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT,
                    password_hash TEXT,
                    external_sub TEXT UNIQUE,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    timezone TEXT,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS web_sessions (
                    session_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    user_agent TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_web_sessions_user ON web_sessions (user_id);
                CREATE TABLE IF NOT EXISTS api_tokens (
                    token_hash TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    scopes TEXT NOT NULL DEFAULT 'mcp',
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens (user_id);
                CREATE TABLE IF NOT EXISTS bee_links (
                    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    state TEXT NOT NULL DEFAULT 'unlinked',
                    bee_user_id INTEGER UNIQUE,
                    bee_first_name TEXT,
                    pairing_url TEXT,
                    pairing_expires_at TEXT,
                    linked_at TEXT,
                    last_ok_at TEXT,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    user_id TEXT,
                    actor_user_id TEXT,
                    action TEXT NOT NULL,
                    detail_json TEXT
                );
            """)

    # ------------------------------------------------------------------ users

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> UserAccount:
        return UserAccount(
            user_id=row["user_id"], username=row["username"], display_name=row["display_name"],
            is_admin=bool(row["is_admin"]), status=row["status"], timezone=row["timezone"],
            external_sub=row["external_sub"], created_at=row["created_at"], last_login_at=row["last_login_at"],
        )

    def create_user(self, user_id: str, username: str, password_hash: Optional[str], *,
                    display_name: Optional[str] = None, is_admin: bool = False,
                    external_sub: Optional[str] = None) -> UserAccount:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO users (user_id, username, display_name, password_hash, external_sub, is_admin, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, display_name, password_hash, external_sub, int(is_admin), _now()),
            )
        return self.get_user(user_id)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[UserAccount]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return self._row_to_user(row) if row else None

    def get_password_hash(self, user_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["password_hash"] if row else None

    def list_users(self) -> List[UserAccount]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [self._row_to_user(r) for r in rows]

    def count_users(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def count_admins(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]

    def update_user(self, user_id: str, **fields: Any) -> None:
        cols = [k for k in fields if k in _USER_FIELDS]
        if not cols:
            return
        values = [int(fields[k]) if k == "is_admin" else fields[k] for k in cols]
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE users SET {', '.join(f'{c} = ?' for c in cols)} WHERE user_id = ?",
                         (*values, user_id))

    def delete_user(self, user_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # --------------------------------------------------------------- sessions

    def create_session(self, session_hash: str, user_id: str, expires_at: str, user_agent: Optional[str]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO web_sessions (session_hash, user_id, created_at, expires_at, user_agent) VALUES (?, ?, ?, ?, ?)",
                (session_hash, user_id, _now(), expires_at, (user_agent or "")[:200]),
            )

    def get_session(self, session_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM web_sessions WHERE session_hash = ? AND revoked = 0", (session_hash,)
            ).fetchone()
        return dict(row) if row else None

    def extend_session(self, session_hash: str, expires_at: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE web_sessions SET expires_at = ? WHERE session_hash = ?", (expires_at, session_hash))

    def revoke_session(self, session_hash: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE web_sessions SET revoked = 1 WHERE session_hash = ?", (session_hash,))

    def revoke_user_sessions(self, user_id: str) -> int:
        with self._lock, self._connect() as conn:
            return conn.execute("UPDATE web_sessions SET revoked = 1 WHERE user_id = ? AND revoked = 0",
                                (user_id,)).rowcount

    def purge_expired_sessions(self, now_iso: Optional[str] = None) -> int:
        with self._lock, self._connect() as conn:
            return conn.execute("DELETE FROM web_sessions WHERE expires_at < ? OR revoked = 1",
                                (now_iso or _now(),)).rowcount

    # ------------------------------------------------------------- api tokens

    @staticmethod
    def _row_to_token(row: sqlite3.Row) -> ApiTokenInfo:
        return ApiTokenInfo(token_id=row["token_id"], user_id=row["user_id"], name=row["name"], scopes=row["scopes"],
                            created_at=row["created_at"], last_used_at=row["last_used_at"], revoked=bool(row["revoked"]))

    def create_api_token(self, token_hash: str, token_id: str, user_id: str, name: str, scopes: str = "mcp") -> ApiTokenInfo:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO api_tokens (token_hash, token_id, user_id, name, scopes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (token_hash, token_id, user_id, name, scopes, _now()),
            )
            row = conn.execute("SELECT * FROM api_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
        return self._row_to_token(row)

    def get_api_token(self, token_hash: str) -> Optional[ApiTokenInfo]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM api_tokens WHERE token_hash = ? AND revoked = 0", (token_hash,)).fetchone()
        return self._row_to_token(row) if row else None

    def touch_api_token(self, token_hash: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE token_hash = ?", (_now(), token_hash))

    def list_api_tokens(self, user_id: str) -> List[ApiTokenInfo]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM api_tokens WHERE user_id = ? AND revoked = 0 ORDER BY created_at",
                                (user_id,)).fetchall()
        return [self._row_to_token(r) for r in rows]

    def revoke_api_token(self, user_id: str, token_id: str) -> bool:
        with self._lock, self._connect() as conn:
            return conn.execute("UPDATE api_tokens SET revoked = 1 WHERE user_id = ? AND token_id = ? AND revoked = 0",
                                (user_id, token_id)).rowcount > 0

    def revoke_user_tokens(self, user_id: str) -> int:
        with self._lock, self._connect() as conn:
            return conn.execute("UPDATE api_tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0",
                                (user_id,)).rowcount

    # -------------------------------------------------------------- bee links

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> BeeLink:
        return BeeLink(**{k: row[k] for k in ("user_id",) + _BEE_FIELDS})

    def get_bee_link(self, user_id: str) -> BeeLink:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM bee_links WHERE user_id = ?", (user_id,)).fetchone()
        return self._row_to_link(row) if row else BeeLink(user_id=user_id)

    def find_bee_link_by_bee_user(self, bee_user_id: int) -> Optional[BeeLink]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM bee_links WHERE bee_user_id = ?", (bee_user_id,)).fetchone()
        return self._row_to_link(row) if row else None

    def save_bee_link(self, link: BeeLink) -> None:
        values = [getattr(link, f) for f in _BEE_FIELDS]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"INSERT INTO bee_links (user_id, {', '.join(_BEE_FIELDS)}) VALUES (?, {', '.join('?' * len(_BEE_FIELDS))}) "
                f"ON CONFLICT(user_id) DO UPDATE SET {', '.join(f'{f} = excluded.{f}' for f in _BEE_FIELDS)}",
                (link.user_id, *values),
            )

    def list_bee_links(self, state: Optional[str] = None) -> List[BeeLink]:
        sql, params = "SELECT * FROM bee_links", ()
        if state:
            sql, params = sql + " WHERE state = ?", (state,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_link(r) for r in rows]

    def delete_bee_link(self, user_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM bee_links WHERE user_id = ?", (user_id,))

    # ------------------------------------------------------------------ audit

    def audit(self, action: str, user_id: Optional[str] = None, actor_user_id: Optional[str] = None,
              detail: Optional[Dict[str, Any]] = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (at, user_id, actor_user_id, action, detail_json) VALUES (?, ?, ?, ?, ?)",
                (_now(), user_id, actor_user_id, action, json.dumps(detail or {}, ensure_ascii=False)),
            )

    def list_audit(self, limit: int = 100, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql, params = "SELECT * FROM audit_log", []
        if user_id:
            sql += " WHERE user_id = ?"
            params.append(user_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
