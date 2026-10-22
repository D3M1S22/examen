"""Stage 3D: Ambient Task Scheduler Node for EXAMEN.

Extracts structured planned tasks, deadlines, and future intentions from ambient
spoken voice without confusing them with completed verified actions.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.models import get_fast_model, has_active_model_credentials
from src.core.schemas import ExamenState, PlannedTask, ScheduledTaskExtraction
from src.core.time_utils import parse_local_iso
from src.core.service_log import model_fallback

logger = logging.getLogger("examen.pipeline.scheduler")

SCHEDULER_SYSTEM_PROMPT = """You are the Ambient Task Extraction Engine for the EXAMEN wearable AI system.
Your mission is to extract actionable future tasks, intentions, commitments, and deadlines from spoken speech.

REFERENCE TIME: {current_time}

EXTRACTION GUIDELINES:
1. title: Clean, concise imperative title (e.g., 'Call Dr. Smith', 'Turn off irrigation valve', 'Send updated NDA to Marco', 'Deploy database update').
2. domain: Classify into 'safety', 'routine', 'work_task', or 'personal'.
   - 'safety': Domestic security/hazards (stove, clothes iron, locks, water valves).
   - 'routine': Medication, daily personal habits, recurring wellness routines.
   - 'work_task': Professional deliverables, pull requests, emails, client presentations.
   - 'personal': Errands, shopping, fitness, personal calls.
3. scheduled_time: ISO-8601 string (e.g. '2026-10-09T15:00:00') computed relative to the reference time.
   - If relative words ('tomorrow at 3 PM', 'in 20 minutes', 'tonight at 9 PM') are used, compute the target timestamp.
   - If no specific time or day is indicated, set scheduled_time to null.
