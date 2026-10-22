"""Action tools for the Alexa+ MCP Serving layer.

Exposes tools for domestic safety verifications, scheduled routine tasks,
and daily activity recaps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.schemas import PlannedTask, VerifiedAction
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore

logger = logging.getLogger("examen.serving.tools.action")


def _format_elapsed_time(timestamp_str: str) -> str:
    """Computes a human-friendly elapsed time string from an ISO timestamp."""
    try:
        if timestamp_str.endswith("Z"):
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        elif "+" in timestamp_str or ("-" in timestamp_str[10:] and "T" in timestamp_str):
            ts = datetime.fromisoformat(timestamp_str)
        else:
            ts = datetime.fromisoformat(timestamp_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if ts.tzinfo is not None:
            delta = now - ts
        else:
            delta = datetime.now() - ts

        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "just now"
        if total_seconds < 60:
            return "just now"

        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"

        hours = minutes // 60
        rem_mins = minutes % 60
        if hours < 24:
            if rem_mins > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} and {rem_mins} minute{'s' if rem_mins != 1 else ''} ago"
            return f"{hours} hour{'s' if hours != 1 else ''} ago"

        days = hours // 24
        return f"{days} day{'s' if days != 1 else ''} ago"
    except Exception as e:
        logger.warning(f"Could not parse timestamp '{timestamp_str}': {e}")
        return timestamp_str


def execute_create_planned_task(
    title: str,
    domain: str = "routine",
    scheduled_time: Optional[str] = None,
    recurrence: str = "none",
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for creating a planned task."""
    ctx_store = store or get_storage_store()
    task = PlannedTask(
        title=title.strip(),
        domain=domain,
        scheduled_time=scheduled_time,
        recurrence=recurrence,
        status="pending",
    )
    task_id = ctx_store.save_planned_task(task)

    logger.info(f"Created planned task {task_id} ({domain})")
    return {
        "status": "scheduled",
        "task_id": task_id,
        "title": task.title,
        "domain": task.domain,
        "scheduled_time": task.scheduled_time,
        "recurrence": task.recurrence,
        "tracking_status": "watching_ambient_stream",
        "message": f"Scheduled task '{task.title}' ({task.domain}). Watching ambient speech stream for completion.",
    }


def create_planned_task(
    title: str,
    domain: str = "routine",
    scheduled_time: Optional[str] = None,
    recurrence: str = "none",
) -> Dict[str, Any]:
    """Schedule a domestic safety check, daily routine, or planned work task.
    
    Args:
        title: Task description (e.g. 'unplug clothes iron', 'take blood pressure medication').
        domain: Category ('safety', 'routine', 'work_task').
        scheduled_time: Target scheduled time (e.g. '08:30', '21:00').
        recurrence: Recurrence frequency ('none', 'daily', 'weekdays', 'weekly').
    """
    return execute_create_planned_task(
        title=title,
        domain=domain,
        scheduled_time=scheduled_time,
        recurrence=recurrence,
    )


def speaker_label(speaker: Any) -> Optional[str]:
    """Short attribution for answers and cards: who said the confirming sentence."""
    if speaker is None:
        return None
    role = getattr(speaker, "role", None)
    source = getattr(speaker, "source", None)
    if getattr(speaker, "addressed_to_user", False):
        return f"asked by {getattr(speaker, 'name', None) or 'someone'}"
    if role == "user":
        return "you (voice match)" if source in ("bee_voice_id", "bee_name") else "you"
    if role == "contact":
        return getattr(speaker, "name", None) or "another person"
    return "unidentified speaker"


