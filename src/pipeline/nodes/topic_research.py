"""Topic Extraction & Deep Research Synthesizer node for EXAMEN (Stage 3C).

Executes multi-stage topic extraction, autonomous web research with query retry feedback,
and deep technical briefing synthesis using Claude 3.5 Sonnet / Nova Pro.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.models import (
    get_fast_model,
    get_reasoner_model,
    has_active_model_credentials,
)
from src.core.schemas import BriefingReport, ExamenState, TopicExtraction
from src.pipeline.tools.web_search import (
    SearchCache,
    WebSearchBatchResult,
    cache_key,
    execute_search_batch,
)

logger = logging.getLogger("examen.pipeline.topic_research")

TOPIC_EXTRACTOR_SYSTEM_PROMPT = """You are the Technical Topic Extractor for the EXAMEN wearable AI engine.
Your role is to analyze a transcribed audio snippet discussing engineering issues, libraries, system design, bugs, or academic lectures.
Extract:
1. topic_title: A concise title of the core technical topic, bug, library, or methodology (e.g. "Raft Consensus Algorithm", "Bedrock AgentCore Timeout").
2. context_type: One of "bug", "feature_discussion", "tech_stack", "academic_lecture", "system_incident", "general_meeting".
3. search_queries: 1 to 2 high-precision, focused web search queries to retrieve documentation, code patterns, or solutions.
   * STRICT CONSTRAINT: Never generate conversational sentences, questions, or transcript chunks as search queries.
   * Format queries as 2 to 5 targeted technical keywords (e.g. "Raft consensus leader election", "Bedrock AgentCore 504 gateway timeout").
   * Strip all discursive filler words (e.g. do not include "how to", "please find", "what is", "abbiamo parlato di", "spiegazione").
4. key_questions: 2 to 3 core questions or technical aspects to resolve in the final dossier.
"""

SYNTHESIZER_SYSTEM_PROMPT = """You are the Senior Technical Research Synthesizer and Executive Knowledge Assistant for the EXAMEN wearable AI engine.
Your mission is to compile an authoritative, high-density briefing report after an ambient meeting, technical discussion, or academic lecture.

CRITICAL INSTRUCTION FOR explanatory_synthesis:
Do NOT simply repeat conversational dialogue or transcripts.
Instead, act as a world-class domain expert. Synthesize a 2-3 paragraph cohesive, educational narrative that deeply explains and unpacks the core themes discussed, using the authoritative web search findings to fill all technical gaps.

ADAPT DEPTH AND PEDAGOGICAL TONE BASED ON context_type:
1. When context_type is "academic_lecture":
   - Explain the core theoretical foundations, key theorems, and conceptual models.
   - Provide intuitive analogies and practical illustrations so the reader thoroughly understands the mechanism.
   - Clarify academic terminology and historical or scientific context.

2. When context_type is "bug" or "system_incident":
   - Explain the underlying technical failure mode (memory leak, race condition, network timeout, cold-start).
   - Unpack why the error occurs in the software architecture based on official documentation and community findings.
   - Outline verified workarounds, configuration flags, or patch recommendations.

3. When context_type is "tech_stack" or "feature_discussion":
   - Detail the architectural trade-offs, scalability bottlenecks, and operational trade-offs.
   - Explain standard best practices, recommended libraries, and standard deployment patterns.

4. When context_type is "general_meeting":
   - Clarify industry concepts, strategic definitions, and the practical implications of decisions considered.

