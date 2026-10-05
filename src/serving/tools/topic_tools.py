"""Topic intelligence tools for the Alexa+ MCP Serving layer.

Exposes executive briefings and technical dossiers synthesized from
ambient meeting conversations and enriched via autonomous web search.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.core.schemas import BriefingReport
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore

logger = logging.getLogger("examen.serving.tools.topic")


def execute_get_topic_briefing(
    topic_query: Optional[str] = None,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for retrieving topic briefings."""
    ctx_store = store or get_storage_store()
    briefing: Optional[BriefingReport] = ctx_store.get_topic_briefing(query=topic_query)

    if briefing:
        summary_bullets = briefing.executive_summary or []
        summary_preview = summary_bullets[0] if summary_bullets else "Technical briefing available."
        sources_count = len(briefing.web_sources)
        actions_count = len(briefing.action_items)

        spoken = (
            f"Here is the briefing on '{briefing.topic_title}'. "
            f"{summary_preview} "
            f"I found {sources_count} online reference(s) and noted {actions_count} follow-up action item(s)."
        )

        return {
            "found": True,
            "id": briefing.id,
            "topic_title": briefing.topic_title,
            "context_type": briefing.context_type,
            "created_at": briefing.created_at,
            "executive_summary": briefing.executive_summary,
            "web_sources": briefing.web_sources,
            "action_items": briefing.action_items,
            "deep_dive_markdown": briefing.deep_dive_markdown,
            "ui_card_type": "DEEP_BRIEFING_VIEWER",
            "spoken_summary": spoken,
        }

    search_desc = f" matching '{topic_query}'" if topic_query else ""
    return {
        "found": False,
        "query": topic_query,
        "message": f"No technical briefing reports found{search_desc}.",
        "ui_card_type": "BRIEFING_NOT_FOUND",
        "spoken_summary": f"I don't have any saved technical briefings{search_desc} yet.",
    }


def get_topic_briefing(
    topic_query: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve executive technical briefing reports enriched with autonomous web research.
    
    Args:
        topic_query: Subject title, framework name, or keyword (e.g. 'AgentCore', 'memory leak').
                     If omitted, returns the latest generated briefing.
    """
    return execute_get_topic_briefing(topic_query=topic_query)
