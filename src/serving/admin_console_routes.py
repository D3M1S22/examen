"""Admin console API: runtime settings, service log, incidents, health, admin SSE channel.

docs/next_steps/admin_console/04 §1. Every route is under ``/api/admin/``: session-only
(``SESSION_ONLY_PREFIXES``) and admin-only (``_require_admin``). Nothing here reads a user's store:
events and incidents are sanitised service data, users appear as their account e-mail.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from src.core.auth import get_auth_store
from src.core.ops_store import get_ops_store, iso, utcnow
from src.core.runtime_settings import SettingsError, get_settings_service
from src.serving.admin_routes import _require_admin
from src.serving.auth_middleware import read_cookie

logger = logging.getLogger("examen.serving.admin_console")


class AdminHub:
    """Admin-only SSE subscribers. Never a tenant channel: user events are never routed here."""

    def __init__(self) -> None:
        self._subscribers: List[Tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._subscribers.append((queue, asyncio.get_running_loop()))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(q, loop) for q, loop in self._subscribers if q is not queue]

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Thread-safe (the service log writer thread publishes here)."""
        message = {"type": event_type, "data": data}
        with self._lock:
            targets = list(self._subscribers)
        for queue, loop in targets:
            if loop.is_closed():
                continue

            def _put(q=queue):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(message)

            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                pass

    def on_sink(self, kind: str, payload: Dict[str, Any]) -> None:
        if kind == "event" and payload.get("level") in ("warning", "error", "critical"):
            self.publish("service_event", public_event(payload))
        elif kind == "incident":
            self.publish(incident_event_type(payload), public_incident(payload))

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subscribers)


hub = AdminHub()


@dataclass
class ConsoleState:
    monitor: Any = None


state = ConsoleState()


def incident_event_type(inc: Dict[str, Any]) -> str:
    if inc.get("status") == "resolved":
        return "incident_resolved"
    return "incident_opened" if inc.get("count", 0) <= 1 or inc.get("first_seen") == inc.get("last_seen") \
        else "incident_updated"


def _emails() -> Dict[str, str]:
    return {u.id: u.email for u in get_auth_store().list_users()}


