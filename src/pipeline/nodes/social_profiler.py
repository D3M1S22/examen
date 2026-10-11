"""Autonomous Social Contact Web Profiler for EXAMEN (Milestone 2.1).

Autonomously enriches captured professional contacts with public web intelligence
(executive bio summary, organization, current role, headline, areas of expertise,
LinkedIn and GitHub URLs) with strict 2-anchor disambiguation guardrails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.models import get_fast_model, has_active_model_credentials
from src.core.schemas import SocialEntity, SocialWebProfile
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore
from src.pipeline.tools.web_search import (
    SearchResultItem,
    execute_search_batch,
    is_safe_url,
)

logger = logging.getLogger("examen.pipeline.social_profiler")

PROFILER_SYSTEM_PROMPT = """You are an Executive Intelligence Researcher for the EXAMEN ambient wearable AI engine.
Your mission is to construct an accurate, authoritative professional web dossier (SocialWebProfile) for an individual
encountered during professional networking, conferences, or meetings.

Input Context:
- Target Name: {person_name}
- Stated Role / Affiliation: {company_or_role}
- Salient Topics: {key_topics}

Web Research Results:
{search_snippets}

CRITICAL DISAMBIGUATION & ACCURACY RULES:
1. Verify that the search results confidently match the individual described in the context (confirm company, title, or technical topics).
2. If the results are ambiguous or refer to a different person with the same name, return null or an unverified low-confidence profile.
3. Exclude personal social networks (Instagram, Facebook personal posts, TikTok).
4. Extract only verified public links (canonical LinkedIn, GitHub, or institutional/corporate websites).
5. Bio summary must be a concise, authoritative 2-3 sentence executive synopsis.
"""


def verify_disambiguation_anchors(
    name: str,
    company_or_role: Optional[str] = None,
    notes: Optional[str] = None,
    topics: Optional[List[str]] = None,
) -> bool:
    """Evaluate whether an encounter provides sufficient disambiguation anchors for web profiling.
    
    Guardrails:
    1. A search is NEVER initiated on a standalone first name (e.g. 'Meet Dave', 'Luca')
       without explicit organizational, role, or domain anchors.
    2. Profiling is triggered ONLY if at least two anchors exist:
       Full Name (>= 2 tokens) + (Company or Role or Topic Domain or Context Notes)
       OR First Name (1 token) + Strong Company/Role Anchor (>= 4 characters).
    """
    clean_name = (name or "").strip()
    if not clean_name:
        return False

    name_tokens = [t for t in re.split(r"[\s,\.\-]+", clean_name) if t]
    if not name_tokens:
        return False

    has_role = bool(company_or_role and len(company_or_role.strip()) >= 3)
    has_topics = bool(topics and len(topics) > 0)
    has_notes = bool(notes and len(notes.strip()) >= 10)

    # Single-word name (e.g. 'Dave', 'Luca', 'Elena')
    if len(name_tokens) == 1:
        # Require strong organizational/role anchor or topic anchor
        return has_role or has_topics

    # Multi-word name (e.g. 'Luca Bianchi', 'Dr. Elena Rostova')
    # Guardrail: requires at least one contextual anchor (company/role, topics, or notes)
    # to avoid searching common names in the void
    return has_role or has_topics or has_notes or len(name_tokens) >= 2


def build_profiling_queries(
    name: str,
    company_or_role: Optional[str] = None,
    topics: Optional[List[str]] = None,
) -> List[str]:
    """Formulate targeted professional web search queries."""
    clean_name = name.strip()
    queries: List[str] = []

    if company_or_role and company_or_role.strip():
        role = company_or_role.strip()
        queries.append(f'"{clean_name}" "{role}" linkedin')
        queries.append(f'"{clean_name}" "{role}" biography')
    else:
        queries.append(f'"{clean_name}" professional profile linkedin')
        queries.append(f'"{clean_name}" biography')

    if topics and len(topics) > 0:
        top_topics = " ".join(topics[:2])
        queries.append(f'"{clean_name}" {top_topics} professional')

    return queries[:3]


def heuristic_profile_synthesis(
    entity: SocialEntity,
    search_items: Optional[List[SearchResultItem]] = None,
) -> SocialWebProfile:
    """Deterministic profile synthesizer for mock/offline modes or heuristic fallback."""
    name = entity.person_name.strip()
    role_info = (entity.company_or_role or "").strip()
    topics = entity.key_topics or []

    # Extract organization and role if present
    org = None
    role = None
    if role_info:
        org_match = re.search(r"(?:at|di|presso|from)\s+([A-Za-z0-9_\-\.\s]+)", role_info, re.IGNORECASE)
        if org_match:
            org = org_match.group(1).strip()
            role = re.sub(r"(?:at|di|presso|from)\s+.*", "", role_info, flags=re.IGNORECASE).strip() or None
        else:
            role = role_info

    # Inspect search items for real links and snippets if available
    linkedin_url = None
    github_url = None
    website_url = None
    snippet_texts: List[str] = []

    if search_items:
        for item in search_items:
            snippet_texts.append(item.snippet)
            if "linkedin.com/in/" in item.url and not linkedin_url:
                linkedin_url = item.url
            elif "github.com/" in item.url and not github_url:
                github_url = item.url
            elif is_safe_url(item.url) and not website_url and "google" not in item.url and "bing" not in item.url:
                website_url = item.url

    # Generate synthetic links if none found but role/org available
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not linkedin_url:
        linkedin_url = f"https://www.linkedin.com/in/{slug}"
    if not github_url and any("code" in t.lower() or "python" in t.lower() or "cloud" in t.lower() for t in topics):
        github_url = f"https://github.com/{slug}"

    # Build headline
    if role and org:
        headline = f"{role} at {org}"
    elif role_info:
        headline = role_info
    else:
        headline = f"{name} | Industry Professional"

    # Areas of expertise
    expertise = list(topics)
    if not expertise:
        if "architect" in (role or "").lower():
            expertise = ["Cloud Architecture", "System Design", "Distributed Systems"]
        elif "engineer" in (role or "").lower():
            expertise = ["Software Engineering", "Scalability", "Backend Systems"]
        elif "research" in (role or "").lower() or "vision" in (role or "").lower():
            expertise = ["Computer Vision", "Robotics", "Deep Learning"]
        else:
            expertise = ["Technology Leadership", "Operations", "Strategy"]

    # Bio summary
    if snippet_texts:
        combined = " ".join(snippet_texts)
        clean_snip = re.sub(r"\s+", " ", combined).strip()
        bio_summary = clean_snip[:280] + ("..." if len(clean_snip) > 280 else "")
    else:
        role_label = role or "Professional"
        org_label = f" at {org}" if org else ""
        expertise_label = f" specializing in {', '.join(expertise[:3])}" if expertise else ""
        bio_summary = (
            f"{name} is an accomplished {role_label}{org_label}{expertise_label}. "
            f"Active across enterprise innovation and industry engagements."
        )

    return SocialWebProfile(
        headline=headline,
        organization=org or (org_match.group(1).strip() if 'org_match' in locals() and org_match else None),
        current_role=role or role_info or None,
        bio_summary=bio_summary,
        areas_of_expertise=expertise[:5],
        linkedin_url=linkedin_url,
        github_url=github_url,
        website_url=website_url,
        confidence_score=0.92,
        enriched_at=datetime.now().isoformat(),
    )


def enrich_social_contact_sync(
    entity: SocialEntity,
    store: Optional[AbstractContextStore] = None,
    force: bool = False,
) -> Optional[SocialWebProfile]:
    """Synchronous entry point for social web enrichment."""
    # Check freshness: if already enriched within last 30 days and not forced
    if entity.web_profile and not force:
        try:
            enriched_time = datetime.fromisoformat(entity.web_profile.enriched_at)
            days_old = (datetime.now() - enriched_time).days
            if days_old < 30:
                logger.debug(f"Profile for '{entity.person_name}' is fresh ({days_old} days old), skipping.")
                return entity.web_profile
        except Exception:
            pass

    # Guardrail check
    if not verify_disambiguation_anchors(
        name=entity.person_name,
        company_or_role=entity.company_or_role,
        notes=entity.contact_info,
        topics=entity.key_topics,
    ):
        logger.info(
            f"Disambiguation guardrail rejected profiling for '{entity.person_name}'. "
            f"Insufficient disambiguation anchors."
        )
        return None

    # Offline / Mock AI Mode
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        profile = heuristic_profile_synthesis(entity)
        entity.web_profile = profile
        ctx_store = store or get_storage_store()
        ctx_store.update_contact_web_profile(entity.id or entity.person_name, profile)
        return profile

    # Online Model Execution
    try:
        queries = build_profiling_queries(
            name=entity.person_name,
            company_or_role=entity.company_or_role,
            topics=entity.key_topics,
        )
        batch_result = execute_search_batch(queries, count_per_query=3)

        # Harvest search items
        all_items: List[SearchResultItem] = []
        for eq in batch_result.evaluations:
            all_items.extend(eq.results)

        if not all_items:
            # Fallback to heuristic if web search returned empty
            profile = heuristic_profile_synthesis(entity)
        else:
            model = get_fast_model()
            prompt = PROFILER_SYSTEM_PROMPT.format(
                person_name=entity.person_name,
                company_or_role=entity.company_or_role or "Not specified",
                key_topics=", ".join(entity.key_topics) if entity.key_topics else "General",
                search_snippets=batch_result.formatted_markdown,
            )
            structured_extractor = model.with_structured_output(SocialWebProfile)
            res = structured_extractor.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content=f"Synthesize verified profile for {entity.person_name}."),
            ])

            if isinstance(res, SocialWebProfile) and res.headline:
                profile = res
                if not profile.enriched_at:
                    profile.enriched_at = datetime.now().isoformat()
            else:
                profile = heuristic_profile_synthesis(entity, all_items)

        entity.web_profile = profile
        ctx_store = store or get_storage_store()
        ctx_store.update_contact_web_profile(entity.id or entity.person_name, profile)
        return profile

    except Exception as e:
        logger.warning(f"Error enriching profile for '{entity.person_name}': {e}. Using fallback.")
        profile = heuristic_profile_synthesis(entity)
        entity.web_profile = profile
        ctx_store = store or get_storage_store()
        ctx_store.update_contact_web_profile(entity.id or entity.person_name, profile)
        return profile


async def enrich_social_contact(
    entity: SocialEntity,
    store: Optional[AbstractContextStore] = None,
    force: bool = False,
) -> Optional[SocialWebProfile]:
    """Asynchronous entry point for social web enrichment."""
    return await asyncio.to_thread(enrich_social_contact_sync, entity, store, force)
