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
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from src.core.config import settings
from src.core.schemas import PlannedTask, SocialCommitment
from src.core.storage import get_storage_store
from src.pipeline.app import agent_invocation
from src.serving.tools import (
    create_planned_task,
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

logger = logging.getLogger("examen.serving.mcp")

# Initialize FastMCP Server
mcp = FastMCP("examen-mcp")

# In-memory SSE subscribers set for real-time dashboard events
_sse_subscribers: set[asyncio.Queue] = set()


def broadcast_event(event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Broadcasts a JSON event to all connected SSE clients."""
    payload = json.dumps({
        "type": event_type,
        "data": data or {},
        "timestamp": datetime.now().isoformat(),
    })
    msg = f"data: {payload}\n\n"
    for q in list(_sse_subscribers):
        try:
            q.put_nowait(msg)
        except Exception:
            _sse_subscribers.discard(q)


# Register the 10 core MCP tools for Alexa+
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


# ---------------------------------------------------------------------------
# REST API Endpoints (for the Web UI & Echo Show Ext-App)
# ---------------------------------------------------------------------------

_bee_status_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}


class OrchestratorManager:
    """Manages the background execution and telemetry lifecycle of the BeeStreamOrchestrator."""
    _instance: Optional["OrchestratorManager"] = None

    def __init__(self):
        self.orchestrator = None
        self.task: Optional[asyncio.Task] = None
        self.is_started = False

    @classmethod
    def get_instance(cls) -> "OrchestratorManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_started(self) -> None:
        """Launches the background orchestrator task if not already active."""
        if self.task is None or self.task.done():
            try:
                loop = asyncio.get_running_loop()
                self.task = loop.create_task(self._run_orchestrator())
                self.is_started = True
            except RuntimeError:
                pass

    async def _run_orchestrator(self) -> None:
        try:
            from src.ingestion.orchestrator import BeeStreamOrchestrator
            store = get_storage_store()
            self.orchestrator = BeeStreamOrchestrator(debug_mode="none", store=store)
            logger.info("Ingestion Orchestrator background service started.")
            await self.orchestrator.run()
        except asyncio.CancelledError:
            logger.info("Ingestion Orchestrator background service stopped.")
        except Exception as e:
            logger.warning(f"Ingestion Orchestrator background service error: {e}")
        finally:
            self.is_started = False

    def stop(self) -> None:
        """Stops the running orchestrator background task."""
        if self.task and not self.task.done():
            self.task.cancel()
        self.is_started = False

    def get_status(self) -> Dict[str, Any]:
        """Returns real-time status of the orchestrator stream and buffers."""
        self.ensure_started()
        if self.orchestrator and hasattr(self.orchestrator, "get_status_dict"):
            st = self.orchestrator.get_status_dict()
            st["service_managed"] = True
            return st
        return {
            "running": self.is_started and (self.task is not None and not self.task.done()),
            "status": "LISTENING" if self.is_started else "STANDBY",
            "mode": "ambient_sse",
            "buffer_chars": 0,
            "chunks_screened": 0,
            "utterances_received": 0,
            "detail": "Orchestrator initializing background stream",
            "service_managed": True,
        }


def _get_bee_device_telemetry() -> Dict[str, Any]:
    """Probes the Bee CLI for real authentication and joins it with Orchestrator stream state."""
    import time
    now = time.time()
    orch_mgr = OrchestratorManager.get_instance()
    orch_status = orch_mgr.get_status()

    if _bee_status_cache["data"] and (now - _bee_status_cache["timestamp"] < 10.0):
        res = dict(_bee_status_cache["data"])
        # Update dynamic streaming status from orchestrator
        if orch_status.get("status") == "STREAMING":
            res["status"] = "STREAMING"
            res["connected"] = True
            res["detail"] = f"Bee Wearable streaming ({orch_status.get('utterances_received', 0)} utterances)"
        elif orch_status.get("status") == "LISTENING" and res.get("account"):
            res["status"] = "LISTENING"
            res["connected"] = False
            res["detail"] = f"Bee account verified as {res['account']}; orchestrator listening for audio stream"
        return res

    from src.ingestion.stream_convo import get_bee_binary_path
    bee_bin = get_bee_binary_path()
    if not bee_bin:
        res = {
            "connected": False,
            "status": "DISCONNECTED",
            "account": None,
            "device_paired": False,
            "detail": "Bee CLI binary not found in resources/bee-cli/dist or PATH",
        }
    else:
        try:
            import subprocess
            proc = subprocess.run(
                [bee_bin, "status"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            out = proc.stdout.strip()
            if "Verified as" in out:
                import re
                m = re.search(r"Verified as (.*?)(?:\s*\(id|\.|$)", out)
                user_name = m.group(1).strip() if m else "Authenticated User"
                
                is_streaming = orch_status.get("status") == "STREAMING"
                is_listening = orch_status.get("status") == "LISTENING" or orch_status.get("running")

                res = {
                    "connected": is_streaming,
                    "status": "STREAMING" if is_streaming else ("LISTENING" if is_listening else "STANDBY"),
                    "account": user_name,
                    "device_paired": is_streaming,
                    "detail": (
                        f"Bee Wearable streaming audio ({orch_status.get('utterances_received', 0)} chunks)"
                        if is_streaming
                        else f"Bee account verified as {user_name}; orchestrator listening for wearable stream"
                    ),
                }
            elif "Not logged in" in out:
                res = {
                    "connected": False,
                    "status": "DISCONNECTED",
                    "account": None,
                    "device_paired": False,
                    "detail": "Bee CLI not logged in. Run 'bee login' to authenticate.",
                }
            else:
                res = {
                    "connected": False,
                    "status": "STANDBY",
                    "account": None,
                    "device_paired": False,
                    "detail": out or "Awaiting Bee device link",
                }
        except Exception as e:
            res = {
                "connected": False,
                "status": "STANDBY",
                "account": None,
                "device_paired": False,
                "detail": f"Bee CLI probe: {str(e)}",
            }

    _bee_status_cache["timestamp"] = now
    _bee_status_cache["data"] = res
    return res


@mcp.custom_route("/api/orchestrator/status", methods=["GET"])
async def api_orchestrator_status(request: Request) -> JSONResponse:
    """Returns the live status of the Ingestion Orchestrator background stream."""
    mgr = OrchestratorManager.get_instance()
    return JSONResponse(mgr.get_status())


@mcp.custom_route("/api/orchestrator/start", methods=["POST"])
async def api_orchestrator_start(request: Request) -> JSONResponse:
    """Explicitly launches the Ingestion Orchestrator background loop."""
    mgr = OrchestratorManager.get_instance()
    mgr.ensure_started()
    return JSONResponse({"success": True, "orchestrator": mgr.get_status()})


@mcp.custom_route("/api/orchestrator/stop", methods=["POST"])
async def api_orchestrator_stop(request: Request) -> JSONResponse:
    """Safely suspends the Ingestion Orchestrator background loop."""
    mgr = OrchestratorManager.get_instance()
    mgr.stop()
    return JSONResponse({"success": True, "status": "STOPPED"})


@mcp.custom_route("/api/status", methods=["GET"])
async def api_status(request: Request) -> JSONResponse:
    """Returns system status, active models/providers, real telemetry averages, and entity counts."""
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
    bee_telemetry = _get_bee_device_telemetry()
    orch_status = OrchestratorManager.get_instance().get_status()

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

    actions = store.list_recent_actions(limit=limit, domain=filter_domain)
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
        })

    return JSONResponse({"actions": result, "count": len(result)})


@mcp.custom_route("/api/events", methods=["GET"])
async def api_events(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint streaming real-time pipeline and entity updates."""
    queue: asyncio.Queue = asyncio.Queue()
    _sse_subscribers.add(queue)

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
            _sse_subscribers.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
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

    # 1. Briefing card
    from src.serving.tools.topic_tools import execute_get_topic_briefing
    briefing_card = execute_get_topic_briefing(store=store)
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
    contacts_with_wp = [c for c in store.search_social_contact("") if c.web_profile]
    if contacts_with_wp:
        profile_card = execute_get_contact_profile(contacts_with_wp[0].person_name, force_enrich=False, store=store)
    else:
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
    commitments_card = execute_get_social_commitments(store=store)

    # 4. Action verified badge
    from src.serving.tools.action_tools import execute_verify_action_status, execute_get_daily_actions_recap, execute_get_upcoming_tasks
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
    topics = store.list_topic_briefings(limit=limit)

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
        })
    return JSONResponse({"topics": result, "count": len(result)})


