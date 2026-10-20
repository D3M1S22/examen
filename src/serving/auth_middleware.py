"""ASGI middleware: authenticates every API and MCP request and binds it to the user's tenant.

- Browser dashboard: ``examen_session`` HttpOnly cookie (src/serving/auth_routes.py).
- MCP clients (Alexa+, Claude, scripts): ``Authorization: Bearer exm_...`` personal access token.

The resolved user id is set as the current tenant (src/core/tenancy.py) for the whole request,
including streamed responses (SSE), and stored in ``scope["state"]["examen_user_id"]`` so MCP tool
handlers, which run in the MCP session manager's tasks, can find it (src/serving/tenant_tools.py).

Cookie-authenticated state-changing requests must come from an allowed origin (CSRF defence; the
session cookie is also ``SameSite=Lax``). With ``AUTH_ENABLED=false`` the middleware is a no-op.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional, Set
from urllib.parse import urlparse

from src.core.config import settings
from src.core.tenancy import reset_tenant, set_tenant

SESSION_COOKIE = "examen_session"

# Reachable without a session (everything else under /api and /mcp needs one)
PUBLIC_API_PATHS: Set[str] = {
    "/api/auth/config",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
    "/api/health",
}

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins() -> Set[str]:
    return {o.strip().rstrip("/") for o in (settings.cors_allowed_origins or "").split(",") if o.strip()}


def _header(scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers") or []:
        if key == name:
            return value.decode("latin-1")
    return None


def read_cookie(scope, name: str = SESSION_COOKIE) -> Optional[str]:
    raw = _header(scope, b"cookie")
    if not raw:
        return None
    for part in raw.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value or None
    return None


def bearer_token(scope) -> Optional[str]:
    auth = _header(scope, b"authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def request_origin(scope) -> str:
    scheme = _header(scope, b"x-forwarded-proto") or scope.get("scheme", "http")
    host = _header(scope, b"x-forwarded-host") or _header(scope, b"host") or ""
    return f"{scheme.split(',')[0].strip()}://{host.split(',')[0].strip()}".rstrip("/")


def origin_allowed(scope, extra: Iterable[str] = ()) -> bool:
    """True when an unsafe cookie request was sent by the dashboard itself or an allowed origin."""
    origin = _header(scope, b"origin")
    if not origin:
        referer = _header(scope, b"referer")
        if not referer:
            return True  # not a browser cross-site request (curl, tests, server-side clients)
        parsed = urlparse(referer)
        origin = f"{parsed.scheme}://{parsed.netloc}"
    origin = origin.rstrip("/")
    if origin == "null":
        return False
    own = request_origin(scope)
    host_only = urlparse(own).netloc
    return origin == own or urlparse(origin).netloc == host_only or origin in allowed_origins() or origin in set(extra)


def is_protected(path: str) -> bool:
    if path == "/mcp" or path.startswith("/mcp/"):
        return True
    return path.startswith("/api/") and path not in PUBLIC_API_PATHS


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not settings.auth_enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        from src.core.auth import get_auth_store

        user = None
        via_cookie = False
        token = bearer_token(scope)
        store = get_auth_store()
        if token:
            user = store.user_for_api_token(token)
        if user is None:
            cookie = read_cookie(scope)
            if cookie:
                user = store.user_for_session(cookie)
                via_cookie = user is not None

        if user is None and is_protected(path):
            await self._reject(send, 401, "authentication_required", "Sign in to continue.",
                               bearer=path.startswith("/mcp"))
            return
        if via_cookie and scope.get("method") in _UNSAFE_METHODS and not origin_allowed(scope):
            await self._reject(send, 403, "origin_not_allowed", "Request origin not allowed.")
            return

        state = scope.setdefault("state", {})
        state["examen_user_id"] = user.id if user else None
        tenant_token = set_tenant(user.id if user else None)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_tenant(tenant_token)

    @staticmethod
    async def _reject(send, status: int, code: str, message: str, bearer: bool = False) -> None:
        body = json.dumps({"error": code, "message": message}).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        if bearer:
            headers.append((b"www-authenticate", b'Bearer realm="examen-mcp"'))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
