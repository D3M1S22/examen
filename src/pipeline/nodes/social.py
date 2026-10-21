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
from src.pipeline.nodes.scheduler import parse_reference_time, parse_relative_time_expression
from src.core.service_log import model_fallback

logger = logging.getLogger("examen.pipeline.social")

SOCIAL_SYSTEM_PROMPT = """You are the Social Recall Extractor for the EXAMEN ambient wearable AI engine.
Your role is to analyze a transcribed audio snippet and extract details regarding personal or professional encounters:
1. Person Name: Full name or first name of the person encountered or introduced.
2. Company or Role: Job title, organization, or affiliation ONLY (e.g. "Cloud Architect at AWS", "Tech Lead at Acme", "42").
   - Strip conversational prepositions ("della 42" -> "42", "presso Acme" -> "Acme").
   - Do NOT include conversational clauses or personal commentary (e.g. "della 42, ultimamente mi occupo di AI" -> company_or_role must be strictly "42").
   - Extract mentioned technologies, topics, or fields (e.g. "AI", "Machine Learning") into Key Topics, NOT into Company or Role.
3. Contact Info: Email, phone, or handle if explicitly shared.
4. Website URL: Detect any spoken or verbalized website, portfolio, or personal page URL and normalize it into a canonical HTTPS URL.
   Transcriptions come from natural speech, so URLs will appear as spoken phrases, NOT formatted links.
   Examples of spoken URL patterns and their canonical forms:
     * "il mio sito è mariorossi punto dev" -> "https://mariorossi.dev"
     * "puoi vedere i miei lavori su lucabianchi punto it" -> "https://lucabianchi.it"
     * "my portfolio is at alexsmith dot io" -> "https://alexsmith.io"
     * "vai su github punto com slash dev-alex" -> "https://github.com/dev-alex"
     * "trovi tutto su w w w punto example punto com" -> "https://www.example.com"
   If a website is detected, store the normalized URL in website_url.
5. Commitments: Explicit bilateral promises or obligations agreed upon. For each commitment:
   - debtor: 'user' if the user promised the contact ('user'), OR 'contact' if the contact promised the user ('contact').
   - description: Concrete action or deliverable promised.
   - due_date_raw: The relative or absolute time constraint mentioned (e.g. 'tomorrow at 10 AM', 'by Friday') or null.
   - status: 'open'.
6. Key Topics: Salient technical or business topics discussed (e.g. ["AgentCore", "Kubernetes", "AI", "Machine Learning"]).

RULES:
- Do NOT hallucinate names or commitments not grounded in the text.
- If no clear person or introduction is detected, return null.
- Extract commitments as concise action statements.
- Multilingual capability: Support Italian introductions and roles (e.g. "ciao sono francesco faccio il sales assistant per una big 3" -> Person Name: "Francesco", Company or Role: "Sales Assistant at Big 3").
"""


def sanitize_company_or_role(raw_role: Optional[str]) -> Optional[str]:
    """Strips conversational prepositions and trailing discursive clauses from role strings.

    Examples:
        'della 42, ultimamente mi sto occupando di Ai e Machine Learning' -> '42'
        'at AWS' -> 'AWS'
        'presso Google' -> 'Google'
        'Cloud Architect at Cyberdyne' -> 'Cloud Architect at Cyberdyne'
    """
    if not raw_role or not isinstance(raw_role, str):
        return None
    role = raw_role.strip()
    if not role:
        return None

    # Cut off at conversational clauses or secondary commentary
    role = re.split(
        r",?\s*(?:ultimamente|attualmente|attivo su|occupando di|mi occupo|lavoro su|working on|dealing with|specializing in|focusing on)",
        role,
        flags=re.IGNORECASE,
    )[0].strip()

    # Strip leading prepositions: "della 42" -> "42", "presso Google" -> "Google", "di Acme" -> "Acme", "at AWS" -> "AWS"
    role = re.sub(
        r"^(?:della|dello|del|dei|degli|di|da|presso|at|from)\s+",
        "",
        role,
        flags=re.IGNORECASE,
    ).strip()

    # Clean trailing punctuation
    role = role.strip(" ,.-:;")
    return role if len(role) >= 2 else None


def _get_social_extractor():
    """Initializes model with structured output for social entity extraction."""
    return get_fast_model().with_structured_output(SocialEntity)


