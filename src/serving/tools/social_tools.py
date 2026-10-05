"""Social tools for the Alexa+ MCP Serving layer.

Exposes relational memory retrieval for people met, corporate roles,
and bilateral commitments.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.schemas import SocialEntity
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore

logger = logging.getLogger("examen.serving.tools.social")


def execute_query_social_contact(
    name_or_query: str,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for searching social contacts."""
    ctx_store = store or get_storage_store()
    matches = ctx_store.search_social_contact(query=name_or_query)

    if matches:
        contact: SocialEntity = matches[0]
        other_matches = [
            {"id": m.id, "name": m.person_name, "role": m.company_or_role}
            for m in matches[1:5]
        ]

        role_str = f" ({contact.company_or_role})" if contact.company_or_role else ""
        topics_str = (
            f" Key topics: {', '.join(contact.key_topics[:3])}."
            if contact.key_topics
            else ""
        )
        commitments_str = (
            f" You have {len(contact.commitments)} recorded commitment(s)."
            if contact.commitments
            else ""
        )
        spoken = f"{contact.person_name}{role_str}.{topics_str}{commitments_str}"

        return {
            "found": True,
            "contact": {
                "id": contact.id,
                "name": contact.person_name,
                "company_or_role": contact.company_or_role,
                "contact_info": contact.contact_info,
                "first_met": contact.timestamp,
                "key_topics": contact.key_topics,
                "commitments": contact.commitments,
            },
            "total_matches": len(matches),
            "other_matches": other_matches,
            "ui_card_type": "SOCIAL_PROFILE_CARD",
            "spoken_summary": spoken,
        }

    return {
        "found": False,
        "query": name_or_query,
        "message": f"No social contact found matching '{name_or_query}'.",
        "ui_card_type": "SOCIAL_NOT_FOUND",
        "spoken_summary": f"I couldn't find any contact records matching '{name_or_query}'.",
    }


def query_social_contact(
    name_or_query: str,
) -> Dict[str, Any]:
    """Search the social interactions registry for contacts by name, company, or discussed topics.
    
    Args:
        name_or_query: Person's name, company, or keyword (e.g. 'Marco', 'Stripe', 'Tech Lead').
    """
    return execute_query_social_contact(name_or_query=name_or_query)
