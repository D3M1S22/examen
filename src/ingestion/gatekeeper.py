"""Semantic Gatekeeper for ambient audio stream screening in EXAMEN."""

import logging
import re
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_aws import ChatBedrockConverse

from src.core.config import settings
from src.core.schemas import ChunkClassification

logger = logging.getLogger(__name__)

GATEKEEPER_SYSTEM_PROMPT = """You are the high-efficiency semantic screening gatekeeper for the EXAMEN wearable AI engine.
Your sole responsibility is to evaluate an incoming transcribed audio chunk and categorize it to prevent wasting downstream compute.

LANGUAGE INSTRUCTION:
Input transcripts may be spoken in any language (e.g., English, Spanish, German, French, Italian). Evaluate the underlying semantic intent regardless of the spoken language.

CATEGORIES TO DETECT:
- "action": Explicit first-person completed actions regarding domestic safety, routine, or completed work tasks.
  * MUST be a confirmed completed action (e.g., "I just turned off the stove", "I unplugged the clothes iron", "Merged PR #42", "I locked the front door").
  * STRICT NEGATIVE FILTER: If it is a doubt, question, or future intention (e.g., "I should remember to turn off the stove", "Did I lock the door?", "I need to deploy later"), classify as "noop"!
- "social": Professional introductions, name/role exchanges, or explicit bilateral promises.
  * E.g., "Nice to meet you, I'm Marco, Tech Lead at Acme", "Pleased to meet you, let's stay in touch and I'll send you the documentation tomorrow".
  * Casual mentions of third parties without meeting or commitments are NOT "social".
- "deep_topic": Technical discussions, architectural debates, specific bugs, named libraries/frameworks, or academic lectures.
  * E.g., "In today's meeting we are evaluating AWS Bedrock AgentCore and investigating a memory leak in the runtime", "Today's lecture covers distributed consensus algorithms".
- "noop": Default for casual chit-chat, small talk, pleasantries, background noise, fragmented speech, or topics lacking durable informational value.
  * E.g., "What's the weather like today?", "Let's grab a coffee at the corner", "Yeah, sure", "See you later", "Sounds good, thanks".

STRICT RULES:
1. BIAS HEAVILY TOWARDS "noop". Over 90% of daily ambient speech should be classified as "noop".
2. If uncertain or speech is trivial/banal, return ["noop"].
3. Return accurate confidence score between 0.0 and 1.0.
4. Provide a single-line summary_hint describing the detected signal (empty if "noop").
"""


def _get_bedrock_classifier():
    """Initializes Bedrock Converse LLM with structured output."""
    llm = ChatBedrockConverse(
        model=settings.gatekeeper_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token,
    )
    return llm.with_structured_output(ChunkClassification)


def _heuristic_classify(transcript: str) -> ChunkClassification:
    """Deterministic English-only heuristic classifier for offline testing, CI/CD, or fallback."""
    text = transcript.lower().strip()
    if not text:
        return ChunkClassification(categories=["noop"], confidence=1.0, summary_hint="Empty transcript")

    # Strict doubt & future intention filter -> immediately NOOP
    doubt_patterns = [
        r"\b(should remember|need to remember|need to|have to|did i|wonder if)\b",
        r"\b(supposed to|planning to|going to|thinking of|tomorrow|later on|later today)\b"
    ]
    if any(re.search(pat, text) for pat in doubt_patterns):
        return ChunkClassification(
            categories=["noop"],
            confidence=0.96,
            summary_hint="Doubt or future intention discarded"
        )

    categories: List[str] = []

    # 1. Action completed check: focus strictly on English first-person completed action verbs
    action_patterns = [
        r"\b(i|we)\s+(just\s+)?(turned off|switched off|unplugged|locked|shut|closed|verified|checked|completed|finished|merged|deployed|sent|confirmed)\b",
        r"\bi('ve| have)\s+(just\s+)?(turned off|switched off|unplugged|locked|shut|closed|verified|checked|completed|finished|merged|deployed|sent|confirmed)\b"
    ]
    if any(re.search(pat, text) for pat in action_patterns):
        categories.append("action")

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
        "social": "Social encounter or commitment detected",
        "deep_topic": "Meeting, architecture review or lecture detected"
    }
    hints = [hint_map[c] for c in categories if c in hint_map]

    return ChunkClassification(
        categories=categories,
        confidence=0.93,
        summary_hint=" & ".join(hints)
    )


def classify_chunk(transcript: str, force_mock: bool = False) -> ChunkClassification:
    """Classifies an ambient speech transcript chunk synchronously.

    Args:
        transcript: The aggregated text from the audio sliding window buffer.
        force_mock: If True, forces heuristic evaluation without calling Bedrock.

    Returns:
        ChunkClassification with categories, confidence, and summary_hint.
    """
    clean_text = transcript.strip()
    if not clean_text:
        return ChunkClassification(categories=["noop"], confidence=1.0, summary_hint="Empty audio chunk")

    # Offline or mock mode
    if force_mock or settings.mock_ai or not settings.has_aws_credentials:
        logger.debug("Gatekeeper using heuristic/mock classifier")
        return _heuristic_classify(clean_text)

    # Real Bedrock call
    try:
        classifier = _get_bedrock_classifier()
        messages = [
            SystemMessage(content=GATEKEEPER_SYSTEM_PROMPT),
            HumanMessage(content=f'Transcript: "{clean_text}"')
        ]
        result: ChunkClassification = classifier.invoke(messages)
        return result
    except Exception as e:
        logger.warning(f"Bedrock Gatekeeper invocation failed ({e}), falling back to heuristic: {e}")
        return _heuristic_classify(clean_text)


async def aclassify_chunk(transcript: str, force_mock: bool = False) -> ChunkClassification:
    """Classifies an ambient speech transcript chunk asynchronously.

    Args:
        transcript: The aggregated text from the audio sliding window buffer.
        force_mock: If True, forces heuristic evaluation without calling Bedrock.

    Returns:
        ChunkClassification with categories, confidence, and summary_hint.
    """
    clean_text = transcript.strip()
    if not clean_text:
        return ChunkClassification(categories=["noop"], confidence=1.0, summary_hint="Empty audio chunk")

    if force_mock or settings.mock_ai or not settings.has_aws_credentials:
        return _heuristic_classify(clean_text)

    try:
        classifier = _get_bedrock_classifier()
        messages = [
            SystemMessage(content=GATEKEEPER_SYSTEM_PROMPT),
            HumanMessage(content=f'Transcript: "{clean_text}"')
        ]
        result: ChunkClassification = await classifier.ainvoke(messages)
        return result
    except Exception as e:
        logger.warning(f"Async Bedrock Gatekeeper invocation failed ({e}), falling back to heuristic")
        return _heuristic_classify(clean_text)


def is_noop(classification: ChunkClassification) -> bool:
    """Helper to check if a classification represents a drop (noop).

    Returns True if 'noop' is in categories and no other valuable categories exist.
    """
    if not classification.categories:
        return True
    if "noop" in classification.categories and len(classification.categories) == 1:
        return True
    return False
