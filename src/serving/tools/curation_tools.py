"""Manual curation: user edits and deletes of extracted results (docs/next_steps/manual_curation/03).

One place owns every curation operation; the REST routes (``mcp_server.py``) and the MCP tools at the
end of this module are thin wrappers, so the two surfaces cannot drift apart. Each operation does
its cascade in the store, keeps the event engine in step (``unlink_micro_event``, ``delete``) and
broadcasts an SSE event. Destructive operations take exact ids only and, over MCP, need
``confirm=True``: without it they return what would be deleted (D4).

Logs carry ids and counts only, never names, titles or transcript text (AGENTS.MD §F3).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, Optional, Union

from pydantic import BaseModel, ValidationError

from src.core.schemas import ActionChanges, ContactChanges, PlannedTask, SocialEntity, TaskChanges, VerifiedAction
from src.core.storage import get_storage_store, rules
from src.core.storage.base import AbstractContextStore
from src.core.storage.errors import UniqueConflict
from src.core.tenancy import get_tenant_id, tenant_scope

logger = logging.getLogger("examen.serving.curation")

Notifier = Callable[..., None]


def _no_notify(event_type: str, data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
    return None


_notify: Notifier = _no_notify


def set_notifier(fn: Optional[Notifier]) -> None:
    """``mcp_server`` registers ``broadcast_event`` here (no import cycle); tests keep the no-op."""
    global _notify
    _notify = fn or _no_notify


class CurationError(Exception):
    """An operation that cannot be done; ``status`` is the HTTP status of the REST route."""

    def __init__(self, message: str, status: int = 400, code: str = "invalid"):
        super().__init__(message)
        self.status = status
        self.code = code


def _not_found(what: str) -> CurationError:
    return CurationError(f"{what} not found", status=404, code="not_found")


def _store(store: Optional[AbstractContextStore]) -> AbstractContextStore:
    return store or get_storage_store()


def _engine(engine: Any) -> Any:
    if engine is not None:
        return engine
    from src.ingestion.event_engine import get_event_engine

    return get_event_engine()


def _validate(model: type, changes: Union[BaseModel, Dict[str, Any], None]) -> Any:
    if isinstance(changes, model):
        return changes
    try:
        return model.model_validate(changes or {})
    except ValidationError as e:
        first = e.errors()[0] if e.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())) or "body"
        raise CurationError(f"Invalid {field}: {first.get('msg', 'invalid value')}") from e


def _excerpt(text: Optional[str], limit: int = 120) -> Optional[str]:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _title(action: VerifiedAction) -> str:
    return action.action_type.replace("_", " ")


def _unlink(engine: Any, store: AbstractContextStore, session_id: Optional[str], event_type: str,
            record_id: str) -> None:
    """Removes the result's link from its event through the engine (D7); store-only as a fallback."""
    if not session_id:
        return
    try:
        _engine(engine).unlink_micro_event(session_id, event_type, record_id)
    except Exception as e:
        logger.warning(f"Engine unlink failed for event {session_id[:8]}: {type(e).__name__}")
        try:
            store.unlink_micro_event(session_id, event_type, record_id)
        except Exception as e2:
            logger.warning(f"Store unlink failed for event {session_id[:8]}: {type(e2).__name__}")


# ---------------------------------------------------------------------------
# Serialisers (the shapes of the existing GET routes)
# ---------------------------------------------------------------------------

def action_dict(a: VerifiedAction) -> Dict[str, Any]:
    return {
        "id": a.id, "action_type": a.action_type, "domain": a.domain, "timestamp": a.timestamp,
        "raw_statement": a.raw_statement, "confidence": round(a.confidence, 2), "matched_task_id": a.matched_task_id,
        "session_id": a.session_id, "ingest_source": a.ingest_source, "ingest_run_id": a.ingest_run_id,
        "speaker": a.speaker.model_dump() if a.speaker else None,
    }


def task_dict(t: PlannedTask, completion_statement: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": t.id, "title": t.title, "domain": t.domain, "scheduled_time": t.scheduled_time,
        "recurrence": t.recurrence, "origin": t.origin, "raw_statement": t.raw_statement,
        "confidence": t.confidence, "relative_time_anchor": t.relative_time_anchor, "session_id": t.session_id,
        "status": t.status, "completed_at": t.completed_at, "verified_action_id": t.verified_action_id,
        "created_at": t.created_at, "ingest_source": t.ingest_source, "ingest_run_id": t.ingest_run_id,
        "recovered": t.recovered, "speaker": t.speaker.model_dump() if t.speaker else None,
        "completion_statement": completion_statement,
    }


