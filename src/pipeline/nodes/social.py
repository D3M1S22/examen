"""Social Recall Extractor node for the EXAMEN pipeline (Stage 3A).

Extracts interpersonal encounters, bilateral commitments, roles, and contacts.
Deduplicates and merges with existing contacts in the context store.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.models import get_fast_model, has_active_model_credentials
from src.core.schemas import ExamenState, SocialCommitment, SocialEntity
from src.core.storage import get_storage_store
from src.pipeline.nodes.scheduler import parse_relative_time_expression

logger = logging.getLogger("examen.pipeline.social")

SOCIAL_SYSTEM_PROMPT = """You are the Social Recall Extractor for the EXAMEN ambient wearable AI engine.
Your role is to analyze a transcribed audio snippet and extract details regarding personal or professional encounters:
1. Person Name: Full name or first name of the person encountered or introduced.
2. Company or Role: Job title, affiliation, or professional context (e.g. "Cloud Architect at AWS", "Tech Lead at Acme").
3. Contact Info: Email, phone, or handle if explicitly shared.
4. Commitments: Explicit bilateral promises or obligations agreed upon. For each commitment:
   - debtor: 'user' if the user promised the contact ('user'), OR 'contact' if the contact promised the user ('contact').
   - description: Concrete action or deliverable promised.
   - due_date_raw: The relative or absolute time constraint mentioned (e.g. 'tomorrow at 10 AM', 'by Friday') or null.
   - status: 'open'.
5. Key Topics: Salient technical or business topics discussed (e.g. ["AgentCore", "Kubernetes", "Hackathon"]).