OUTPUT RULES:
- Write explanatory_synthesis with dense, professional clarity (2-3 structured, educational paragraphs).
- Structure deep_dive_markdown with clear headings, code snippets, and direct citations.
- Include 3-4 high-impact bullets in executive_summary.
- Provide concrete, pragmatic action_items.
- Keep the output clean, objective, and dense with verified technical details.
"""


def _get_fast_extractor():
    """Initializes fast model with structured output for topic extraction."""
    return get_fast_model().with_structured_output(TopicExtraction)


def _get_reasoner_synthesizer():
    """Initializes deep reasoning model with structured output for dossier synthesis."""
    return get_reasoner_model().with_structured_output(BriefingReport)


def _heuristic_extract_topic(transcript: str) -> TopicExtraction:
    """Heuristic extractor for offline tests, CI/CD, or API fallbacks."""
    text = transcript.strip()
    words = text.split()

    # Detect context type
    context_type = "tech_stack"
    lower_text = text.lower()
    if any(k in lower_text for k in ["outage", "incident", "down", "p0", "p1"]):
        context_type = "system_incident"
    elif any(k in lower_text for k in ["bug", "error", "leak", "crash", "issue", "exception", "failed"]):
        context_type = "bug"
    elif any(k in lower_text for k in ["feature", "proposal", "roadmap", "plan", "rfc"]):
        context_type = "feature_discussion"
    elif any(k in lower_text for k in ["lecture", "theory", "theorem", "paper", "professor", "class"]):
        context_type = "academic_lecture"
    elif any(k in lower_text for k in ["meeting", "agenda", "sync", "status", "alignment"]):
        context_type = "general_meeting"

    # Identify candidate topic title from capitalized entities or prominent tech keywords
    tech_keywords = [
        "Bedrock AgentCore", "LangGraph StateGraph", "LangGraph", "AWS Bedrock",
        "FastMCP", "DuckDuckGo Search", "DynamoDB", "SQLite FTS5", "Bee Wearable AI",
        "Docker", "Kubernetes", "OpenTelemetry", "Raft Consensus", "Raft Algorithm",
        "Raft", "Distributed Consensus", "Machine Learning", "Deep Learning",
        "Artificial Intelligence", "PostgreSQL", "Redis", "Kafka", "RabbitMQ",
        "Microservices", "REST API", "GraphQL"
    ]
    topic_title = None
    for kw in tech_keywords:
        if kw.lower() in lower_text:
            topic_title = kw
            break

    if not topic_title:
        # Filter out common conversational stopwords in Italian and English
        stopwords = {
            "oggi", "a", "lezione", "abbiamo", "parlato", "spiegato", "visto", "con",
            "il", "la", "i", "gli", "le", "un", "una", "uno", "per", "di", "da", "in",
            "su", "nel", "nella", "dei", "del", "della", "stiamo", "avendo", "problemi",
            "today", "in", "class", "we", "discussed", "talked", "about", "covered",
            "having", "issues", "with", "the", "a", "an", "is", "are", "was", "were",
        }
        content_words = [
            w.strip(".,;:?!'\"")
            for w in words
            if w.lower().strip(".,;:?!'\"") not in stopwords and len(w.strip(".,;:?!'\"")) > 2
        ]
        if content_words:
            topic_title = " ".join(content_words[:3]).title()
        else:
            topic_title = "Technical Discussion"

    # Formulate 1-2 search queries
    search_queries = [f"{topic_title} documentation best practices"]
    if context_type in ("bug", "system_incident"):
        search_queries.append(f"{topic_title} troubleshooting fix")

    key_questions = [
        f"What are the core architectural mechanisms of {topic_title}?",
        f"What are current production best practices and common pitfalls for {topic_title}?"
    ]

    return TopicExtraction(
        topic_title=topic_title,
        context_type=context_type,  # type: ignore[arg-type]
        search_queries=search_queries,
        key_questions=key_questions
    )


def _heuristic_synthesize_report(
    topic: TopicExtraction,
    transcript: str,
    search_batch: WebSearchBatchResult
) -> BriefingReport:
    """Deterministic report synthesizer for offline dev or fallback."""
    title = topic.topic_title
    exec_summary = [
        f"Evaluated key requirements and runtime architecture for {title}.",
        f"Retrieved {len(search_batch.source_urls)} authoritative external documentation sources.",
        f"Context verified from ambient transcript discussion.",
        "Concrete follow-up steps identified for implementation."
    ]

    # Generate contextual explanatory synthesis adapted to context_type
    if topic.context_type in ("bug", "system_incident"):
        explanatory_synthesis = (
            f"The discussion centered on an operational failure mode concerning {title}. "
            f"According to authoritative documentation and community troubleshooting guides, such runtime anomalies "
            f"frequently stem from configuration drift, resource lifecycle exhaustion, or unexpected thread contention. "
            f"Resolving these incidents requires inspecting log traces, applying idempotent backoff strategies, and verifying "
            f"dependency compatibility across active service tiers."
        )
    elif topic.context_type == "academic_lecture":
        explanatory_synthesis = (
            f"This session explored fundamental theoretical frameworks and conceptual principles underpinning {title}. "
            f"In foundational academic literature, the core mechanism relies on rigorous invariants, structured abstractions, "
            f"and analytical models governing state behavior. Understanding these foundational principles allows practitioners "
            f"to bridge theoretical proofs with real-world computational implementations."
        )
    else:  # tech_stack, feature_discussion, general_meeting
        explanatory_synthesis = (
            f"The architectural debate focused on evaluating {title} within modern distributed systems. "
            f"Authoritative research and engineering documentation demonstrate that adopting this approach involves key trade-offs between "
            f"operational complexity, end-to-end latency, and consistency guarantees. "
            f"Production best practices recommend establishing strict interface contracts, telemetry instrumentation, and staged rollouts "
            f"to maximize reliability and maintainability."
        )

    # Build deep dive markdown from search results and transcript
    doc_sections = []
    for ev in search_batch.evaluations:
        for r in ev.results:
            doc_sections.append(f"### [{r.title}]({r.url})\n{r.snippet}\n")

    docs_body = "\n".join(doc_sections) if doc_sections else "No external documentation was retrieved for this topic."

    deep_dive = f"""# {title} — Executive Technical Dossier

