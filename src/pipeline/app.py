"""AWS Bedrock AgentCore Runtime Entrypoint for EXAMEN.

Wraps the LangGraph StateGraph inside a BedrockAgentCoreApp instance,
serving ambient speech insights and actions over the AgentCore microVM runtime.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from src.core.schemas import ExamenState
from src.ingestion.gatekeeper import classify_chunk
from src.pipeline.graph import pipeline_graph

logger = logging.getLogger("examen.pipeline.app")

app = BedrockAgentCoreApp()


def _build_summary(result_state: Dict[str, Any]) -> str:
    """Builds a human-readable summary of the actions and entities extracted."""
    summaries: List[str] = []

    action_data = result_state.get("action_data")
    if action_data:
        task_str = f" (linked task: {action_data.matched_task_id})" if action_data.matched_task_id else ""
        summaries.append(
            f"Verified completed action '{action_data.action_type}' in domain '{action_data.domain}'{task_str}"
        )

    social_data = result_state.get("social_data")
    if social_data:
        role_str = f" ({social_data.company_or_role})" if social_data.company_or_role else ""
        commitments_count = len(social_data.commitments)
        summaries.append(
            f"Social encounter recorded for {social_data.person_name}{role_str} with {commitments_count} commitment(s)"
        )

    briefing_report = result_state.get("briefing_report")
    if briefing_report:
        sources_count = len(briefing_report.web_sources)
        summaries.append(
            f"Technical briefing compiled on '{briefing_report.topic_title}' with {sources_count} web source(s)"
        )

    scheduled_task = result_state.get("scheduled_task")
    if scheduled_task:
        target_str = f" scheduled for {scheduled_task.scheduled_time}" if scheduled_task.scheduled_time else ""
        summaries.append(
            f"Ambient scheduled task recorded '{scheduled_task.title}' in domain '{scheduled_task.domain}'{target_str}"
        )

    if not summaries:
        return "No actionable signals extracted"

    return " ; ".join(summaries)


@app.entrypoint
def agent_invocation(payload: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Main AWS Bedrock AgentCore entrypoint for incoming agent requests.

    Args:
        payload: Dict containing incoming audio chunk or conversational prompt.
        context: BedrockAgentCoreContext / RequestContext provided by AWS runtime.

    Returns:
        Structured JSON dictionary containing processing status and extracted entities.
    """
    logger.info(f"AgentCore invocation received payload keys: {list(payload.keys())}")

    # 1. Transcript Resolution
    raw_val = (
        payload.get("raw_transcript")
        or payload.get("transcript_chunk")
        or payload.get("transcript")
        or payload.get("text")
        or payload.get("prompt")
        or payload.get("input")
        or payload.get("content")
        or payload.get("message")
        or payload.get("utterance")
        or ""
    )
    if isinstance(raw_val, dict):
        raw_transcript = str(raw_val.get("text") or raw_val.get("content") or "").strip()
    elif isinstance(raw_val, str):
        raw_transcript = raw_val.strip()
    else:
        raw_transcript = str(raw_val or "").strip()

    if not raw_transcript:
        logger.warning("AgentCore invocation received empty transcript or prompt.")
        return {
            "status": "noop",
            "session_id": payload.get("session_id") or str(uuid.uuid4()),
            "categories": ["noop"],
            "summary": "Empty transcript received",
            "action_data": None,
            "social_data": None,
            "briefing_report": None,
            "scheduled_task": None,
        }

    # 2. Session ID Resolution
    session_id = payload.get("session_id")
    if not session_id and context:
        session_id = getattr(context, "session_id", None)
        if not session_id and hasattr(context, "get_session_id"):
            try:
                session_id = context.get_session_id()
            except Exception:
                pass
    if not session_id:
        session_id = str(uuid.uuid4())

    # 3. Categories Resolution
    categories: Optional[List[str]] = payload.get("categories")
    confidence: float = float(payload.get("confidence", 1.0))
    summary_hint: str = str(payload.get("summary_hint", ""))

    # Ingress fallback: If invoked without pre-screening categories (e.g. direct AWS Console test)
    if not categories:
        logger.debug("Ingress payload lacks pre-screened categories; screening via Gatekeeper.")
        classification = classify_chunk(
            raw_transcript, prior_context=payload.get("historical_context")
        )
        categories = classification.categories
        confidence = classification.confidence
        summary_hint = classification.summary_hint

    # 4. Formulate strictly-typed ExamenState
    state: ExamenState = {
        "raw_transcript": raw_transcript,
        "session_id": session_id,
        "event_managed": bool(payload.get("event_managed", False)),
        "categories": categories,
        "confidence": confidence,
        "summary_hint": summary_hint,
        "timestamp": payload.get("timestamp") or datetime.now().isoformat(),
        "historical_context": payload.get("historical_context"),
        "location": payload.get("location"),
        "speaker": payload.get("speaker") or payload.get("speaker_id"),
        "speaker_role": payload.get("speaker_role"),
        "utterance_id": payload.get("utterance_id") or payload.get("chunk_id"),
    }

    # 5. Execute LangGraph StateGraph
    start_time = datetime.now()
    try:
        result_state: Dict[str, Any] = pipeline_graph.invoke(state)
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000.0
        try:
            from src.core.storage import get_storage_store
            get_storage_store().record_latency(
                event_type="agentcore_pipeline",
                latency_ms=elapsed_ms,
                model_id=None,
                details={"categories": categories, "session_id": session_id},
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"AgentCore pipeline execution failed: {e}", exc_info=True)
        return {
            "status": "error",
            "session_id": session_id,
            "categories": categories,
            "error": str(e),
            "summary": f"Pipeline execution error: {e}",
            "action_data": None,
            "social_data": None,
            "briefing_report": None,
            "scheduled_task": None,
        }

    # 6. Structured Output Serialization
    action_data = result_state.get("action_data")
    social_data = result_state.get("social_data")
    briefing_report = result_state.get("briefing_report")
    scheduled_task = result_state.get("scheduled_task")

    response: Dict[str, Any] = {
        "status": "success",
        "session_id": session_id,
        "categories": result_state.get("categories", categories),
        "summary": _build_summary(result_state),
        "action_data": action_data.model_dump() if action_data and hasattr(action_data, "model_dump") else action_data,
        "social_data": social_data.model_dump() if social_data and hasattr(social_data, "model_dump") else social_data,
        "briefing_report": briefing_report.model_dump() if briefing_report and hasattr(briefing_report, "model_dump") else briefing_report,
        "scheduled_task": scheduled_task.model_dump() if scheduled_task and hasattr(scheduled_task, "model_dump") else scheduled_task,
    }

    logger.info(f"AgentCore invocation completed for session {session_id}: {response['summary']}")
    return response


if __name__ == "__main__":
    app.run()
