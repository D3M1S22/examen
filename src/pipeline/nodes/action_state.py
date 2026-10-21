"""Action-State Verifier node for the EXAMEN pipeline (Stage 3B).

Extracts and verifies first-person completed domestic safety routines,
personal habits, and work tasks. Strictly filters out doubts and future intentions.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from src.core.config import settings
from src.core.models import get_fast_model, has_active_model_credentials
from src.core.schemas import ExamenState, PlannedTask, VerifiedAction
from src.core.storage import get_storage_store
from src.core.service_log import model_fallback

logger = logging.getLogger("examen.pipeline.action_state")

ACTION_SYSTEM_PROMPT = """You are the Action-State Verifier for the EXAMEN ambient wearable AI engine.
Your role is to analyze a transcribed audio snippet and determine whether the speaker has EXPLICITLY CONFIRMED a completed action regarding:
1. Domestic safety (e.g., turning off stove/oven, unplugging clothes iron, locking the front door, closing windows).
2. Personal routines (e.g., taking daily medication/vitamins, feeding pets, taking out the trash).
3. Completed work tasks (e.g., merging a pull request, deploying a service, sending a key email).

CRITICAL VERACITY AND NEGATIVE FILTER RULES:
- The statement MUST be a confirmed, completed action spoken in the first person (e.g., "I just turned off the stove", "The iron is unplugged, verified", "I took my blood pressure medication", "Merged the PR").
- STRICTLY REJECT doubts, questions, or future intentions:
  * "I should remember to turn off the stove" -> REJECT (return null or confidence < 0.5)
  * "Did I lock the door?" -> REJECT
  * "I need to take my pills later tonight" -> REJECT
  * "I'm going to deploy the build tomorrow" -> REJECT
- Output a normalized action_type in snake_case (e.g., "stove_off", "iron_unplugged", "door_locked", "medication_taken", "pr_merged", "build_deployed").
- Assign a domain: "safety", "routine", or "work_task".
- Set confidence to >= 0.85 only when completion is explicitly stated.
"""


def build_action_prompt(pending_tasks: Optional[List[PlannedTask]] = None) -> str:
    """Builds the Action Verifier system prompt, dynamically appending active pending tasks."""
    if not pending_tasks:
        return ACTION_SYSTEM_PROMPT

    task_lines = []
    for t in pending_tasks:
        task_lines.append(f'- [Task ID: "{t.id}"] Title: "{t.title}" (Domain: {t.domain})')

    if not task_lines:
        return ACTION_SYSTEM_PROMPT

    tasks_section = f"""

ACTIVE SCHEDULED / PLANNED TASKS TO WATCH FOR:
The user has scheduled the following specific tasks and is expecting verification:
{chr(10).join(task_lines)}

PRIORITY MATCHING INSTRUCTIONS:
1. If the transcript confirms completion of ANY scheduled task listed above:
   - Set `matched_task_id` to that exact Task ID string.
   - Set `action_type` to a normalized snake_case label matching the task (e.g., "bedroom_window_closed", "heater_off").
   - Inherit the `domain` from the scheduled task.
   - Set `confidence` >= 0.90 even if expressed informally.
2. If the transcript confirms a completed action that is NOT in the scheduled list:
   - Extract it normally.
   - Set `matched_task_id = null`.