def extract_verbalized_urls(text: str) -> Optional[str]:
    """Heuristic spoken URL normalizer for offline/mock modes.

    Converts verbalized URL patterns from speech transcription into
    canonical HTTPS URLs.

    Examples:
        'mariorossi punto dev' -> 'https://mariorossi.dev'
        'github dot com slash alex' -> 'https://github.com/alex'
        'w w w punto example punto it' -> 'https://www.example.it'
    """
    t = text.lower()
    # Normalize spoken URL delimiters
    t = re.sub(r'\bw\s+w\s+w\b', 'www', t)
    t = re.sub(r'\s+punto\s+', '.', t)
    t = re.sub(r'\s+dot\s+', '.', t)
    t = re.sub(r'\s+slash\s+', '/', t)
    t = re.sub(r'\s+trattino\s+', '-', t)
    t = re.sub(r'\s+dash\s+', '-', t)
    # Try to find a domain-like pattern
    m = re.search(
        r'(?:https?://)?(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9_\-]*\.(?:com|it|io|dev|org|net|ai|me|eu|co|tech)(?:/[^\s,;!?]*)?)',
        t
    )
    if m:
        url = m.group(0).strip().rstrip('.')
        if not url.startswith('http'):
            url = f'https://{url}'
        return url
    return None