## 1. Overview & Architectural Context
Based on ambient audio discussion:
> "{transcript}"

The system initiated autonomous background research into **{title}** to consolidate authoritative architectural specifications, API usage patterns, and runtime constraints.

## 2. Verified Technical Documentation & Evidence
{docs_body}

## 3. Implementation Recommendations
- Maintain strict typing and schema validation using Pydantic V2.
- Integrate automated resilience checks and observability hooks for runtime evaluation.
- Review linked authoritative documentation sources prior to production deployment.
"""

    action_items = [
        f"Review documentation links for {title}.",
        "Implement proposed integration patterns in the staging environment.",
        "Verify latency benchmarks and error handling under peak load."
    ]

    return BriefingReport(
        topic_title=title,
        context_type=topic.context_type,
        executive_summary=exec_summary,
        explanatory_synthesis=explanatory_synthesis,
        deep_dive_markdown=deep_dive.strip(),
        web_sources=search_batch.source_urls,
        action_items=action_items,
        created_at=datetime.now().isoformat()
    )


# ---------------------------------------------------------------------------
# Reusable Stage 3C steps (shared by the LangGraph node and the Deep Topic Event Engine)
# ---------------------------------------------------------------------------

class EventOutline(BaseModel):
    """What is already known about the event a text belongs to (doc 03 §2)."""
    event_title: Optional[str] = None
    context_type: Optional[str] = None
    part_index: Optional[int] = None
    previous_parts: List[str] = Field(default_factory=list)
    key_points: List[str] = Field(default_factory=list)
    researched_queries: List[str] = Field(default_factory=list)

    def as_prompt(self) -> str:
        lines: List[str] = []
        if self.part_index:
            what = self.context_type.replace("_", " ") if self.context_type else "event"
            title = f" titled '{self.event_title}'" if self.event_title else ""
            lines.append(f"This text is part {self.part_index} of an ongoing {what}{title}.")
        if self.previous_parts:
            lines.append("Earlier parts covered: " + "; ".join(self.previous_parts) + ".")
        if self.key_points:
            lines.append("Key points so far: " + "; ".join(self.key_points[:10]) + ".")
        if self.researched_queries:
            lines.append(
                "Web queries already researched for this event (do NOT repeat them or trivial variants): "
                + "; ".join(self.researched_queries[:20]) + "."
            )
        return "\n".join(lines)


@dataclass
class SynthesisOutcome:
    briefing: BriefingReport
    research: List[Dict[str, Any]] = field(default_factory=list)  # [{"query": cache_key, "sources": [...]}]
    topic: Optional[TopicExtraction] = None


def _llm_available(provider: str) -> bool:
    return not settings.mock_ai and has_active_model_credentials(provider)


def extract_topics(
    text: str,
    *,
    outline: Optional[EventOutline] = None,
    max_queries: int = 2,
    gap_only: bool = False,
) -> TopicExtraction:
    """Step 1: topic, context type and focused search queries.

    gap_only: only propose queries for important concepts not covered by outline.researched_queries
              (consolidated event synthesis); an empty query list is a valid answer.
    """
    topic: Optional[TopicExtraction] = None
    if _llm_available(settings.gatekeeper_provider):
        try:
            context = outline.as_prompt() if outline else ""
            if gap_only:
                instruction = (
                    f"Identify the overall subject of this event from its partial briefings.\n"
                    f"Propose at most {max_queries} search queries ONLY for important concepts that the already "
                    f"researched queries do not cover. Return an empty search_queries list if coverage is sufficient."
                )
            else:
                instruction = (
                    f"Identify the technical topic, bug, or lecture subject discussed.\n"
                    f"Generate 1-{max_queries} focused search queries."
                )
            prompt = f"{instruction}\n\n{context}\n\nTranscript: \"{text}\"" if context else (
                f"{instruction}\n\nTranscript: \"{text}\""
            )
            topic = _get_fast_extractor().invoke([
                SystemMessage(content=TOPIC_EXTRACTOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
        except Exception as e:
            logger.warning(f"Topic extraction model failed: {e}. Falling back to heuristic.")
            topic = None
    else:
        logger.debug("Extracting topic via heuristic fallback (mock_ai or no credentials).")

    if not topic:
        topic = _heuristic_extract_topic(text)
    topic.search_queries = list(topic.search_queries or [])[:max_queries]
    return topic


def research(
    topic: TopicExtraction,
    text: str,
    *,
    outline: Optional[EventOutline] = None,
    cache: Optional[SearchCache] = None,
    allow_empty: bool = False,
) -> WebSearchBatchResult:
    """Step 2: web search with retry feedback. Queries the event already researched are served from the
    cache only (never re-hit the network)."""
    queries = list(topic.search_queries or [])
    if not queries and not allow_empty:
        queries = [topic.topic_title]
    if not queries:
        return execute_search_batch([])

    already = set(outline.researched_queries) if outline else set()
    logger.info(f"Executing web search for queries: {queries}")
    search_batch = execute_search_batch(queries, count_per_query=3, cache=cache, cache_only=already)

    if search_batch.needs_retry and search_batch.retry_feedback:
        logger.info("Initial web search yielded insufficient results. Triggering retry loop.")
        refined_query = None
        if _llm_available(settings.gatekeeper_provider):
            try:
                retry_prompt = (
                    f"Context transcript: \"{text[:2000]}\"\n\n"
                    f"{search_batch.retry_feedback}\n\n"
                    f"Please reformulate a higher-precision technical search query for topic '{topic.topic_title}'."
                )
                refined_topic: TopicExtraction = _get_fast_extractor().invoke([
                    SystemMessage(content=TOPIC_EXTRACTOR_SYSTEM_PROMPT),
                    HumanMessage(content=retry_prompt),
                ])
                if refined_topic and refined_topic.search_queries:
                    refined_query = refined_topic.search_queries[0]
            except Exception as e:
                logger.warning(f"Query reformulation prompt failed: {e}")

        if not refined_query:
            refined_query = f"{topic.topic_title} documentation"

        logger.info(f"Retrying web search with refined query: '{refined_query}'")
        second_batch = execute_search_batch([refined_query], count_per_query=3, cache=cache)
        if second_batch.has_satisfactory_results:
            search_batch = second_batch

    return search_batch


_KIND_INSTRUCTIONS = {
    "segment": (
        "EVENT PART BRIEFING: the transcript is one part of a longer event. Focus on what is new in this "
        "part; mention earlier parts only for continuity. Do not restart the explanation from scratch."
    ),
    "checkpoint": (
        "EVENT CHECKPOINT BRIEFING: the transcript is the latest stretch of an event that is still running. "
        "Focus on what is new in this stretch; mention earlier parts only for continuity."
    ),
    "final": (
        "CONSOLIDATED EVENT BRIEFING: the input contains the partial briefings (Part 1..N) of one whole event. "
        "Produce a single cohesive narrative that follows the order of the parts, merges overlapping points, "
        "and does not drop concepts from any part. The topic_title must describe the whole event."
    ),
}


def synthesize_briefing(
    text: str,
    topic: TopicExtraction,
    search_batch: WebSearchBatchResult,
    *,
    kind: str = "standalone",
    outline: Optional[EventOutline] = None,
) -> BriefingReport:
    """Step 3: deep synthesis with the reasoner model (heuristic fallback offline)."""
    report: Optional[BriefingReport] = None
    if _llm_available(settings.reasoner_provider):
        try:
            extra = ""
            if kind in _KIND_INSTRUCTIONS:
                extra = _KIND_INSTRUCTIONS[kind] + "\n"
                if outline:
                    extra += outline.as_prompt() + "\n"
            label = "Partial briefings of the event" if kind == "final" else "User discussion transcript"
            prompt = (
                f"{extra}\n{label}:\n\"{text}\"\n\n"
                f"Identified topic: '{topic.topic_title}' (Context: {topic.context_type})\n"
                f"Key questions to address: {', '.join(topic.key_questions)}\n\n"
                f"Retrieved Web Documentation:\n{search_batch.formatted_markdown}\n\n"
                f"Synthesize an Executive Briefing Report with detailed technical markdown."
            )
            report = _get_reasoner_synthesizer().invoke([
                SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            if report:
                if not report.web_sources:
                    report.web_sources = search_batch.source_urls
                if not report.deep_dive_markdown or len(report.deep_dive_markdown.strip()) < 10:
                    report.deep_dive_markdown = _heuristic_synthesize_report(topic, text, search_batch).deep_dive_markdown
                if not report.explanatory_synthesis:
                    report.explanatory_synthesis = _heuristic_synthesize_report(topic, text, search_batch).explanatory_synthesis
        except Exception as e:
            logger.warning(f"Briefing synthesis model failed: {e}. Falling back to heuristic.")
            report = None
    else:
        logger.debug("Synthesizing briefing report via heuristic fallback (mock_ai or no credentials).")

    if not report:
        report = _heuristic_synthesize_report(topic, text, search_batch)
    report.kind = kind  # type: ignore[assignment]
    return report


def condense_transcript(text: str, max_words: int, block_words: int = 1500) -> str:
    """Keeps long transcripts within budget: older blocks become dense notes (fast model), the most
    recent block stays verbatim (doc 03 §2.1)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    blocks = [" ".join(words[i:i + block_words]) for i in range(0, len(words), block_words)]
    notes: List[str] = []
    for idx, block in enumerate(blocks[:-1], 1):
        summary = None
        if _llm_available(settings.gatekeeper_provider):
            try:
                result = get_fast_model().invoke([
                    SystemMessage(content=(
                        "Condense this lecture/meeting transcript block into dense factual notes (max 150 words). "
                        "Keep definitions, formulas, names, numbers and decisions. No preamble."
                    )),
                    HumanMessage(content=block),
                ])
                summary = str(getattr(result, "content", "") or "").strip() or None
            except Exception as e:
                logger.warning(f"Transcript condensation failed on block {idx}: {e}")
        if not summary:
            summary = " ".join(block.split()[:150]) + " …"
        notes.append(f"[Notes block {idx}] {summary}")
    return "\n".join(notes) + f"\n[Latest block, verbatim] {blocks[-1]}"


