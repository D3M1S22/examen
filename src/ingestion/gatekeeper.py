"""Semantic Gatekeeper for ambient audio stream screening in EXAMEN."""

import logging
import re
from typing import List, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from src.core.config import settings
from src.core.models import get_fast_model, has_active_model_credentials
from src.core.schemas import ChunkClassification

logger = logging.getLogger(__name__)

GATEKEEPER_SYSTEM_PROMPT = """You are the high-efficiency semantic screening gatekeeper for the EXAMEN wearable AI engine.
Your sole responsibility is to evaluate an incoming transcribed audio chunk and categorize it to prevent wasting downstream compute.

LANGUAGE INSTRUCTION:
Input transcripts may be spoken in any language (e.g., English, Spanish, German, French, Italian). Evaluate the underlying semantic intent regardless of the spoken language.

CATEGORIES TO DETECT:
- "action": Explicit first-person completed actions regarding domestic safety, routine, or completed work tasks.
  * MUST be a confirmed completed action (e.g., "I just turned off the stove", "I unplugged the clothes iron", "Merged PR #42", "I locked the front door").
  * STRICT NEGATIVE FILTER: Future intentions or doubts are NOT completed actions!
- "scheduled_task": Spoken future intentions, commitments to do something later, or explicit deadlines.
  * E.g., "I need to call Dr. Smith at 3 PM tomorrow", "Remind me to turn off the irrigation valve in an hour", "I must send the report before Friday", "Don't forget to take blood pressure medication tonight".
  * Doubts or retrospective questions (e.g. "Did I lock the door?", "I wonder if I turned it off") are NOT scheduled tasks and MUST be "noop"!
- "social": Professional introductions, name/role exchanges, or explicit bilateral promises.
  * E.g., "Nice to meet you, I'm Marco, Tech Lead at Acme", "Pleased to meet you, let's stay in touch and I'll send you the documentation tomorrow".
  * Casual mentions of third parties without meeting or commitments are NOT "social".
- "deep_topic": Technical discussions, architectural debates, specific bugs, named libraries/frameworks, or academic lectures.
  * E.g., "In today's meeting we are evaluating AWS Bedrock AgentCore and investigating a memory leak in the runtime", "Today's lecture covers distributed consensus algorithms".
- "noop": Default for casual chit-chat, small talk, pleasantries, background noise, fragmented speech, doubts, or topics lacking durable informational value.
  * E.g., "What's the weather like today?", "Let's grab a coffee at the corner", "Did I unplug the stove? I wonder if I turned it off.", "Yeah, sure", "See you later", "Sounds good, thanks".

STRICT RULES:
1. BIAS HEAVILY TOWARDS "noop". Over 90% of daily ambient speech should be classified as "noop".
2. If uncertain or speech is trivial/banal, return ["noop"].
3. Return accurate confidence score between 0.0 and 1.0.
4. Provide a single-line summary_hint describing the detected signal (empty if "noop").
"""


def build_gatekeeper_prompt(
    active_tasks: Optional[List[str]] = None,
    prior_context: Optional[str] = None,
) -> str:
    """Builds the Gatekeeper system prompt, dynamically appending prior dialogue context and active tasks."""
    prompt = GATEKEEPER_SYSTEM_PROMPT

    if prior_context and prior_context.strip():
        extra_ctx = f"""

PRIOR CONVERSATION CONTEXT (FOR PRONOUN & ANAPHORA RESOLUTION):
The following recent dialogue context preceded this audio chunk:
{prior_context.strip()}

If the current transcript refers to an action, commitment, or topic introduced in the prior context (e.g. "Sure, consider it done. I'll email it first thing in the morning", "I will do that", "Yes, locked and turned off"), resolve the reference using the prior context!
"""
        prompt += extra_ctx

    if active_tasks:
        task_bullets = "\n".join(f"- {task.strip()}" for task in active_tasks if task and task.strip())
        if task_bullets:
            extra_section = f"""

ACTIVE PENDING TASKS / ROUTINES TO WATCH FOR:
The user has scheduled or is expecting completion of the following specific tasks:
{task_bullets}

PRIORITY INSTRUCTION FOR ACTIVE TASKS:
If the transcript indicates that the speaker has completed, verified, or executed ANY of the active pending tasks above, IMMEDIATELY classify as "action" with high confidence (>= 0.90), even if phrased informally or conversationally.
"""
            prompt += extra_section
    return prompt


def _get_bedrock_classifier():
    """Initializes classifier model with structured output via model factory."""
    llm = get_fast_model()
    return llm.with_structured_output(ChunkClassification)


