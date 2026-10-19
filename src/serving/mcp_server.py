"""Unified FastMCP Server & Web Serving Layer for EXAMEN.

Exposes:
1. Standard Model Context Protocol (MCP) streamable-HTTP endpoints for Alexa+ (/mcp).
2. JSON REST APIs for dashboard live telemetry (/api/*).
3. Echo Show (ext-apps) & desktop web UI dashboard static assets (/ and /ext-app).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from src.core.config import settings
from src.core.identity import MissingUserContext, UserContext, get_current_user, require_user
from src.core.schemas import PlannedTask, SocialCommitment, UserAccount
from src.core.storage import get_storage_store, get_system_store
from src.pipeline.app import agent_invocation
from src.serving.tools import (
    create_planned_task,
    get_ingestion_coverage,
    get_live_event_outline,
    get_contact_profile,
    get_daily_actions_recap,
    get_session_dossier,
    get_social_commitments,
    get_upcoming_tasks,
    list_session_dossiers,
    query_social_contact,
    verify_action_status,
)
from src.serving.tools.action_tools import _format_elapsed_time
from src.serving.tools.topic_tools import get_topic_briefing
from src.serving.auth import SESSION_COOKIE, AuthError, AuthMiddleware, get_auth_provider
from src.serving.bee_accounts import BeeLinkError, erase_account, public_link, refresh_link, start_pairing
from src.serving.bee_accounts import unlink as unlink_bee
from src.serving.user_runtime import TooManyActiveUsers, UserRuntime, get_event_hub, get_runtime_manager

logger = logging.getLogger("examen.serving.mcp")

# Initialize FastMCP Server
mcp = FastMCP("examen-mcp")

def broadcast_event(event_type: str, data: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> None:
    """Publishes an SSE event to one user's dashboards (default: the user of the current context).

    Without a user the event is dropped: speech-derived events are never broadcast to everyone."""
    uid = user_id
    if uid is None:
        ctx = get_current_user()
        if ctx is None:
            logger.debug(f"SSE event '{event_type}' dropped: no user context")
            return
        uid = ctx.user_id
    get_event_hub().publish(uid, event_type, data)


def _runtime() -> UserRuntime:
    """The live runtime of the user in the current context."""
    return get_runtime_manager().current()


def _ensure_event_engine() -> Any:
    """Starts the caller's Event Engine runtime (and backfill service); returns the caller's engine."""
    return _runtime().ensure_engine()


def _ensure_backfill_service() -> Any:
    runtime = _runtime()
    runtime.ensure_engine()
    return runtime.backfill


# Register the core MCP tools for Alexa+ (each call runs as the token's user: AuthMiddleware)
mcp.tool()(create_planned_task)
mcp.tool()(get_upcoming_tasks)
mcp.tool()(verify_action_status)
mcp.tool()(get_daily_actions_recap)
mcp.tool()(query_social_contact)
mcp.tool()(get_contact_profile)
mcp.tool()(get_social_commitments)
mcp.tool()(get_topic_briefing)
mcp.tool()(get_session_dossier)
mcp.tool()(list_session_dossiers)
mcp.tool()(get_live_event_outline)
mcp.tool()(get_ingestion_coverage)


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def _ctx(request: Request) -> UserContext:
    ctx = getattr(request.state, "user", None)
    if ctx is None:  # AuthMiddleware guards protected routes; this is a second line of defence
        raise MissingUserContext("unauthenticated")
    return ctx


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _json_body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _auth_error(e: AuthError) -> JSONResponse:
    return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status)


def _user_payload(user: UserAccount) -> Dict[str, Any]:
    return user.model_dump(exclude={"external_sub"})


def _bee_device_telemetry() -> Dict[str, Any]:
    """The caller's Bee status from their link and live runtime (no `bee status` subprocess per request)."""
    user_id = require_user().user_id
    link = get_system_store().get_bee_link(user_id)
    runtime = get_runtime_manager().get(user_id)
    orch = runtime.get_status() if runtime is not None else None
    account = link.bee_first_name if link.state == "linked" else None
    if link.state == "pairing":
        status, detail = "PAIRING", "Waiting for the Bee app to approve the pairing link"
    elif link.state != "linked":
        status = "DISCONNECTED"
        detail = link.last_error or "No Bee account linked. Use 'Connect Bee' to pair your own Bee."
    elif orch and orch.get("status") == "STREAMING":
        status, detail = "STREAMING", f"Bee streaming ({orch.get('utterances_received', 0)} utterances)"
    elif runtime is not None and runtime.streaming:
        status, detail = "LISTENING", f"Bee account {account} linked; listening for speech"
    else:
        status, detail = "STANDBY", link.last_error or f"Bee account {account} linked; live ingestion not running"
    return {
        "connected": status == "STREAMING",
        "status": status,
        "account": account,
        # Means "utterances are flowing": the Bee CLI exposes no BLE pairing / battery / RSSI
        "device_paired": status == "STREAMING",
        "detail": detail,
        "link_state": link.state,
        "last_error": link.last_error,
    }


# ---------------------------------------------------------------------------
# Authentication & account (docs/next_steps/multi_user/02, 04 §1)
# ---------------------------------------------------------------------------

@mcp.custom_route("/api/health", methods=["GET"])
async def api_health(request: Request) -> JSONResponse:
    """Unauthenticated liveness probe (deploy health checks)."""
    return JSONResponse({"status": "ok", "timestamp": datetime.now().isoformat()})


@mcp.custom_route("/api/auth/login", methods=["POST"])
async def api_auth_login(request: Request) -> JSONResponse:
    """Username + password sign-in: sets the HttpOnly session cookie."""
    body = await _json_body(request)
    try:
        user, token = await asyncio.to_thread(
            get_auth_provider().login, str(body.get("username") or ""), str(body.get("password") or ""),
            ip=_client_ip(request), user_agent=request.headers.get("user-agent", ""),
        )
    except AuthError as e:
        return _auth_error(e)
    response = JSONResponse({
        "success": True,
        "user": _user_payload(user),
        "bee_link": public_link(get_system_store().get_bee_link(user.user_id)),
    })
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(settings.auth_session_days * 86400), httponly=True,
        samesite="lax", secure=settings.auth_cookie_secure, path="/",
    )
    return response


@mcp.custom_route("/api/auth/session", methods=["GET"])
async def api_auth_session(request: Request) -> JSONResponse:
    """Current user (or ``authenticated: false``) and their Bee link."""
    ctx = getattr(request.state, "user", None)
    if ctx is None:
        return JSONResponse({"authenticated": False, "user": None, "bee_link": None,
                             "signup_enabled": settings.auth_allow_signup})
    user = get_system_store().get_user(ctx.user_id)
    return JSONResponse({
        "authenticated": user is not None,
        "user": _user_payload(user) if user else None,
        "auth_method": ctx.auth_method,
        "bee_link": public_link(get_system_store().get_bee_link(ctx.user_id)),
        "bee_device": _bee_device_telemetry(),
    })


