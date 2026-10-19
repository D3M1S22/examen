"""Account store (``EXAMEN_DATA_DIR/auth.db``): users, browser sessions and MCP access tokens.

Only what is needed to authenticate is kept here (GDPR data minimisation): a normalised email, a
scrypt password hash, an optional display name and the privacy-notice consent. Everything the user
produces lives in their own tenant database (src/core/tenancy.py).

Secrets are stored as SHA-256 digests only: a leaked auth.db reveals no usable session or token.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.core.auth.passwords import dummy_verify, hash_password, needs_rehash, verify_password
from src.core.config import settings
from src.core.tenancy import data_root

SESSION_TOKEN_BYTES = 32
API_TOKEN_PREFIX = "exm_"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_plausible_email(email: str) -> bool:
    if not email or len(email) > 254 or email.count("@") != 1:
        return False
    local, domain = email.split("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".") and " " not in email


class User(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    created_at: str
    last_login_at: Optional[str] = None
    privacy_consent_version: Optional[str] = None
    privacy_consent_at: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        return self.model_dump()


class ApiToken(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: str
    last_used_at: Optional[str] = None


class AuthError(Exception):
    """Raised with a message that is safe to show to the user."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class AuthStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            root = data_root()
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            db_path = str(root / "auth.db")
        else:
            Path(db_path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    password_changed_at TEXT,
                    privacy_consent_version TEXT,
                    privacy_consent_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    prefix TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens (user_id);
                """
            )
        try:
            Path(self.db_path).chmod(0o600)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    @staticmethod
    def _user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"], email=row["email"], display_name=row["display_name"], created_at=row["created_at"],
            last_login_at=row["last_login_at"], privacy_consent_version=row["privacy_consent_version"],
            privacy_consent_at=row["privacy_consent_at"],
        )

    def create_user(self, email: str, password: str, display_name: Optional[str] = None,
                    consent_version: Optional[str] = None) -> User:
        from src.core.auth.passwords import password_problem

        email = normalize_email(email)
        if not is_plausible_email(email):
            raise AuthError("Enter a valid email address.")
        problem = password_problem(password, email, settings.auth_min_password_length)
        if problem:
            raise AuthError(problem)
        name = (display_name or "").strip()[:60] or None
        now = iso(utcnow())
        user_id = f"usr_{uuid.uuid4().hex}"
        pw_hash = hash_password(password)
        with self._lock, self._conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, display_name, created_at, password_changed_at,"
                    " privacy_consent_version, privacy_consent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, email, pw_hash, name, now, now, consent_version, now if consent_version else None),
                )
            except sqlite3.IntegrityError:
                raise AuthError("An account with this email already exists.", status=409)
        return self.get_user(user_id)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> Optional[User]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
        return self._user(row) if row else None

    def list_users(self) -> List[User]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [self._user(r) for r in rows]

    def count_users(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """Returns the user when the credentials match. Timing does not reveal unknown emails."""
        email = normalize_email(email)
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            dummy_verify(password or "")
            return None
        if not verify_password(password or "", row["password_hash"]):
            return None
        now = iso(utcnow())
        with self._lock, self._conn() as conn:
            if needs_rehash(row["password_hash"]):
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), row["id"]))
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        return self.get_user(row["id"])

    def verify_user_password(self, user_id: str, password: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        return bool(row) and verify_password(password or "", row["password_hash"])

    def set_password(self, user_id: str, new_password: str) -> None:
        from src.core.auth.passwords import password_problem

        user = self.get_user(user_id)
        if user is None:
            raise AuthError("Account not found.", status=404)
        problem = password_problem(new_password, user.email, settings.auth_min_password_length)
        if problem:
            raise AuthError(problem)
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
                (hash_password(new_password), iso(utcnow()), user_id),
            )

    def update_profile(self, user_id: str, display_name: Optional[str]) -> Optional[User]:
        name = (display_name or "").strip()[:60] or None
        with self._lock, self._conn() as conn:
            conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
        return self.get_user(user_id)

    def record_consent(self, user_id: str, version: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE users SET privacy_consent_version = ?, privacy_consent_at = ? WHERE id = ?",
                (version, iso(utcnow()), user_id),
            )

    def delete_user(self, user_id: str) -> bool:
        """Deletes the account row; sessions and tokens cascade."""
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Browser sessions
    # ------------------------------------------------------------------

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        now = utcnow()
        expires = now + timedelta(hours=settings.auth_session_ttl_hours)
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (iso(now),))
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (digest(token), user_id, iso(now), iso(expires), iso(now)),
            )
        return token

    def user_for_session(self, token: Optional[str]) -> Optional[User]:
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (digest(token),)
            ).fetchone()
        if row is None or row["expires_at"] < iso(utcnow()):
            return None
        return self.get_user(row["user_id"])

    def revoke_session(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token),))

    def revoke_user_sessions(self, user_id: str, keep_token: Optional[str] = None) -> int:
        with self._lock, self._conn() as conn:
            if keep_token:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, digest(keep_token))
                )
            else:
                cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            return cur.rowcount

    # ------------------------------------------------------------------
    # MCP / API access tokens (Alexa+, MCP clients)
    # ------------------------------------------------------------------

    def create_api_token(self, user_id: str, name: str) -> Dict[str, Any]:
        """Returns the token in clear text once; only its digest is stored."""
        secret = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = ApiToken(
            id=f"tok_{uuid.uuid4().hex[:16]}", name=(name or "MCP client").strip()[:60] or "MCP client",
            prefix=secret[:10], created_at=iso(utcnow()),
        )
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO api_tokens (id, token_hash, user_id, name, prefix, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (token.id, digest(secret), user_id, token.name, token.prefix, token.created_at),
            )
        return {"token": secret, **token.model_dump()}

    def list_api_tokens(self, user_id: str) -> List[ApiToken]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, prefix, created_at, last_used_at FROM api_tokens WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [ApiToken(**dict(r)) for r in rows]

    def revoke_api_token(self, user_id: str, token_id: str) -> bool:
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM api_tokens WHERE id = ? AND user_id = ?", (token_id, user_id))
            return cur.rowcount > 0

    def user_for_api_token(self, secret: Optional[str]) -> Optional[User]:
        if not secret or not secret.startswith(API_TOKEN_PREFIX):
            return None
        with self._conn() as conn:
            row = conn.execute("SELECT id, user_id FROM api_tokens WHERE token_hash = ?", (digest(secret),)).fetchone()
        if row is None:
            return None
        with self._lock, self._conn() as conn:
            conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (iso(utcnow()), row["id"]))
        return self.get_user(row["user_id"])


_auth_store: Optional[AuthStore] = None
_auth_lock = threading.Lock()


def get_auth_store() -> AuthStore:
    global _auth_store
    with _auth_lock:
        if _auth_store is None:
            _auth_store = AuthStore()
        return _auth_store


def reset_auth_store(store: Optional[AuthStore] = None) -> None:
    """Test seam: replace (or forget) the process-wide store."""
    global _auth_store
    with _auth_lock:
        _auth_store = store
