"""Authentication for the dashboard, REST, SSE and MCP (docs/next_steps/multi_user/02 §2, 04 §1).

``LocalAuthProvider`` (homelab / local): username + password (Argon2id), server-side sessions in an
``HttpOnly`` cookie, personal access tokens (``Authorization: Bearer exm_pat_…``) for MCP clients.
``AuthMiddleware`` resolves a ``UserContext`` for every protected path and sets ``current_user_ctx``,
which also reaches MCP tool calls (the SDK forwards the request context).
"""

import hashlib
import json
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from typing import Dict, List, Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from src.core.config import settings
from src.core.identity import UserContext, current_user_ctx
from src.core.schemas import ApiTokenInfo, UserAccount
from src.core.storage import SystemStore, get_system_store

logger = logging.getLogger("examen.serving.auth")

SESSION_COOKIE = "examen_session"
PAT_PREFIX = "exm_pat_"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "examen"
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
MIN_PASSWORD_LENGTH = 12
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES_PER_USER = 5
LOGIN_MAX_FAILURES_PER_IP = 20

# Paths reachable without a user (the dashboard bundle must load to show the sign-in form)
PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/session", "/api/health"}

_hasher = PasswordHasher()


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_user_id() -> str:
    return f"usr_{secrets.token_hex(8)}"


def validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError("weak_password", f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


class LocalAuthProvider:
    def __init__(self, store_getter=get_system_store, clock=time.time):
        self._store_getter = store_getter
        self.clock = clock
        self._failures: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    @property
    def store(self) -> SystemStore:
        return self._store_getter()

    # ---------------------------------------------------------------- users

    def create_user(self, username: str, password: str, *, display_name: Optional[str] = None,
                    is_admin: bool = False) -> UserAccount:
        username = (username or "").strip()
        if not USERNAME_RE.match(username):
            raise AuthError("invalid_username", "Username: 3-32 letters, digits, '.', '_' or '-'")
        validate_password(password)
        if self.store.get_user_by_username(username):
            raise AuthError("username_taken", "Username already exists", status=409)
        user = self.store.create_user(new_user_id(), username, _hasher.hash(password),
                                      display_name=display_name or username, is_admin=is_admin)
        self.store.audit("user_created", user_id=user.user_id, detail={"is_admin": is_admin})
        return user

    def set_password(self, user_id: str, new_password: str) -> None:
        validate_password(new_password)
        self.store.update_user(user_id, password_hash=_hasher.hash(new_password))
        self.store.revoke_user_sessions(user_id)
        self.store.audit("password_changed", user_id=user_id)

    def verify_password(self, user_id: str, password: str) -> bool:
        stored = self.store.get_password_hash(user_id)
        if not stored:
            return False
        try:
            _hasher.verify(stored, password or "")
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        if _hasher.check_needs_rehash(stored):
            self.store.update_user(user_id, password_hash=_hasher.hash(password))
        return True

    def ensure_bootstrap_admin(self) -> Optional[str]:
        """First start with no users: creates ``EXAMEN_BOOTSTRAP_ADMIN``. Returns a generated password."""
        username = settings.examen_bootstrap_admin
        if not username or self.store.count_users() > 0:
            return None
        password = settings.examen_bootstrap_admin_password or secrets.token_urlsafe(12)
        self.create_user(username, password, is_admin=True)
        if settings.examen_bootstrap_admin_password:
            logger.warning(f"Bootstrap admin '{username}' created")
            return None
        logger.warning(f"Bootstrap admin '{username}' created with one-time password: {password} (change it after login)")
        return password

    # -------------------------------------------------------------- sessions

    def _rate_limited(self, *keys: str) -> bool:
        now = self.clock()
        with self._lock:
            for key in keys:
                recent = [t for t in self._failures.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
                self._failures[key] = recent
                limit = LOGIN_MAX_FAILURES_PER_IP if key.startswith("ip:") else LOGIN_MAX_FAILURES_PER_USER
                if len(recent) >= limit:
                    return True
        return False

    def _record_failure(self, *keys: str) -> None:
        now = self.clock()
        with self._lock:
            for key in keys:
                self._failures.setdefault(key, []).append(now)

    def login(self, username: str, password: str, *, ip: str = "", user_agent: str = "") -> Tuple[UserAccount, str]:
        keys = (f"user:{(username or '').lower()}", f"ip:{ip}")
        if self._rate_limited(*keys):
            raise AuthError("rate_limited", "Too many failed attempts, try again later", status=429)
        user = self.store.get_user_by_username((username or "").strip())
        if user is None or user.status != "active" or not self.verify_password(user.user_id, password):
            self._record_failure(*keys)
            if user is not None:
                self.store.audit("login_failed", user_id=user.user_id, detail={"ip": ip})
            raise AuthError("invalid_credentials", "Invalid username or password", status=401)
        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(days=settings.auth_session_days)
        self.store.create_session(secret_hash(token), user.user_id, expires.isoformat(), user_agent)
        self.store.update_user(user.user_id, last_login_at=datetime.now().isoformat())
        self.store.audit("login", user_id=user.user_id, detail={"ip": ip})
        return user, token

    def authenticate_session(self, token: str) -> Optional[UserContext]:
        if not token:
            return None
        h = secret_hash(token)
        session = self.store.get_session(h)
        if session is None:
            return None
        now = datetime.now()
        expires = datetime.fromisoformat(session["expires_at"])
        if expires <= now:
            self.store.revoke_session(h)
            return None
        user = self.store.get_user(session["user_id"])
        if user is None or user.status != "active":
            return None
        # Sliding expiry: extend once less than half of the lifetime is left
        lifetime = timedelta(days=settings.auth_session_days)
        if expires - now < lifetime / 2:
            self.store.extend_session(h, (now + lifetime).isoformat())
        return UserContext(user_id=user.user_id, is_admin=user.is_admin, auth_method="session")

    def logout(self, token: str) -> None:
        if token:
            self.store.revoke_session(secret_hash(token))

    def revoke_everything(self, user_id: str) -> None:
        self.store.revoke_user_sessions(user_id)
        self.store.revoke_user_tokens(user_id)
        self.store.audit("sessions_revoked", user_id=user_id)

    # ------------------------------------------------------------ api tokens

    def create_api_token(self, user_id: str, name: str) -> Tuple[str, ApiTokenInfo]:
        name = (name or "").strip()[:60] or "MCP client"
        raw = PAT_PREFIX + secrets.token_urlsafe(32)
        info = self.store.create_api_token(secret_hash(raw), f"tok_{secrets.token_hex(6)}", user_id, name)
        self.store.audit("api_token_created", user_id=user_id, detail={"token_id": info.token_id, "name": name})
        return raw, info

    def authenticate_bearer(self, token: str) -> Optional[UserContext]:
        if not token or not token.startswith(PAT_PREFIX):
            return None
        h = secret_hash(token)
        info = self.store.get_api_token(h)
        if info is None:
            return None
        user = self.store.get_user(info.user_id)
        if user is None or user.status != "active":
            return None
        self.store.touch_api_token(h)
        return UserContext(user_id=user.user_id, is_admin=False, auth_method="api_token")


_provider: Optional[LocalAuthProvider] = None


def get_auth_provider() -> LocalAuthProvider:
    global _provider
    if _provider is None:
        if settings.auth_provider.lower() != "local":
            raise NotImplementedError(f"AUTH_PROVIDER={settings.auth_provider} is planned for the AWS stage")
        _provider = LocalAuthProvider()
    return _provider


def reset_auth_provider(provider: Optional[LocalAuthProvider] = None) -> None:
    global _provider
    _provider = provider


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------

def _header(scope, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key == name:
            return value.decode("latin-1")
    return ""


def session_token_from_scope(scope) -> str:
    raw = _header(scope, b"cookie")
    if not raw:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:
        return ""
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else ""


def is_protected_path(path: str) -> bool:
    if path in PUBLIC_API_PATHS:
        return False
    return path.startswith("/api/") or path == "/mcp" or path.startswith("/mcp/")


async def _send_json(send, status: int, body: dict) -> None:
    payload = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]})
    await send({"type": "http.response.body", "body": payload})


class AuthMiddleware:
    """Resolves the caller for protected paths; fails closed with 401 (403 on a missing CSRF header)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        provider = get_auth_provider()

        ctx: Optional[UserContext] = None
        authorization = _header(scope, b"authorization")
        if authorization.lower().startswith("bearer "):
            ctx = provider.authenticate_bearer(authorization[7:].strip())
        if ctx is None:
            ctx = provider.authenticate_session(session_token_from_scope(scope))
            if ctx is not None and method not in ("GET", "HEAD", "OPTIONS") \
                    and _header(scope, CSRF_HEADER.encode()).lower() != CSRF_VALUE:
                if is_protected_path(path) or path == "/api/auth/login":
                    return await _send_json(send, 403, {"error": "csrf", "message": f"Missing {CSRF_HEADER} header"})

        if ctx is None and method != "OPTIONS" and is_protected_path(path):
            return await _send_json(send, 401, {"error": "unauthenticated", "message": "Sign in required"})

        scope.setdefault("state", {})["user"] = ctx
        token = current_user_ctx.set(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user_ctx.reset(token)