def _heuristic_classify(
    transcript: str,
    active_tasks: Optional[List[str]] = None,
    prior_context: Optional[str] = None,
) -> ChunkClassification:
    """Deterministic English-only heuristic classifier for offline testing, CI/CD, or fallback."""
    text = transcript.lower().strip()
    if not text:
        return ChunkClassification(categories=["noop"], confidence=1.0, summary_hint="Empty transcript")

    # 0. Strict doubt & retrospective uncertainty check -> immediately NOOP
    doubt_patterns = [
        r"\b(did i|did we|wonder if|i wonder|have i|was it|were they|maybe i)\b",
    ]
    if any(re.search(pat, text) for pat in doubt_patterns):
        return ChunkClassification(
            categories=["noop"],
            confidence=0.96,
            summary_hint="Doubt or retrospective question discarded"
        )

    categories: List[str] = []

    # 0b. Anaphora & Context Window check (Milestone 3.1)
    if prior_context and prior_context.strip():
        ctx_lower = prior_context.lower()
        # Follow-up agreement/promise, e.g. "Sure, consider it done. I'll email it first thing in the morning."
        anaphoric_scheduled = [
            r"\b(consider it done|i'll email it|i will email it|i'll send it|i will send it|i'll do that|i will do that)\b",
            r"\b(sure,?\s*(consider it done|i'll|i will|let me|we will))\b",
            r"\b(i'll make sure to|i'll take care of it|i will take care of it)\b",
        ]
        if any(re.search(pat, text) for pat in anaphoric_scheduled):
            categories.append("scheduled_task")
            if any(w in ctx_lower for w in ["send", "email", "report", "review", "contract", "can you", "could you", "please"]):
                categories.append("social")

        # Follow-up confirmation, e.g. "I just did", "It's done", "Locked it and turned it off"
        anaphoric_action = [
            r"\b(i just did|it's done|all done|locked it|turned it off|switched it off|unplugged it)\b",
            r"\b(done and verified|taken care of)\b",
        ]
        if any(re.search(pat, text) for pat in anaphoric_action):
            if any(w in ctx_lower for w in ["stove", "iron", "door", "lock", "medication", "pill", "window", "car", "pr", "deploy"]):
                categories.append("action")


    # 1. Action completed check: focus strictly on English first-person completed action verbs
    action_patterns = [
        r"\b(i|we)\s+(just\s+)?(turned off|switched off|unplugged|locked|shut|closed|verified|checked|completed|finished|merged|deployed|sent|confirmed|took|taken)\b",
        r"\bi('ve| have)\s+(just\s+)?(turned off|switched off|unplugged|locked|shut|closed|verified|checked|completed|finished|merged|deployed|sent|confirmed|took|taken)\b"
    ]
    if any(re.search(pat, text) for pat in action_patterns):
        categories.append("action")

    # 1b. Active pending tasks check: if active tasks are provided, check if completion signal + task keywords match
    if "action" not in categories and active_tasks:
        completion_signals = [
            r"\b(done|finished|completed|checked|verified|unplugged|turned off|locked|closed|took|taken|switched off|shut)\b",
            r"\b(i did|we did|it's done|all done|taken care of|is done|are done)\b"
        ]
        has_completion_signal = any(re.search(pat, text) for pat in completion_signals)

        stop_words = {"the", "and", "for", "with", "this", "that", "from", "into", "over", "take", "make", "turn", "out", "my", "your"}
        for task in active_tasks:
            task_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", task.lower()) if w not in stop_words]
            if task_words and any(w in text for w in task_words):
                if has_completion_signal:
                    categories.append("action")
                    break

    # 1c. Scheduled task / future intention check: explicit future commitments, reminders, or deadlines
    scheduled_patterns = [
        r"\b(i need to|need to|i have to|have to|i must|must|remind me to|don't forget to|remember to|schedule a|schedule an)\b",
        r"\b(i will|i'll)\s+(call|send|meet|finish|buy|turn off|unplug|lock|shut|take|deploy|review|deliver)\b",
    ]
    if any(re.search(pat, text) for pat in scheduled_patterns) and "action" not in categories:
        categories.append("scheduled_task")

    # 2. Social interaction check: strictly explicit introductions, professional roles, or follow-up commitments
    social_patterns = [
        # Explicit meeting introductions
        r"\b(nice to meet you|pleased to meet you|great to meet you)\b",
        r"\b(nice to meet you|pleased to meet you|great to meet you)\s+[a-z]+",
        r"\b(nice to meet you|pleased to meet you)\b.*?\b(i'm|my name is)\b",
        r"\b(my name is)\s+[a-z]+",
        # Professional role exchange
        r"\b(tech lead|cto|founder|chief|head of|lead engineer)\s+(at|for|in)\b",
        r"\b(i work as|i'm the|i am the)\s+[a-z\s]+(at|for)\b",
        # Explicit meeting follow-up commitments
        r"\b(let's keep in touch|let's stay in touch)\b",
        r"\b(i will follow up with you|i'll follow up with you)\b"
    ]
    if any(re.search(pat, text) for pat in social_patterns):
        categories.append("social")

    # 3. Deep Topic check: strictly meeting agendas, architectural reviews, technical debugging, or lectures
    topic_patterns = [
        # Meeting & review contexts
        r"\b(in today's meeting|agenda for today|during this meeting|sprint review|sprint retrospective|daily standup)\b",
        r"\b(architecture review|system design discussion|evaluating the architecture|architectural tradeoff)\b",
        # Academic & lecture contexts
        r"\b(today's lecture|lecture on|theorem of|distributed systems|distributed consensus|cap theorem)\b",
        # Specific engineering investigations
        r"\b(investigating the memory leak|debugging the race condition|root cause analysis|performance bottleneck)\b"
    ]
    if any(re.search(pat, text) for pat in topic_patterns):
        categories.append("deep_topic")

    # Default to NOOP if no distinct signal (conservative fallback)
    if not categories:
        return ChunkClassification(
            categories=["noop"],
            confidence=0.98,
            summary_hint="Chit-chat or uninformative conversation detected"
        )

    hint_map = {
        "action": "Completed action confirmed",
        "scheduled_task": "Spoken future intention or scheduled task detected",
        "social": "Social encounter or commitment detected",
        "deep_topic": "Meeting, architecture review or lecture detected"
    }
    hints = [hint_map[c] for c in categories if c in hint_map]

    return ChunkClassification(
        categories=categories,
        confidence=0.93,
        summary_hint=" & ".join(hints)
    )


