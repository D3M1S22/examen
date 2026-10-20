"""Account administration (docs/13_multi_user_accounts.md §3.1).

| Route | Purpose |
|---|---|
| ``GET  /api/admin/users`` | Accounts with their Bee link state and whether their live stream runs |
| ``POST /api/admin/users`` | Create an account (``{email, display_name?, is_admin?}``) with a one-time password |
| ``POST /api/admin/users/{id}/status`` | ``{"status": "active" | "disabled"}``; disabling signs the user out everywhere and stops their ingestion |
| ``POST /api/admin/users/{id}/reset-password`` | Issue a one-time password (no e-mail on the homelab) |

Admins manage **accounts only**: nothing here reads a user's speech-derived data. Every route needs an
admin's dashboard session (access tokens are refused by AuthMiddleware) and every change is audited.
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.core.auth import AuthError, User, get_auth_store
from src.core.config import settings
from src.core.tenancy import get_tenant_id


def _one_time_password() -> str:
    return secrets.token_urlsafe(12)


def _require_admin() -> tuple[Optional[User], Optional[JSONResponse]]:
    if not settings.auth_enabled:
        return None, JSONResponse({"error": "auth_disabled"}, status_code=404)
    uid = get_tenant_id()
    user = get_auth_store().get_user(uid) if uid else None
    if user is None:
        return None, JSONResponse({"error": "authentication_required"}, status_code=401)
    if not user.is_admin:
        return None, JSONResponse({"error": "forbidden", "message": "Administrator account required."},
                                  status_code=403)
    return user, None


def register_admin_routes(mcp: Any, hooks: Any) -> None:

    @mcp.custom_route("/api/admin/users", methods=["GET", "POST"])
    async def api_admin_users(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        store = get_auth_store()
        if request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                body = {}
            body = body if isinstance(body, dict) else {}
            password = _one_time_password()
            try:
                user = await asyncio.to_thread(
                    store.create_user, str(body.get("email") or ""), password, body.get("display_name"), None,
                    bool(body.get("is_admin", False)),
                )
            except AuthError as e:
                return JSONResponse({"error": "auth_error", "message": e.message}, status_code=e.status)
            store.audit("admin_user_created", user_id=user.id, actor_id=admin.id,
                        detail={"is_admin": user.is_admin})
            # Shown once to the admin; the user signs in with it and should change it
            return JSONResponse({"user": user.public(), "initial_password": password}, status_code=201)

        users = []
        for user in store.list_users():
            link = store.get_bee_link(user.id)
            users.append({**user.public(), "bee_link_state": link.state, "bee_account": link.bee_first_name,
                          "bee_last_error": link.last_error, "streaming": bool(hooks.is_streaming(user.id))})
        return JSONResponse({"users": users, "count": len(users)})

    @mcp.custom_route("/api/admin/users/{user_id}/status", methods=["POST"])
    async def api_admin_user_status(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        store = get_auth_store()
        user_id = request.path_params["user_id"]
        try:
            body = await request.json()
        except Exception:
            body = {}
        status = (body or {}).get("status") if isinstance(body, dict) else None
        if status not in ("active", "disabled") or store.get_user(user_id) is None:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        if user_id == admin.id and status == "disabled":
            return JSONResponse({"error": "forbidden", "message": "You cannot disable your own account."},
                                status_code=403)
        store.set_status(user_id, status)
        if status == "disabled":
            task = hooks.stop_runtime(user_id, False)
            if task is not None:
                await asyncio.wait({task}, timeout=10)
        else:
            hooks.start_runtime(user_id)
        store.audit(f"admin_user_{status}", user_id=user_id, actor_id=admin.id)
        return JSONResponse({"success": True, "user": store.get_user(user_id).public()})

    @mcp.custom_route("/api/admin/users/{user_id}/reset-password", methods=["POST"])
    async def api_admin_reset_password(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        store = get_auth_store()
        user_id = request.path_params["user_id"]
        if store.get_user(user_id) is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        password = _one_time_password()
        await asyncio.to_thread(store.set_password, user_id, password)
        store.revoke_user_sessions(user_id)
        store.audit("admin_password_reset", user_id=user_id, actor_id=admin.id)
        return JSONResponse({"success": True, "initial_password": password})
