"""Persistence node for the EXAMEN pipeline.

Atomically commits extracted actions, social contacts, and topic briefings
to the configured context store (SQLite with FTS5 locally, or AWS DynamoDB/AgentCore Memory).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from src.core.schemas import ExamenState, MicroEventRef
from src.core.storage import get_storage_store

logger = logging.getLogger("examen.pipeline.persist")


def node_persist(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Persistence Node.

    Commits all extracted entities to the persistent storage layer
    and links micro-events to any active macro session.
    """
    store = get_storage_store()
    session_id = state.get("session_id")

    # 1. Persist Verified Action & Auto-Resolve Planned Tasks
    action_data = state.get("action_data")
    if action_data:
        try:
            if session_id and not action_data.session_id:
                action_data.session_id = session_id
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
            rec_id = store.save_social_contact(social_data)
            logger.info(f"Persisted social contact '{social_data.person_name}' (ID: {rec_id})")
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

    # 3. Persist Topic Briefing Report
    briefing_report = state.get("briefing_report")
    if briefing_report:
        try:
            rec_id = store.save_topic_briefing(briefing_report)
            logger.info(f"Persisted topic briefing '{briefing_report.topic_title}' (ID: {rec_id})")
            if session_id and hasattr(store, "conclude_session_dossier"):
                store.conclude_session_dossier(session_id=session_id, briefing_report_id=rec_id)
        except Exception as e:
            logger.error(f"Failed to persist topic briefing: {e}", exc_info=True)

    # 4. Persist Scheduled Task (Stage 3D Ambient Voice Tasks)
    scheduled_task = state.get("scheduled_task")
    if scheduled_task:
        try:
            if session_id and not scheduled_task.session_id:
                scheduled_task.session_id = session_id
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