def research_entries(search_batch: WebSearchBatchResult) -> List[Dict[str, Any]]:
    """Ledger entries for the queries that returned results (cache hits included). Failed queries are
    left out so a later segment may retry them (e.g. after a transient captcha/rate limit)."""
    entries = []
    for ev in search_batch.evaluations:
        if not ev.results:
            continue
        entries.append({
            "query": cache_key(ev.normalized_query or ev.query),
            "sources": [r.url for r in ev.results],
        })
    return entries


_MICRO_EVENT_LABELS = {
    "action": "Verified actions",
    "social_contact": "Contacts encountered",
    "task_scheduled": "Scheduled tasks",
    "social_commitment": "Commitments",
}


def append_micro_events_section(report: BriefingReport, micro_events: List[Any]) -> BriefingReport:
    """Adds the deterministic 'During this event' section (doc 03 §3) to a consolidated briefing."""
    if not micro_events:
        return report
    grouped: Dict[str, List[str]] = {}
    for ref in micro_events:
        event_type = getattr(ref, "event_type", None) or (ref.get("event_type") if isinstance(ref, dict) else None)
        headline = getattr(ref, "headline", None) or (ref.get("headline") if isinstance(ref, dict) else None)
        if event_type and headline:
            grouped.setdefault(event_type, []).append(headline)
    if not grouped:
        return report
    lines = ["", "## During this event"]
    for event_type, headlines in grouped.items():
        lines.append(f"### {_MICRO_EVENT_LABELS.get(event_type, event_type)}")
        lines.extend(f"- {h}" for h in headlines)
    report.deep_dive_markdown = (report.deep_dive_markdown or "").rstrip() + "\n" + "\n".join(lines)
    return report