def completion_statement(store: AbstractContextStore, task: PlannedTask) -> Optional[str]:
    """The transcript of the action that completed ``task`` (None if manual, missing or revoked)."""
    if task.status != "completed" or not task.verified_action_id:
        return None
    try:
        action = store.get_verified_action(task.verified_action_id)
    except Exception:
        return None
    return action.raw_statement if action and not action.is_revoked else None


def contact_dict(c: SocialEntity) -> Dict[str, Any]:
    commitments = []
    for com in c.commitments or []:
        commitments.append(com.model_dump() if hasattr(com, "model_dump") else com)
    return {
        "id": c.id, "name": c.person_name, "company_or_role": c.company_or_role, "contact_info": c.contact_info,
        "website_url": c.website_url or (c.web_profile.website_url if c.web_profile else None),
        "key_topics": c.key_topics, "commitments": commitments, "location_encountered": c.location_encountered,
        "web_profile": c.web_profile.model_dump() if c.web_profile else None, "session_id": c.session_id,
        "timestamp": c.timestamp,
    }


def _preview(kind: str, details: Dict[str, Any], spoken: str) -> Dict[str, Any]:
    return {"status": "confirm_required", "confirm_required": True, "would_delete": {"type": kind, **details},
            "spoken_summary": spoken}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def execute_update_action(action_id: str, changes: Any, store: Optional[AbstractContextStore] = None
                          ) -> Dict[str, Any]:
    ctx = _store(store)
    parsed = _validate(ActionChanges, changes)
    try:
        action = ctx.update_action(action_id, parsed)
    except ValueError as e:
        raise CurationError(str(e)) from e
    if action is None:
        raise _not_found("Action")
    logger.info(f"Action {action_id[:8]} edited")
    _notify("action_updated", {"action_id": action_id})
    return {"status": "updated", "action": action_dict(action),
            "spoken_summary": f"Updated the note to '{_title(action)}'."}


def execute_delete_action(action_id: str, confirm: bool = False, store: Optional[AbstractContextStore] = None,
                          engine: Any = None) -> Dict[str, Any]:
    ctx = _store(store)
    action = ctx.get_verified_action(action_id)
    if action is None or action.is_revoked:
        raise _not_found("Action")
    task = ctx.get_planned_task(action.matched_task_id) if action.matched_task_id else None
    reopens = task if task and task.status == "completed" and task.verified_action_id == action_id else None
    if not confirm:
        spoken = f"This deletes the note '{_title(action)}'"
        spoken += f" and puts the routine '{reopens.title}' back to pending." if reopens else "."
        return _preview("action", {"id": action_id, "title": _title(action), "transcript": _excerpt(action.raw_statement),
                                   "reopens_routine": reopens.title if reopens else None}, spoken)
    result = ctx.revoke_action(action_id)
    if result is None:
        raise _not_found("Action")
    _unlink(engine, ctx, action.session_id, "action", action_id)
    logger.info(f"Action {action_id[:8]} revoked (routine reopened: {bool(result.reopened_task_id)})")
    _notify("action_deleted", {"action_id": action_id, "reopened_task_id": result.reopened_task_id})
    if result.reopened_task_id:
        _notify("routine_updated", {"id": result.reopened_task_id, "status": "pending"})
    spoken = f"I deleted the note '{_title(action)}'"
    spoken += f" and reopened your routine '{reopens.title}'." if result.reopened_task_id and reopens else "."
    return {"status": "deleted", "deleted_id": action_id, "reopened_task_id": result.reopened_task_id,
            "spoken_summary": spoken}


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------

