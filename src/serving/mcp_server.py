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
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from src.core.config import settings
from src.core.schemas import PlannedTask
from src.core.storage import get_storage_store
from src.pipeline.app import agent_invocation
from src.serving.tools import (
    create_planned_task,
    get_daily_actions_recap,
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


# Register the 5 core MCP tools for Alexa+
mcp.tool()(create_planned_task)
mcp.tool()(verify_action_status)
mcp.tool()(get_daily_actions_recap)
mcp.tool()(query_social_contact)
mcp.tool()(get_topic_briefing)


# ---------------------------------------------------------------------------
# REST API Endpoints (for the Web UI & Echo Show Ext-App)
# ---------------------------------------------------------------------------

@mcp.custom_route("/api/status", methods=["GET"])
async def api_status(request: Request) -> JSONResponse:
    """Returns system status, active models/providers, and entity counts."""
    store = get_storage_store()
    recent_actions = store.list_recent_actions(limit=100)
    planned_tasks = store.list_planned_tasks()
    all_contacts = store.search_social_contact("")
    all_topics = store.list_topic_briefings(limit=100)

    completed_tasks = sum(1 for t in planned_tasks if t.status == "completed")
    pending_tasks = sum(1 for t in planned_tasks if t.status != "completed")

    return JSONResponse({
        "status": "online",
        "service": "EXAMEN Ambient Intelligence Engine",
        "timestamp": datetime.now().isoformat(),
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
            status="pending",
        )
        task_id = store.save_planned_task(task)
        broadcast_event("routine_created", {
            "task_id": task_id,
            "title": task.title,
            "domain": task.domain,
        })
        return JSONResponse({
            "success": True,
            "task_id": task_id,
            "title": task.title,
            "domain": task.domain,
            "scheduled_time": task.scheduled_time,
            "recurrence": task.recurrence,
            "status": task.status,
        }, status_code=201)

    # GET
    domain = request.query_params.get("domain")
    status = request.query_params.get("status")
    filter_domain = None if (not domain or domain.lower() == "all") else domain.lower()
    filter_status = None if (not status or status.lower() == "all") else status.lower()

    tasks = store.list_planned_tasks(domain=filter_domain, status=filter_status)
    result = []
    for t in tasks:
        result.append({
            "id": t.id,
            "title": t.title,
            "domain": t.domain,
            "scheduled_time": t.scheduled_time,
            "recurrence": t.recurrence,
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
        result.append({
            "id": c.id,
            "name": c.person_name,
            "company_or_role": c.company_or_role,
            "contact_info": c.contact_info,
            "key_topics": c.key_topics,
            "commitments": c.commitments,
            "timestamp": c.timestamp,
        })
    return JSONResponse({"contacts": result, "count": len(result)})


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

    chunk = body.get("transcript_chunk")
    if not chunk or not chunk.strip():
        return JSONResponse({"error": "Field 'transcript_chunk' is required"}, status_code=400)

    actor_id = body.get("actor_id", "user_web_sim")
    payload = {
        "transcript_chunk": chunk.strip(),
        "timestamp": datetime.now().isoformat(),
        "actor_id": actor_id,
    }

    start_time = datetime.now()
    try:
        result = agent_invocation(payload=payload)
        elapsed_sec = (datetime.now() - start_time).total_seconds()
        broadcast_event("pipeline_invoked", {
            "summary": result.get("summary"),
            "elapsed_seconds": round(elapsed_sec, 3),
        })
        return JSONResponse({
            "success": True,
            "elapsed_seconds": round(elapsed_sec, 3),
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

    # Locate static web UI directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    web_ui_dir = os.path.join(project_root, "src", "web_ui")

    if os.path.isdir(web_ui_dir):
        logger.info(f"Mounting Web UI static assets from: {web_ui_dir}")
        # Mount for Echo Show Ext-App sandboxed iframe
        app.mount("/ext-app", StaticFiles(directory=web_ui_dir, html=True), name="ext-app")
        # Mount for root web dashboard
        app.mount("/", StaticFiles(directory=web_ui_dir, html=True), name="web-ui")
    else:
        logger.warning(f"Web UI directory not found at {web_ui_dir}. Skipping static mount.")

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
