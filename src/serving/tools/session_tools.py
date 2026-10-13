"""Session dossier tools for the Alexa+ MCP Serving layer.

Exposes holistic macro-session dossiers, linked micro-events, and synthesized
briefings for Echo Show and multimodal assistants.
"""

from __future__ import annotations

import logging
from datetime import datetime
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

        # Event briefings: consolidated final if ready, else the latest segment/checkpoint briefing
        briefings_by_id: Dict[str, Any] = {}
        if dossier.segments:
            try:
                briefings_by_id = {b.id: b for b in ctx_store.list_briefings_for_session(dossier.session_id)}
            except NotImplementedError:
                briefings_by_id = {}
        display_briefing = dossier.briefing_report
        is_final = display_briefing is not None
        if display_briefing is None:
            for seg in reversed(dossier.segments):
                if seg.briefing_id and seg.briefing_id in briefings_by_id:
                    display_briefing = briefings_by_id[seg.briefing_id]
                    break

        briefing_synthesis = ""
        briefing_sources: List[str] = []
        if display_briefing:
            briefing_synthesis = (
                display_briefing.explanatory_synthesis
                or ("\n".join(display_briefing.executive_summary) if display_briefing.executive_summary else "")
            )
            briefing_sources = display_briefing.web_sources

        segments_payload = [_segment_payload(seg, briefings_by_id) for seg in dossier.segments]
        top_terms = _top_terms(dossier)

        segment_titles = [s.title for s in dossier.segments if s.title]
        parts_sentence = ""
        if segment_titles:
            ordinals = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth"]
            parts_sentence = " ".join(
                f"{ordinals[i] if i < len(ordinals) else f'Part {i + 1}'} part: {t}." for i, t in enumerate(segment_titles)
            ) + " "
        if dossier.segments and dossier.status != "concluded":
            spoken = (
                f"{title} is still {'in progress' if dossier.status == 'active' else 'paused'}. "
                f"{parts_sentence}"
                f"So far I tracked {len(actions)} verified action(s), {len(tasks)} scheduled task(s), and {len(contacts)} contact(s)."
            )
        else:
            spoken = (
                f"Here is the recap for {title}. "
                f"{parts_sentence or f'The session recorded {len(dossier.transcript_chunks)} transcript segments. '}"
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
            "segments": [
                {k: s[k] for k in ("index", "title", "status", "time_range", "kind")} for s in segments_payload
            ],
            "is_final": is_final,
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
            "final_status": dossier.final_status,
            "briefing_report": dossier.briefing_report.model_dump() if dossier.briefing_report else None,
            "display_briefing": display_briefing.model_dump() if display_briefing else None,
            "is_final": is_final,
            "segments": segments_payload,
            "transitions": [t.model_dump() for t in dossier.transitions],
            "conversation_uuids": dossier.conversation_uuids,
            "top_terms": top_terms,
            "research_queries": [e.get("query") for e in dossier.research_ledger if e.get("query")],
            "paused_at": dossier.paused_at,
            "hard_close_deadline": dossier.hard_close_deadline,
            "last_on_topic_at": dossier.last_on_topic_at,
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
            "segments_count": len(d.segments),
            "final_status": d.final_status,
        })

    spoken = f"Found {len(summaries)} session dossier(s)."
    return {
        "found": len(summaries) > 0,
        "total": len(summaries),
        "status_filter": status,
        "sessions": summaries,
        "spoken_summary": spoken,
    }


def _fmt_time(iso: Optional[str]) -> str:
    if not iso:
        return "…"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return iso


def _segment_payload(seg: Any, briefings_by_id: Dict[str, Any]) -> Dict[str, Any]:
    briefing = briefings_by_id.get(seg.briefing_id) if seg.briefing_id else None
    end = _fmt_time(seg.end_time) if seg.status != "open" else "…"
    return {
        "segment_id": seg.segment_id,
        "index": seg.index,
        "kind": seg.kind,
        "title": seg.title,
        "status": seg.status,
        "start_time": seg.start_time,
        "end_time": seg.end_time,
        "time_range": f"{_fmt_time(seg.start_time)}–{end}",
        "word_count": seg.word_count,
        "close_reason": seg.close_reason,
        "briefing_id": seg.briefing_id,
        "briefing": briefing.model_dump() if briefing else None,
    }


def _top_terms(dossier: SessionDossier, n: int = 10) -> List[str]:
    if not dossier.topic_profile or not dossier.topic_profile.keywords:
        return []
    ranked = sorted(dossier.topic_profile.keywords.items(), key=lambda kv: (-kv[1], kv[0]))
    return [term for term, _ in ranked[:n]]


def execute_get_live_event_outline(engine: Optional[Any] = None) -> Dict[str, Any]:
    """Outline of the event currently being recorded (no LLM call): title, parts, top terms, elapsed time."""
    if engine is None:
        from src.ingestion.event_engine import get_event_engine

        engine = get_event_engine()
    ev = engine.current_event()
    if ev is None:
        return {
            "found": False,
            "display_template": "SESSION_NOT_FOUND",
            "ui_card_type": "SESSION_NOT_FOUND",
            "spoken_summary": "No lecture or meeting is being recorded right now.",
        }
    start = datetime.fromisoformat(ev.start_time)
    elapsed_min = max(0, int((datetime.now() - start).total_seconds() // 60))
    titles = [s.title for s in ev.segments if s.title]
    terms = _top_terms(ev, 6)
    title = ev.title if ev.title and not ev.title.startswith("Ongoing session") else None
    about = f"about {title}" if title else (f"mentioning {', '.join(terms[:4])}" if terms else "in progress")
    spoken = (
        f"A {ev.domain if ev.domain != 'general' else 'session'} {about} has been running for {elapsed_min} minutes"
        + (f" and is currently paused" if ev.status == "paused" else "")
        + (f". Parts so far: {'; '.join(titles)}." if titles else ".")
    )
    return {
        "found": True,
        "session_id": ev.session_id,
        "title": ev.title,
        "status": ev.status,
        "domain": ev.domain,
        "elapsed_minutes": elapsed_min,
        "segments": [{"index": s.index, "title": s.title, "status": s.status} for s in ev.segments],
        "top_terms": terms,
        "display_template": "SESSION_DOSSIER_VIEWER",
        "ui_card_type": "SESSION_DOSSIER_VIEWER",
        "spoken_summary": spoken,
    }


def get_live_event_outline() -> Dict[str, Any]:
    """Describe the lecture or meeting currently being recorded ("Alexa, what is this lecture about so far?").

    Returns the live event title, its parts so far, the most frequent terms and elapsed minutes.
    """
    return execute_get_live_event_outline()


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
        status: Optional filter by lifecycle status ('active', 'paused', 'concluded').
        limit: Maximum number of session dossiers to return (default 10).
    """
    return execute_list_session_dossiers(status=status, limit=limit)