RULES:
- Do NOT hallucinate names or commitments not grounded in the text.
- If no clear person or introduction is detected, return null.
- Extract commitments as concise action statements.
"""


def _get_social_extractor():
    """Initializes model with structured output for social entity extraction."""
    return get_fast_model().with_structured_output(SocialEntity)


def _heuristic_extract_social(
    transcript: str,
    historical_context: Optional[str] = None,
    speaker_role: Optional[str] = None,
) -> Optional[SocialEntity]:
    """Deterministic heuristic extractor for offline dev, testing, or API fallbacks."""
    text = transcript.strip()
    if not text:
        return None

    # Name and role patterns
    # e.g. "Hi, I'm Luca Rossi, Cloud Architect at AWS. I'll send you the whitepaper tomorrow."
    # e.g. "Nice to meet you, my name is Sarah Connor from Cyberdyne Systems."
    # e.g. "Piacere, sono Marco Bianchi, CTO di Acme."
    name_patterns = [
        r"(?:i am|i['’]m|my name is|this is|sono|mi chiamo)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:meet|with|incontrato)\s+(?!you\b|me\b|us\b|them\b|him\b|her\b)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ]

    person_name = None
    for pat in name_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            person_name = m.group(1).title().strip()
            break

    # If name not in current chunk, resolve anaphora from historical context
    if not person_name and historical_context:
        for pat in name_patterns:
            m = re.search(pat, historical_context, re.IGNORECASE)
            if m:
                person_name = m.group(1).title().strip()
                break

    if not person_name:
        return None

    # Extract company or role
    company_or_role = None
    combined_context = f"{historical_context or ''} {text}"
    m_role = re.search(r"(?:,\s*|\s+)(?:a\s+|an\s+)?([A-Za-z\s]+(?:Architect|Lead|Engineer|Director|Manager|CTO|CEO|Founder|Researcher)\s*(?:at|di|in)?\s*[A-Za-z0-9_\-\.]*)", text, re.IGNORECASE)
    if m_role:
        company_or_role = m_role.group(1).strip()
    else:
        m_co = re.search(r"(?:at|di|presso|from)\s+([A-Z][A-Za-z0-9_\-\.]+)", text)
        if m_co:
            company_or_role = f"at {m_co.group(1)}"
        elif historical_context:
            m_hist_role = re.search(r"(?:,\s*|\s+)(?:a\s+|an\s+)?([A-Za-z\s]+(?:Architect|Lead|Engineer|Director|Manager|CTO|CEO|Founder|Researcher)\s*(?:at|di|in)?\s*[A-Za-z0-9_\-\.]*)", historical_context, re.IGNORECASE)
            if m_hist_role:
                company_or_role = m_hist_role.group(1).strip()
            else:
                m_hist_co = re.search(r"(?:at|di|presso|from)\s+([A-Z][A-Za-z0-9_\-\.]+)", historical_context)
                if m_hist_co:
                    company_or_role = f"at {m_hist_co.group(1)}"

    # Extract bilateral commitments
    commitments: List[SocialCommitment] = []
    
    # 1. User promises (debtor = 'user', unless speaker is identified as contact)
    effective_user_debtor = "contact" if speaker_role == "contact" else "user"
    user_patterns = [
        r"(i(?:'ll| will)\s+(?:send|email|forward|share|review|call|text|prepare)\s+[^.,;!?]+)",
        r"(let(?:'s| us)\s+stay in touch[^.,;!?]*)",
        r"((?:ti|vi)\s+(?:mando|invio|spedisco|scrivo)\s+[^.,;!?]+)",
        r"(ci\s+sentiamo\s+[^.,;!?]+)",
    ]
    for pat in user_patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            comm_desc = match.group(1).strip()
            norm_iso, raw_time = parse_relative_time_expression(comm_desc)
            if not raw_time:
                norm_iso, raw_time = parse_relative_time_expression(text)
            commitments.append(SocialCommitment(
                contact_name=person_name,
                debtor=effective_user_debtor,
                description=comm_desc,
                due_date_raw=raw_time,
                normalized_deadline=norm_iso,
                status="open",
            ))

    # 2. Contact promises (debtor = 'contact')
    contact_patterns = [
        r"((?:he|she|they|[A-Z][a-z]+)\s+(?:will|promised to|agreed to)\s+[^.,;!?]+)",
        r"((?:lui|lei|[A-Z][a-z]+)\s+(?:mi\s+manda|invier[aà]|ha\s+promesso\s+di)\s+[^.,;!?]+)",
    ]
    for pat in contact_patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            comm_desc = match.group(1).strip()
            norm_iso, raw_time = parse_relative_time_expression(comm_desc)
            if not raw_time:
                norm_iso, raw_time = parse_relative_time_expression(text)
            commitments.append(SocialCommitment(
                contact_name=person_name,
                debtor="contact",
                description=comm_desc,
                due_date_raw=raw_time,
                normalized_deadline=norm_iso,
                status="open",
            ))

    # Extract key topics from technical keywords
    topics: List[str] = []
    tech_keywords = [
        "Bedrock", "AgentCore", "LangGraph", "DynamoDB", "AWS", "Docker", "Kubernetes",
        "Python", "Alexa", "MCP", "AI", "Agent", "Architecture", "Microservices"
    ]
    for kw in tech_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
            topics.append(kw)

    # Extract contact info (email / phone)
    contact_info = None
    m_email = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    if m_email:
        contact_info = m_email.group(0)

    return SocialEntity(
        person_name=person_name,
        company_or_role=company_or_role,
        contact_info=contact_info,
        commitments=commitments,
        key_topics=topics,
        timestamp=datetime.now().isoformat()
    )


def _deduplicate_and_merge(extracted: SocialEntity) -> SocialEntity:
    """Check context store for existing contact and merge commitments/topics."""
    try:
        store = get_storage_store()
        existing = store.search_social_contact(extracted.person_name)
        if existing:
            primary = existing[0]
            # Merge ID
            extracted.id = primary.id
            if not extracted.company_or_role and primary.company_or_role:
                extracted.company_or_role = primary.company_or_role
            if not extracted.contact_info and primary.contact_info:
                extracted.contact_info = primary.contact_info

            # Merge commitments
            merged_commitments = list(primary.commitments)
            existing_descs = {
                (c.description.lower() if hasattr(c, "description") else str(c).lower())
                for c in merged_commitments
            }
            for c in extracted.commitments:
                desc = (c.description.lower() if hasattr(c, "description") else str(c).lower())
                if desc not in existing_descs:
                    merged_commitments.append(c)
                    existing_descs.add(desc)
            extracted.commitments = merged_commitments

            # Merge topics
            merged_topics = list(primary.key_topics)
            for t in extracted.key_topics:
                if t not in merged_topics:
                    merged_topics.append(t)
            extracted.key_topics = merged_topics

            # Merge web profile
            if not extracted.web_profile and primary.web_profile:
                extracted.web_profile = primary.web_profile

            logger.info(f"Merged social entity with existing contact '{primary.person_name}' (ID: {primary.id})")
    except Exception as e:
        logger.warning(f"Social deduplication lookup failed: {e}")

    return extracted


def _enrich_if_qualified(entity: Optional[SocialEntity]) -> Optional[SocialEntity]:
    """Autonomously enriches newly encountered contacts if they satisfy disambiguation guardrails."""
    if not entity or entity.web_profile:
        return entity
    try:
        from src.pipeline.nodes.social_profiler import (
            enrich_social_contact_sync,
            verify_disambiguation_anchors,
        )
        if verify_disambiguation_anchors(
            name=entity.person_name,
            company_or_role=entity.company_or_role,
            notes=entity.contact_info,
            topics=entity.key_topics,
        ):
            enrich_social_contact_sync(entity)
    except Exception as e:
        logger.warning(f"Autonomous web enrichment hook failed: {e}")
    return entity


def node_extract_social(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Stage 3A Social Recall Extractor.

    Extracts contact info and commitments, grounds location telemetry, resolves
    speaker roles, merges with existing records, and outputs social_data.
    """
    transcript = state.get("raw_transcript", "").strip()
    if not transcript:
        return {"social_data": None}

    historical_context = state.get("historical_context")
    location = state.get("location")
    speaker_role = state.get("speaker_role")

    # Fallback if mock_ai or missing provider credentials
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Extracting social entity via heuristic fallback (mock_ai or no credentials).")
        social = _heuristic_extract_social(
            transcript, historical_context=historical_context, speaker_role=speaker_role
        )
        if social:
            if location and not social.location_encountered and location.get("place_name"):
                social.location_encountered = location.get("place_name")
            social = _deduplicate_and_merge(social)
            social = _enrich_if_qualified(social)
        return {"social_data": social}

    try:
        extractor = _get_social_extractor()
        context_prefix = f"Recent Dialogue Context:\n{historical_context}\n\n" if historical_context else ""
        prompt = (
            f"Extract person encounter details, company/role, contact info, and promises made.\n\n"
            f"{context_prefix}Transcript: \"{transcript}\""
        )
        messages = [
            SystemMessage(content=SOCIAL_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        result: Optional[SocialEntity] = extractor.invoke(messages)

        if result and result.person_name and result.person_name.strip().lower() not in ("unknown", "none", "n/a", "null", ""):
            if not result.timestamp:
                result.timestamp = datetime.now().isoformat()

            if location and not result.location_encountered and location.get("place_name"):
                result.location_encountered = location.get("place_name")

            # If LLM left commitments empty, supplement with heuristic extraction
            if not result.commitments:
                h_social = _heuristic_extract_social(
                    transcript, historical_context=historical_context, speaker_role=speaker_role
                )
                if h_social and h_social.commitments:
                    result.commitments = h_social.commitments

            # Post-process commitments to ensure contact_name, normalized_deadline, and debtor alignment
            processed_commitments = []
            for c in result.get_commitments_as_objects():
                if not c.contact_name:
                    c.contact_name = result.person_name
                if speaker_role == "contact":
                    c.debtor = "contact"
                if not c.normalized_deadline:
                    probe_text = f"{c.due_date_raw or ''} {c.description} {transcript}"
                    norm_iso, raw_time = parse_relative_time_expression(probe_text)
                    if norm_iso:
                        c.normalized_deadline = norm_iso
                        if not c.due_date_raw:
                            c.due_date_raw = raw_time
                processed_commitments.append(c)
            result.commitments = processed_commitments

            result = _deduplicate_and_merge(result)
            result = _enrich_if_qualified(result)
            return {"social_data": result}
        else:
            return {"social_data": None}

    except Exception as e:
        logger.warning(f"Social extraction model failed: {e}. Falling back to heuristic.")
        social = _heuristic_extract_social(
            transcript, historical_context=historical_context, speaker_role=speaker_role
        )
        if social:
            if location and not social.location_encountered and location.get("place_name"):
                social.location_encountered = location.get("place_name")
            social = _deduplicate_and_merge(social)
            social = _enrich_if_qualified(social)
        return {"social_data": social}