def classify_chunk(
    transcript: str,
    active_tasks: Optional[List[str]] = None,
    force_mock: bool = False,
    prior_context: Optional[str] = None,
) -> ChunkClassification:
    """Classifies an ambient speech transcript chunk synchronously.

    Args:
        transcript: The aggregated text from the audio sliding window buffer.
        active_tasks: Optional list of pending planned task titles to watch for.
        force_mock: If True, forces heuristic evaluation without calling Bedrock.
        prior_context: Optional concatenated recent dialogue context for anaphora resolution.

    Returns:
        ChunkClassification with categories, confidence, and summary_hint.
    """
    clean_text = transcript.strip()
    if not clean_text:
        return ChunkClassification(categories=["noop"], confidence=1.0, summary_hint="Empty audio chunk")

    # Offline or mock mode
    if force_mock or settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Gatekeeper using heuristic/mock classifier")
        return _heuristic_classify(clean_text, active_tasks=active_tasks, prior_context=prior_context)

    # Real Model call
    try:
        classifier = _get_bedrock_classifier()
        system_prompt = build_gatekeeper_prompt(active_tasks=active_tasks, prior_context=prior_context)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f'Transcript: "{clean_text}"')
        ]
        result: ChunkClassification = classifier.invoke(messages)
        return result
    except Exception as e:
        logger.warning(f"Gatekeeper invocation failed ({e}), falling back to heuristic: {e}")
        return _heuristic_classify(clean_text, active_tasks=active_tasks, prior_context=prior_context)


async def aclassify_chunk(
    transcript: str,
    active_tasks: Optional[List[str]] = None,
    force_mock: bool = False,
    prior_context: Optional[str] = None,
) -> ChunkClassification:
    """Classifies an ambient speech transcript chunk asynchronously.

    Args:
        transcript: The aggregated text from the audio sliding window buffer.
        active_tasks: Optional list of pending planned task titles to watch for.
        force_mock: If True, forces heuristic evaluation without calling Bedrock.
        prior_context: Optional concatenated recent dialogue context for anaphora resolution.

    Returns:
        ChunkClassification with categories, confidence, and summary_hint.
    """
    clean_text = transcript.strip()
    if not clean_text:
        return ChunkClassification(categories=["noop"], confidence=1.0, summary_hint="Empty audio chunk")

    if force_mock or settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        return _heuristic_classify(clean_text, active_tasks=active_tasks, prior_context=prior_context)

    try:
        classifier = _get_bedrock_classifier()
        system_prompt = build_gatekeeper_prompt(active_tasks=active_tasks, prior_context=prior_context)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f'Transcript: "{clean_text}"')
        ]
        result: ChunkClassification = await classifier.ainvoke(messages)
        return result
    except Exception as e:
        logger.warning(f"Async Bedrock Gatekeeper invocation failed ({e}), falling back to heuristic")
        return _heuristic_classify(clean_text, active_tasks=active_tasks, prior_context=prior_context)



def is_noop(classification: ChunkClassification) -> bool:
    """Helper to check if a classification represents a drop (noop).

    Returns True if 'noop' is in categories and no other valuable categories exist.
    """
    if not classification.categories:
        return True
    if "noop" in classification.categories and len(classification.categories) == 1:
        return True
    return False
