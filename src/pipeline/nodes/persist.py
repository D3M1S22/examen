"""Persistence node for the EXAMEN pipeline.

Atomically commits extracted actions, social contacts, and topic briefings
to the configured context store (SQLite with FTS5 locally, or AWS DynamoDB/AgentCore Memory).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.core.schemas import ExamenState
from src.core.storage import get_storage_store

logger = logging.getLogger("examen.pipeline.persist")


def node_persist(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Persistence Node.

    Commits all extracted entities to the persistent storage layer.
    """
    store = get_storage_store()

    # 1. Persist Verified Action & Auto-Resolve Planned Tasks
    action_data = state.get("action_data")
    if action_data:
        try:
            rec_id = store.save_action(action_data)
            logger.info(
                f"Persisted verified action '{action_data.action_type}' (ID: {rec_id}, "
                f"matched_task: {action_data.matched_task_id})"
            )
        except Exception as e:
            logger.error(f"Failed to persist verified action: {e}", exc_info=True)

    # 2. Persist Social Contact
    social_data = state.get("social_data")
    if social_data:
        try:
            rec_id = store.save_social_contact(social_data)
            logger.info(f"Persisted social contact '{social_data.person_name}' (ID: {rec_id})")
        except Exception as e:
            logger.error(f"Failed to persist social contact: {e}", exc_info=True)

    # 3. Persist Topic Briefing Report
    briefing_report = state.get("briefing_report")
    if briefing_report:
        try:
            rec_id = store.save_topic_briefing(briefing_report)
            logger.info(f"Persisted topic briefing '{briefing_report.topic_title}' (ID: {rec_id})")
        except Exception as e:
            logger.error(f"Failed to persist topic briefing: {e}", exc_info=True)

    # 4. Persist Scheduled Task (Stage 3D Ambient Voice Tasks)
    scheduled_task = state.get("scheduled_task")
    if scheduled_task:
        try:
            rec_id = store.save_planned_task(scheduled_task)
            logger.info(
                f"Persisted ambient scheduled task '{scheduled_task.title}' (ID: {rec_id}, origin: {scheduled_task.origin})"
            )
        except Exception as e:
            logger.error(f"Failed to persist ambient scheduled task: {e}", exc_info=True)

    return {}