"""
    return ACTION_SYSTEM_PROMPT + tasks_section


def _get_action_extractor():
    """Initializes model with structured output for action verification."""
    return get_fast_model().with_structured_output(VerifiedAction)


def _heuristic_extract_action(
    transcript: str,
    pending_tasks: Optional[List[PlannedTask]] = None,
    historical_context: Optional[str] = None,
) -> Optional[VerifiedAction]:
    """Deterministic heuristic extractor for offline dev, testing, or API fallbacks."""
    text = transcript.lower().strip()
    if not text:
        return None

    if isinstance(historical_context, list):
        historical_context = " ".join(
            (item.get("text", "") if isinstance(item, dict) else str(item))
            for item in historical_context
        )

    # Strict doubt & future intention filter
    doubt_patterns = [
        r"\b(should remember|need to remember|need to|have to|did i|wonder if)\b",
        r"\b(supposed to|planning to|going to|thinking of|tomorrow|later on|later today|later tonight)\b",
        r"\b(devo ricordarmi|dovrei ricordarmi|ho spento|avrò spento|chissà se|devo staccare|più tardi|domani)\b",
    ]
    if any(re.search(pat, text) for pat in doubt_patterns):
        logger.debug("Action extraction discarded due to doubt/future intent")
        return None

    # 1. Match against active scheduled/pending tasks if provided
    if pending_tasks:
        completion_signals = [
            r"\b(done|finished|completed|checked|verified|unplugged|turned off|switched off|shut|locked|closed|took|taken|preso|chiuso|spento|staccato|fatto)\b",
            r"\b(i did|we did|it's done|all done|taken care of|is done|are done|ho fatto|è fatto)\b"
        ]
        has_completion_signal = any(re.search(pat, text) for pat in completion_signals)

        stop_words = {"the", "and", "for", "with", "this", "that", "from", "into", "over", "take", "make", "turn", "out", "my", "your", "close", "off"}
        for task in pending_tasks:
            task_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", task.title.lower()) if w not in stop_words]
            if task_words and any(w in text for w in task_words):
                if has_completion_signal:
                    normalized_slug = re.sub(r"[^a-z0-9]+", "_", task.title.lower()).strip("_")
                    return VerifiedAction(
                        action_type=normalized_slug,
                        domain=task.domain,
                        raw_statement=transcript.strip(),
                        confidence=0.95,
                        timestamp=datetime.now().isoformat(),
                        is_revoked=False,
                        matched_task_id=task.id,
                    )

    # 1b. Anaphora resolution using historical context (Milestone 3.1)
    if historical_context:
        ctx_lower = historical_context.lower()
        if re.search(r"\b(turned it off|switched it off|shut it off)\b", text):
            if any(w in ctx_lower for w in ["stove", "oven", "gas", "burner"]):
                return VerifiedAction(action_type="stove_off", domain="safety", raw_statement=transcript.strip(), confidence=0.95, timestamp=datetime.now().isoformat(), is_revoked=False)
        if re.search(r"\b(unplugged it|disconnected it)\b", text):
            if any(w in ctx_lower for w in ["iron", "clothes iron"]):
                return VerifiedAction(action_type="iron_unplugged", domain="safety", raw_statement=transcript.strip(), confidence=0.95, timestamp=datetime.now().isoformat(), is_revoked=False)
        if re.search(r"\b(locked it|closed it|bolted it|i just did|just did|did that)\b", text):
            if any(w in ctx_lower for w in ["door", "front door", "gate", "entrance", "lock"]):
                return VerifiedAction(action_type="door_locked", domain="safety", raw_statement=transcript.strip(), confidence=0.95, timestamp=datetime.now().isoformat(), is_revoked=False)

    # 2. Standard completed action rules (unplanned)
    action_rules: List[tuple[str, str, str]] = [
        (r"\b(turned off|switched off|shut off|spento|chiuso)\s+.*?\b(stove|oven|gas|burner|fornello|gas)\b", "stove_off", "safety"),
        (r"\b(stove|oven|gas|burner|fornello)\b.*?\b(off|turned off|spento|chiuso)\b", "stove_off", "safety"),
        (r"\b(unplugged|disconnected|staccato|disconnesso)\s+.*?\b(iron|clothes iron|ferro da stiro|ferro)\b", "iron_unplugged", "safety"),
        (r"\b(iron|ferro da stiro)\b.*?\b(unplugged|staccato|spento)\b", "iron_unplugged", "safety"),
        (r"\b(locked|closed|bolted|chiuso|bloccato)\s+.*?\b(door|front door|porta|portone)\b", "door_locked", "safety"),
        (r"\b(door|front door|porta)\b.*?\b(locked|closed|bloccata|chiusa)\b", "door_locked", "safety"),
        (r"\b(took|taken|swallowed|preso|presa|assunto)\s+.*?\b(medication|medicine|pill|pills|vitamins|pastiglia|farmaco)\b", "medication_taken", "routine"),
        (r"\b(merged|closed)\s+.*?\b(pr|pull request)\b", "pr_merged", "work_task"),
        (r"\b(deployed|released)\s+.*?\b(service|staging|production|app|build)\b", "service_deployed", "work_task"),
        (r"\b(sent|emailed|inviato|spedito)\s+.*?\b(email|report|message|slides|pitch deck|deck|document)\b", "email_sent", "work_task"),
    ]

    for pattern, action_type, domain in action_rules:
        if re.search(pattern, text):
            # Check if this rule-matched action matches any pending task
            matched_id = None
            matched_domain = domain
            if pending_tasks:
                for task in pending_tasks:
                    task_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", task.title.lower()) if w not in {"the", "and", "for", "with", "this", "that"}]
                    if task_words and any(w in text for w in task_words):
                        matched_id = task.id
                        matched_domain = task.domain
                        break

            return VerifiedAction(
                action_type=action_type,
                domain=matched_domain,  # type: ignore[arg-type]
                raw_statement=transcript.strip(),
                confidence=0.95,
                timestamp=datetime.now().isoformat(),
                is_revoked=False,
                matched_task_id=matched_id,
            )

    return None


def node_extract_action(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Stage 3B Action-State Verifier.

    Extracts confirmed actions, drops doubts/intentions, grounds location telemetry,
    and outputs action_data. Dynamically injects pending planned tasks into the verification prompt.
    """
    transcript = state.get("raw_transcript", "").strip()
    if not transcript:
        return {"action_data": None}

    historical_context = state.get("historical_context")
    location = state.get("location")

    # Fetch pending planned tasks from context store
    store = get_storage_store()
    pending_tasks: List[PlannedTask] = []
    try:
        pending_tasks = store.list_planned_tasks(status="pending")
    except Exception as e:
        logger.warning(f"Failed to query pending planned tasks: {e}")

    # Use heuristic fallback if mock_ai or missing provider credentials
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Extracting action via heuristic fallback (mock_ai or no credentials).")
        action = _heuristic_extract_action(
            transcript, pending_tasks=pending_tasks, historical_context=historical_context
        )
        if action and location and not action.location:
            action.location = location
        return {"action_data": action}

    try:
        extractor = _get_action_extractor()
        system_prompt = build_action_prompt(pending_tasks)
        context_prefix = f"Recent Dialogue Context:\n{historical_context}\n\n" if historical_context else ""
        prompt = (
            f"Analyze the following transcript. If an action was explicitly completed, "
            f"extract it. Otherwise reject it.\n\n{context_prefix}Transcript: \"{transcript}\""
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]
        result: Optional[VerifiedAction] = extractor.invoke(messages)

        # Validate confidence threshold
        if result and result.confidence >= 0.75:
            # Always ground the timestamp on ingestion time: the LLM has no clock and hallucinates dates
            result.timestamp = state.get("timestamp") or datetime.now().isoformat()

            # Defensive check: if result matches a pending task but matched_task_id is missing, auto-resolve
            if not result.matched_task_id and pending_tasks:
                action_text = f"{result.action_type} {result.raw_statement}".lower()
                for task in pending_tasks:
                    words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", task.title.lower()) if w not in {"the", "and", "for", "with", "this", "that"}]
                    if words and any(w in action_text for w in words):
                        result.matched_task_id = task.id
                        result.domain = task.domain
                        break

            if location and not result.location:
                result.location = location

            return {"action_data": result}
        else:
            logger.info(f"Action candidate rejected (confidence too low or empty): {result}")
            heuristic_action = _heuristic_extract_action(
                transcript, pending_tasks=pending_tasks, historical_context=historical_context
            )
            if heuristic_action and heuristic_action.confidence >= 0.90:
                if location and not heuristic_action.location:
                    heuristic_action.location = location
                return {"action_data": heuristic_action}
            return {"action_data": None}

    except Exception as e:
        model_fallback(logger, "action_state", e)
        action = _heuristic_extract_action(
            transcript, pending_tasks=pending_tasks, historical_context=historical_context
        )
        if action and location and not action.location:
            action.location = location
        return {"action_data": action}