def execute_update_task(task_id: str, changes: Any, store: Optional[AbstractContextStore] = None) -> Dict[str, Any]:
    ctx = _store(store)
    parsed: TaskChanges = _validate(TaskChanges, changes)
    task = ctx.get_planned_task(task_id)
    if task is None:
        raise _not_found("Routine")
    data = parsed.model_dump(exclude_unset=True)
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise CurationError("Invalid title: cannot be empty")
        task.title = title
    for field in ("domain", "recurrence"):
        if data.get(field) is not None:
            setattr(task, field, data[field])
    if "scheduled_time" in data:
        task.scheduled_time = (data["scheduled_time"] or "").strip() or None
    if data.get("status") is not None and data["status"] != task.status:
        from datetime import datetime

        if data["status"] == "completed":
            task.completed_at = datetime.now().isoformat()
        else:
            task.completed_at = None
            task.verified_action_id = None
        task.status = data["status"]
    if not ctx.update_planned_task(task):
        raise _not_found("Routine")
    payload = task_dict(task, completion_statement(ctx, task))
    logger.info(f"Routine {task_id[:8]} edited")
    _notify("routine_updated", payload)
    return {"status": "updated", "task": payload, "spoken_summary": f"Updated the routine '{task.title}'."}


def execute_delete_task(task_id: str, confirm: bool = False, store: Optional[AbstractContextStore] = None,
                        engine: Any = None) -> Dict[str, Any]:
    ctx = _store(store)
    task = ctx.get_planned_task(task_id)
    if task is None:
        raise _not_found("Routine")
    if not confirm:
        return _preview("routine", {"id": task_id, "title": task.title, "scheduled_time": task.scheduled_time,
                                    "recurrence": task.recurrence},
                        f"This deletes the routine '{task.title}'.")
    if not ctx.delete_planned_task(task_id):
        raise _not_found("Routine")
    _unlink(engine, ctx, task.session_id, "task_scheduled", task_id)
    logger.info(f"Routine {task_id[:8]} deleted")
    _notify("routine_deleted", {"task_id": task_id, "title": task.title})
    return {"status": "deleted", "deleted_id": task_id, "spoken_summary": f"I deleted the routine '{task.title}'."}


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

class _AnchorGuard:
    """Store proxy for a background enrichment: drops the profile write when the contact's anchors
    changed after the run started (a newer edit started its own run)."""

    def __init__(self, store: AbstractContextStore, contact_id: str, anchors: tuple):
        self._store = store
        self._contact_id = contact_id
        self._anchors = anchors
        self.stale = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def update_contact_web_profile(self, contact_id_or_name: str, profile: Any) -> bool:
        current = self._store.get_social_contact(self._contact_id)
        if current is None or _anchor_values(current) != self._anchors:
            self.stale = True
            return False
        return self._store.update_contact_web_profile(self._contact_id, profile)


def _anchor_values(contact: SocialEntity) -> tuple:
    return tuple(rules.contact_name_key(getattr(contact, field)) for field in rules.CONTACT_ANCHORS)


def _enrich(contact: SocialEntity, store: AbstractContextStore, tenant: Optional[str]) -> None:
    """Background web search for an edited contact; the outcome goes to the dashboard over SSE."""
    from src.pipeline.nodes.social_profiler import enrich_social_contact_sync

    guard = _AnchorGuard(store, contact.id, _anchor_values(contact))
    with tenant_scope(tenant):
        try:
            profile = enrich_social_contact_sync(contact, store=guard, force=True)
        except Exception as e:
            from src.core.service_log import report_event

            report_event("contact.enrich_failed", "warning", f"Contact re-enrichment failed: {type(e).__name__}",
                         component="serving", error=e)
            _notify("contact_enrich_failed", {"contact_id": contact.id, "reason": "error"}, tenant=tenant)
            return
        if guard.stale:
            return  # a newer edit runs its own enrichment
        if profile is None:
            _notify("contact_enrich_failed", {"contact_id": contact.id, "reason": "insufficient_anchors"},
                    tenant=tenant)
            return
        logger.info(f"Contact {contact.id[:8]} re-enriched after an edit")
        _notify("contact_enriched", {"id": contact.id, "web_profile": profile.model_dump()}, tenant=tenant)


def _start_enrichment(contact: SocialEntity, store: AbstractContextStore) -> None:
    tenant = get_tenant_id()
    threading.Thread(target=_enrich, args=(contact, store, tenant), name="contact-enrich", daemon=True).start()


# Test seam: replaced by tests to run the enrichment inline or not at all
schedule_enrichment: Callable[[SocialEntity, AbstractContextStore], None] = _start_enrichment


