"""Persistence node for the EXAMEN pipeline.

Atomically commits extracted actions, social contacts, and topic briefings
to the configured context store (SQLite with FTS5 locally, or AWS DynamoDB/AgentCore Memory).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from src.core.schemas import ExamenState, MicroEventRef
from src.core.storage import get_storage_store
from src.core.time_utils import historical_action_may_resolve, parse_local_iso

logger = logging.getLogger("examen.pipeline.persist")

# Namespace for ids derived from the source utterance (idempotent re-processing, historical backfill)
_ENTITY_NAMESPACE = uuid.UUID("6f1d3c2a-9b4e-4c8a-8f0e-1d2b3c4d5e6f")


def derived_entity_id(source_key: Optional[str], kind: str) -> Optional[str]:
    """Deterministic entity id for one utterance: the same sentence never yields two records."""
    if not source_key:
        return None
    return str(uuid.uuid5(_ENTITY_NAMESPACE, f"{source_key}:{kind}"))


def node_persist(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Persistence Node.

    Commits all extracted entities to the persistent storage layer
    and links micro-events to any active macro session.
    """
    store = get_storage_store()
    session_id = state.get("session_id")
    source_key = state.get("source_key")
    ingest_source = state.get("ingest_source") or "live"
    run_id = state.get("ingest_run_id")
    historical = ingest_source == "backfill"
    spoken_at = state.get("timestamp")

    # 1. Persist Verified Action & Auto-Resolve Planned Tasks
    action_data = state.get("action_data")
    if action_data:
        try:
            if session_id and not action_data.session_id:
                action_data.session_id = session_id
            action_data.ingest_source = ingest_source
            action_data.ingest_run_id = run_id
            action_data.source_key = source_key
            action_data.id = action_data.id or derived_entity_id(source_key, "action")
            if historical:
                # Heuristic extractors stamp "now": a recovered action happened when it was spoken
                action_data.timestamp = spoken_at or action_data.timestamp
                if action_data.matched_task_id:
                    task = store.get_planned_task(action_data.matched_task_id)
                    if task is None or not historical_action_may_resolve(
                        action_data.timestamp, task.created_at, task.recurrence
                    ):
                        action_data.matched_task_id = None
            existing = store.get_verified_action(action_data.id) if source_key else None
            if existing is not None:
                logger.info(f"Verified action for '{source_key}' already persisted; skipping duplicate")
                rec_id = existing.id
            else:
                rec_id = store.save_action(action_data)
            logger.info(
                f"Persisted verified action '{action_data.action_type}' (ID: {rec_id}, "
                f"matched_task: {action_data.matched_task_id})"
            )
            if session_id and hasattr(store, "link_micro_event_to_session"):
                store.link_micro_event_to_session(
                    session_id=session_id,
                    event_ref=MicroEventRef(
                        event_type="action",
                        record_id=rec_id,
                        headline=action_data.raw_statement or action_data.action_type,
                        timestamp=action_data.timestamp,
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to persist verified action: {e}", exc_info=True)

    # 2. Persist Social Contact
    social_data = state.get("social_data")
    if social_data:
        try:
            if session_id and not social_data.session_id:
                social_data.session_id = session_id
            if historical and spoken_at:
                social_data.timestamp = spoken_at
            rec_id = store.save_social_contact(social_data)
            logger.info(f"Persisted social contact {rec_id}")
            if session_id and hasattr(store, "link_micro_event_to_session"):
                store.link_micro_event_to_session(
                    session_id=session_id,
                    event_ref=MicroEventRef(
                        event_type="social_contact",
                        record_id=rec_id,
                        headline=f"Met {social_data.person_name} ({social_data.company_or_role or 'Contact'})",
                        timestamp=social_data.timestamp,
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to persist social contact: {e}", exc_info=True)

    # 3. Persist Topic Briefing Report (standalone invocation; event briefings are produced and
    #    persisted by the Deep Topic Event Engine, which also owns session conclusion)
    briefing_report = state.get("briefing_report")
    if briefing_report:
        try:
            if session_id and not briefing_report.session_id:
                briefing_report.session_id = session_id
            rec_id = store.save_topic_briefing(briefing_report)
            logger.info(f"Persisted topic briefing {rec_id}")
        except Exception as e:
            logger.error(f"Failed to persist topic briefing: {e}", exc_info=True)

    # 4. Persist Scheduled Task (Stage 3D Ambient Voice Tasks)
    scheduled_task = state.get("scheduled_task")
    if scheduled_task:
        try:
            if session_id and not scheduled_task.session_id:
                scheduled_task.session_id = session_id
            scheduled_task.ingest_source = ingest_source
            scheduled_task.ingest_run_id = run_id
            scheduled_task.source_key = source_key
            scheduled_task.id = scheduled_task.id or derived_entity_id(source_key, "task")
            if historical:
                # The intention was voiced in the past: date it then, and never fire a stale reminder
                scheduled_task.created_at = spoken_at or scheduled_task.created_at
                due = parse_local_iso(scheduled_task.scheduled_time)
                if due is not None and due < datetime.now() and scheduled_task.status == "pending":
                    scheduled_task.status = "overdue"
                    scheduled_task.recovered = True
            existing_task = store.get_planned_task(scheduled_task.id) if source_key else None
            if existing_task is not None:
                # Keep any status the user changed meanwhile
                logger.info(f"Scheduled task for '{source_key}' already persisted; skipping duplicate")
                rec_id = existing_task.id
            else:
                rec_id = store.save_planned_task(scheduled_task)
            logger.info(
                f"Persisted ambient scheduled task '{scheduled_task.title}' (ID: {rec_id}, origin: {scheduled_task.origin})"
            )
            if session_id and hasattr(store, "link_micro_event_to_session"):
                store.link_micro_event_to_session(
                    session_id=session_id,
                    event_ref=MicroEventRef(
                        event_type="task_scheduled",
                        record_id=rec_id,
                        headline=f"Task: {scheduled_task.title}",
                        timestamp=scheduled_task.created_at or datetime.now().isoformat(),
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to persist ambient scheduled task: {e}", exc_info=True)

    return {}
