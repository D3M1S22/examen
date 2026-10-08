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


def execute_get_social_commitments(
    contact_name: Optional[str] = None,
    debtor: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for retrieving structured bilateral commitments."""
    ctx_store = store or get_storage_store()
    commitments = ctx_store.list_social_commitments(
        contact_name=contact_name,
        debtor=debtor,
        status=status,
        limit=limit,
    )

    comms_data = []
    user_promises = 0
    contact_promises = 0

    for c in commitments:
        if c.debtor == "user":
            user_promises += 1
        else:
            contact_promises += 1
        comms_data.append({
            "id": c.id,
            "contact_name": c.contact_name,
            "debtor": c.debtor,
            "description": c.description,
            "due_date_raw": c.due_date_raw,
            "normalized_deadline": c.normalized_deadline,
            "status": c.status,
            "auto_scheduled_task_id": c.auto_scheduled_task_id,
            "created_at": c.created_at,
        })

    if comms_data:
        spoken_parts = []
        if user_promises > 0:
            spoken_parts.append(f"{user_promises} commitment(s) you made to others")
        if contact_promises > 0:
            spoken_parts.append(f"{contact_promises} promise(s) made to you")
        summary_str = f"Found {len(comms_data)} commitment(s): {', and '.join(spoken_parts)}."
        first_few = [
            f"{'You promised ' if c['debtor'] == 'user' else c['contact_name'] + ' promised '} '{c['description']}'"
            + (f" by {c['due_date_raw']}" if c['due_date_raw'] else "")
            for c in comms_data[:3]
        ]
        spoken = f"{summary_str} For example: {'; '.join(first_few)}."
    else:
        spoken = "No matching social commitments found."

    return {
        "found": len(comms_data) > 0,
        "commitments": comms_data,
        "total": len(comms_data),
        "user_promises_count": user_promises,
        "contact_promises_count": contact_promises,
        "ui_card_type": "SOCIAL_COMMITMENTS_CARD",
        "spoken_summary": spoken,
    }


def get_social_commitments(
    contact_name: Optional[str] = None,
    debtor: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve bilateral commitments and promises made between you and contacts.
    
    Args:
        contact_name: Filter by contact name (e.g. 'Luca', 'Sara Bianchi').
        debtor: Filter by debtor role ('user' for promises you made, 'contact' for promises they made to you).
        status: Filter by status ('open', 'fulfilled', 'cancelled'). Default is all.
    """
    return execute_get_social_commitments(
        contact_name=contact_name,
        debtor=debtor,
        status=status,
    )
