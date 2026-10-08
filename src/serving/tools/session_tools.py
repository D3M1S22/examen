"""Session dossier tools for the Alexa+ MCP Serving layer.

Exposes holistic macro-session dossiers, linked micro-events, and synthesized
briefings for Echo Show and multimodal assistants.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.schemas import SessionDossier
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore

logger = logging.getLogger("examen.serving.tools.session")


def execute_get_session_dossier(
    session_id: Optional[str] = None,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for retrieving a macro session dossier with linked micro-events."""
    ctx_store = store or get_storage_store()
    dossier: Optional[SessionDossier] = ctx_store.get_session_dossier(session_id=session_id)

    if dossier:
        actions = [e for e in dossier.linked_micro_events if e.event_type == "action"]
        tasks = [e for e in dossier.linked_micro_events if e.event_type == "task_scheduled"]
        contacts = [e for e in dossier.linked_micro_events if e.event_type == "social_contact"]
        commitments = [e for e in dossier.linked_micro_events if e.event_type == "social_commitment"]

        location_name = (
            dossier.location.get("place_name")
            or dossier.location.get("semantic_zone")
            if dossier.location
            else "Unknown location"
        )

        title = dossier.title or f"Meeting Session ({dossier.session_id[:8]})"
        briefing_synthesis = ""
        briefing_sources: List[str] = []
        if dossier.briefing_report:
            briefing_synthesis = (
                dossier.briefing_report.explanatory_synthesis
                or (
                    "\n".join(dossier.briefing_report.executive_summary)
                    if dossier.briefing_report.executive_summary
                    else ""
                )
            )
            briefing_sources = dossier.briefing_report.web_sources

        spoken = (
            f"Here is the recap for {title}. "
            f"The session recorded {len(dossier.transcript_chunks)} transcript segments. "
            f"I tracked {len(actions)} verified action(s), {len(tasks)} scheduled task(s), and {len(contacts)} contact(s) encountered."
        )

        events_payload = [
            e.model_dump() if hasattr(e, "model_dump") else e
            for e in dossier.linked_micro_events
        ]

        card_payload = {
            "template": "SESSION_DOSSIER_VIEWER",
            "session_id": dossier.session_id,
            "title": title,
            "domain": dossier.domain,
            "status": dossier.status,
            "start_time": dossier.start_time,
            "concluded_at": dossier.concluded_at,
            "location_name": location_name,
            "transcript_chunks_count": len(dossier.transcript_chunks),
            "transcript_chunks": dossier.transcript_chunks,
            "key_discussion_points": dossier.key_discussion_points,
            "linked_micro_events": events_payload,
            "actions": [e.model_dump() if hasattr(e, "model_dump") else e for e in actions],
            "tasks": [e.model_dump() if hasattr(e, "model_dump") else e for e in tasks],
            "contacts": [e.model_dump() if hasattr(e, "model_dump") else e for e in contacts],
            "explanatory_synthesis": briefing_synthesis,
            "web_sources": briefing_sources,
            "spoken_summary": spoken,
        }

        return {
            "found": True,
            "session_id": dossier.session_id,
            "title": title,
            "domain": dossier.domain,
            "status": dossier.status,
            "start_time": dossier.start_time,
            "concluded_at": dossier.concluded_at,
            "location": dossier.location,
            "transcript_chunks_count": len(dossier.transcript_chunks),
            "key_discussion_points": dossier.key_discussion_points,
            "linked_micro_events": events_payload,
            "actions_count": len(actions),
            "tasks_count": len(tasks),
            "contacts_count": len(contacts),
            "commitments_count": len(commitments),
            "final_briefing_id": dossier.final_briefing_id,
            "briefing_report": dossier.briefing_report.model_dump() if dossier.briefing_report else None,
            "display_template": "SESSION_DOSSIER_VIEWER",
            "ui_card_type": "SESSION_DOSSIER_VIEWER",
            "spoken_summary": spoken,
            "card_payload": card_payload,
        }

    return {
        "found": False,
        "session_id": session_id,
        "message": f"No session dossier found for session '{session_id}'." if session_id else "No recorded session dossiers available.",
        "display_template": "SESSION_NOT_FOUND",
        "ui_card_type": "SESSION_NOT_FOUND",
        "spoken_summary": "I could not find any recorded session dossiers.",
    }


def execute_list_session_dossiers(
    status: Optional[str] = None,
    limit: int = 10,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for listing recorded session dossiers."""
    ctx_store = store or get_storage_store()
    dossiers = ctx_store.list_session_dossiers(status=status, limit=limit)

    summaries = []
    for d in dossiers:
        summaries.append({
            "session_id": d.session_id,
            "title": d.title or f"Session {d.session_id[:8]}",
            "domain": d.domain,
            "status": d.status,
            "start_time": d.start_time,
            "concluded_at": d.concluded_at,
            "chunks_count": len(d.transcript_chunks),
            "micro_events_count": len(d.linked_micro_events),
            "has_briefing": bool(d.final_briefing_id),
        })

    spoken = f"Found {len(summaries)} session dossier(s)."
    return {
        "found": len(summaries) > 0,
        "total": len(summaries),
        "status_filter": status,
        "sessions": summaries,
        "spoken_summary": spoken,
    }


def get_session_dossier(
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve an integrated macro-session dossier with linked micro-events and holistic briefing.

    Args:
        session_id: Optional UUID of the meeting or conversation session.
                    If omitted, retrieves the most recent recorded session.
    """
    return execute_get_session_dossier(session_id=session_id)


def list_session_dossiers(
    status: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """List recorded conversation session dossiers.

    Args:
        status: Optional filter by lifecycle status ('active', 'finalizing', 'concluded').
        limit: Maximum number of session dossiers to return (default 10).
    """
    return execute_list_session_dossiers(status=status, limit=limit)