def execute_update_contact(contact_id: str, changes: Any, store: Optional[AbstractContextStore] = None
                           ) -> Dict[str, Any]:
    ctx = _store(store)
    parsed = _validate(ContactChanges, changes)
    try:
        update = ctx.update_social_contact(contact_id, parsed)
    except UniqueConflict as e:
        raise CurationError("Another contact already has this name", status=409, code="name_taken") from e
    if update is None:
        raise _not_found("Contact")
    enrichment = "scheduled" if update.anchors_changed else "unchanged"
    if update.anchors_changed:
        schedule_enrichment(update.contact, ctx)
    logger.info(f"Contact {contact_id[:8]} edited (renamed: {update.renamed_from is not None}, "
                f"enrichment: {enrichment})")
    _notify("contact_updated", {"contact_id": contact_id, "enrichment": enrichment})
    spoken = f"Updated {update.contact.person_name}."
    if update.anchors_changed:
        spoken += " I am searching the web again with the new details."
    return {"status": "updated", "contact": contact_dict(update.contact), "enrichment": enrichment,
            "spoken_summary": spoken}


def contact_cascade_preview(contact_id: str, store: Optional[AbstractContextStore] = None) -> Dict[str, Any]:
    """What deleting a contact also deletes (dashboard confirmation and MCP preview)."""
    ctx = _store(store)
    contact = ctx.get_social_contact(contact_id)
    if contact is None or contact.id != contact_id:
        raise _not_found("Contact")
    commitments = rules.contact_cascade(ctx, contact.person_name)
    tasks = []
    for com in commitments:
        task = ctx.get_planned_task(com.auto_scheduled_task_id) if com.auto_scheduled_task_id else None
        if task is not None:
            tasks.append({"id": task.id, "title": task.title})
    return {
        "id": contact_id, "name": contact.person_name,
        "commitments": [{"id": c.id, "description": c.description, "debtor": c.debtor, "status": c.status}
                        for c in commitments],
        "tasks": tasks,
    }


def execute_delete_contact(contact_id: str, confirm: bool = False, store: Optional[AbstractContextStore] = None,
                           engine: Any = None) -> Dict[str, Any]:
    ctx = _store(store)
    cascade = contact_cascade_preview(contact_id, ctx)
    if not confirm:
        spoken = f"This deletes {cascade['name']}"
        if cascade["commitments"]:
            spoken += f", {len(cascade['commitments'])} commitment(s) and {len(cascade['tasks'])} routine(s)"
        return _preview("contact", cascade, spoken + ".")
    deleted = ctx.delete_social_contact(contact_id)
    if deleted is None:
        raise _not_found("Contact")
    _unlink(engine, ctx, deleted.session_id, "social_contact", contact_id)
    logger.info(f"Contact {contact_id[:8]} deleted with {deleted.commitments_deleted} commitment(s) and "
                f"{deleted.tasks_deleted} task(s)")
    _notify("contact_deleted", {"contact_id": contact_id, "commitments_deleted": deleted.commitments_deleted,
                                "tasks_deleted": deleted.tasks_deleted})
    return {"status": "deleted", "deleted_id": contact_id, "commitments_deleted": deleted.commitments_deleted,
            "tasks_deleted": deleted.tasks_deleted, "spoken_summary": f"I deleted {deleted.name}."}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def execute_delete_event(session_id: str, confirm: bool = False, store: Optional[AbstractContextStore] = None,
                         engine: Any = None) -> Dict[str, Any]:
    eng = _engine(engine)
    ctx = store or eng.store
    dossier = ctx.get_session_dossier(session_id, include_chunks=False)
    if dossier is None:
        raise _not_found("Event")
    title = dossier.title or "Untitled event"
    if not confirm:
        briefings = len(ctx.list_briefings_for_session(session_id))
        return _preview("event", {"id": session_id, "title": title, "start_time": dossier.start_time,
                                  "concluded_at": dossier.concluded_at, "briefings": briefings},
                        f"This deletes the event '{title}' with its transcript and {briefings} briefing(s). "
                        "The actions, contacts and routines found in it are kept.")
    deleted = eng.delete(session_id)
    if deleted is None:
        raise _not_found("Event")
    logger.info(f"Event {session_id[:8]} deleted ({deleted.chunks_deleted} chunks, "
                f"{deleted.briefings_deleted} briefings)")
    _notify("event_deleted", {"session_id": session_id})
    return {"status": "deleted", "deleted_id": session_id, "briefings_deleted": deleted.briefings_deleted,
            "chunks_deleted": deleted.chunks_deleted, "spoken_summary": f"I deleted the event '{title}'."}


# ---------------------------------------------------------------------------
# MCP tools (registered in mcp_server.py with ToolAnnotations, under tenant_tool)
# ---------------------------------------------------------------------------

