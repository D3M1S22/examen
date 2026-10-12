"""Topic Extraction & Deep Research Synthesizer node for EXAMEN (Stage 3C).

Executes multi-stage topic extraction, autonomous web research with query retry feedback,
and deep technical briefing synthesis using Claude 3.5 Sonnet / Nova Pro.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.models import (
    get_fast_model,
    get_reasoner_model,
    has_active_model_credentials,
)
from src.core.schemas import BriefingReport, ExamenState, TopicExtraction
from src.pipeline.tools.web_search import (
    execute_search_batch,
    WebSearchBatchResult,
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


def node_topic_research(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Stage 3C Deep Research & Briefing Synthesizer.

    Executes topic extraction, autonomous web search with retry feedback, and dossier synthesis.
    """
    transcript = state.get("raw_transcript", "").strip()
    if not transcript:
        return {"topic_extracted": None, "briefing_report": None}

    # --- Step 1: Topic Extraction ---
    topic: Optional[TopicExtraction] = None
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Extracting topic via heuristic fallback (mock_ai or no credentials).")
        topic = _heuristic_extract_topic(transcript)
    else:
        try:
            fast_extractor = _get_fast_extractor()
            extract_prompt = (
                f"Identify the technical topic, bug, or lecture subject discussed.\n"
                f"Generate 1-2 focused search queries.\n\n"
                f"Transcript: \"{transcript}\""
            )
            messages = [
                SystemMessage(content=TOPIC_EXTRACTOR_SYSTEM_PROMPT),
                HumanMessage(content=extract_prompt),
            ]
            topic = fast_extractor.invoke(messages)
        except Exception as e:
            logger.warning(f"Topic extraction model failed: {e}. Falling back to heuristic.")
            topic = _heuristic_extract_topic(transcript)

    if not topic:
        topic = _heuristic_extract_topic(transcript)

    # --- Step 2: Autonomous Web Search with Retry Loop ---
    queries = topic.search_queries if topic.search_queries else [topic.topic_title]
    logger.info(f"Executing web search for queries: {queries}")
    search_batch = execute_search_batch(queries, count_per_query=3)

    # Retry loop: if search yielded no satisfactory results and needs_retry is True
    if search_batch.needs_retry and search_batch.retry_feedback:
        logger.info(f"Initial web search yielded insufficient results. Triggering retry loop.")
        refined_query = None

        if not settings.mock_ai and has_active_model_credentials(settings.gatekeeper_provider):
            try:
                fast_extractor = _get_fast_extractor()
                retry_prompt = (
                    f"Context transcript: \"{transcript}\"\n\n"
                    f"{search_batch.retry_feedback}\n\n"
                    f"Please reformulate a higher-precision technical search query for topic '{topic.topic_title}'."
                )
                refined_topic: TopicExtraction = fast_extractor.invoke([
                    SystemMessage(content=TOPIC_EXTRACTOR_SYSTEM_PROMPT),
                    HumanMessage(content=retry_prompt),
                ])
                if refined_topic and refined_topic.search_queries:
                    refined_query = refined_topic.search_queries[0]
            except Exception as e:
                logger.warning(f"Query reformulation prompt failed: {e}")

        if not refined_query:
            # Clean fallback query focusing purely on topic title
            refined_query = f"{topic.topic_title} documentation"

        logger.info(f"Retrying web search with refined query: '{refined_query}'")
        second_batch = execute_search_batch([refined_query], count_per_query=3)
        if second_batch.has_satisfactory_results:
            search_batch = second_batch

    # --- Step 3: Deep Synthesis with Reasoner Model ---
    report: Optional[BriefingReport] = None
    if settings.mock_ai or not has_active_model_credentials(settings.reasoner_provider):
        logger.debug("Synthesizing briefing report via heuristic fallback (mock_ai or no credentials).")
        report = _heuristic_synthesize_report(topic, transcript, search_batch)
    else:
        try:
            synthesizer = _get_reasoner_synthesizer()
            prompt = (
                f"User discussion transcript:\n\"{transcript}\"\n\n"
                f"Identified topic: '{topic.topic_title}' (Context: {topic.context_type})\n"
                f"Key questions to address: {', '.join(topic.key_questions)}\n\n"
                f"Retrieved Web Documentation:\n{search_batch.formatted_markdown}\n\n"
                f"Synthesize an Executive Briefing Report with detailed technical markdown."
            )
            messages = [
                SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            report = synthesizer.invoke(messages)
            # Ensure web sources, deep dive markdown, and explanatory synthesis are populated
            if report:
                if not report.web_sources:
                    report.web_sources = search_batch.source_urls
                if not report.deep_dive_markdown or len(report.deep_dive_markdown.strip()) < 10:
                    heuristic = _heuristic_synthesize_report(topic, transcript, search_batch)
                    report.deep_dive_markdown = heuristic.deep_dive_markdown
                if not report.explanatory_synthesis:
                    heuristic = _heuristic_synthesize_report(topic, transcript, search_batch)
                    report.explanatory_synthesis = heuristic.explanatory_synthesis
        except Exception as e:
            logger.warning(f"Briefing synthesis model failed: {e}. Falling back to heuristic.")
            report = _heuristic_synthesize_report(topic, transcript, search_batch)

    if not report:
        report = _heuristic_synthesize_report(topic, transcript, search_batch)

    return {
        "topic_extracted": topic,
        "briefing_report": report
    }
