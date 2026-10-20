"""Account, session, Bee pairing and GDPR routes (docs/13_multi_user_accounts.md).

| Route | Purpose |
|---|---|
| ``GET  /api/auth/config`` | Whether accounts are enabled, password policy, privacy-notice version |
| ``POST /api/auth/register`` | Create an account (email, password, explicit privacy consent) and sign in |
| ``POST /api/auth/login`` / ``POST /api/auth/logout`` | Sign in / out (HttpOnly session cookie) |
| ``POST /api/auth/sessions/revoke-all`` | Sign out everywhere: every session and MCP access token |
| ``GET  /api/auth/session`` | Who is signed in, with their Bee state |
| ``GET/PATCH/DELETE /api/account`` | Profile; erasure of the whole account (Art. 17) |
| ``POST /api/account/password`` | Change password (other sessions are signed out) |
| ``GET  /api/account/export`` | Download every stored record as JSON (Art. 15 / 20) |
| ``GET/POST /api/account/tokens``, ``DELETE /api/account/tokens/{id}`` | MCP access tokens for Alexa+ |
| ``GET/POST/DELETE /api/bee/pair`` | Pair this user's Bee (QR / link), poll, cancel |
| ``POST /api/bee/disconnect`` | Remove this user's Bee login and stop their ingestion |

Logging out of the dashboard never disconnects the Bee: ambient ingestion keeps running for the
user until they disconnect it explicitly or delete the account.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.auth import AuthError, BeeLink, User, get_auth_store
from src.core.auth.rate_limit import login_limiter
from src.core.config import settings
from src.core.tenancy import delete_tenant_data, get_tenant_id, tenant_has_bee_login, tenant_scope
from src.ingestion.bee_pairing import BeePairing, bee_logout
from src.serving.auth_middleware import SESSION_COOKIE, read_cookie, request_origin

logger = logging.getLogger("examen.serving.auth")


@dataclass
class TenantHooks:
    """Callbacks into the server (src/serving/mcp_server.py) that manage per-user runtimes."""
    start_runtime: Callable[[str], None]
    stop_runtime: Callable[[str, bool], Optional["asyncio.Task"]]
    broadcast: Callable[..., None]
    invalidate_bee_status: Callable[..., None]
    bee_telemetry: Callable[[], Dict[str, Any]]
    # True while the user's live Bee stream runs (admin overview); never touches the user's data
    is_streaming: Callable[[str], bool] = lambda _uid: False


_pairings: Dict[Optional[str], BeePairing] = {}

BEE_ACCOUNT_TAKEN = "This Bee account is already connected to another EXAMEN account."


async def link_bee_account(user_id: str) -> BeeLink:
    """After a successful `bee login`: identify the Bee account (`bee me`) and bind it to the user.

    A Bee account belongs to at most one EXAMEN user (two accounts reading one Bee would duplicate
    every action, contact and event). On a conflict the new login is removed from this user's folder
    only; the account that already holds the Bee is untouched.
    """
    from src.ingestion.stream_convo import BeeClient

    store = get_auth_store()
    link = store.get_bee_link(user_id)
    with tenant_scope(user_id):
        client = BeeClient()  # captures this user's BEE_CONFIG_DIR
    me = await client.run_json(["me"])
    if not me or me.get("id") is None:
        link.state, link.last_error = "invalid", "Bee login saved but the account could not be verified: try again."
        return store.save_bee_link(link)
    bee_user_id = int(me["id"])
    owner = store.find_bee_link(bee_user_id)
    if owner is not None and owner.user_id != user_id:
        await bee_logout(user_id)
        link.state, link.last_error = "conflict", BEE_ACCOUNT_TAKEN
        link.bee_user_id = link.bee_first_name = None
        store.audit("bee_conflict", user_id=user_id)
        return store.save_bee_link(link)
    newly = link.state != "linked" or link.bee_user_id != bee_user_id
    link.state, link.last_error = "linked", None
    link.bee_user_id, link.bee_first_name = bee_user_id, (me.get("first_name") or "").strip() or None
    if newly:
        link.linked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.audit("bee_linked", user_id=user_id)
    return store.save_bee_link(link)


def _pairing_for(tenant: Optional[str], hooks: TenantHooks) -> BeePairing:
    pairing = _pairings.get(tenant)
    if pairing is None:
        async def on_connected(snapshot: Dict[str, Any], _t=tenant) -> None:
            hooks.invalidate_bee_status(tenant=_t)
            if _t is not None:
                link = await link_bee_account(_t)
                if link.state != "linked":
                    hooks.broadcast("bee_link_error", {"state": link.state, "message": link.last_error}, tenant=_t)
                    return
                hooks.start_runtime(_t)
            hooks.broadcast("bee_connected", {"account": snapshot.get("account")}, tenant=_t)

        pairing = BeePairing(user_id=tenant, on_connected=on_connected)
        _pairings[tenant] = pairing
    return pairing


async def _json(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    host = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    return f"ip:{host}"


def _secure_cookie(request: Request) -> bool:
    mode = settings.auth_cookie_secure
    if mode == "true":
        return True
    if mode == "false":
        return False
    return request_origin(request.scope).startswith("https://")


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(settings.auth_session_ttl_hours * 3600), path="/",
        httponly=True, samesite="lax", secure=_secure_cookie(request),
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=_secure_cookie(request))


def _error(e: AuthError) -> JSONResponse:
    return JSONResponse({"error": "auth_error", "message": e.message}, status_code=e.status)


def _disabled() -> JSONResponse:
    return JSONResponse({"error": "auth_disabled", "message": "Accounts are disabled on this server (AUTH_ENABLED=false)."},
                        status_code=404)


def _current_user() -> Optional[User]:
    uid = get_tenant_id()
    return get_auth_store().get_user(uid) if uid else None


def register_auth_routes(mcp: Any, hooks: TenantHooks) -> None:

    def pairing_snapshot(tenant: Optional[str], pairing: Optional[BeePairing]) -> Dict[str, Any]:
        """The pairing state, with the outcome of the Bee-account check (conflict / invalid) on top."""
        snap = pairing.snapshot() if pairing else {"status": "idle", "connected": False}
        if tenant is None or snap.get("status") in ("starting", "pending"):
            return snap
        link = get_auth_store().get_bee_link(tenant)
        if link.state in ("conflict", "invalid"):
            return {**snap, "status": link.state, "connected": False, "pairing_url": None, "error": link.last_error}
        if snap.get("status") == "connected" and link.state != "linked":
            # `bee login` finished; `bee me` and the one-Bee-per-user check are still running
            return {**snap, "status": "verifying", "connected": False}
        return snap

    def bee_state(tenant: Optional[str]) -> Dict[str, Any]:
        snap = pairing_snapshot(tenant, _pairings.get(tenant))
        paired = tenant_has_bee_login(tenant) if tenant else None
        state: Dict[str, Any] = {"pairing": snap, "linked": bool(paired) if tenant else None}
        if tenant is not None:
            link = get_auth_store().get_bee_link(tenant)
            state["link"] = {"state": link.state, "account": link.bee_first_name, "error": link.last_error}
        return state

    # ------------------------------------------------------------------
    # Sign up / in / out
    # ------------------------------------------------------------------

    @mcp.custom_route("/api/auth/config", methods=["GET"])
    async def api_auth_config(request: Request) -> JSONResponse:
        return JSONResponse({
            "auth_enabled": settings.auth_enabled,
            "min_password_length": settings.auth_min_password_length,
            "privacy_notice_version": settings.privacy_notice_version,
            "signup_enabled": settings.auth_allow_signup,
        })

    @mcp.custom_route("/api/auth/register", methods=["POST"])
    async def api_auth_register(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return _disabled()
        if not settings.auth_allow_signup:
            return JSONResponse({"error": "signup_disabled",
                                 "message": "Registration is closed on this server: ask an administrator."},
                                status_code=403)
        body = await _json(request)
        keys = [_client_key(request)]
        signup_key = "signup-" + keys[0]  # successful registrations per address (AUTH_SIGNUP_MAX_PER_IP)
        wait = login_limiter.blocked([*keys, signup_key])
        if wait:
            return JSONResponse({"error": "rate_limited", "message": "Too many attempts. Try again later.",
                                 "retry_after_seconds": int(wait) + 1}, status_code=429)
        if body.get("privacy_consent") is not True:
            return JSONResponse({"error": "consent_required",
                                 "message": "Accept the privacy notice to create an account."}, status_code=400)
        store = get_auth_store()
        try:
            user = await asyncio.to_thread(
                store.create_user, str(body.get("email") or ""), str(body.get("password") or ""),
                body.get("display_name"), settings.privacy_notice_version,
            )
        except AuthError as e:
            login_limiter.fail(keys)
            return _error(e)
        login_limiter.record([signup_key])
        token = store.create_session(user.id)
        hooks.start_runtime(user.id)
        response = JSONResponse({"authenticated": True, "user": user.public()}, status_code=201)
        _set_session_cookie(response, request, token)
        logger.info("Account created")  # no email or name in logs
        return response

    @mcp.custom_route("/api/auth/login", methods=["POST"])
    async def api_auth_login(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return _disabled()
        body = await _json(request)
        email = str(body.get("email") or "").strip().lower()
        keys = [_client_key(request), f"email:{email}"]
        wait = login_limiter.blocked(keys)
        if wait:
            return JSONResponse({"error": "rate_limited", "message": "Too many failed attempts. Try again later.",
                                 "retry_after_seconds": int(wait) + 1}, status_code=429)
        store = get_auth_store()
        user = await asyncio.to_thread(store.authenticate, email, str(body.get("password") or ""))
        if user is None:
            login_limiter.fail(keys)
            known = store.get_user_by_email(email)
            if known is not None:
                store.audit("login_failed", user_id=known.id)
            return JSONResponse({"error": "invalid_credentials", "message": "Invalid email or password."},
                                status_code=401)
        login_limiter.clear([f"email:{email}"])
        token = store.create_session(user.id)
        hooks.start_runtime(user.id)
        response = JSONResponse({
            "authenticated": True,
            "user": user.public(),
            "consent_required": user.privacy_consent_version != settings.privacy_notice_version,
        })
        _set_session_cookie(response, request, token)
        return response

    @mcp.custom_route("/api/auth/logout", methods=["POST"])
    async def api_auth_logout(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return JSONResponse({"success": True})
        get_auth_store().revoke_session(read_cookie(request.scope))
        response = JSONResponse({"success": True, "message": "Signed out. Your Bee keeps listening for you."})
        _clear_session_cookie(response, request)
        return response

    @mcp.custom_route("/api/auth/sessions/revoke-all", methods=["POST"])
    async def api_auth_revoke_all(request: Request) -> JSONResponse:
        """Signs the caller out everywhere: every browser session and every MCP access token."""
        if not settings.auth_enabled:
            return _disabled()
        user = _current_user()
        if user is None:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        store = get_auth_store()
        store.revoke_user_sessions(user.id)
        store.revoke_user_tokens(user.id)
        store.audit("sessions_revoked", user_id=user.id, actor_id=user.id)
        response = JSONResponse({"success": True, "message": "Signed out on every device; access tokens revoked."})
        _clear_session_cookie(response, request)
        return response

    @mcp.custom_route("/api/auth/session", methods=["GET"])
    async def api_auth_session(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            telemetry = await asyncio.to_thread(hooks.bee_telemetry)
            return JSONResponse({"auth_enabled": False, "authenticated": True,
                                 "user": {"id": None, "email": None, "display_name": "Local user"},
                                 "bee_device": telemetry, "bee": bee_state(None)})
        user = _current_user()
        if user is None:
            return JSONResponse({"auth_enabled": True, "authenticated": False, "user": None})
        telemetry = await asyncio.to_thread(hooks.bee_telemetry)
        return JSONResponse({
            "auth_enabled": True,
            "authenticated": True,
            "user": user.public(),
            "consent_required": user.privacy_consent_version != settings.privacy_notice_version,
            "privacy_notice_version": settings.privacy_notice_version,
            "bee_device": telemetry,
            "bee": bee_state(user.id),
        })

    # ------------------------------------------------------------------
    # Account (GDPR)
    # ------------------------------------------------------------------

    @mcp.custom_route("/api/account", methods=["GET", "PATCH", "DELETE"])
    async def api_account(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return _disabled()
        user = _current_user()
        if user is None:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        store = get_auth_store()
        body = await _json(request) if request.method != "GET" else {}

        if request.method == "PATCH":
            if "privacy_consent" in body:
                if body.get("privacy_consent") is not True:
                    return JSONResponse({"error": "consent_required",
                                         "message": "Consent can only be given here; delete the account to withdraw it."},
                                        status_code=400)
                store.record_consent(user.id, settings.privacy_notice_version)
            if "display_name" in body:
                store.update_profile(user.id, body.get("display_name"))
            return JSONResponse({"user": store.get_user(user.id).public()})

        if request.method == "DELETE":
            if not await asyncio.to_thread(store.verify_user_password, user.id, str(body.get("password") or "")):
                return JSONResponse({"error": "invalid_credentials", "message": "Password is incorrect."}, status_code=403)
            await _erase_account(user.id)
            response = JSONResponse({"success": True, "deleted": True,
                                     "message": "Your account and all of its data were permanently deleted."})
            _clear_session_cookie(response, request)
            return response

        return JSONResponse({
            "user": user.public(),
            "tokens": [t.model_dump() for t in store.list_api_tokens(user.id)],
            "bee": bee_state(user.id),
            "privacy_notice_version": settings.privacy_notice_version,
        })

    async def _erase_account(user_id: str) -> None:
        """Art. 17 erasure: stop everything that runs for the user, then delete their folder and account."""
        pairing = _pairings.pop(user_id, None)
        if pairing is not None:
            await pairing.cancel()
        task = hooks.stop_runtime(user_id, True)
        if task is not None:
            # Let the orchestrator finish its shutdown (it stops the user's bee proxy and stream)
            await asyncio.wait({task}, timeout=10)
        if tenant_has_bee_login(user_id):
            await bee_logout(user_id)  # revoke locally; the folder (token file) is deleted next
        from src.core.storage import drop_tenant_store

        drop_tenant_store(user_id)
        await asyncio.to_thread(delete_tenant_data, user_id)
        get_auth_store().delete_user(user_id)
        get_auth_store().audit("account_erased")  # no user reference survives the erasure
        logger.info("Account erased")

    @mcp.custom_route("/api/account/password", methods=["POST"])
    async def api_account_password(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return _disabled()
        user = _current_user()
        if user is None:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        body = await _json(request)
        store = get_auth_store()
        if not await asyncio.to_thread(store.verify_user_password, user.id, str(body.get("current_password") or "")):
            return JSONResponse({"error": "invalid_credentials", "message": "Current password is incorrect."},
                                status_code=403)
        try:
            await asyncio.to_thread(store.set_password, user.id, str(body.get("new_password") or ""))
        except AuthError as e:
            return _error(e)
        signed_out = store.revoke_user_sessions(user.id, keep_token=read_cookie(request.scope))
        return JSONResponse({"success": True, "other_sessions_signed_out": signed_out})

    @mcp.custom_route("/api/account/export", methods=["GET"])
    async def api_account_export(request: Request) -> Response:
        if not settings.auth_enabled:
            return _disabled()
        user = _current_user()
        if user is None:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        from src.core.storage import get_storage_store

        data = await asyncio.to_thread(get_storage_store().export_all)
        auth = get_auth_store()
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "format": "examen-export-v1",
            "account": user.public(),
            "access_tokens": [t.model_dump() for t in auth.list_api_tokens(user.id)],
            "bee": {"linked": tenant_has_bee_login(user.id)},
            "data": data,
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        stamp = datetime.now().strftime("%Y%m%d")
        return Response(body, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="examen-export-{stamp}.json"',
            "Cache-Control": "no-store",
        })

    @mcp.custom_route("/api/account/tokens", methods=["GET", "POST"])
    async def api_account_tokens(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return _disabled()
        user = _current_user()
        if user is None:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        store = get_auth_store()
        if request.method == "POST":
            body = await _json(request)
            created = store.create_api_token(user.id, str(body.get("name") or "Alexa+"))
            return JSONResponse({"token": created, "message": "Copy this token now: it is shown only once."},
                                status_code=201)
        return JSONResponse({"tokens": [t.model_dump() for t in store.list_api_tokens(user.id)]})

    @mcp.custom_route("/api/account/tokens/{token_id}", methods=["DELETE"])
    async def api_account_token_delete(request: Request) -> JSONResponse:
        if not settings.auth_enabled:
            return _disabled()
        user = _current_user()
        if user is None:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        ok = get_auth_store().revoke_api_token(user.id, request.path_params.get("token_id", ""))
        return JSONResponse({"success": ok}, status_code=200 if ok else 404)

    # ------------------------------------------------------------------
    # Bee pairing (per user)
    # ------------------------------------------------------------------

    @mcp.custom_route("/api/bee/pair", methods=["GET", "POST", "DELETE"])
    async def api_bee_pair(request: Request) -> JSONResponse:
        tenant = get_tenant_id()
        pairing = _pairing_for(tenant, hooks)
        if request.method == "POST":
            if tenant is not None and tenant_has_bee_login(tenant):
                return JSONResponse({"bee_pairing": {"status": "connected", "connected": True},
                                     "message": "A Bee is already connected to this account."})
            if tenant is not None:
                link = get_auth_store().get_bee_link(tenant)
                if link.state in ("conflict", "invalid"):  # a new attempt clears the previous outcome
                    link.state, link.last_error = "unlinked", None
                    get_auth_store().save_bee_link(link)
            snap = await pairing.start()
            return JSONResponse({"bee_pairing": snap}, status_code=200 if snap["status"] != "failed" else 502)
        if request.method == "DELETE":
            await pairing.cancel()
            return JSONResponse({"bee_pairing": pairing.snapshot()})
        snap = pairing_snapshot(tenant, pairing)
        if tenant is not None and tenant_has_bee_login(tenant) and snap["status"] not in ("pending", "invalid"):
            snap = {**snap, "status": "connected", "connected": True}
        return JSONResponse({"bee_pairing": snap})

    @mcp.custom_route("/api/bee/disconnect", methods=["POST"])
    async def api_bee_disconnect(request: Request) -> JSONResponse:
        tenant = get_tenant_id()
        pairing = _pairings.get(tenant)
        if pairing is not None:
            await pairing.cancel()
        if tenant is not None:
            task = hooks.stop_runtime(tenant, False)
            if task is not None:
                await asyncio.wait({task}, timeout=10)
        ok = await bee_logout(tenant)
        if tenant is not None:
            get_auth_store().delete_bee_link(tenant)
        hooks.invalidate_bee_status(tenant=tenant)
        hooks.broadcast("bee_disconnected", {}, tenant=tenant)
        return JSONResponse({"success": ok, "connected": False,
                             "message": "Bee disconnected from this account. Your stored data is kept."})

    # Backwards-compatible aliases used by older dashboard builds
    @mcp.custom_route("/api/auth/bee-link", methods=["GET", "POST"])
    async def api_auth_bee_link(request: Request) -> JSONResponse:
        tenant = get_tenant_id()
        if tenant is not None and tenant_has_bee_login(tenant):
            return JSONResponse({"success": True, "bee_pairing": {"status": "already_connected", "connected": True}})
        snap = await _pairing_for(tenant, hooks).start()
        return JSONResponse({"success": snap["status"] != "failed", "bee_pairing": snap})

    @mcp.custom_route("/api/auth/bee-disconnect", methods=["POST"])
    async def api_auth_bee_disconnect(request: Request) -> JSONResponse:
        return await api_bee_disconnect(request)