def _tool(fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    try:
        return fn()
    except CurationError as e:
        return {"status": e.code, "message": str(e)}


def _changes(**fields: Any) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None}


def update_action(action_id: str, title: Optional[str] = None, domain: Optional[str] = None) -> Dict[str, Any]:
    """Correct an extracted action (Peace of Mind note): its title or its domain.

    Args:
        action_id: Exact action id, from get_daily_actions_recap or verify_action_status. Never guess it.
        title: Corrected title (e.g. 'gas stove off').
        domain: 'safety', 'routine' or 'work_task'.
    """
    return _tool(lambda: execute_update_action(action_id, _changes(action_type=title, domain=domain)))


def delete_action(action_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Delete an extracted action that is wrong or not of interest. A routine it had completed goes
    back to pending.

    Call it first WITHOUT confirm: you get what would be deleted. Read it back to the user and call
    again with confirm=true only after they agree.

    Args:
        action_id: Exact action id, from get_daily_actions_recap or verify_action_status. Never guess it.
        confirm: True only after the user confirmed the preview.
    """
    return _tool(lambda: execute_delete_action(action_id, confirm=confirm))


def update_planned_task(task_id: str, title: Optional[str] = None, domain: Optional[str] = None,
                        scheduled_time: Optional[str] = None, recurrence: Optional[str] = None) -> Dict[str, Any]:
    """Correct a routine (planned task): title, domain, time or recurrence.

    Args:
        task_id: Exact task id, from get_upcoming_tasks or get_daily_actions_recap. Never guess it.
        title: Corrected title.
        domain: 'safety', 'routine', 'work_task' or 'personal'.
        scheduled_time: 'HH:MM' or an ISO timestamp.
        recurrence: 'none', 'daily', 'weekdays' or 'weekly'.
    """
    return _tool(lambda: execute_update_task(task_id, _changes(title=title, domain=domain,
                                                               scheduled_time=scheduled_time,
                                                               recurrence=recurrence)))


def delete_planned_task(task_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Delete a routine (planned task).

    Call it first WITHOUT confirm: you get what would be deleted. Read it back to the user and call
    again with confirm=true only after they agree.

    Args:
        task_id: Exact task id, from get_upcoming_tasks or get_daily_actions_recap. Never guess it.
        confirm: True only after the user confirmed the preview.
    """
    return _tool(lambda: execute_delete_task(task_id, confirm=confirm))


def update_contact(contact_id: str, name: Optional[str] = None, company_or_role: Optional[str] = None,
                   contact_info: Optional[str] = None, website_url: Optional[str] = None,
                   key_topics: Optional[list[str]] = None) -> Dict[str, Any]:
    """Correct or complete a contact (e.g. a misspelled name, the company). Changing the name or the
    company/role discards the old web profile and searches the web again automatically.

    Args:
        contact_id: Exact contact id, from query_social_contact or get_contact_profile. Never guess it.
        name: Corrected full name.
        company_or_role: Company, title or professional context.
        contact_info: Email, phone or handle.
        website_url: Personal or company website (http/https).
        key_topics: Topics discussed with this person (replaces the list).
    """
    return _tool(lambda: execute_update_contact(contact_id, _changes(
        person_name=name, company_or_role=company_or_role, contact_info=contact_info, website_url=website_url,
        key_topics=key_topics)))


def delete_contact(contact_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Delete a contact that is not of interest, together with its commitments and the routines they
    scheduled.

    Call it first WITHOUT confirm: you get the contact and everything that goes with it. Read it back to
    the user and call again with confirm=true only after they agree.

    Args:
        contact_id: Exact contact id, from query_social_contact or get_contact_profile. Never guess it.
        confirm: True only after the user confirmed the preview.
    """
    return _tool(lambda: execute_delete_contact(contact_id, confirm=confirm))


def delete_session_dossier(session_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Delete a topic event (session dossier) with its transcript log and briefings. Actions, contacts
    and routines found in it are kept.

    Call it first WITHOUT confirm: you get what would be deleted. Read it back to the user and call
    again with confirm=true only after they agree.

    Args:
        session_id: Exact event id, from list_session_dossiers or get_session_dossier. Never guess it.
        confirm: True only after the user confirmed the preview.
    """
    return _tool(lambda: execute_delete_event(session_id, confirm=confirm))