@mcp.custom_route("/api/auth/logout", methods=["POST"])
async def api_auth_logout(request: Request) -> JSONResponse:
    """Ends this web session only: the Bee link and live ingestion keep running (D8)."""
    from src.serving.auth import session_token_from_scope

    get_auth_provider().logout(session_token_from_scope(request.scope))
    response = JSONResponse({"success": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@mcp.custom_route("/api/auth/sessions/revoke-all", methods=["POST"])
async def api_auth_revoke_all(request: Request) -> JSONResponse:
    """Logs the caller out everywhere: every web session and personal access token."""
    get_auth_provider().revoke_everything(_ctx(request).user_id)
    response = JSONResponse({"success": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@mcp.custom_route("/api/auth/password", methods=["POST"])
async def api_auth_password(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    body = await _json_body(request)
    provider = get_auth_provider()
    if not await asyncio.to_thread(provider.verify_password, ctx.user_id, str(body.get("current_password") or "")):
        return JSONResponse({"error": "invalid_credentials", "message": "Current password is wrong"}, status_code=401)
    try:
        await asyncio.to_thread(provider.set_password, ctx.user_id, str(body.get("new_password") or ""))
    except AuthError as e:
        return _auth_error(e)
    return JSONResponse({"success": True, "message": "Password changed: sign in again"})


@mcp.custom_route("/api/account/tokens", methods=["GET", "POST"])
async def api_account_tokens(request: Request) -> JSONResponse:
    """Personal access tokens for MCP clients (the token value is returned once, at creation)."""
    ctx = _ctx(request)
    if request.method == "POST":
        if ctx.auth_method == "api_token":
            return JSONResponse({"error": "forbidden", "message": "Tokens cannot create tokens"}, status_code=403)
        body = await _json_body(request)
        raw, info = get_auth_provider().create_api_token(ctx.user_id, str(body.get("name") or ""))
        return JSONResponse({"success": True, "token": raw, "info": info.model_dump()}, status_code=201)
    tokens = get_system_store().list_api_tokens(ctx.user_id)
    return JSONResponse({"tokens": [t.model_dump() for t in tokens]})


@mcp.custom_route("/api/account/tokens/{token_id}", methods=["DELETE"])
async def api_account_token_revoke(request: Request) -> JSONResponse:
    ctx = _ctx(request)
    if not get_system_store().revoke_api_token(ctx.user_id, request.path_params["token_id"]):
        return JSONResponse({"error": "not_found"}, status_code=404)
    get_system_store().audit("api_token_revoked", user_id=ctx.user_id, detail={"token_id": request.path_params["token_id"]})
    return JSONResponse({"success": True})


@mcp.custom_route("/api/account/erase", methods=["POST"])
async def api_account_erase(request: Request) -> JSONResponse:
    """GDPR Art. 17: deletes the caller's data, Bee link, sessions and account (password required)."""
    ctx = _ctx(request)
    if ctx.auth_method != "session":
        return JSONResponse({"error": "forbidden", "message": "Erasure needs a signed-in session"}, status_code=403)
    body = await _json_body(request)
    if not await asyncio.to_thread(get_auth_provider().verify_password, ctx.user_id, str(body.get("password") or "")):
        return JSONResponse({"error": "invalid_credentials", "message": "Password required to erase the account"},
                            status_code=401)
    await erase_account(ctx.user_id, actor_user_id=ctx.user_id)
    response = JSONResponse({"success": True, "erased": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ---------------------------------------------------------------------------
# Admin: accounts only, never other users' speech-derived data (02 §3)
# ---------------------------------------------------------------------------

def _require_admin(request: Request) -> Optional[JSONResponse]:
    ctx = _ctx(request)
    if not ctx.is_admin or ctx.auth_method != "session":
        return JSONResponse({"error": "forbidden", "message": "Admin session required"}, status_code=403)
    return None


@mcp.custom_route("/api/admin/users", methods=["GET", "POST"])
async def api_admin_users(request: Request) -> JSONResponse:
    denied = _require_admin(request)
    if denied:
        return denied
    system = get_system_store()
    if request.method == "POST":
        body = await _json_body(request)
        password = str(body.get("password") or "") or secrets.token_urlsafe(12)
        try:
            user = await asyncio.to_thread(
                get_auth_provider().create_user, str(body.get("username") or ""), password,
                display_name=body.get("display_name"), is_admin=bool(body.get("is_admin", False)),
            )
        except AuthError as e:
            return _auth_error(e)
        system.audit("admin_user_created", user_id=user.user_id, actor_user_id=_ctx(request).user_id)
        return JSONResponse({"success": True, "user": _user_payload(user),
                             "initial_password": None if body.get("password") else password}, status_code=201)
    users = []
    for user in system.list_users():
        link = system.get_bee_link(user.user_id)
        runtime = get_runtime_manager().get(user.user_id)
        users.append({**_user_payload(user), "bee_link_state": link.state, "bee_account": link.bee_first_name,
                      "bee_last_error": link.last_error, "streaming": bool(runtime and runtime.streaming)})
    return JSONResponse({"users": users, "count": len(users)})


@mcp.custom_route("/api/admin/users/{user_id}/status", methods=["POST"])
async def api_admin_user_status(request: Request) -> JSONResponse:
    """Body ``{"status": "active" | "disabled"}``; disabling stops the user's live ingestion."""
    denied = _require_admin(request)
    if denied:
        return denied
    user_id = request.path_params["user_id"]
    body = await _json_body(request)
    status = body.get("status")
    system = get_system_store()
    if status not in ("active", "disabled") or system.get_user(user_id) is None:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    if user_id == _ctx(request).user_id and status == "disabled":
        return JSONResponse({"error": "forbidden", "message": "You cannot disable yourself"}, status_code=403)
    system.update_user(user_id, status=status)
    if status == "disabled":
        system.revoke_user_sessions(user_id)
        await get_runtime_manager().stop_stream(user_id)
    system.audit(f"admin_user_{status}", user_id=user_id, actor_user_id=_ctx(request).user_id)
    return JSONResponse({"success": True})


@mcp.custom_route("/api/admin/users/{user_id}/reset-password", methods=["POST"])
async def api_admin_reset_password(request: Request) -> JSONResponse:
    """Issues a one-time password (no e-mail on the homelab, open question Q4 of doc 05)."""
    denied = _require_admin(request)
    if denied:
        return denied
    user_id = request.path_params["user_id"]
    if get_system_store().get_user(user_id) is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    password = secrets.token_urlsafe(12)
    await asyncio.to_thread(get_auth_provider().set_password, user_id, password)
    get_system_store().audit("admin_password_reset", user_id=user_id, actor_user_id=_ctx(request).user_id)
    return JSONResponse({"success": True, "initial_password": password})


# ---------------------------------------------------------------------------
# Bee account link (one Bee account per user, 02 §4)
# ---------------------------------------------------------------------------

def _bee_error(e: BeeLinkError) -> JSONResponse:
    return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status)


@mcp.custom_route("/api/bee/link", methods=["GET", "POST"])
async def api_bee_link(request: Request) -> JSONResponse:
    """GET re-checks the caller's Bee token (and completes an approved pairing); POST starts a pairing."""
    user_id = _ctx(request).user_id
    try:
        link = await (start_pairing(user_id) if request.method == "POST" else refresh_link(user_id))
    except BeeLinkError as e:
        return _bee_error(e)
    return JSONResponse({"bee_link": public_link(link), "bee_device": _bee_device_telemetry()})


@mcp.custom_route("/api/bee/unlink", methods=["POST"])
async def api_bee_unlink(request: Request) -> JSONResponse:
    """Stops the caller's ingestion and logs out their Bee account (their data is kept)."""
    link = await unlink_bee(_ctx(request).user_id)
    broadcast_event("bee_disconnected", {})
    return JSONResponse({"success": True, "bee_link": public_link(link)})


# ---------------------------------------------------------------------------
# Live ingestion of the caller
# ---------------------------------------------------------------------------

@mcp.custom_route("/api/orchestrator/status", methods=["GET"])
async def api_orchestrator_status(request: Request) -> JSONResponse:
    """Live status of the caller's ingestion stream."""
    status = _runtime().get_status()
    status.update(_history_status())
    return JSONResponse(status)


@mcp.custom_route("/api/orchestrator/start", methods=["POST"])
async def api_orchestrator_start(request: Request) -> JSONResponse:
    """(Re)starts the caller's live ingestion (requires a linked Bee account)."""
    user_id = _ctx(request).user_id
    if get_system_store().get_bee_link(user_id).state != "linked":
        return JSONResponse({"error": "bee_not_linked", "message": "Connect your Bee account first"}, status_code=409)
    try:
        runtime = get_runtime_manager().start_stream(user_id)
    except TooManyActiveUsers as e:
        return JSONResponse({"error": "capacity", "message": str(e)}, status_code=503)
    return JSONResponse({"success": True, "orchestrator": runtime.get_status()})


@mcp.custom_route("/api/orchestrator/stop", methods=["POST"])
async def api_orchestrator_stop(request: Request) -> JSONResponse:
    """Suspends the caller's live ingestion (until restart or the next start)."""
    await get_runtime_manager().stop_stream(_ctx(request).user_id)
    return JSONResponse({"success": True, "status": "STOPPED"})


@mcp.custom_route("/api/status", methods=["GET"])
async def api_status(request: Request) -> JSONResponse:
    """Returns system status, active models/providers, real telemetry averages, and entity counts."""
    _ensure_event_engine()
    store = get_storage_store()
    recent_actions = store.list_recent_actions(limit=100)
    planned_tasks = store.list_planned_tasks()
    all_contacts = store.search_social_contact("")
    all_topics = store.list_topic_briefings(limit=100)
    all_commitments = store.list_social_commitments(limit=100)

    completed_tasks = sum(1 for t in planned_tasks if t.status == "completed")
    pending_tasks = sum(1 for t in planned_tasks if t.status != "completed")
    open_commitments = sum(1 for c in all_commitments if c.status == "open")

    latency_metrics = store.get_latency_metrics()
    bee_telemetry = _bee_device_telemetry()
    orch_status = _runtime().get_status()
    history_status = _history_status()

    # Dynamic sensor mesh description based on live hardware & orchestrator state
    if bee_telemetry.get("status") == "STREAMING":
        sensor_mesh_str = "Bee Wearable Audio Mesh (Live Streaming)"
    elif bee_telemetry.get("status") == "LISTENING":
        sensor_mesh_str = f"Bee Wearable Audio Mesh (Listening • {bee_telemetry.get('account')})"
    elif bee_telemetry.get("account"):
        sensor_mesh_str = f"Bee Wearable (Standby • {bee_telemetry.get('account')})"
    else:
        sensor_mesh_str = "Web Simulator / Edge Ingestion (Standby)"

    return JSONResponse({
        "status": "online",
        "service": "EXAMEN Ambient Intelligence Engine",
        "timestamp": datetime.now().isoformat(),
        "telemetry": {
            "sensor_mesh": sensor_mesh_str,
            "bee_device": bee_telemetry,
            "orchestrator": orch_status,
            "processing_model": {
                "gatekeeper": settings.gatekeeper_model_id,
                "reasoner": settings.reasoner_model_id,
                "gatekeeper_provider": settings.gatekeeper_provider,
                "reasoner_provider": settings.reasoner_provider,
                "active_runtime": "AWS Bedrock AgentCore",
            },
            "latency": latency_metrics,
            "coverage": history_status["coverage"],
            "backfill": history_status["backfill"],
        },
        "config": {
            "gatekeeper_provider": settings.gatekeeper_provider,
            "reasoner_provider": settings.reasoner_provider,
            "gatekeeper_model": settings.gatekeeper_model_id,
            "reasoner_model": settings.reasoner_model_id,
            "storage_backend": settings.storage_backend,
            "sqlite_db_path": settings.sqlite_db_path,
            "aws_region": settings.aws_region,
        },
        "stats": {
            "total_actions": len(recent_actions),
            "planned_tasks_total": len(planned_tasks),
            "planned_tasks_completed": completed_tasks,
            "planned_tasks_pending": pending_tasks,
            "total_contacts": len(all_contacts),
            "total_topics": len(all_topics),
            "total_commitments": len(all_commitments),
            "open_commitments": open_commitments,
        },
    })


@mcp.custom_route("/api/actions", methods=["GET"])
async def api_actions(request: Request) -> JSONResponse:
    """Returns recent verified actions with elapsed time human format."""
    store = get_storage_store()
    limit = int(request.query_params.get("limit", "25"))
    domain = request.query_params.get("domain")
    filter_domain = None if (not domain or domain.lower() == "all") else domain.lower()

    ingest_source = request.query_params.get("ingest_source") or None
    actions = store.list_recent_actions(limit=limit, domain=filter_domain, ingest_source=ingest_source)
    result = []
    for a in actions:
        result.append({
            "id": a.id,
            "action_type": a.action_type,
            "domain": a.domain,
            "timestamp": a.timestamp,
            "elapsed_time_human": _format_elapsed_time(a.timestamp),
            "raw_statement": a.raw_statement,
            "confidence": round(a.confidence, 2),
            "matched_task_id": a.matched_task_id,
            "ingest_source": a.ingest_source,
            "ingest_run_id": a.ingest_run_id,
        })

    return JSONResponse({"actions": result, "count": len(result)})


@mcp.custom_route("/api/events", methods=["GET"])
async def api_events(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint streaming real-time pipeline and entity updates."""
    user_id = _ctx(request).user_id
    hub = get_event_hub()
    queue = hub.subscribe(user_id)

    limit_param = request.query_params.get("limit")
    max_events = int(limit_param) if limit_param and limit_param.isdigit() else None

    async def event_generator():
        sent = 0
        try:
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"
            sent += 1
            if max_events is not None and sent >= max_events:
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                    sent += 1
                    if max_events is not None and sent >= max_events:
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@mcp.custom_route("/api/routines", methods=["GET", "POST"])
async def api_routines(request: Request) -> JSONResponse:
    """Lists planned routine tasks (GET) or registers a new planned task (POST)."""
    store = get_storage_store()

    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        title = body.get("title")
        if not title or not title.strip():
            return JSONResponse({"error": "Field 'title' is required"}, status_code=400)

        task = PlannedTask(
            title=title.strip(),
            domain=body.get("domain", "routine"),
            scheduled_time=body.get("scheduled_time"),
            recurrence=body.get("recurrence", "none"),
            origin=body.get("origin", "manual"),
            raw_statement=body.get("raw_statement"),
            confidence=float(body.get("confidence", 1.0)),
            relative_time_anchor=body.get("relative_time_anchor"),
            session_id=body.get("session_id"),
            status="pending",
        )
        task_id = store.save_planned_task(task)
        broadcast_event("routine_created", {
            "task_id": task_id,
            "title": task.title,
            "domain": task.domain,
            "origin": task.origin,
        })
        return JSONResponse({
            "success": True,
            "task_id": task_id,
            "title": task.title,
            "domain": task.domain,
            "scheduled_time": task.scheduled_time,
            "recurrence": task.recurrence,
            "origin": task.origin,
            "raw_statement": task.raw_statement,
            "confidence": task.confidence,
            "relative_time_anchor": task.relative_time_anchor,
            "session_id": task.session_id,
            "status": task.status,
        }, status_code=201)

    # GET
    domain = request.query_params.get("domain")
    status = request.query_params.get("status")
    origin = request.query_params.get("origin")
    filter_domain = None if (not domain or domain.lower() == "all") else domain.lower()
    filter_status = None if (not status or status.lower() == "all") else status.lower()
    filter_origin = None if (not origin or origin.lower() == "all") else origin.lower()

    tasks = store.list_planned_tasks(
        domain=filter_domain,
        status=filter_status,
        origin=filter_origin,
        ingest_source=request.query_params.get("ingest_source") or None,
    )
    result = []
    for t in tasks:
        result.append({
            "id": t.id,
            "title": t.title,
            "domain": t.domain,
            "scheduled_time": t.scheduled_time,
            "recurrence": t.recurrence,
            "origin": t.origin,
            "raw_statement": t.raw_statement,
            "confidence": t.confidence,
            "relative_time_anchor": t.relative_time_anchor,
            "session_id": t.session_id,
            "status": t.status,
            "completed_at": t.completed_at,
            "verified_action_id": t.verified_action_id,
            "created_at": t.created_at,
            "ingest_source": t.ingest_source,
            "ingest_run_id": t.ingest_run_id,
            "recovered": t.recovered,
        })
    return JSONResponse({"tasks": result, "count": len(result)})


@mcp.custom_route("/api/routines/{task_id}", methods=["PUT", "DELETE"])
async def api_routine_detail(request: Request) -> JSONResponse:
    """Updates (PUT) or deletes (DELETE) a planned routine task."""
    store = get_storage_store()
    task_id = request.path_params.get("task_id")
    if not task_id:
        return JSONResponse({"error": "Missing task_id"}, status_code=400)

    task = store.get_planned_task(task_id)
    if not task:
        return JSONResponse({"error": f"Task '{task_id}' not found"}, status_code=404)

    if request.method == "DELETE":
        deleted = store.delete_planned_task(task_id)
        if not deleted:
            return JSONResponse({"error": "Failed to delete task"}, status_code=500)
        broadcast_event("routine_deleted", {"task_id": task_id, "title": task.title})
        return JSONResponse({"success": True, "deleted_id": task_id})

    # PUT
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    if "title" in body and body["title"].strip():
        task.title = body["title"].strip()
    if "domain" in body:
        task.domain = body["domain"]
    if "scheduled_time" in body:
        task.scheduled_time = body["scheduled_time"]
    if "recurrence" in body:
        task.recurrence = body["recurrence"]
    if "origin" in body:
        task.origin = body["origin"]
    if "raw_statement" in body:
        task.raw_statement = body["raw_statement"]
    if "relative_time_anchor" in body:
        task.relative_time_anchor = body["relative_time_anchor"]
    if "status" in body:
        new_status = body["status"]
        if new_status == "completed" and task.status != "completed":
            task.completed_at = datetime.now().isoformat()
        elif new_status != "completed":
            task.completed_at = None
            task.verified_action_id = None
        task.status = new_status

    updated = store.update_planned_task(task)
    if not updated:
        return JSONResponse({"error": "Failed to update task"}, status_code=500)

    task_dict = {
        "id": task.id,
        "title": task.title,
        "domain": task.domain,
        "scheduled_time": task.scheduled_time,
        "recurrence": task.recurrence,
        "origin": task.origin,
        "raw_statement": task.raw_statement,
        "confidence": task.confidence,
        "relative_time_anchor": task.relative_time_anchor,
        "session_id": task.session_id,
        "status": task.status,
        "completed_at": task.completed_at,
        "verified_action_id": task.verified_action_id,
        "created_at": task.created_at,
    }
    broadcast_event("routine_updated", task_dict)
    return JSONResponse({"success": True, "task": task_dict})


@mcp.custom_route("/api/routines/{task_id}/toggle", methods=["POST"])
async def api_routine_toggle(request: Request) -> JSONResponse:
    """Toggles status between pending and completed for a planned routine."""
    store = get_storage_store()
    task_id = request.path_params.get("task_id")
    if not task_id:
        return JSONResponse({"error": "Missing task_id"}, status_code=400)

    task = store.get_planned_task(task_id)
    if not task:
        return JSONResponse({"error": f"Task '{task_id}' not found"}, status_code=404)

    if task.status == "completed":
        task.status = "pending"
        task.completed_at = None
        task.verified_action_id = None
    else:
        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

    store.update_planned_task(task)
    task_dict = {
        "id": task.id,
        "title": task.title,
        "domain": task.domain,
        "scheduled_time": task.scheduled_time,
        "recurrence": task.recurrence,
        "status": task.status,
        "completed_at": task.completed_at,
        "verified_action_id": task.verified_action_id,
        "created_at": task.created_at,
    }
    broadcast_event("routine_toggled", task_dict)
    return JSONResponse({"success": True, "task": task_dict})


@mcp.custom_route("/api/contacts", methods=["GET"])
async def api_contacts(request: Request) -> JSONResponse:
    """Lists or searches social contacts."""
    store = get_storage_store()
    query = request.query_params.get("q", "")
    contacts = store.search_social_contact(query=query)

    result = []
    for c in contacts:
        comms_list = []
        for com in (c.commitments or []):
            if hasattr(com, "model_dump"):
                comms_list.append(com.model_dump())
            elif isinstance(com, dict):
                comms_list.append(com)
            else:
                comms_list.append(str(com))

        result.append({
            "id": c.id,
            "name": c.person_name,
            "company_or_role": c.company_or_role,
            "contact_info": c.contact_info,
            "website_url": getattr(c, "website_url", None) or (c.web_profile.website_url if c.web_profile else None),
            "key_topics": c.key_topics,
            "commitments": comms_list,
            "web_profile": c.web_profile.model_dump() if c.web_profile else None,
            "timestamp": c.timestamp,
        })
    return JSONResponse({"contacts": result, "count": len(result)})


@mcp.custom_route("/api/contacts/{contact_id}/profile", methods=["GET"])
async def api_contact_profile(request: Request) -> JSONResponse:
    """Returns detailed dossier and web profile for a specific contact."""
    contact_id = request.path_params["contact_id"]
    from src.serving.tools.social_tools import execute_get_contact_profile
    data = execute_get_contact_profile(name_or_query=contact_id)
    if not data.get("found"):
        return JSONResponse({"error": f"Contact '{contact_id}' not found", "found": False}, status_code=404)
    return JSONResponse(data)


@mcp.custom_route("/api/contacts/{contact_id}/enrich", methods=["POST"])
async def api_enrich_contact(request: Request) -> JSONResponse:
    """Manually or autonomously triggers web intelligence enrichment for a contact."""
    contact_id = request.path_params["contact_id"]
    store = get_storage_store()
    contact = store.get_social_contact(contact_id)
    if not contact:
        matches = store.search_social_contact(query=contact_id)
        if matches:
            contact = matches[0]

    if not contact:
        return JSONResponse({"error": f"Contact '{contact_id}' not found", "found": False}, status_code=404)

    from src.pipeline.nodes.social_profiler import enrich_social_contact_sync
    profile = enrich_social_contact_sync(contact, store=store, force=True)
    if not profile:
        return JSONResponse({
            "success": False,
            "message": f"Unable to enrich profile for '{contact.person_name}': insufficient disambiguation anchors or no results.",
            "contact_id": contact.id,
        }, status_code=422)

    contact_dict = {
        "id": contact.id,
        "name": contact.person_name,
        "company_or_role": contact.company_or_role,
        "website_url": getattr(contact, "website_url", None) or profile.website_url,
        "web_profile": profile.model_dump(),
    }
    broadcast_event("contact_enriched", contact_dict)
    return JSONResponse({
        "success": True,
        "message": f"Successfully enriched profile for '{contact.person_name}'.",
        "web_profile": profile.model_dump(),
        "contact": contact_dict,
    })


@mcp.custom_route("/api/commitments", methods=["GET"])
async def api_commitments(request: Request) -> JSONResponse:
    """Returns bilateral commitments with optional filtering."""
    store = get_storage_store()
    contact_name = request.query_params.get("contact_name")
    debtor = request.query_params.get("debtor")
    status = request.query_params.get("status")
    limit = int(request.query_params.get("limit", "50"))

    commitments = store.list_social_commitments(
        contact_name=contact_name,
        debtor=debtor,
        status=status,
        limit=limit,
    )
    result = [
        {
            "id": c.id,
            "contact_name": c.contact_name,
            "debtor": c.debtor,
            "description": c.description,
            "due_date_raw": c.due_date_raw,
            "normalized_deadline": c.normalized_deadline,
            "status": c.status,
            "auto_scheduled_task_id": c.auto_scheduled_task_id,
            "created_at": c.created_at,
        }
        for c in commitments
    ]
    return JSONResponse({"commitments": result, "count": len(result)})


@mcp.custom_route("/api/commitments", methods=["POST"])
async def api_create_commitment(request: Request) -> JSONResponse:
    """Manually creates a new bilateral commitment."""
    store = get_storage_store()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    contact_name = body.get("contact_name")
    description = body.get("description")
    if not contact_name or not description:
        return JSONResponse({"error": "Fields 'contact_name' and 'description' are required"}, status_code=400)

    debtor = body.get("debtor", "user")
    if debtor not in ("user", "contact"):
        debtor = "user"

    commitment = SocialCommitment(
        contact_name=contact_name.strip(),
        debtor=debtor,
        description=description.strip(),
        due_date_raw=body.get("due_date_raw"),
        normalized_deadline=body.get("normalized_deadline"),
        status=body.get("status", "open"),
    )
    com_id = store.save_social_commitment(commitment)
    saved = store.get_social_commitment(com_id)
    if not saved:
        return JSONResponse({"error": "Failed to create commitment"}, status_code=500)

    com_dict = {
        "id": saved.id,
        "contact_name": saved.contact_name,
        "debtor": saved.debtor,
        "description": saved.description,
        "due_date_raw": saved.due_date_raw,
        "normalized_deadline": saved.normalized_deadline,
        "status": saved.status,
        "auto_scheduled_task_id": saved.auto_scheduled_task_id,
        "created_at": saved.created_at,
    }
    broadcast_event("commitment_created", com_dict)
    # If a planned task was created, also notify routines
    if saved.auto_scheduled_task_id:
        task = store.get_planned_task(saved.auto_scheduled_task_id)
        if task:
            broadcast_event("routine_created", {
                "id": task.id,
                "title": task.title,
                "domain": task.domain,
                "scheduled_time": task.scheduled_time,
                "recurrence": task.recurrence,
                "origin": task.origin,
                "status": task.status,
                "created_at": task.created_at,
            })
    return JSONResponse({"success": True, "commitment": com_dict}, status_code=201)


@mcp.custom_route("/api/commitments/{commitment_id}/fulfill", methods=["POST"])
async def api_fulfill_commitment(request: Request) -> JSONResponse:
    """Marks a bilateral commitment as fulfilled."""
    store = get_storage_store()
    commitment_id = request.path_params.get("commitment_id")
    if not commitment_id:
        return JSONResponse({"error": "Missing commitment_id"}, status_code=400)

    updated = store.update_social_commitment_status(commitment_id, "fulfilled")
    if not updated:
        return JSONResponse({"error": f"Commitment '{commitment_id}' not found"}, status_code=404)

    com = store.get_social_commitment(commitment_id)
    com_dict = {
        "id": com.id,
        "contact_name": com.contact_name,
        "debtor": com.debtor,
        "description": com.description,
        "due_date_raw": com.due_date_raw,
        "normalized_deadline": com.normalized_deadline,
        "status": com.status,
        "auto_scheduled_task_id": com.auto_scheduled_task_id,
        "created_at": com.created_at,
    }
    broadcast_event("commitment_updated", com_dict)
    if com.auto_scheduled_task_id:
        task = store.get_planned_task(com.auto_scheduled_task_id)
        if task:
            broadcast_event("routine_updated", {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "completed_at": task.completed_at,
            })

    return JSONResponse({"success": True, "commitment": com_dict})


@mcp.custom_route("/api/commitments/{commitment_id}/cancel", methods=["POST"])
async def api_cancel_commitment(request: Request) -> JSONResponse:
    """Marks a bilateral commitment as cancelled."""
    store = get_storage_store()
    commitment_id = request.path_params.get("commitment_id")
    if not commitment_id:
        return JSONResponse({"error": "Missing commitment_id"}, status_code=400)

    updated = store.update_social_commitment_status(commitment_id, "cancelled")
    if not updated:
        return JSONResponse({"error": f"Commitment '{commitment_id}' not found"}, status_code=404)

    com = store.get_social_commitment(commitment_id)
    com_dict = {
        "id": com.id,
        "contact_name": com.contact_name,
        "debtor": com.debtor,
        "description": com.description,
        "due_date_raw": com.due_date_raw,
        "normalized_deadline": com.normalized_deadline,
        "status": com.status,
        "auto_scheduled_task_id": com.auto_scheduled_task_id,
        "created_at": com.created_at,
    }
    broadcast_event("commitment_updated", com_dict)
    return JSONResponse({"success": True, "commitment": com_dict})


@mcp.custom_route("/api/commitments/{commitment_id}", methods=["GET", "DELETE"])
async def api_commitment_detail(request: Request) -> JSONResponse:
    """Retrieves (GET) or deletes (DELETE) a bilateral commitment."""
    store = get_storage_store()
    commitment_id = request.path_params.get("commitment_id")
    if not commitment_id:
        return JSONResponse({"error": "Missing commitment_id"}, status_code=400)

    com = store.get_social_commitment(commitment_id)
    if not com:
        return JSONResponse({"error": f"Commitment '{commitment_id}' not found"}, status_code=404)

    if request.method == "DELETE":
        deleted = store.delete_social_commitment(commitment_id)
        if not deleted:
            return JSONResponse({"error": "Failed to delete commitment"}, status_code=500)
        broadcast_event("commitment_deleted", {"id": commitment_id, "contact_name": com.contact_name})
        return JSONResponse({"success": True, "deleted_id": commitment_id})

    # GET
    com_dict = {
        "id": com.id,
        "contact_name": com.contact_name,
        "debtor": com.debtor,
        "description": com.description,
        "due_date_raw": com.due_date_raw,
        "normalized_deadline": com.normalized_deadline,
        "status": com.status,
        "auto_scheduled_task_id": com.auto_scheduled_task_id,
        "created_at": com.created_at,
    }
    return JSONResponse({"commitment": com_dict})


@mcp.custom_route("/api/cards/preview", methods=["GET"])
async def api_cards_preview(request: Request) -> JSONResponse:
    """Returns rich card payloads and spoken voice text for Echo Show Ext-App templates."""
    store = get_storage_store()
    template = request.query_params.get("template")
    query = request.query_params.get("query") or request.query_params.get("q")

    # 1. Briefing card
    from src.serving.tools.topic_tools import execute_get_topic_briefing
    briefing_card = execute_get_topic_briefing(topic_query=query, store=store) if query else execute_get_topic_briefing(store=store)
    if not briefing_card.get("found"):
        briefing_card = {
            "found": True,
            "topic_title": "AWS Bedrock AgentCore & Runtime Architecture",
            "context_type": "tech_stack",
            "created_at": datetime.now().isoformat(),
            "executive_summary": [
                "Serverless microVM execution runtime for autonomous LLM agents.",
                "Sub-second state restoration and bidirectional audio streaming.",
                "Built-in IAM credential isolation and automatic telemetry.",
            ],
            "explanatory_synthesis": "AWS Bedrock AgentCore provides high-performance microVM isolation tailored for ambient voice agents with strict low-latency requirements.",
            "web_sources": ["https://aws.amazon.com/bedrock", "https://docs.aws.amazon.com/bedrock/agentcore"],
            "action_items": ["Review IAM microVM execution policies", "Test audio chunking buffer"],
            "display_template": "DEEP_BRIEFING_VIEWER",
            "ui_card_type": "DEEP_BRIEFING_VIEWER",
            "spoken_summary": "Here is the briefing on AWS Bedrock AgentCore Runtime. It provides serverless microVM execution for autonomous LLM agents.",
            "card_payload": {
                "template": "DEEP_BRIEFING_VIEWER",
                "topic_title": "AWS Bedrock AgentCore & Runtime Architecture",
                "title": "AWS Bedrock AgentCore & Runtime Architecture",
                "context_type": "tech_stack",
                "bullets": [
                    "Serverless microVM execution runtime for autonomous LLM agents.",
                    "Sub-second state restoration and bidirectional audio streaming.",
                ],
                "synthesis": "AWS Bedrock AgentCore provides high-performance microVM isolation tailored for ambient voice agents.",
                "sources": ["https://aws.amazon.com/bedrock"],
            },
        }

    # 2. Social profile card
    from src.serving.tools.social_tools import execute_get_contact_profile
    if query:
        profile_card = execute_get_contact_profile(query, force_enrich=False, store=store)
    else:
        contacts_with_wp = [c for c in store.search_social_contact("") if c.web_profile]
        if contacts_with_wp:
            profile_card = execute_get_contact_profile(contacts_with_wp[0].person_name, force_enrich=False, store=store)
        else:
            profile_card = {"found": False}

    if not profile_card.get("found"):
        profile_card = {
            "found": True,
            "display_template": "SOCIAL_PROFILE_CARD",
            "ui_card_type": "SOCIAL_PROFILE_CARD",
            "contact": {
                "name": "Luca Bianchi",
                "company_or_role": "VP of Infrastructure @ CloudScale",
                "key_topics": ["Distributed Systems", "AWS Architecture"],
            },
            "web_profile": {
                "headline": "VP of Infrastructure @ CloudScale | ex-AWS DynamoDB",
                "organization": "CloudScale",
                "current_role": "VP of Infrastructure",
                "bio_summary": "Luca leads the distributed systems and cloud reliability team at CloudScale. Prior to CloudScale, he spent 6 years at AWS working on DynamoDB storage engines.",
                "areas_of_expertise": ["Distributed Systems", "Kubernetes", "AWS Architecture"],
                "linkedin_url": "https://www.linkedin.com/in/luca-bianchi-cloud",
                "github_url": "https://github.com/lbianchi-infra",
                "website_url": "https://cloudscale.io",
                "confidence_score": 0.98,
            },
            "commitments": [
                {
                    "contact_name": "Luca Bianchi",
                    "debtor": "user",
                    "description": "Send architecture whitepaper by Friday 5 PM",
                    "status": "open",
                }
            ],
            "open_commitments_count": 1,
            "spoken_summary": "Luca Bianchi is VP of Infrastructure at CloudScale. You have 1 open bilateral commitment.",
            "card_payload": {
                "template": "SOCIAL_PROFILE_CARD",
                "name": "Luca Bianchi",
                "headline": "VP of Infrastructure @ CloudScale | ex-AWS DynamoDB",
                "organization": "CloudScale",
                "bio_summary": "Luca leads the distributed systems and cloud reliability team at CloudScale.",
                "bio": "Luca leads the distributed systems and cloud reliability team at CloudScale.",
                "areas_of_expertise": ["Distributed Systems", "Kubernetes", "AWS Architecture"],
                "expertise": ["Distributed Systems", "Kubernetes", "AWS Architecture"],
                "linkedin": "https://www.linkedin.com/in/luca-bianchi-cloud",
                "github": "https://github.com/lbianchi-infra",
                "website": "https://cloudscale.io",
                "confidence": 0.98,
                "commitments": [
                    {"description": "Send architecture whitepaper by Friday 5 PM", "debtor": "user"}
                ],
                "spoken_summary": "Luca Bianchi is VP of Infrastructure at CloudScale. You have 1 open bilateral commitment.",
            },
        }

    # 3. Commitments card
    from src.serving.tools.social_tools import execute_get_social_commitments
    commitments_card = execute_get_social_commitments(contact_name=query, store=store) if query else execute_get_social_commitments(store=store)

    # 4. Action verified badge
    from src.serving.tools.action_tools import execute_verify_action_status, execute_get_daily_actions_recap, execute_get_upcoming_tasks
    if query:
        action_card = execute_verify_action_status(action_query=query, store=store)
    else:
        actions = store.list_recent_actions(limit=1)
        if actions:
            action_card = execute_verify_action_status(action_query=actions[0].action_type, store=store)
        else:
            action_card = {
            "status": "verified",
            "action_type": "unplug_clothes_iron",
            "domain": "safety",
            "timestamp": datetime.now().isoformat(),
            "raw_statement": "Ho appena staccato il ferro da stiro prima di uscire.",
            "confidence": 0.98,
            "elapsed_time_human": "just now",
            "display_template": "ACTION_VERIFIED_BADGE",
            "ui_card_type": "ACTION_VERIFIED_BADGE",
            "spoken_summary": "Yes, you confirmed unplugging the clothes iron: 'Ho appena staccato il ferro da stiro prima di uscire' just now.",
            "card_payload": {
                "template": "ACTION_VERIFIED_BADGE",
                "status": "verified",
                "action_type": "unplug_clothes_iron",
                "domain": "safety",
                "raw_statement": "Ho appena staccato il ferro da stiro prima di uscire.",
                "confidence": 0.98,
                "elapsed_time": "just now",
                "elapsed_time_human": "just now",
                "spoken_summary": "Yes, you confirmed unplugging the clothes iron: 'Ho appena staccato il ferro da stiro prima di uscire' just now.",
            },
        }

    # 5. Daily recap
    daily_card = execute_get_daily_actions_recap(store=store)

    # 6. Upcoming tasks
    upcoming_card = execute_get_upcoming_tasks(store=store)

    # 7. Session dossier card (Milestone 3.2)
    from src.serving.tools.session_tools import execute_get_session_dossier
    session_card = execute_get_session_dossier(store=store)
    if not session_card.get("found"):
        session_card = {
            "found": True,
            "session_id": "sess-arch-01",
            "title": "Architecture Session: Postgres to DynamoDB Migration",
            "domain": "meeting",
            "status": "concluded",
            "start_time": datetime.now().isoformat(),
            "concluded_at": datetime.now().isoformat(),
            "location": {"place_name": "Conference Room B", "semantic_zone": "office"},
            "transcript_chunks_count": 8,
            "key_discussion_points": [
                "DynamoDB Single-Table Design vs RDBMS Postgres",
                "GSI replication delay and 400KB item size constraints",
                "Deployment pipeline configuration via Terraform",
            ],
            "linked_micro_events": [
                {
                    "event_type": "action",
                    "record_id": "act-tf-01",
                    "headline": "Terraform apply executed (Tables created in eu-west-1)",
                    "timestamp": datetime.now().isoformat(),
                },
                {
                    "event_type": "task_scheduled",
                    "record_id": "tsk-bench-01",
                    "headline": "Deliver latency benchmarks to Marco",
                    "timestamp": datetime.now().isoformat(),
                },
                {
                    "event_type": "social_contact",
                    "record_id": "soc-sarah-01",
                    "headline": "Met Dr. Sarah Lin (Datadog Principal Architect)",
                    "timestamp": datetime.now().isoformat(),
                },
            ],
            "actions_count": 1,
            "tasks_count": 1,
            "contacts_count": 1,
            "display_template": "SESSION_DOSSIER_VIEWER",
            "ui_card_type": "SESSION_DOSSIER_VIEWER",
            "spoken_summary": "Here is the recap for Architecture Session: Postgres to DynamoDB Migration. I tracked 1 verified action, 1 scheduled task, and 1 contact encountered.",
            "card_payload": {
                "template": "SESSION_DOSSIER_VIEWER",
                "title": "Architecture Session: Postgres to DynamoDB Migration",
                "location_name": "Conference Room B",
                "explanatory_synthesis": "The team agreed on DynamoDB single-table design for sub-10ms read latencies, with GSI replication considerations.",
                "actions": [{"headline": "Terraform apply executed (Tables created in eu-west-1)"}],
                "tasks": [{"headline": "Deliver latency benchmarks to Marco"}],
                "contacts": [{"headline": "Dr. Sarah Lin (Datadog Principal Architect)"}],
                "status": "concluded",
                "is_final": True,
                "segments": [
                    {"index": 1, "title": "Postgres limits & access patterns", "status": "synthesized", "time_range": "14:00–14:22", "kind": "segment"},
                    {"index": 2, "title": "DynamoDB single-table design", "status": "synthesized", "time_range": "14:27–14:45", "kind": "segment"},
                ],
            },
        }

    cards = {
        "DEEP_BRIEFING_VIEWER": briefing_card,
        "SOCIAL_PROFILE_CARD": profile_card,
        "SOCIAL_COMMITMENTS_CARD": commitments_card,
        "ACTION_VERIFIED_BADGE": action_card,
        "DAILY_ACTIONS_RECAP": daily_card,
        "UPCOMING_TASKS_VIEWER": upcoming_card,
        "SESSION_DOSSIER_VIEWER": session_card,
    }

    if template:
        selected = cards.get(template, briefing_card)
        return JSONResponse(selected)

    return JSONResponse({"cards": cards})


@mcp.custom_route("/api/topics", methods=["GET"])
async def api_topics(request: Request) -> JSONResponse:
    """Lists recent synthesized technical briefings."""
    store = get_storage_store()
    limit = int(request.query_params.get("limit", "10"))
    topics = store.list_topic_briefings(
        limit=limit,
        kind=request.query_params.get("kind") or None,
        session_id=request.query_params.get("session_id") or None,
    )

    result = []
    for t in topics:
        result.append({
            "id": t.id,
            "topic_title": t.topic_title,
            "context_type": t.context_type,
            "executive_summary": t.executive_summary,
            "explanatory_synthesis": t.explanatory_synthesis,
            "web_sources": t.web_sources,
            "action_items": t.action_items,
            "deep_dive_markdown": t.deep_dive_markdown,
            "created_at": t.created_at,
            "kind": t.kind,
            "session_id": t.session_id,
            "segment_id": t.segment_id,
        })
    return JSONResponse({"topics": result, "count": len(result)})


@mcp.custom_route("/api/sessions", methods=["GET"])
async def api_sessions(request: Request) -> JSONResponse:
    """Lists recorded macro session dossiers."""
    store = get_storage_store()
    status = request.query_params.get("status")
    limit = int(request.query_params.get("limit", "10"))
    events_only = request.query_params.get("events_only", "").lower() in ("1", "true", "yes")
    dossiers = store.list_session_dossiers(
        status=status,
        limit=limit * 3 if events_only else limit,
        ingest_source=request.query_params.get("ingest_source") or None,
        ingest_run_id=request.query_params.get("ingest_run_id") or None,
    )
    if events_only:
        dossiers = [d for d in dossiers if d.segments][:limit]
    result = [_session_summary(d) for d in dossiers]
    return JSONResponse({"sessions": result, "count": len(result)})


def _session_summary(d: Any) -> Dict[str, Any]:
    """Lightweight event/session card for lists (no transcript, no embedding centroid)."""
    from src.serving.tools.session_tools import _segment_payload, _top_terms

    return {
        "session_id": d.session_id,
        "title": d.title,
        "domain": d.domain,
        "status": d.status,
        "final_status": d.final_status,
        "start_time": d.start_time,
        "last_updated_at": d.last_updated_at,
        "concluded_at": d.concluded_at,
        "paused_at": d.paused_at,
        "hard_close_deadline": d.hard_close_deadline,
        "location_name": (d.location or {}).get("place_name") if d.location else None,
        "conversation_uuids": d.conversation_uuids,
        "segments": [{k: v for k, v in _segment_payload(s, {}).items() if k != "briefing"} for s in d.segments],
        "final_briefing_id": d.final_briefing_id,
        "final_title": d.briefing_report.topic_title if d.briefing_report else None,
        "micro_events_count": len(d.linked_micro_events),
        "linked_micro_events": [e.model_dump() for e in d.linked_micro_events],
        "last_transition": d.transitions[-1].model_dump() if d.transitions else None,
        "transitions_count": len(d.transitions),
        "top_terms": _top_terms(d, 6),
        "transcript_chunks_count": len(d.transcript_chunks),
        "ingest_source": d.ingest_source,
        "ingest_run_id": d.ingest_run_id,
    }


@mcp.custom_route("/api/sessions/{session_id}", methods=["GET"])
async def api_session_detail(request: Request) -> JSONResponse:
    """Retrieves a specific session dossier by ID."""
    session_id = request.path_params.get("session_id")
    from src.serving.tools.session_tools import execute_get_session_dossier
    data = execute_get_session_dossier(session_id=session_id)
    if not data.get("found"):
        return JSONResponse({"error": f"Session '{session_id}' not found", "found": False}, status_code=404)
    return JSONResponse(data)


@mcp.custom_route("/api/sessions/{session_id}/conclude", methods=["POST"])
async def api_session_conclude(request: Request) -> JSONResponse:
    """Concludes a session/event (rule R8). Final synthesis is scheduled asynchronously."""
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Missing session_id"}, status_code=400)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    store = get_storage_store()
    briefing_id = body.get("briefing_report_id")
    existing = store.get_session_dossier(session_id)
    if existing is None:
        return JSONResponse({"error": f"Session '{session_id}' not found"}, status_code=404)

    if briefing_id or (not existing.segments and body.get("auto_synthesize")):
        # Legacy sessions (no segments) or explicit briefing linkage
        from src.ingestion.session_manager import SessionManager
        mgr = SessionManager(store=store)
        if briefing_id:
            dossier = mgr.conclude_session(session_id=session_id, briefing_report_id=briefing_id)
        else:
            await asyncio.to_thread(mgr.synthesize_session_dossier, session_id, True)
            dossier = store.get_session_dossier(session_id)
    else:
        engine = _ensure_event_engine()
        dossier = engine.conclude(session_id)

    if not dossier:
        return JSONResponse({"error": f"Session '{session_id}' not found"}, status_code=404)

    broadcast_event("session_concluded", dossier.model_dump())
    return JSONResponse({"success": True, "concluded": True, "dossier": dossier.model_dump()})


@mcp.custom_route("/api/sessions/{session_id}/chunks", methods=["GET"])
async def api_session_chunks(request: Request) -> JSONResponse:
    """Paginated transcript of an event (session_chunks)."""
    session_id = request.path_params.get("session_id")
    store = get_storage_store()
    segment_id = request.query_params.get("segment_id") or None
    limit = int(request.query_params.get("limit", "500"))
    seg_of = store.get_chunk_segments(session_id)
    chunks = store.list_session_chunks(session_id, segment_id=segment_id, limit=limit)
    return JSONResponse({
        "session_id": session_id,
        "count": len(chunks),
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "timestamp": c.timestamp,
                "text": c.text,
                "speaker_id": c.speaker_id,
                "speaker_role": c.speaker_role,
                "categories": c.categories,
                "segment_id": seg_of.get(c.chunk_id),
            }
            for c in chunks
        ],
    })


def _engine_op_response(event_type: str, dossier: Any, error: str) -> JSONResponse:
    if dossier is None:
        return JSONResponse({"success": False, "error": error}, status_code=409)
    payload = _session_summary(dossier)
    broadcast_event(event_type, payload)
    return JSONResponse({"success": True, "event": payload})


@mcp.custom_route("/api/sessions/{session_id}/pause", methods=["POST"])
async def api_session_pause(request: Request) -> JSONResponse:
    """Manual soft close: closes the current segment and synthesizes it now."""
    engine = _ensure_event_engine()
    dossier = await asyncio.to_thread(engine.pause, request.path_params.get("session_id"))
    return _engine_op_response("event_paused", dossier, "Only the active event can be paused")


@mcp.custom_route("/api/sessions/{session_id}/resume", methods=["POST"])
async def api_session_resume(request: Request) -> JSONResponse:
    """Forces the paused current event to resume (overrides a pending split decision)."""
    engine = _ensure_event_engine()
    dossier = await asyncio.to_thread(engine.resume, request.path_params.get("session_id"))
    return _engine_op_response("event_resumed", dossier, "Only the paused current event can be resumed")


@mcp.custom_route("/api/sessions/{session_id}/split", methods=["POST"])
async def api_session_split(request: Request) -> JSONResponse:
    """Manual split: {"at_time": ISO} or {"at_chunk_id": str}; later chunks move to a new event."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    engine = _ensure_event_engine()
    result = await asyncio.to_thread(
        engine.split, request.path_params.get("session_id"), body.get("at_time"), body.get("at_chunk_id")
    )
    if result is None:
        return JSONResponse({"success": False, "error": "Nothing to split at that point"}, status_code=409)
    old, new = result
    payload = {"old": _session_summary(old), "new": _session_summary(new)}
    broadcast_event("event_split", payload)
    return JSONResponse({"success": True, **payload})


@mcp.custom_route("/api/sessions/merge", methods=["POST"])
async def api_sessions_merge(request: Request) -> JSONResponse:
    """Manual merge: {"session_ids": [...]} into the earliest event; its final briefing is regenerated."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = body.get("session_ids") or []
    engine = _ensure_event_engine()
    target = await asyncio.to_thread(engine.merge, ids)
    return _engine_op_response("event_merged", target, "Provide at least two existing events")


@mcp.custom_route("/api/simulate/tick", methods=["POST"])
async def api_simulate_tick(request: Request) -> JSONResponse:
    """Simulator: fast-forwards the event engine virtual clock by {"seconds": n} and runs its timers."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    engine = _ensure_event_engine()
    if body.get("reset"):
        engine.clock_offset = 0.0
        transitions = []
    else:
        transitions = await asyncio.to_thread(engine.advance_clock, float(body.get("seconds", 60)))
    return JSONResponse({
        "success": True,
        "clock_offset_seconds": engine.clock_offset,
        "virtual_now": datetime.fromtimestamp(engine.now()).isoformat(),
        "transitions": [
            {"rule": t.rule, "to_status": t.to_status, "reason": t.reason, "detail": t.detail} for t in transitions
        ],
        **engine.status_summary(),
    })


@mcp.custom_route("/api/event-scenarios", methods=["GET"])
async def api_event_scenarios(request: Request) -> JSONResponse:
    """Replay scenarios for the simulator scenario player (resources/event_scenarios.json)."""
    from src.ingestion.scenario_replay import load_event_scenarios

    try:
        scenarios = load_event_scenarios()
    except FileNotFoundError:
        scenarios = []
    return JSONResponse({"scenarios": scenarios, "count": len(scenarios)})


@mcp.custom_route("/api/event-engine/status", methods=["GET"])
async def api_event_engine_status(request: Request) -> JSONResponse:
    """Returns the Deep Topic Event Engine state (open event, pending synthesis jobs, config)."""
    engine = _ensure_event_engine()
    cfg = engine.config
    return JSONResponse({
        "enabled": settings.event_engine_enabled,
        "profile": settings.event_profile,
        "config": {
            "t_soft_seconds": cfg.t_soft,
            "t_hard_seconds": cfg.t_hard,
            "t_checkpoint_seconds": cfg.t_checkpoint,
            "min_segment_words": cfg.min_segment_words,
        },
        "clock_offset_seconds": engine.clock_offset,
        "virtual_now": datetime.fromtimestamp(engine.now()).isoformat(),
        **engine.status_summary(),
    })


@mcp.custom_route("/api/simulate", methods=["POST"])
async def api_simulate(request: Request) -> JSONResponse:
    """Simulates an ambient speech chunk through the AgentCore pipeline.
    
    Accepts: {"transcript_chunk": str, "actor_id": Optional[str], "event_mode": Optional[bool],
              "timestamp": Optional[ISO str], "location": Optional[dict], "speaker_role": Optional[str],
              "conversation_uuid": Optional[str]}
    With event_mode the chunk is routed through the Deep Topic Event Engine (deep_topic content is
    accumulated into an event and synthesized per segment/event instead of per utterance).
    Returns: Complete execution response with gatekeeper decision and extracted state.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    chunk = body.get("transcript_chunk") or body.get("raw_transcript") or body.get("text")
    if not chunk or not chunk.strip():
        return JSONResponse({"error": "Field 'transcript_chunk' is required"}, status_code=400)

    actor_id = body.get("actor_id", "user_web_sim")
    timestamp = body.get("timestamp") or datetime.now().isoformat()
    payload: Dict[str, Any] = {
        "raw_transcript": chunk.strip(),
        "transcript_chunk": chunk.strip(),
        "timestamp": timestamp,
        "actor_id": actor_id,
    }
    if body.get("location"):
        payload["location"] = body["location"]
    if body.get("speaker_role"):
        payload["speaker_role"] = body["speaker_role"]

    start_time = datetime.now()
    try:
        event_info: Optional[Dict[str, Any]] = None
        if body.get("event_mode") and settings.event_engine_enabled:
            # Route through the shared Deep Topic Event Engine (doc 05 §4)
            from src.core.schemas import UtteranceChunk
            from src.ingestion.gatekeeper import aclassify_chunk

            from src.core.schemas import ChunkClassification

            engine = _ensure_event_engine()
            if not body.get("timestamp"):
                # Engine time includes the simulator virtual clock offset
                timestamp = datetime.fromtimestamp(engine.now()).isoformat()
                payload["timestamp"] = timestamp
            if body.get("categories"):
                # Scenario player: replay the recorded gatekeeper labels (fast, deterministic)
                classification = ChunkClassification(
                    categories=list(body["categories"]), confidence=1.0, summary_hint="scenario label"
                )
            else:
                event_hint = engine.active_event_hint()
                classification = await aclassify_chunk(transcript=chunk.strip(), prior_context=event_hint or None)
            utterance = UtteranceChunk(
                conversation_uuid=body.get("conversation_uuid") or "web_simulator",
                text=chunk.strip(),
                speaker_role=body.get("speaker_role") or "unknown",
                timestamp=timestamp,
                received_at=timestamp,
                categories=list(classification.categories),
                location=body.get("location"),
            )
            outcome = await asyncio.to_thread(engine.record_chunk, utterance)
            event_info = {
                "session_id": outcome.event_id,
                "status": outcome.event_status,
                "on_topic": outcome.on_topic,
                "transitions": [
                    {"rule": t.rule, "to_status": t.to_status, "reason": t.reason, "detail": t.detail}
                    for t in outcome.transitions
                ],
            }
            payload.update({
                "categories": classification.categories,
                "confidence": classification.confidence,
                "summary_hint": classification.summary_hint,
                "session_id": outcome.event_id or utterance.conversation_uuid,
                "utterance_id": utterance.chunk_id,
                "event_managed": outcome.event_managed,
            })

        # agent_invocation is synchronous: keep it off the event loop
        result = await asyncio.to_thread(agent_invocation, payload)
        if event_info is not None:
            result["event"] = event_info
        elapsed_sec = (datetime.now() - start_time).total_seconds()
        elapsed_ms = round(elapsed_sec * 1000.0, 1)

        try:
            store = get_storage_store()
            store.record_latency(
                event_type="api_simulate",
                latency_ms=elapsed_ms,
                model_id=settings.reasoner_model_id,
                details={"categories": result.get("categories"), "actor_id": actor_id},
            )
        except Exception:
            pass

        broadcast_event("pipeline_invoked", {
            "summary": result.get("summary"),
            "elapsed_seconds": round(elapsed_sec, 3),
            "elapsed_ms": elapsed_ms,
        })
        return JSONResponse({
            "success": True,
            "elapsed_seconds": round(elapsed_sec, 3),
            "elapsed_ms": elapsed_ms,
            "result": result,
        })
    except Exception as e:
        logger.exception("Error executing simulation pipeline")
        return JSONResponse({
            "success": False,
            "error": str(e),
        }, status_code=500)


# ---------------------------------------------------------------------------
# Historical Transcript Backfill (docs/next_steps/historical_backfill/04 §3)
# ---------------------------------------------------------------------------

def _history_status() -> Dict[str, Any]:
    """Coverage + backfill summary shared by /api/status and /api/orchestrator/status."""
    from src.ingestion.coverage import compute_gaps

    store = get_storage_store()
    mgr = _runtime()
    now = datetime.now().replace(microsecond=0)
    week_ago = (now - timedelta(days=7)).isoformat()
    coverage: Dict[str, Any] = {"live_since": mgr.live_since(), "last_gap": None, "uncovered_seconds_7d": None}
    try:
        intervals = store.list_coverage(week_ago, now.isoformat())
        if intervals:
            first_start = min(i.start for i in intervals)
            gaps = compute_gaps(first_start, mgr.live_since() or now.isoformat(), intervals,
                                min_gap_seconds=settings.backfill_min_gap_seconds)
            coverage["last_gap"] = gaps[-1].model_dump() if gaps else None
            coverage["uncovered_seconds_7d"] = round(sum(g.seconds for g in gaps), 1)
    except NotImplementedError:
        pass
    backfill: Dict[str, Any] = {"enabled": settings.backfill_enabled, "active_run": None, "queued": 0}
    if settings.backfill_enabled:
        backfill = _runtime().backfill.status_summary()
    return {"coverage": coverage, "backfill": backfill}


def _backfill_error(e: Exception) -> JSONResponse:
    from src.ingestion.backfill import BackfillRequestError

    if isinstance(e, BackfillRequestError):
        return JSONResponse({"error": e.code, "message": str(e), **e.extra}, status_code=e.status)
    logger.warning(f"History backfill request failed: {e}")
    return JSONResponse({"error": "backfill_failed", "message": str(e)}, status_code=502)


def _backfill_window(params: Dict[str, Any], default_days: float = 1.0) -> Tuple[str, str]:
    now = datetime.now().replace(microsecond=0)
    window_to = params.get("to") or params.get("window_to") or now.isoformat()
    window_from = params.get("from") or params.get("window_from") or (now - timedelta(days=default_days)).isoformat()
    return str(window_from), str(window_to)


@mcp.custom_route("/api/backfill/coverage", methods=["GET"])
async def api_backfill_coverage(request: Request) -> JSONResponse:
    """Coverage timeline: live/backfill intervals, gaps and per-hour/day buckets."""
    from src.ingestion.coverage import compute_gaps, coverage_buckets, coverage_summary

    store = get_storage_store()
    window_from, window_to = _backfill_window(dict(request.query_params), default_days=7)
    bucket = request.query_params.get("bucket", "hour")
    intervals = store.list_coverage(window_from, window_to)
    return JSONResponse({
        "window_from": window_from,
        "window_to": window_to,
        "live_since": _runtime().live_since(),
        "summary": coverage_summary(window_from, window_to, intervals),
        "intervals": [i.model_dump() for i in intervals],
        "gaps": [g.model_dump() for g in compute_gaps(window_from, window_to, intervals)],
        "buckets": coverage_buckets(window_from, window_to, intervals, "day" if bucket == "day" else "hour"),
    })


@mcp.custom_route("/api/backfill/preview", methods=["POST"])
async def api_backfill_preview(request: Request) -> JSONResponse:
    """Cost-free plan of a window: Bee REST calls only, no LLM."""
    if not settings.backfill_enabled:
        return JSONResponse({"error": "disabled"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    window_from, window_to = _backfill_window(body)
    service = _ensure_backfill_service()
    try:
        result = await service.preview(window_from, window_to, bool(body.get("retry_failed_live", True)))
    except Exception as e:
        return _backfill_error(e)
    from src.ingestion.backfill import over_budget

    return JSONResponse({**result.plan.model_dump(), "over_budget": over_budget(result.plan)})


@mcp.custom_route("/api/backfill/runs", methods=["GET", "POST"])
async def api_backfill_runs(request: Request) -> JSONResponse:
    """Lists runs (GET) or queues a manual run (POST, 202)."""
    if not settings.backfill_enabled:
        return JSONResponse({"error": "disabled"}, status_code=404)
    service = _ensure_backfill_service()
    if request.method == "GET":
        status = request.query_params.get("status")
        limit = int(request.query_params.get("limit", "20"))
        runs = service.list_runs(statuses=[status] if status else None, limit=limit)
        return JSONResponse({"runs": [r.model_dump() for r in runs], "count": len(runs)})
    try:
        body = await request.json()
    except Exception:
        body = {}
    window_from, window_to = _backfill_window(body)
    try:
        run = await service.create_run(
            window_from,
            window_to,
            retry_failed_live=bool(body.get("retry_failed_live", True)),
            confirm_over_budget=bool(body.get("confirm_over_budget", False)),
            requested_by=body.get("user_id") or request.headers.get("x-user-id"),
        )
    except Exception as e:
        return _backfill_error(e)
    return JSONResponse({"run": run.model_dump()}, status_code=202)


@mcp.custom_route("/api/backfill/runs/{run_id}", methods=["GET"])
async def api_backfill_run_detail(request: Request) -> JSONResponse:
    """One run with links to what it produced."""
    run_id = request.path_params.get("run_id")
    service = _ensure_backfill_service()
    run = service.get_run(run_id)
    if run is None:
        return JSONResponse({"error": f"Backfill run '{run_id}' not found"}, status_code=404)
    store = get_storage_store()
    events = store.list_session_dossiers(limit=100, ingest_run_id=run_id)
    return JSONResponse({
        "run": run.model_dump(),
        "progress": service.progress_payload(run),
        "links": {
            "events": [_session_summary(d) for d in events],
            "actions": run.counters.get("actions", 0),
            "contacts": run.counters.get("contacts", 0),
            "tasks": run.counters.get("tasks", 0),
        },
    })


@mcp.custom_route("/api/backfill/runs/{run_id}/cancel", methods=["POST"])
async def api_backfill_run_cancel(request: Request) -> JSONResponse:
    """Cancels a queued run, or stops a running one after the in-flight utterance."""
    run_id = request.path_params.get("run_id")
    run = _ensure_backfill_service().cancel(run_id)
    if run is None:
        return JSONResponse({"error": f"Backfill run '{run_id}' not found"}, status_code=404)
    return JSONResponse({"run": run.model_dump()})


@mcp.custom_route("/api/backfill/settings", methods=["GET"])
async def api_backfill_settings(request: Request) -> JSONResponse:
    """Effective BACKFILL_* configuration (read-only)."""
    data = {k: v for k, v in settings.model_dump().items() if k.startswith(("backfill_", "coverage_"))}
    return JSONResponse({"settings": data})


# ---------------------------------------------------------------------------
# ASGI Application Builder & Server Runner
# ---------------------------------------------------------------------------

def create_app() -> Starlette:
    """Constructs the unified ASGI application serving MCP, API, and Web UI."""
    app = mcp.streamable_http_app()

    # Multi-user: every /api and /mcp request runs as an authenticated user (docs/next_steps/multi_user/04 §1)
    app.add_middleware(AuthMiddleware)
    # CORS (outermost): credentialed requests need explicit origins, so only local dev origins are allowed
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mcp_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(asgi_app):
        async with mcp_lifespan(asgi_app):
            await asyncio.to_thread(get_auth_provider().ensure_bootstrap_admin)
            startup = asyncio.create_task(get_runtime_manager().start_all_linked())
            try:
                yield
            finally:
                startup.cancel()
                await get_runtime_manager().shutdown_all()

    app.router.lifespan_context = lifespan

    # Locate static web UI directory (Next.js static export 'out' folder)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    web_ui_dir = os.path.join(project_root, "src", "web_ui", "out")

    if os.path.isdir(web_ui_dir):
        logger.info(f"Mounting Web UI static assets from: {web_ui_dir}")
        # Mount for Echo Show Ext-App sandboxed iframe
        app.mount("/ext-app", StaticFiles(directory=web_ui_dir, html=True), name="ext-app")
        # Mount for root web dashboard
        app.mount("/", StaticFiles(directory=web_ui_dir, html=True), name="web-ui")
    else:
        logger.warning(f"Next.js static export directory not found at {web_ui_dir}. Run 'npm run build' in src/web_ui. Skipping static mount.")

    return app


app = create_app()


def run_server(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> None:
    """Starts the FastMCP & Web UI server using Uvicorn."""
    srv_host = host or settings.mcp_host
    srv_port = port or settings.mcp_port

    logger.info(f"Starting EXAMEN FastMCP & Web UI on http://{srv_host}:{srv_port}")
    logger.info(f" - Alexa+ MCP Endpoint: http://{srv_host}:{srv_port}/mcp")
    logger.info(f" - Web Dashboard UI:    http://{srv_host}:{srv_port}/")
    logger.info(f" - Echo Show Ext-App:   http://{srv_host}:{srv_port}/ext-app/")
    logger.info(f" - REST APIs:           http://{srv_host}:{srv_port}/api/status")

    uvicorn.run(app, host=srv_host, port=srv_port, log_level="info")


if __name__ == "__main__":
    run_server()