@mcp.custom_route("/api/sessions", methods=["GET"])
async def api_sessions(request: Request) -> JSONResponse:
    """Lists recorded macro session dossiers."""
    store = get_storage_store()
    status = request.query_params.get("status")
    limit = int(request.query_params.get("limit", "10"))
    dossiers = store.list_session_dossiers(status=status, limit=limit)
    result = [d.model_dump() for d in dossiers]
    return JSONResponse({"sessions": result, "count": len(result)})


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
    """Marks a session dossier as concluded, with optional briefing report synthesis."""
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Missing session_id"}, status_code=400)

    from src.ingestion.session_manager import SessionManager
    store = get_storage_store()
    mgr = SessionManager(store=store)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    briefing_id = body.get("briefing_report_id")
    auto_synthesize = body.get("auto_synthesize", False)

    if auto_synthesize and not briefing_id:
        mgr.synthesize_session_dossier(session_id=session_id, auto_conclude=True)
        dossier = store.get_session_dossier(session_id)
        if dossier:
            broadcast_event("session_concluded", dossier.model_dump())
            return JSONResponse({"success": True, "concluded": True, "dossier": dossier.model_dump()})

    dossier = mgr.conclude_session(session_id=session_id, briefing_report_id=briefing_id)
    if not dossier:
        return JSONResponse({"error": f"Session '{session_id}' not found"}, status_code=404)

    broadcast_event("session_concluded", dossier.model_dump())
    return JSONResponse({"success": True, "concluded": True, "dossier": dossier.model_dump()})


@mcp.custom_route("/api/simulate", methods=["POST"])
async def api_simulate(request: Request) -> JSONResponse:
    """Simulates an ambient speech chunk through the AgentCore pipeline.
    
    Accepts: {"transcript_chunk": str, "actor_id": Optional[str]}
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
    payload = {
        "raw_transcript": chunk.strip(),
        "transcript_chunk": chunk.strip(),
        "timestamp": datetime.now().isoformat(),
        "actor_id": actor_id,
    }

    start_time = datetime.now()
    try:
        result = agent_invocation(payload=payload)
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
# ASGI Application Builder & Server Runner
# ---------------------------------------------------------------------------

def create_app() -> Starlette:
    """Constructs the unified ASGI application serving MCP, API, and Web UI."""
    app = mcp.streamable_http_app()

    # Enable CORS for Next.js dev server and external web callers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
