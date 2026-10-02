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
1. topic_title: A concise title of the core technical topic, bug, library, or methodology.
2. context_type: One of "bug", "feature_discussion", "tech_stack", "academic_lecture".
3. search_queries: 1 to 2 high-precision, focused web search queries to retrieve documentation, code patterns, or solutions.
   * Strip conversational words (e.g. do not include "how to", "please find", "what is").
   * Focus on distinctive library names, error messages, or architectural keywords.
4. key_questions: 2 to 3 core questions or technical aspects to resolve in the final dossier.
"""

SYNTHESIZER_SYSTEM_PROMPT = """You are the Senior Technical Research Synthesizer for the EXAMEN engine on AWS Bedrock.
You synthesize authoritative, high-density Executive Briefings and Technical Dossiers for engineers and Echo Show multimodal displays.

INSTRUCTIONS:
1. Synthesize an Executive Summary in 3-4 high-impact bullet points.
2. In deep_dive_markdown, provide a thorough, production-grade technical breakdown with:
   - Clear architectural definitions and mechanism explanations.
   - Code snippets, CLI commands, or configuration examples where appropriate.
   - Direct citations to consulted web sources using markdown links.
3. List actionable next steps in action_items.
4. Keep the output clean, objective, and dense with verified technical details.
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
    if any(k in lower_text for k in ["bug", "error", "leak", "crash", "issue", "exception", "failed"]):
        context_type = "bug"
    elif any(k in lower_text for k in ["feature", "proposal", "roadmap", "plan", "rfc"]):
        context_type = "feature_discussion"
    elif any(k in lower_text for k in ["lecture", "theory", "theorem", "paper", "professor", "class"]):
        context_type = "academic_lecture"

    # Identify candidate topic title from capitalized entities or prominent tech keywords
    tech_keywords = [
        "Bedrock AgentCore", "LangGraph StateGraph", "LangGraph", "AWS Bedrock",
        "FastMCP", "DuckDuckGo Search", "DynamoDB", "SQLite FTS5", "Bee Wearable AI",
        "Docker", "Kubernetes", "OpenTelemetry"
    ]
    topic_title = None
    for kw in tech_keywords:
        if kw.lower() in lower_text:
            topic_title = kw
            break

    if not topic_title:
        # Fallback to first 4-5 words as title
        topic_title = " ".join(words[:4]).title() if len(words) >= 4 else "Technical Discussion"

    # Formulate 1-2 search queries
    search_queries = [f"{topic_title} documentation best practices"]
    if context_type == "bug":
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
            # Ensure web sources are populated from real search results
            if report and not report.web_sources:
                report.web_sources = search_batch.source_urls
        except Exception as e:
            logger.warning(f"Briefing synthesis model failed: {e}. Falling back to heuristic.")
            report = _heuristic_synthesize_report(topic, transcript, search_batch)

    if not report:
        report = _heuristic_synthesize_report(topic, transcript, search_batch)

    return {
        "topic_extracted": topic,
        "briefing_report": report
    }
