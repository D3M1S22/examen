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

        web_prof = contact.web_profile.model_dump() if contact.web_profile else None

        card_payload = {
            "template": "SOCIAL_PROFILE_CARD",
            "name": contact.person_name,
            "company_or_role": contact.company_or_role,
            "headline": (contact.web_profile.headline if contact.web_profile else None) or contact.company_or_role,
            "organization": contact.web_profile.organization if contact.web_profile else None,
            "bio_summary": contact.web_profile.bio_summary if contact.web_profile else None,
            "areas_of_expertise": contact.web_profile.areas_of_expertise if contact.web_profile else [],
            "links": {
                "linkedin": contact.web_profile.linkedin_url if contact.web_profile else None,
                "github": contact.web_profile.github_url if contact.web_profile else None,
                "website": (contact.web_profile.website_url if contact.web_profile else None) or getattr(contact, "website_url", None),
            },
            "key_topics": contact.key_topics,
            "commitments": contact.commitments,
            "spoken_summary": spoken,
        }

        return {
            "found": True,
            "contact": {
                "id": contact.id,
                "name": contact.person_name,
                "company_or_role": contact.company_or_role,
                "contact_info": contact.contact_info,
                "website_url": getattr(contact, "website_url", None) or (contact.web_profile.website_url if contact.web_profile else None),
                "first_met": contact.timestamp,
                "key_topics": contact.key_topics,
                "commitments": contact.commitments,
                "web_profile": web_prof,
            },
            "web_profile": web_prof,
            "total_matches": len(matches),
            "other_matches": other_matches,
            "display_template": "SOCIAL_PROFILE_CARD",
            "ui_card_type": "SOCIAL_PROFILE_CARD",
            "spoken_summary": spoken,
            "card_payload": card_payload,
        }

    return {
        "found": False,
        "query": name_or_query,
        "message": f"No social contact found matching '{name_or_query}'.",
        "display_template": "SOCIAL_NOT_FOUND",
        "ui_card_type": "SOCIAL_NOT_FOUND",
        "spoken_summary": f"I couldn't find any contact records matching '{name_or_query}'.",
        "card_payload": {
            "template": "SOCIAL_NOT_FOUND",
            "query": name_or_query,
            "message": f"No social contact found matching '{name_or_query}'.",
        },
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

    user_promises_list = [c for c in comms_data if c["debtor"] == "user"]
    contact_promises_list = [c for c in comms_data if c["debtor"] == "contact"]

    card_payload = {
        "template": "SOCIAL_COMMITMENTS_CARD",
        "contact_name": contact_name,
        "debtor_filter": debtor,
        "status_filter": status,
        "user_promises": user_promises_list,
        "user_debts": user_promises_list,
        "contact_promises": contact_promises_list,
        "total_commitments": len(comms_data),
        "total_user_debts": len(user_promises_list),
        "total_contact_promises": len(contact_promises_list),
        "spoken_summary": spoken,
    }

    return {
        "found": len(comms_data) > 0,
        "commitments": comms_data,
        "total": len(comms_data),
        "user_promises_count": user_promises,
        "contact_promises_count": contact_promises,
        "display_template": "SOCIAL_COMMITMENTS_CARD",
        "ui_card_type": "SOCIAL_COMMITMENTS_CARD",
        "spoken_summary": spoken,
        "card_payload": card_payload,
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


def execute_get_contact_profile(
    name_or_query: str,
    force_enrich: bool = False,
    store: Optional[AbstractContextStore] = None,
) -> Dict[str, Any]:
    """Internal implementation for retrieving an enriched executive contact dossier."""
    ctx_store = store or get_storage_store()
    contact = ctx_store.get_social_contact(name_or_query)
    if not contact:
        matches = ctx_store.search_social_contact(query=name_or_query)
        if matches:
            contact = matches[0]

    if not contact:
        return {
            "found": False,
            "query": name_or_query,
            "message": f"No contact record found for '{name_or_query}'.",
            "display_template": "SOCIAL_NOT_FOUND",
            "ui_card_type": "SOCIAL_NOT_FOUND",
            "spoken_summary": f"I couldn't find any contact record matching '{name_or_query}'.",
            "card_payload": {
                "template": "SOCIAL_NOT_FOUND",
                "query": name_or_query,
                "message": f"No contact record found for '{name_or_query}'.",
            },
        }

    # Autonomous profiling if web_profile is missing or forced
    if not contact.web_profile or force_enrich:
        try:
            from src.pipeline.nodes.social_profiler import enrich_social_contact_sync
            enriched = enrich_social_contact_sync(contact, store=ctx_store, force=force_enrich)
            if enriched:
                contact.web_profile = enriched
        except Exception as e:
            logger.warning(f"On-demand profile enrichment failed: {e}")

    # Commitments
    commitments = ctx_store.list_social_commitments(contact_name=contact.person_name)
    open_commitments = [c for c in commitments if c.status == "open"]

    profile_data = contact.web_profile.model_dump() if contact.web_profile else None

    spoken_parts = [contact.person_name]
    if profile_data and profile_data.get("headline"):
        spoken_parts.append(f", {profile_data['headline']}.")
    elif contact.company_or_role:
        spoken_parts.append(f", {contact.company_or_role}.")
    else:
        spoken_parts.append(".")

    if profile_data and profile_data.get("bio_summary"):
        spoken_parts.append(f" {profile_data['bio_summary']}")

    if open_commitments:
        spoken_parts.append(f" You have {len(open_commitments)} open bilateral commitment(s).")

    spoken = "".join(spoken_parts)

    card_payload = {
        "template": "SOCIAL_PROFILE_CARD",
        "name": contact.person_name,
        "company_or_role": contact.company_or_role,
        "headline": (contact.web_profile.headline if contact.web_profile else None) or contact.company_or_role,
        "organization": contact.web_profile.organization if contact.web_profile else None,
        "bio_summary": contact.web_profile.bio_summary if contact.web_profile else None,
        "areas_of_expertise": contact.web_profile.areas_of_expertise if contact.web_profile else [],
        "links": {
            "linkedin": contact.web_profile.linkedin_url if contact.web_profile else None,
            "github": contact.web_profile.github_url if contact.web_profile else None,
            "website": contact.web_profile.website_url if contact.web_profile else None,
        },
        "confidence_score": contact.web_profile.confidence_score if contact.web_profile else None,
        "user_promises": [c.model_dump() for c in commitments if c.debtor == "user"],
        "contact_promises": [c.model_dump() for c in commitments if c.debtor == "contact"],
        "open_commitments_count": len(open_commitments),
        "spoken_summary": spoken,
    }

    return {
        "found": True,
        "contact": {
            "id": contact.id,
            "name": contact.person_name,
            "company_or_role": contact.company_or_role,
            "contact_info": contact.contact_info,
            "first_met": contact.timestamp,
            "key_topics": contact.key_topics,
        },
        "web_profile": profile_data,
        "commitments": [c.model_dump() for c in commitments],
        "open_commitments_count": len(open_commitments),
        "display_template": "SOCIAL_PROFILE_CARD",
        "ui_card_type": "SOCIAL_PROFILE_CARD",
        "spoken_summary": spoken,
        "card_payload": card_payload,
    }


def get_contact_profile(
    name: str,
) -> Dict[str, Any]:
    """Retrieve an enriched executive contact dossier including public web bio, career credentials, verified links, and active mutual commitments.
    
    Args:
        name: Name or identifier of the contact (e.g. 'Luca Bianchi', 'Elena Rostova').
    """
    return execute_get_contact_profile(name_or_query=name)