4. relative_time_anchor: Verbatim spoken phrase indicating the temporal anchor (e.g., 'at 3 PM tomorrow', 'in an hour', 'before Friday at 5 PM').
5. recurrence: 'none', 'daily', 'weekdays', or 'weekly'.
6. confidence: Float between 0.0 and 1.0 indicating certainty of intention.
"""


def parse_reference_time(ref_time_iso: Optional[str]) -> Optional[datetime]:
    """Parses the utterance time used as anchor for relative expressions (naive local time)."""
    return parse_local_iso(ref_time_iso)


def parse_relative_time_expression(
    text: str, ref_dt: Optional[datetime] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Deterministically extracts relative time expressions and computes target ISO-8601 timestamp.
    
    Returns:
        Tuple of (scheduled_time_iso, relative_time_anchor_str)
    """
    ref = ref_dt or datetime.now()
    text_lower = text.lower()

    # 1. "in (\d+) minute(s)?"
    m_min = re.search(r"\bin\s+(\d+)\s+minutes?\b", text_lower)
    if m_min:
        mins = int(m_min.group(1))
        target = ref + timedelta(minutes=mins)
        return target.replace(microsecond=0).isoformat(), m_min.group(0)

    # 2. "in (an|\d+) hour(s)?"
    m_hr = re.search(r"\bin\s+(an|\d+)\s+hours?\b", text_lower)
    if m_hr:
        hrs = 1 if m_hr.group(1) == "an" else int(m_hr.group(1))
        target = ref + timedelta(hours=hrs)
        return target.replace(microsecond=0).isoformat(), m_hr.group(0)

    # 3. "tomorrow (morning|afternoon|evening)? (at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
    m_tom_time = re.search(
        r"\btomorrow(?:\s+(?:morning|afternoon|evening))?(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        text_lower
    )
    if m_tom_time:
        hr = int(m_tom_time.group(1))
        minute = int(m_tom_time.group(2)) if m_tom_time.group(2) else 0
        meridiem = m_tom_time.group(3)
        if meridiem == "pm" and hr < 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        elif not meridiem and hr <= 7:
            # Assume afternoon if 1-7 without am/pm
            hr += 12

        target = (ref + timedelta(days=1)).replace(hour=hr, minute=minute, second=0, microsecond=0)
        return target.isoformat(), m_tom_time.group(0)

    # 3b. Just "tomorrow morning/afternoon/tonight"
    if "tomorrow morning" in text_lower:
        target = (ref + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return target.isoformat(), "tomorrow morning"
    if "tomorrow afternoon" in text_lower:
        target = (ref + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        return target.isoformat(), "tomorrow afternoon"
    if "tomorrow" in text_lower:
        target = (ref + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return target.isoformat(), "tomorrow"

    # 4. "tonight at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?" or just "tonight"
    m_tonight = re.search(r"\btonight(?:\s+at)?\s*(\d{1,2})?(?::(\d{2}))?\s*(am|pm)?\b", text_lower)
    if m_tonight and m_tonight.group(1):
        hr = int(m_tonight.group(1))
        minute = int(m_tonight.group(2)) if m_tonight.group(2) else 0
        if hr < 12:
            hr += 12
        target = ref.replace(hour=hr, minute=minute, second=0, microsecond=0)
        return target.isoformat(), m_tonight.group(0)
    elif "tonight" in text_lower:
        target = ref.replace(hour=21, minute=0, second=0, microsecond=0)
        return target.isoformat(), "tonight"

    # 5. "at (\d{1,2})(?::(\d{2}))?\s*(am|pm)"
    m_at_time = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text_lower)
    if m_at_time:
        hr = int(m_at_time.group(1))
        minute = int(m_at_time.group(2)) if m_at_time.group(2) else 0
        meridiem = m_at_time.group(3)
        if meridiem == "pm" and hr < 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        target = ref.replace(hour=hr, minute=minute, second=0, microsecond=0)
        if target < ref:
            target += timedelta(days=1)
        return target.isoformat(), m_at_time.group(0)

    # 6. "before (friday|monday|tuesday|wednesday|thursday|saturday|sunday)(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?"
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    m_weekday = re.search(
        r"\b(?:before|on|by)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?\b",
        text_lower
    )
    if m_weekday:
        day_name = m_weekday.group(1)
        target_weekday = weekdays.index(day_name)
        days_ahead = (target_weekday - ref.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        hr = 17  # Default 5 PM for business deadlines
        minute = 0
        if m_weekday.group(2):
            hr = int(m_weekday.group(2))
            minute = int(m_weekday.group(3)) if m_weekday.group(3) else 0
            if m_weekday.group(4) == "pm" and hr < 12:
                hr += 12
        target = (ref + timedelta(days=days_ahead)).replace(hour=hr, minute=minute, second=0, microsecond=0)
        return target.isoformat(), m_weekday.group(0)

    return None, None


def _clean_task_title(transcript: str, time_anchor: Optional[str] = None) -> str:
    """Strips conversational lead-ins and temporal markers from spoken text to produce a clean imperative title."""
    clean = transcript.strip()

    # Strip conversational prefixes
    lead_in_patterns = [
        r"^(i\s+need\s+to\s+remember\s+to\s+|need\s+to\s+remember\s+to\s+)",
        r"^(i\s+need\s+to\s+|need\s+to\s+|i\s+have\s+to\s+|have\s+to\s+|i\s+must\s+|must\s+)",
        r"^(remind\s+me\s+to\s+|don't\s+forget\s+to\s+|dont\s+forget\s+to\s+|remember\s+to\s+)",
        r"^(schedule\s+a\s+|schedule\s+an\s+|schedule\s+)",
        r"^(let's\s+make\s+sure\s+to\s+|make\s+sure\s+to\s+)",
        r"^(i\s+will\s+|i'll\s+)",
    ]
    for pat in lead_in_patterns:
        clean = re.sub(pat, "", clean, flags=re.IGNORECASE).strip()

    # Strip time anchor from title if it occurs at the end or beginning
    if time_anchor:
        clean = re.sub(re.escape(time_anchor), "", clean, flags=re.IGNORECASE).strip()

    # Clean dangling prepositions (e.g. "before", "at", "on", "by")
    clean = re.sub(r"\s+\b(at|on|before|by|in)\s*$", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"^[,\s\.\-]+|[,\s\.\-]+$", "", clean)

    if not clean:
        clean = transcript.strip()

    # Capitalize first character
    return clean[0].upper() + clean[1:] if len(clean) > 1 else clean.upper()


def _detect_domain(text: str) -> str:
    """Infers task domain from action keywords."""
    lower = text.lower()
    if any(w in lower for w in ["iron", "stove", "valve", "lock", "alarm", "gas", "door", "window", "irrigation"]):
        return "safety"
    if any(w in lower for w in ["deploy", "pr", "pull request", "nda", "client", "report", "presentation", "ticket", "code", "architecture"]):
        return "work_task"
    if any(w in lower for w in ["gym", "workout", "groceries", "milk", "buy", "dinner", "lunch", "coffee", "doctor", "dr."]):
        return "personal"
    return "routine"


def _heuristic_extract_scheduled_task(
    transcript: str, ref_time_iso: Optional[str] = None, session_id: Optional[str] = None
) -> Optional[PlannedTask]:
    """Deterministic heuristic extraction for ambient scheduled tasks."""
    clean_text = transcript.strip()
    if not clean_text:
        return None

    ref_dt = None
    if ref_time_iso:
        try:
            ref_dt = datetime.fromisoformat(ref_time_iso.replace("Z", "+00:00"))
        except Exception:
            pass

    scheduled_time, anchor = parse_relative_time_expression(clean_text, ref_dt)
    title = _clean_task_title(clean_text, anchor)
    domain = _detect_domain(clean_text)

    return PlannedTask(
        title=title,
        domain=domain,
        scheduled_time=scheduled_time,
        recurrence="none",
        status="pending",
        origin="ambient_voice",
        raw_statement=clean_text,
        confidence=0.94,
        relative_time_anchor=anchor,
        session_id=session_id,
        created_at=datetime.now().isoformat(),
    )


def _get_scheduled_task_extractor():
    """Initializes structured LLM extractor via model factory."""
    llm = get_fast_model()
    return llm.with_structured_output(ScheduledTaskExtraction)


def node_extract_scheduled_task(state: ExamenState) -> Dict[str, Any]:
    """LangGraph node: Stage 3D Ambient Task Scheduler.

    Extracts forward-looking commitments and scheduled tasks from ambient spoken audio. Who spoke matters
    (docs/next_steps/08_speaker_identity.md §5): the owner's own intentions and requests other people address
    to the owner ("Damiano, remember to ...") become the owner's tasks; another person's own plans do not.
    """
    transcript = (state.get("raw_transcript") or "").strip()
    session_id = state.get("session_id")
    ref_time_iso = state.get("timestamp") or datetime.now().isoformat()
    speaker = _SpeakerView.from_state(state)

    if not transcript:
        return {"scheduled_task": None}

    # Heuristic / Mock path
    if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
        logger.debug("Extracting ambient scheduled task via heuristic engine.")
        return {"scheduled_task": _heuristic_for_speaker(transcript, ref_time_iso, session_id, speaker)}

    # LLM Structured Extraction
    try:
        extractor = _get_scheduled_task_extractor()
        sys_prompt = SCHEDULER_SYSTEM_PROMPT.format(current_time=ref_time_iso) + speaker.prompt_section()
        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(content=f'Spoken statement: "{transcript}"'),
        ]
        extracted: ScheduledTaskExtraction = extractor.invoke(messages)

        if not extracted or not extracted.title:
            return {"scheduled_task": _heuristic_for_speaker(transcript, ref_time_iso, session_id, speaker)}
        if not extracted.for_owner:
            logger.debug("Scheduled task dropped: not for the device owner")
            return {"scheduled_task": None}
        addressed = speaker.role == "contact" or (speaker.role == "unknown" and (
            bool(extracted.requested_by) or _addressed_to_owner(transcript, speaker.owner)))

        # If LLM didn't resolve scheduled_time but relative anchor was mentioned, use regex parser
        scheduled_time = extracted.scheduled_time
        anchor = extracted.relative_time_anchor
        if not scheduled_time:
            # Anchor on the utterance time, not on "now" (history backfill replays old speech)
            parsed_time, parsed_anchor = parse_relative_time_expression(
                transcript, parse_reference_time(ref_time_iso)
            )
            scheduled_time = parsed_time
            if not anchor:
                anchor = parsed_anchor

        task = PlannedTask(
            title=extracted.title.strip(),
            domain=extracted.domain,
            scheduled_time=scheduled_time,
            recurrence=extracted.recurrence or "none",
            status="pending",
            origin="ambient_voice",
            raw_statement=transcript,
            confidence=extracted.confidence,
            relative_time_anchor=anchor,
            session_id=session_id,
            created_at=datetime.now().isoformat(),
        )
        if addressed:
            task.speaker = speaker.as_request(extracted.requested_by)
        return {"scheduled_task": task}
    except Exception as e:
        model_fallback(logger, "scheduler", e)
        return {"scheduled_task": _heuristic_for_speaker(transcript, ref_time_iso, session_id, speaker)}


# ---------------------------------------------------------------------------
# Speaker awareness
# ---------------------------------------------------------------------------

_REQUEST_LEAD = r"(?:please|pls|can you|could you|would you|remember to|don't forget to|dont forget to|remind yourself to)"
_SELF_LEAD = r"(?:remind me|i need to|i have to|i must|i'll|i will|i should|i'm going to|i am going to|let me)\b"


class _SpeakerView:
    """Who said the statement, as the pipeline knows it (role from the Bee tag, owner's first name)."""

    def __init__(self, role: str, name: Optional[str], owner: Optional[str], score: Any, source: Optional[str]):
        self.role = role if role in ("user", "contact", "unknown") else "unknown"
        self.name = (name or "").strip() or None
        self.owner = (owner or "").strip() or None
        self.score = score
        self.source = source

    @classmethod
    def from_state(cls, state: ExamenState) -> "_SpeakerView":
        return cls(state.get("speaker_role") or "unknown", state.get("speaker"), state.get("wearer_name"),
                   state.get("speaker_score"), state.get("speaker_source"))

    def prompt_section(self) -> str:
        owner = self.owner or "the owner"
        if self.role == "user":
            who = f"The speaker is the device owner ({owner}); Bee recognised their voice."
        elif self.role == "contact":
            who = (f"The speaker is NOT the device owner: it is {self.name or 'another person'}. Set for_owner=true "
                   f"only if they ask the owner ({owner}, or 'you') to do something, and set requested_by to "
                   f"their name. Their own plans ('remind me', 'I need to') are for_owner=false.")
        else:
            who = (f"The speaker was not identified: it is probably the device owner ({owner}), but it may be "
                   f"someone else. If the statement addresses the owner by name or asks them to do something "
                   f"('{owner}, remember to ...'), it is a request from another person: for_owner=true, "
                   f"requested_by = the asker's name if it is said, else null.")
        return f"\n\nSPEAKER:\n{who}\nThe title is always what the owner has to do (e.g. 'Start the washing machine').\n"

    def as_request(self, requested_by: Optional[str] = None):
        from src.core.schemas import SpeakerAttribution

        name = (requested_by or "").strip() or (self.name if self.role == "contact" else None)
        source = self.source if self.source in ("bee_voice_id", "bee_name", "history_name", "untagged",
                                                "internal") else "untagged"
        try:
            score = None if self.score is None else max(0.0, min(1.0, float(self.score)))
        except (TypeError, ValueError):
            score = None
        role = "contact" if self.role == "contact" else "unknown"
        return SpeakerAttribution(role=role, name=name, score=score if role == "contact" else None,
                                  source=source, addressed_to_user=True)


def _addressed_to_owner(text: str, owner: Optional[str]) -> bool:
    """'Damiano, remember to ...' / 'Damiano can you ...': the owner is asked to do something."""
    lower = text.strip().lower()
    if owner:
        name = re.escape(owner.strip().lower())
        if re.match(rf"^\W*(?:hey\s+|ok\s+|so\s+)?{name}\b", lower):
            return True
        if re.search(rf"\b{name}\b\W*{_REQUEST_LEAD}\b", lower):
            return True
    return False


def is_request_to_owner(text: str, owner: Optional[str]) -> bool:
    """Said by another person, is this a request for the owner? Named ('Damiano, ...') or a request lead
    ('can you ...', 'please ...', 'don't forget to ...') that is not the speaker's own plan ('remind me')."""
    if _addressed_to_owner(text, owner):
        return True
    lower = text.strip().lower()
    lower = re.sub(r"^\W*(?:please|pls)\W+", "", lower)
    if re.match(rf"^\W*{_SELF_LEAD}", lower):
        return False
    return re.match(rf"^\W*{_REQUEST_LEAD}\b", text.strip().lower()) is not None


def _strip_address(text: str, owner: Optional[str]) -> str:
    clean = text.strip()
    if owner:
        clean = re.sub(rf"^\W*(?:hey\s+|ok\s+|so\s+)?{re.escape(owner.strip())}\b[\s,!.:]*", "", clean,
                       flags=re.IGNORECASE)
    previous = None
    while previous != clean:  # "pls remember to ..." carries two lead-ins
        previous = clean
        clean = re.sub(rf"^{_REQUEST_LEAD}[\s,]+", "", clean, flags=re.IGNORECASE).strip()
    return clean or text.strip()


def _heuristic_for_speaker(transcript: str, ref_time_iso: Optional[str], session_id: Optional[str],
                           speaker: _SpeakerView) -> Optional[PlannedTask]:
    # The owner talking to themselves ("Damiano, remember ...") is still their own task
    addressed = speaker.role != "user" and _addressed_to_owner(transcript, speaker.owner)
    if speaker.role == "contact":
        if not is_request_to_owner(transcript, speaker.owner):
            return None  # another person's own plan
        addressed = True
    text = _strip_address(transcript, speaker.owner) if addressed else transcript
    task = _heuristic_extract_scheduled_task(text, ref_time_iso, session_id)
    if task is not None:
        task.raw_statement = transcript.strip()
        if addressed:
            task.speaker = speaker.as_request()
            if task.speaker.name:  # "can you call me" from Marco: the owner calls Marco
                task.title = re.sub(r"\bme\b", task.speaker.name, task.title, flags=re.IGNORECASE)
    return task