def public_event(event: Dict[str, Any], emails: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    out = {k: event.get(k) for k in ("id", "ref", "at", "level", "code", "component", "user_id", "message",
                                     "fingerprint", "context", "error_type", "location")}
    if out.get("user_id"):
        out["user_email"] = (emails if emails is not None else _emails()).get(out["user_id"])
    return out


def public_incident(inc: Dict[str, Any], emails: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    out = dict(inc)
    if out.get("user_id"):
        out["user_email"] = (emails if emails is not None else _emails()).get(out["user_id"])
    return out


async def _json(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _settings_error(e: SettingsError) -> JSONResponse:
    return JSONResponse({"error": e.code, "message": e.message, "errors": e.errors}, status_code=e.status)


def register_admin_console_routes(mcp: Any) -> None:

    # ------------------------------------------------------------------ settings

    @mcp.custom_route("/api/admin/settings", methods=["GET", "PUT"])
    async def api_admin_settings(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        service = get_settings_service()
        if request.method == "GET":
            return JSONResponse(json.loads(json.dumps(service.describe(), default=str)))
        body = await _json(request)
        try:
            result = await service.save(body.get("changes") or {}, admin.id, force=bool(body.get("force")),
                                        base_version=body.get("base_version"), note=(body.get("note") or None))
        except SettingsError as e:
            return _settings_error(e)
        result["requires_restart"] = []
        return JSONResponse(result)

    @mcp.custom_route("/api/admin/settings/test", methods=["POST"])
    async def api_admin_settings_test(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        body = await _json(request)
        try:
            return JSONResponse(await get_settings_service().test(body.get("changes") or {}, admin.id))
        except SettingsError as e:
            return _settings_error(e)

    @mcp.custom_route("/api/admin/settings/history", methods=["GET"])
    async def api_admin_settings_history(request: Request) -> JSONResponse:
        _, denied = _require_admin()
        if denied:
            return denied
        limit = int(request.query_params.get("limit", "50") or 50)
        emails = _emails()
        history = get_settings_service().history(limit)
        for entry in history:
            entry["by_email"] = emails.get(entry["by_user"])
        return JSONResponse({"history": history})

    @mcp.custom_route("/api/admin/settings/revert", methods=["POST"])
    async def api_admin_settings_revert(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        body = await _json(request)
        try:
            return JSONResponse(await get_settings_service().revert(str(body.get("change_id") or ""), admin.id))
        except SettingsError as e:
            return _settings_error(e)

    @mcp.custom_route("/api/admin/settings/reset-all", methods=["POST"])
    async def api_admin_settings_reset_all(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        return JSONResponse(await get_settings_service().reset(admin.id))

    @mcp.custom_route("/api/admin/settings/{key}", methods=["DELETE"])
    async def api_admin_settings_reset_key(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        try:
            return JSONResponse(await get_settings_service().reset(admin.id, request.path_params["key"]))
        except SettingsError as e:
            return _settings_error(e)

    # ------------------------------------------------------------- service log

    @mcp.custom_route("/api/admin/logs", methods=["GET"])
    async def api_admin_logs(request: Request) -> JSONResponse:
        _, denied = _require_admin()
        if denied:
            return denied
        q = request.query_params

        def _int(name: str) -> Optional[int]:
            try:
                return int(q[name]) if q.get(name) else None
            except ValueError:
                return None

        events = get_ops_store().list_events(
            level=q.get("level") or None, component=q.get("component") or None, code=q.get("code") or None,
            user_id=q.get("user_id") or None, since=q.get("since") or None, until=q.get("until") or None,
            q=q.get("q") or None, before_id=_int("before_id"), limit=_int("limit") or 100)
        emails = _emails()
        return JSONResponse({"events": [public_event(e, emails) for e in events]})

    @mcp.custom_route("/api/admin/incidents", methods=["GET"])
    async def api_admin_incidents(request: Request) -> JSONResponse:
        _, denied = _require_admin()
        if denied:
            return denied
        q = request.query_params
        incidents = get_ops_store().list_incidents(
            status=q.get("status") or "active", severity=q.get("severity") or None,
            component=q.get("component") or None, user_id=q.get("user_id") or None)
        emails = _emails()
        return JSONResponse({"incidents": [public_incident(i, emails) for i in incidents]})

    @mcp.custom_route("/api/admin/incidents/{incident_id}", methods=["GET"])
    async def api_admin_incident(request: Request) -> JSONResponse:
        _, denied = _require_admin()
        if denied:
            return denied
        store = get_ops_store()
        inc = store.get_incident(request.path_params["incident_id"])
        if inc is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        emails = _emails()
        events = [] if inc["fingerprint"].startswith("check:") else \
            store.list_events(fingerprint=inc["fingerprint"], limit=50)
        return JSONResponse({"incident": public_incident(inc, emails), "events": [public_event(e, emails) for e in events]})

    @mcp.custom_route("/api/admin/incidents/{incident_id}/{action}", methods=["POST"])
    async def api_admin_incident_action(request: Request) -> JSONResponse:
        admin, denied = _require_admin()
        if denied:
            return denied
        action = request.path_params["action"]
        if action not in ("ack", "resolve"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        store = get_ops_store()
        inc = store.get_incident(request.path_params["incident_id"])
        if inc is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if action == "ack" and inc["status"] == "open":
            inc.update(status="acknowledged", ack_by=admin.id)
        elif action == "resolve" and inc["status"] != "resolved":
            inc.update(status="resolved", resolved_at=iso(utcnow()))
        store.save_incident(inc)
        get_auth_store().audit("incident_acknowledged" if action == "ack" else "incident_resolved", actor_id=admin.id,
                               detail={"incident_id": inc["id"], "code": inc["code"]})
        public = public_incident(inc)
        hub.publish(incident_event_type(inc) if action == "resolve" else "incident_updated", public)
        return JSONResponse({"incident": public})

    @mcp.custom_route("/api/admin/audit", methods=["GET"])
    async def api_admin_audit(request: Request) -> JSONResponse:
        """Security log (audit_log): events, actor and subject accounts, no personal data."""
        _, denied = _require_admin()
        if denied:
            return denied
        limit = max(1, min(int(request.query_params.get("limit", "100") or 100), 500))
        emails = _emails()
        rows = get_auth_store().list_audit(limit=limit)
        for row in rows:
            row["user_email"] = emails.get(row.get("user_id"))
            row["actor_email"] = emails.get(row.get("actor_id"))
        return JSONResponse({"audit": rows})

    # ----------------------------------------------------------------- health

    @mcp.custom_route("/api/admin/health", methods=["GET"])
    async def api_admin_health(request: Request) -> JSONResponse:
        _, denied = _require_admin()
        if denied:
            return denied
        monitor = state.monitor
        if monitor is None:
            return JSONResponse({"error": "unavailable", "message": "Health monitor not running"}, status_code=503)
        snap = await asyncio.to_thread(monitor.snapshot)
        emails = _emails()
        for row in snap["streams"]["users"]:
            row["user_email"] = emails.get(row["user_id"])
        snap["settings_version"] = get_settings_service().version
        return JSONResponse(snap)

    # --------------------------------------------------------- admin SSE channel

    @mcp.custom_route("/api/admin/events", methods=["GET"])
    async def api_admin_events(request: Request):
        admin, denied = _require_admin()
        if denied:
            return denied
        cookie = read_cookie(request.scope)
        queue = hub.subscribe()

        def _still_admin() -> bool:
            user = get_auth_store().user_for_session(cookie) if cookie else None
            return bool(user and user.is_admin and user.id == admin.id)

        async def stream():
            last_check = asyncio.get_running_loop().time()
            last_health = 0.0
            try:
                yield f"event: hello\ndata: {json.dumps({'at': iso(utcnow())})}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    now = asyncio.get_running_loop().time()
                    if now - last_check >= 60:
                        last_check = now
                        if not await asyncio.to_thread(_still_admin):
                            break
                    if state.monitor is not None and now - last_health >= 30:
                        last_health = now
                        snap = await asyncio.to_thread(state.monitor.snapshot)
                        yield f"event: health\ndata: {json.dumps(snap, default=str)}\n\n"
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=5.0)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"event: {message['type']}\ndata: {json.dumps(message['data'], default=str)}\n\n"
            finally:
                hub.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