class PipelineEventSynthesizer:
    """Default synthesizer of the Deep Topic Event Engine: segment/checkpoint and consolidated final
    briefings with event context, research reuse (ledger + cache) and long-transcript condensation."""

    def __init__(self, store_getter: Callable[[], Any], max_words: int = 6000):
        self._store_getter = store_getter
        self.max_words = max_words

    def _cache(self) -> SearchCache:
        return SearchCache(self._store_getter(), ttl_seconds=settings.web_search_cache_ttl_seconds)

    def segment(
        self, text: str, session_id: str, outline: Optional[EventOutline] = None, kind: str = "segment"
    ) -> SynthesisOutcome:
        condensed = condense_transcript(text, self.max_words)
        topic = extract_topics(condensed, outline=outline, max_queries=3)
        batch = research(topic, condensed, outline=outline, cache=self._cache())
        report = synthesize_briefing(condensed, topic, batch, kind=kind, outline=outline)
        return SynthesisOutcome(briefing=report, research=research_entries(batch), topic=topic)

    def final(
        self,
        parts: List[BriefingReport],
        extra_text: str,
        session_id: str,
        outline: Optional[EventOutline] = None,
        micro_events: Optional[List[Any]] = None,
    ) -> SynthesisOutcome:
        sections: List[str] = []
        for idx, part in enumerate(parts, 1):
            bullets = " ".join(part.executive_summary)
            sections.append(f"Part {idx}: {part.topic_title}\nSummary: {bullets}\nNarrative: {part.explanatory_synthesis}")
        if extra_text.strip():
            label = "Additional transcript (not covered by part briefings)" if parts else "Transcript"
            sections.append(f"{label}: {condense_transcript(extra_text, self.max_words)}")
        text = "\n\n".join(sections)

        if parts:
            # Gap research only: concepts the parts already researched are not searched again
            topic = extract_topics(text, outline=outline, max_queries=2, gap_only=True)
            batch = research(topic, text, outline=outline, cache=self._cache(), allow_empty=True)
        else:
            topic = extract_topics(text, outline=outline, max_queries=2)
            batch = research(topic, text, outline=outline, cache=self._cache())

        report = synthesize_briefing(text, topic, batch, kind="final", outline=outline)
        merged_sources: List[str] = []
        for url in [u for p in parts for u in p.web_sources] + list(report.web_sources) + batch.source_urls:
            if url and url not in merged_sources:
                merged_sources.append(url)
        report.web_sources = merged_sources
        append_micro_events_section(report, micro_events or [])
        return SynthesisOutcome(briefing=report, research=research_entries(batch), topic=topic)


def node_topic_research(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Stage 3C Deep Research & Briefing Synthesizer (standalone invocation).

    Executes topic extraction, autonomous web search with retry feedback, and dossier synthesis.
    """
    transcript = state.get("raw_transcript", "").strip()
    if not transcript:
        return {"topic_extracted": None, "briefing_report": None}

    topic = extract_topics(transcript, max_queries=2)
    search_batch = research(topic, transcript)
    report = synthesize_briefing(transcript, topic, search_batch, kind="standalone")
    return {
        "topic_extracted": topic,
        "briefing_report": report
    }
