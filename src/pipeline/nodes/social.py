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
from src.core.schemas import ExamenState, SocialEntity
from src.core.storage import get_storage_store

logger = logging.getLogger("examen.pipeline.social")

SOCIAL_SYSTEM_PROMPT = """You are the Social Recall Extractor for the EXAMEN ambient wearable AI engine.
Your role is to analyze a transcribed audio snippet and extract details regarding personal or professional encounters:
1. Person Name: Full name or first name of the person encountered or introduced.
2. Company or Role: Job title, affiliation, or professional context (e.g. "Cloud Architect at AWS", "Tech Lead at Acme").
3. Contact Info: Email, phone, or handle if explicitly shared.
4. Commitments: Explicit promises or action items agreed upon (e.g. "Send whitepaper tomorrow", "Review PR by Friday").
5. Key Topics: Salient technical or business topics discussed (e.g. ["AgentCore", "Kubernetes", "Hackathon"]).

RULES:
- Do NOT hallucinate names or commitments not grounded in the text.
- If no clear person or introduction is detected, return null.
- Extract commitments as concise action statements.
"""


def _get_social_extractor():
    """Initializes model with structured output for social entity extraction."""
    return get_fast_model().with_structured_output(SocialEntity)


def _heuristic_extract_social(transcript: str) -> Optional[SocialEntity]:
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

    if not person_name:
        return None

    # Extract company or role
    role_pattern = r"(?:(?:at|from|di|in|con)\s+([A-Z][a-zA-Z0-9_\-\.]+)|(?:as\s+a|come)\s+([a-zA-Z\s]+))"
    company_or_role = None
    m_role = re.search(r"(?:,\s*|\s+)(?:a\s+|an\s+)?([A-Za-z\s]+(?:Architect|Lead|Engineer|Director|Manager|CTO|CEO|Founder|Researcher)\s*(?:at|di|in)?\s*[A-Za-z0-9_\-\.]*)", text, re.IGNORECASE)
    if m_role:
        company_or_role = m_role.group(1).strip()
    else:
        m_co = re.search(r"(?:at|di|presso|from)\s+([A-Z][A-Za-z0-9_\-\.]+)", text)
        if m_co:
            company_or_role = f"at {m_co.group(1)}"

    # Extract commitments
    commitments: List[str] = []
    commitment_patterns = [
        r"(i(?:'ll| will)\s+(?:send|email|forward|share|review|call|text|prepare)\s+[^.,;!?]+)",
        r"(let(?:'s| us)\s+stay in touch[^.,;!?]*)",
        r"((?:ti|vi)\s+(?:mando|invio|spedisco|scrivo)\s+[^.,;!?]+)",
        r"(ci\s+sentiamo\s+[^.,;!?]+)",
    ]
    for pat in commitment_patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            comm = match.group(1).strip()
            if comm and comm not in commitments:
                commitments.append(comm)

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
            for c in extracted.commitments:
                if c not in merged_commitments:
                    merged_commitments.append(c)
            extracted.commitments = merged_commitments

            # Merge topics
            merged_topics = list(primary.key_topics)
            for t in extracted.key_topics:
                if t not in merged_topics:
                    merged_topics.append(t)
            extracted.key_topics = merged_topics
            logger.info(f"Merged social entity with existing contact '{primary.person_name}' (ID: {primary.id})")
    except Exception as e:
        logger.warning(f"Social deduplication lookup failed: {e}")

    return extracted


def node_extract_social(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Stage 3A Social Recall Extractor.

    Extracts contact info and commitments, merges with existing records, and outputs social_data.
    """
    transcript = state.get("raw_transcript", "").strip()
    if not transcript:
        return {"social_data": None}

    # Fallback if mock_ai or missing provider credentials
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Extracting social entity via heuristic fallback (mock_ai or no credentials).")
        social = _heuristic_extract_social(transcript)
        if social:
            social = _deduplicate_and_merge(social)
        return {"social_data": social}

    try:
        extractor = _get_social_extractor()
        prompt = (
            f"Extract person encounter details, company/role, contact info, and promises made.\n\n"
            f"Transcript: \"{transcript}\""
        )
        messages = [
            SystemMessage(content=SOCIAL_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        result: Optional[SocialEntity] = extractor.invoke(messages)

        if result and result.person_name:
            if not result.timestamp:
                result.timestamp = datetime.now().isoformat()
            result = _deduplicate_and_merge(result)
            return {"social_data": result}
        else:
            return {"social_data": None}

    except Exception as e:
        logger.warning(f"Social extraction model failed: {e}. Falling back to heuristic.")
        social = _heuristic_extract_social(transcript)
        if social:
            social = _deduplicate_and_merge(social)
        return {"social_data": social}