def execute_verify_action_status(
    action_query: str,
    target_date: Optional[str] = None,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for checking verified action status."""
    ctx_store = store or get_storage_store()
    action = ctx_store.get_action_status(action_query=action_query, target_date=target_date)

    if action:
        elapsed = _format_elapsed_time(action.timestamp)
        spoken_by = speaker_label(action.speaker)
        voice_note = {
            "you (voice match)": " Bee recognised your voice.",
            "unidentified speaker": " Bee could not confirm it was your voice.",
        }.get(spoken_by or "", "")
        spoken = (
            f"Yes, you confirmed {action.action_type.replace('_', ' ')}: "
            f"'{action.raw_statement}' approximately {elapsed}.{voice_note}"
        )
        card_payload = {
            "template": "ACTION_VERIFIED_BADGE",
            "status": "verified",
            "action_type": action.action_type,
            "domain": action.domain,
            "timestamp": action.timestamp,
            "raw_statement": action.raw_statement,
            "confidence": round(action.confidence, 2),
            "elapsed_time_human": elapsed,
            "matched_task_id": action.matched_task_id,
            "spoken_by": spoken_by,
            "spoken_summary": spoken,
        }
        return {
            "status": "verified",
            "action_id": action.id,  # what update_action / delete_action take
            "action_type": action.action_type,
            "domain": action.domain,
            "timestamp": action.timestamp,
            "raw_statement": action.raw_statement,
            "confidence": round(action.confidence, 2),
            "elapsed_time_human": elapsed,
            "matched_task_id": action.matched_task_id,
            "spoken_by": spoken_by,
            "voice_verified": spoken_by == "you (voice match)",
            "display_template": "ACTION_VERIFIED_BADGE",
            "ui_card_type": "ACTION_VERIFIED_BADGE",
            "spoken_summary": spoken,
            "card_payload": card_payload,
        }

    target_d = target_date or datetime.now().strftime("%Y-%m-%d")
    spoken = f"I have no record of you completing '{action_query}' yet."
    card_payload = {
        "template": "ACTION_UNVERIFIED_BADGE",
        "status": "unverified",
        "action_query": action_query,
        "target_date": target_d,
        "message": f"No verified completion recorded for '{action_query}'.",
        "spoken_summary": spoken,
    }
    return {
        "status": "unverified",
        "action_query": action_query,
        "target_date": target_d,
        "message": f"No verified completion recorded for '{action_query}'.",
        "display_template": "ACTION_UNVERIFIED_BADGE",
        "ui_card_type": "ACTION_UNVERIFIED_BADGE",
        "spoken_summary": spoken,
        "card_payload": card_payload,
    }


def verify_action_status(
    action_query: str,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Check the completion status and timestamp of a domestic safety action or routine task.
    
    Args:
        action_query: Action keyword to verify (e.g. 'iron', 'stove', 'door', 'keys', 'ferro', 'porta').
        target_date: Reference date in YYYY-MM-DD format (default: today).
    """
    return execute_verify_action_status(
        action_query=action_query,
        target_date=target_date,
    )


def execute_get_daily_actions_recap(
    domain: Optional[str] = None,
    limit: int = 10,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for daily actions recap."""
    ctx_store = store or get_storage_store()
    filter_domain = None if (domain is None or domain.lower() == "all") else domain.lower()

    planned_tasks = ctx_store.list_planned_tasks(domain=filter_domain)
    recent_actions = ctx_store.list_recent_actions(limit=limit, domain=filter_domain)

    completed_tasks = [t for t in planned_tasks if t.status == "completed"]
    pending_tasks = [t for t in planned_tasks if t.status != "completed"]

    spontaneous = [a for a in recent_actions if not a.matched_task_id]

    planned_formatted = []
    for t in planned_tasks:
        completed_time = None
        if t.completed_at:
            completed_time = (
                t.completed_at.split("T")[1][:5]
                if "T" in t.completed_at
                else t.completed_at
            )
        planned_formatted.append({
            "id": t.id,
            "title": t.title,
            "domain": t.domain,
            "scheduled_time": t.scheduled_time,
            "status": t.status,
            "completed_at": completed_time,
            "verified_by_audio": t.status == "completed" and bool(t.verified_action_id),
        })

    spontaneous_formatted = []
    for a in spontaneous:
        time_part = a.timestamp.split("T")[1][:5] if "T" in a.timestamp else a.timestamp
        spontaneous_formatted.append({
            "id": a.id,
            "time": time_part,
            "action": a.raw_statement or a.action_type.replace("_", " "),
            "action_type": a.action_type,
            "type": a.domain,
            "confidence": round(a.confidence, 2),
        })

    today_str = datetime.now().strftime("%Y-%m-%d")
    spoken = (
        f"Today you have {len(completed_tasks)} of {len(planned_tasks)} planned routine(s) completed, "
        f"and {len(spontaneous_formatted)} spontaneous action(s) recorded."
    )
    card_payload = {
        "template": "DAILY_ACTIONS_RECAP",
        "date": today_str,
        "summary": {
            "planned_total": len(planned_tasks),
            "planned_completed": len(completed_tasks),
            "planned_pending": len(pending_tasks),
            "spontaneous_actions": len(spontaneous_formatted),
        },
        "total_actions": len(spontaneous_formatted) + len(completed_tasks),
        "tasks_count": len(planned_tasks),
        "completed_tasks_count": len(completed_tasks),
        "recent_actions": spontaneous_formatted,
        "planned_routines": planned_formatted,
        "spontaneous_actions": spontaneous_formatted,
        "spoken_summary": spoken,
    }

    return {
        "date": today_str,
        "summary": {
            "planned_total": len(planned_tasks),
            "planned_completed": len(completed_tasks),
            "planned_pending": len(pending_tasks),
            "spontaneous_actions": len(spontaneous_formatted),
        },
        "planned_routines": planned_formatted,
        "spontaneous_actions": spontaneous_formatted,
        "display_template": "DAILY_ACTIONS_RECAP",
        "ui_card_type": "DAILY_ACTIONS_RECAP",
        "spoken_summary": spoken,
        "card_payload": card_payload,
    }


def get_daily_actions_recap(
    domain: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Retrieve the daily checklist of planned routines and chronological timeline of spontaneous ambient actions.
    
    Args:
        domain: Filter category ('all', 'safety', 'routine', 'work_task', or None).
        limit: Max number of spontaneous actions to return (default 10).
    """
    return execute_get_daily_actions_recap(domain=domain, limit=limit)


def execute_get_upcoming_tasks(
    domain: Optional[str] = None,
    limit: int = 10,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for querying pending tasks and reminders."""
    ctx_store = store or get_storage_store()
    filter_domain = None if (not domain or domain.lower() == "all") else domain.lower()
    tasks = ctx_store.list_planned_tasks(status="pending", domain=filter_domain)
    tasks = tasks[:limit]

    formatted = []
    for t in tasks:
        formatted.append({
            "id": t.id,
            "title": t.title,
            "domain": t.domain,
            "scheduled_time": t.scheduled_time,
            "recurrence": t.recurrence,
            "origin": t.origin,
            "raw_statement": t.raw_statement,
            "relative_time_anchor": t.relative_time_anchor,
            "status": t.status,
            "created_at": t.created_at,
            "spoken_by": speaker_label(t.speaker),
        })

    spoken_summary = (
        f"You have {len(formatted)} upcoming scheduled task{'s' if len(formatted) != 1 else ''}."
        if formatted else "You have no upcoming scheduled tasks."
    )

    card_payload = {
        "template": "UPCOMING_TASKS_VIEWER",
        "tasks": formatted,
        "count": len(formatted),
        "domain_filter": domain,
        "spoken_summary": spoken_summary,
    }

    return {
        "tasks": formatted,
        "count": len(formatted),
        "spoken_summary": spoken_summary,
        "display_template": "UPCOMING_TASKS_VIEWER",
        "ui_card_type": "UPCOMING_TASKS_VIEWER",
        "card_payload": card_payload,
    }


def get_upcoming_tasks(
    domain: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Query upcoming scheduled tasks and deadlines, including those captured ambiently via voice.
    
    Args:
        domain: Optional filter category ('safety', 'routine', 'work_task', 'personal', or None).
        limit: Maximum number of tasks to return (default 10).
    """
    return execute_get_upcoming_tasks(domain=domain, limit=limit)