def _heuristic_extract_social(
    transcript: str,
    historical_context: Optional[str] = None,
    speaker_role: Optional[str] = None,
    ref_dt: Optional[datetime] = None,
) -> Optional[SocialEntity]:
    """Deterministic heuristic extractor for offline dev, testing, or API fallbacks."""
    text = transcript.strip()
    if not text:
        return None

    if isinstance(historical_context, list):
        historical_context = " ".join(
            (item.get("text", "") if isinstance(item, dict) else str(item))
            for item in historical_context
        )

    # Name and role patterns
    # e.g. "Hi, I'm Luca Rossi, Cloud Architect at AWS. I'll send you the whitepaper tomorrow."
    # e.g. "Nice to meet you, my name is Sarah Connor from Cyberdyne Systems."
    # e.g. "Piacere, sono Marco Bianchi, CTO di Acme."
    name_patterns = [
        r"(?:i am|i['’]m|my name is|this is|sono|mi chiamo)\s+(?:(?:dr\.|prof\.|mr\.|ms\.|mrs\.)\s+)?([A-Za-z]+(?:\s+(?:de|di|del|della|van|von|da)\s+[A-Za-z]+|\s+[A-Za-z]+)?)",
        r"(?:nice to meet you|pleased to meet you|great to meet you|piacere di conoscerti|piacere),?\s+(?:(?:dr\.|prof\.|mr\.|ms\.|mrs\.)\s+)?([A-Za-z]+(?:\s+(?:de|di|del|della|van|von|da)\s+[A-Za-z]+|\s+[A-Za-z]+)?)",
        r"(?:meet|with|incontrato)\s+(?!you\b|me\b|us\b|them\b|him\b|her\b)(?:(?:dr\.|prof\.|mr\.|ms\.|mrs\.)\s+)?([A-Za-z]+(?:\s+(?:de|di|del|della|van|von|da)\s+[A-Za-z]+|\s+[A-Za-z]+)?)",
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
    m_it_role = re.search(r"(?:faccio il|faccio la|lavoro come|lavoro per|lavoro in|lavoro da)\s+([A-Za-z0-9\s_\-\.]+)", text, re.IGNORECASE)
    if m_it_role:
        company_or_role = m_it_role.group(1).strip()
    else:
        m_role = re.search(r"(?:,\s*|\s+)(?:a\s+|an\s+)?([A-Za-z\s]+(?:Architect|Lead|Engineer|Director|Manager|CTO|CEO|Founder|Researcher|Assistant|Consultant|Developer)\s*(?:at|di|in|per)?\s*[A-Za-z0-9_\-\.\s]*)", text, re.IGNORECASE)
        if m_role:
            company_or_role = m_role.group(1).strip()
        else:
            m_co = re.search(r"(?:at|di|presso|from|della|del)\s+([A-Za-z0-9_\-\.]+)", text, re.IGNORECASE)
            if m_co:
                company_or_role = m_co.group(1).strip()
            elif historical_context:
                m_hist_role = re.search(r"(?:,\s*|\s+)(?:a\s+|an\s+)?([A-Za-z\s]+(?:Architect|Lead|Engineer|Director|Manager|CTO|CEO|Founder|Researcher)\s*(?:at|di|in)?\s*[A-Za-z0-9_\-\.]*)", historical_context, re.IGNORECASE)
                if m_hist_role:
                    company_or_role = m_hist_role.group(1).strip()
                else:
                    m_hist_co = re.search(r"(?:at|di|presso|from|della|del)\s+([A-Za-z0-9_\-\.]+)", historical_context, re.IGNORECASE)
                    if m_hist_co:
                        company_or_role = m_hist_co.group(1).strip()

    company_or_role = sanitize_company_or_role(company_or_role)

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
            norm_iso, raw_time = parse_relative_time_expression(comm_desc, ref_dt)
            if not raw_time:
                norm_iso, raw_time = parse_relative_time_expression(text, ref_dt)
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
            norm_iso, raw_time = parse_relative_time_expression(comm_desc, ref_dt)
            if not raw_time:
                norm_iso, raw_time = parse_relative_time_expression(text, ref_dt)
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
        "Python", "Alexa", "MCP", "AI", "Agent", "Architecture", "Microservices",
        "Machine Learning", "Deep Learning", "Data Science", "Cloud", "Raft", "Distributed Systems"
    ]
    for kw in tech_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
            topics.append(kw)

    # Extract contact info (email / phone)
    contact_info = None
    m_email = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    if m_email:
        contact_info = m_email.group(0)

    # Extract spoken website URL (heuristic fallback for mock/offline mode)
    spoken_url = extract_verbalized_urls(text)
    if not spoken_url and historical_context:
        spoken_url = extract_verbalized_urls(historical_context)

    return SocialEntity(
        person_name=person_name,
        company_or_role=company_or_role,
        contact_info=contact_info,
        website_url=spoken_url,
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

            # Homonym check: if both have explicit but conflicting organizations, do not merge!
            if primary.company_or_role and extracted.company_or_role:
                p_words = set(re.findall(r"\w+", primary.company_or_role.lower()))
                e_words = set(re.findall(r"\w+", extracted.company_or_role.lower()))
                stopwords = {
                    "presso", "from", "with", "lead", "engineer", "officer", "manager",
                    "director", "specialist", "head", "dell", "della", "chief", "senior", "junior"
                }
                p_meaningful = {w for w in p_words if len(w) > 2 and w not in stopwords}
                e_meaningful = {w for w in e_words if len(w) > 2 and w not in stopwords}
                if p_meaningful and e_meaningful and not (p_meaningful & e_meaningful):
                    logger.info(
                        f"Detected homonym for '{extracted.person_name}': existing '{primary.company_or_role}' "
                        f"vs new '{extracted.company_or_role}'. Storing as distinct contact."
                    )
                    return extracted

            # Merge ID
            extracted.id = primary.id
            if not extracted.company_or_role and primary.company_or_role:
                extracted.company_or_role = primary.company_or_role
            if not extracted.contact_info and primary.contact_info:
                extracted.contact_info = primary.contact_info

            # Merge website_url: conversational URL has absolute priority
            if not extracted.website_url and primary.website_url:
                extracted.website_url = primary.website_url

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

            # Merge web profile, propagating conversational website if available
            if not extracted.web_profile and primary.web_profile:
                extracted.web_profile = primary.web_profile
            if extracted.web_profile and extracted.website_url and not extracted.web_profile.website_url:
                extracted.web_profile.website_url = extracted.website_url

            logger.info(f"Merged social entity with existing contact {primary.id}")
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
    # Relative deadlines ("tomorrow", "by Friday") are anchored on the utterance time
    ref_dt = parse_reference_time(state.get("timestamp"))

    # Fallback if mock_ai or missing provider credentials
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Extracting social entity via heuristic fallback (mock_ai or no credentials).")
        social = _heuristic_extract_social(
            transcript, historical_context=historical_context, speaker_role=speaker_role, ref_dt=ref_dt
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
            result.company_or_role = sanitize_company_or_role(result.company_or_role)
            # Always ground the timestamp on ingestion time: the LLM has no clock and hallucinates dates
            result.timestamp = state.get("timestamp") or datetime.now().isoformat()

            if location and not result.location_encountered and location.get("place_name"):
                result.location_encountered = location.get("place_name")

            # If LLM left commitments empty, supplement with heuristic extraction
            if not result.commitments:
                h_social = _heuristic_extract_social(
                    transcript, historical_context=historical_context, speaker_role=speaker_role, ref_dt=ref_dt
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
                    norm_iso, raw_time = parse_relative_time_expression(probe_text, ref_dt)
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
        model_fallback(logger, "social", e)
        social = _heuristic_extract_social(
            transcript, historical_context=historical_context, speaker_role=speaker_role, ref_dt=ref_dt
        )
        if social:
            if location and not social.location_encountered and location.get("place_name"):
                social.location_encountered = location.get("place_name")
            social = _deduplicate_and_merge(social)
            social = _enrich_if_qualified(social)
        return {"social_data": social}

