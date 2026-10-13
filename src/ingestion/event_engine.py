"""Deep Topic Event Engine — Phase A (time & lifecycle foundations).

Groups the stream of short Bee utterances into macro events (lectures, meetings, talks),
splits them into segments at pauses/checkpoints and schedules synthesis per segment and per
event, instead of researching every deep_topic utterance in isolation.

Specification: docs/next_steps/deep_topic_event_engine/
  - 01_event_model_and_state_machine.md  (rules R0-R8 implemented here; R7/R9 arrive in Phase C)
  - 03_synthesis_scheduling.md           (segment / checkpoint / final synthesis)
  - 05_ingestion_and_pipeline_integration.md

Phase A scope: decisions use time, GPS and explicit cues only. A paused event always
resumes when on-topic content returns within T_hard (topic-based splitting is Phase C).
"""

from __future__ import annotations

import asyncio
import logging
import re
import statistics
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

from src.core.config import Settings, settings
from src.core.schemas import (
    BriefingReport,
    EventTransitionLog,
    SessionDossier,
    SessionSegment,
    UtteranceChunk,
)
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore
from src.ingestion.session_manager import calculate_haversine_distance

logger = logging.getLogger("examen.ingestion.event_engine")

Clock = Callable[[], float]
Listener = Callable[[str, Dict[str, Any]], None]
Synthesizer = Callable[[str, str], Optional[BriefingReport]]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineConfig:
    t_soft: float = 300.0
    t_hard: float = 1800.0
    t_hard_after_close_cue: float = 300.0
    t_hard_transit: float = 120.0
    t_checkpoint: float = 1200.0
    min_segment_words: int = 300
    location_shift_meters: float = 400.0
    tick_seconds: float = 15.0
    synthesis_max_words: int = 6000
    max_job_attempts: int = 3

    @classmethod
    def demo(cls) -> "EngineConfig":
        """Compressed timings so the full lifecycle fits in a short live demo."""
        return cls(
            t_soft=20.0,
            t_hard=90.0,
            t_hard_after_close_cue=15.0,
            t_hard_transit=10.0,
            t_checkpoint=120.0,
            min_segment_words=30,
            tick_seconds=2.0,
        )

    @classmethod
    def from_settings(cls, cfg: Optional[Settings] = None) -> "EngineConfig":
        s = cfg or settings
        if s.event_profile == "demo":
            return cls.demo()
        return cls(
            t_soft=s.event_t_soft_seconds,
            t_hard=s.event_t_hard_seconds,
            t_hard_after_close_cue=s.event_t_hard_after_close_cue_seconds,
            t_hard_transit=s.event_t_hard_transit_seconds,
            t_checkpoint=s.event_t_checkpoint_seconds,
            min_segment_words=s.event_min_segment_words,
            location_shift_meters=s.event_location_shift_meters,
            tick_seconds=s.event_tick_seconds,
            synthesis_max_words=s.event_synthesis_max_words,
        )


# ---------------------------------------------------------------------------
# Cue lexicon (doc 01 §4.1). Deliberately stricter than the legacy closing regex
# in session_manager.py: "we can conclude that ..." must not end a lecture.
# ---------------------------------------------------------------------------

_PAUSE_CUE_PATTERNS = [
    r"\b(?:facciamo|prendiamo(?:ci)?|faccio)\s+(?:una\s+)?(?:breve\s+|piccola\s+)?pausa\b",
    r"\b(?:\d+|cinque|dieci|quindici|venti)\s+minuti\s+di\s+pausa\b",
    r"\bpausa\s+caff[eè]\b",
    r"\b(?:let'?s\s+)?take\s+(?:a\s+)?(?:short\s+|quick\s+|\d+[- ]minutes?\s+)?break\b",
    r"\blet'?s\s+take\s+(?:five|ten)\b",
    r"\b(?:short|coffee|quick)\s+break\b",
]

_CLOSING_CUE_PATTERNS = [
    r"\bthat\s+concludes\s+(?:today'?s|the|our|this)\b",
    r"\b(?:meeting|session|lecture|class)\s+is\s+(?:adjourned|over|finished)\b",
    r"\blet'?s\s+call\s+it\s+a\s+day\b",
    r"\bthat'?s\s+(?:all|it)\s+for\s+today\b",
    r"\bsee\s+you\s+(?:next\s+(?:week|time|class|lecture)|on\s+(?:monday|tuesday|wednesday|thursday|friday))\b",
    r"\bper\s+oggi\s+(?:è|e'|e)\s+tutto\b",
    r"\bci\s+vediamo\s+(?:la\s+prossima|alla\s+prossima|domani|luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì])\b",
    r"\b(?:fine|chiudiamo|concludiamo)\s+(?:la\s+|qui\s+la\s+)?(?:riunione|lezione|seduta)\b",
    r"\bla\s+(?:lezione|riunione)\s+(?:è|e')\s+(?:finita|conclusa|terminata)\b",
]

_PAUSE_CUE_RE = re.compile("|".join(_PAUSE_CUE_PATTERNS), re.IGNORECASE)
_CLOSING_CUE_RE = re.compile("|".join(_CLOSING_CUE_PATTERNS), re.IGNORECASE)


def detect_cues(text: str) -> Tuple[bool, bool]:
    """Returns (pause_cue, closing_cue) for an utterance."""
    if not text:
        return False, False
    closing = bool(_CLOSING_CUE_RE.search(text))
    pause = bool(_PAUSE_CUE_RE.search(text))
    return pause and not closing, closing


# ---------------------------------------------------------------------------
# Time helpers (engine works on epoch seconds, storage on ISO strings)
# ---------------------------------------------------------------------------

def to_epoch(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).isoformat()


# ---------------------------------------------------------------------------
# Pure decision logic (doc 01 §3, §5) — no I/O, fully unit-testable
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EventSnapshot:
    """Minimal view of the open event used by the decision functions."""
    status: Optional[str] = None            # None (no open event) | "active" | "paused"
    last_on_topic_at: Optional[float] = None
    paused_at: Optional[float] = None
    hard_close_deadline: Optional[float] = None
    segment_start: Optional[float] = None   # start of the open segment, if any
    segment_words: int = 0

    def effective_deadline(self, cfg: EngineConfig) -> Optional[float]:
        if self.status != "paused" or self.paused_at is None:
            return None
        deadline = self.paused_at + cfg.t_hard
        if self.hard_close_deadline is not None:
            deadline = min(deadline, self.hard_close_deadline)
        return deadline


@dataclass(frozen=True)
class ChunkSignal:
    ts: float
    on_topic: bool
    pause_cue: bool = False
    closing_cue: bool = False
    location_shift: bool = False
    transit: bool = False


@dataclass(frozen=True)
class Transition:
    rule: str
    to_status: str          # "active" | "paused" | "concluded"
    reason: str
    at: float
    detail: str = ""
    new_deadline: Optional[float] = None


def next_pre_chunk_transition(
    snap: EventSnapshot, sig: ChunkSignal, cfg: EngineConfig
) -> Optional[Transition]:
    """Transitions to apply BEFORE the chunk is appended (catch-up timers, location, open/resume)."""
    if snap.status in ("active", "paused") and sig.location_shift:
        return Transition("R6", "concluded", "location_shift", sig.ts, "Wearer moved away from the event location")

    if snap.status == "active":
        if snap.last_on_topic_at is not None and sig.ts - snap.last_on_topic_at >= cfg.t_soft:
            at = snap.last_on_topic_at + cfg.t_soft
            return Transition("R1", "paused", "soft_timeout", at,
                              f"No on-topic speech for {sig.ts - snap.last_on_topic_at:.0f}s (>= {cfg.t_soft:.0f}s)")
        return None

    if snap.status == "paused":
        deadline = snap.effective_deadline(cfg)
        if deadline is not None and sig.ts >= deadline:
            return Transition("R5", "concluded", "hard_timeout", deadline, "Pause exceeded the hard-close deadline")
        if sig.transit:
            candidate = sig.ts + cfg.t_hard_transit
            if snap.hard_close_deadline is None or candidate < snap.hard_close_deadline:
                return Transition("R5", "paused", "transit_deadline", sig.ts,
                                  "Wearer is in transit: hard close brought forward", new_deadline=candidate)
        if sig.on_topic:
            return Transition("R4", "active", "resume_on_topic", sig.ts, "On-topic speech returned within T_hard")
        return None

    if sig.on_topic:
        return Transition("R0", "active", "open", sig.ts, "First on-topic speech")
    return None


def next_post_chunk_transition(
    snap: EventSnapshot, sig: ChunkSignal, cfg: EngineConfig
) -> Optional[Transition]:
    """Transitions to apply AFTER the chunk is appended (explicit cues, checkpoint)."""
    if snap.status != "active":
        return None
    if sig.closing_cue:
        return Transition("R2", "paused", "closing_cue", sig.ts, "Explicit closing phrase",
                          new_deadline=sig.ts + cfg.t_hard_after_close_cue)
    if sig.pause_cue:
        return Transition("R2", "paused", "pause_cue", sig.ts, "Explicit pause phrase")
    return _checkpoint_transition(snap, sig.ts, cfg)


def next_tick_transition(snap: EventSnapshot, now: float, cfg: EngineConfig) -> Optional[Transition]:
    """Time-based transitions that must fire even when no audio arrives."""
    if snap.status == "active":
        if snap.last_on_topic_at is not None and now - snap.last_on_topic_at >= cfg.t_soft:
            return Transition("R1", "paused", "soft_timeout", snap.last_on_topic_at + cfg.t_soft,
                              f"No on-topic speech for {cfg.t_soft:.0f}s")
        return _checkpoint_transition(snap, now, cfg)
    if snap.status == "paused":
        deadline = snap.effective_deadline(cfg)
        if deadline is not None and now >= deadline:
            return Transition("R5", "concluded", "hard_timeout", deadline, "Pause exceeded the hard-close deadline")
    return None


def _checkpoint_transition(snap: EventSnapshot, now: float, cfg: EngineConfig) -> Optional[Transition]:
    if (
        snap.segment_start is not None
        and now - snap.segment_start >= cfg.t_checkpoint
        and snap.segment_words >= cfg.min_segment_words
    ):
        return Transition("R3", "active", "checkpoint", now,
                          f"Continuous on-topic segment reached {cfg.t_checkpoint:.0f}s")
    return None


def is_displaced(anchor: Optional[dict], location: Optional[dict], threshold_m: float) -> bool:
    """Accuracy-aware displacement test (doc 01 §4.2)."""
    if not anchor or not location:
        return False
    try:
        lat1, lon1 = float(anchor["latitude"]), float(anchor["longitude"])
        lat2, lon2 = float(location["latitude"]), float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    distance = calculate_haversine_distance(lat1, lon1, lat2, lon2)
    slack = float(anchor.get("accuracy_meters") or 0.0) + float(location.get("accuracy_meters") or 0.0)
    return distance - slack >= threshold_m


# ---------------------------------------------------------------------------
# Synthesis jobs
# ---------------------------------------------------------------------------

@dataclass
class SynthesisJob:
    kind: str                      # "segment" | "final"
    session_id: str
    segment_id: Optional[str] = None
    attempts: int = 0

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.kind, self.session_id, self.segment_id or "")


def default_synthesizer(text: str, session_id: str) -> Optional[BriefingReport]:
    """Runs Stage 3C (topic extraction + web research + synthesis) on aggregated event text."""
    from src.pipeline.nodes.topic_research import node_topic_research

    result = node_topic_research({
        "raw_transcript": text,
        "session_id": session_id,
        "categories": ["deep_topic"],
    })
    return result.get("briefing_report")


_CONTEXT_TYPE_TO_DOMAIN = {
    "academic_lecture": "lecture",
    "general_meeting": "meeting",
    "feature_discussion": "technical_debate",
    "tech_stack": "technical_debate",
    "bug": "technical_debate",
    "system_incident": "technical_debate",
}

_PLACEHOLDER_TITLE_PREFIX = "Ongoing session"


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    half = max_words // 2
    return " ".join(words[:half]) + " [...] " + " ".join(words[-half:])


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class ChunkOutcome:
    event_id: Optional[str]
    event_status: Optional[str]
    on_topic: bool
    transitions: List[Transition] = field(default_factory=list)

    @property
    def event_managed(self) -> bool:
        return self.event_id is not None


class EventEngine:
    """Stateful lifecycle manager for deep_topic events (one wearer, at most one open event)."""

    def __init__(
        self,
        store: Optional[AbstractContextStore] = None,
        config: Optional[EngineConfig] = None,
        clock: Optional[Clock] = None,
        synthesizer: Optional[Synthesizer] = None,
    ):
        self._store = store
        self.config = config or EngineConfig.from_settings()
        self.clock: Clock = clock or time.time
        self.synthesizer: Synthesizer = synthesizer or default_synthesizer
        self._lock = threading.RLock()
        self._current: Optional[SessionDossier] = None
        self._last_seen_ts: float = 0.0
        self._jobs: Deque[SynthesisJob] = deque()
        self._job_keys: Set[Tuple[str, str, str]] = set()
        self._listeners: List[Listener] = []
        self._shift_strikes = 0
        self._last_fix_key: Optional[Tuple[Any, Any, Any]] = None
        self._last_fix_verdict = False
        self._anchor_samples: List[dict] = []
        self._rehydrated = False

    # -- infrastructure ------------------------------------------------------

    @property
    def store(self) -> AbstractContextStore:
        # Resolve the global store lazily on every access unless one was injected, so that a
        # replaced store singleton (tests, /reset-db) is picked up.
        return self._store if self._store is not None else get_storage_store()

    def add_listener(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event_type, payload)
            except Exception as e:
                logger.debug(f"Event listener error for '{event_type}': {e}")

    def now(self) -> float:
        """Engine time: never behind the latest utterance seen (supports virtual clocks)."""
        return max(self.clock(), self._last_seen_ts)

    def rehydrate(self) -> None:
        """Restores the open event and re-enqueues interrupted synthesis jobs after a restart."""
        with self._lock:
            if self._rehydrated:
                return
            self._rehydrated = True
            try:
                self._current = self.store.get_open_event()
            except NotImplementedError:
                self._current = None
            if self._current:
                for seg in self._current.segments:
                    if seg.status in ("closed", "synthesizing"):
                        self._enqueue(SynthesisJob("segment", self._current.session_id, seg.segment_id))
            try:
                for ev in self.store.list_events_pending_final():
                    for seg in ev.segments:
                        if seg.status in ("closed", "synthesizing"):
                            self._enqueue(SynthesisJob("segment", ev.session_id, seg.segment_id))
                    self._enqueue(SynthesisJob("final", ev.session_id))
            except NotImplementedError:
                pass

    # -- public queries -------------------------------------------------------

    def current_event(self) -> Optional[SessionDossier]:
        self.rehydrate()
        return self._current

    def current_event_id(self) -> Optional[str]:
        ev = self.current_event()
        return ev.session_id if ev else None

    def status_summary(self) -> Dict[str, Any]:
        ev = self.current_event()
        if not ev:
            return {"active_event": None, "pending_jobs": len(self._jobs)}
        seg = ev.open_segment
        return {
            "active_event": {
                "session_id": ev.session_id,
                "title": ev.title,
                "status": ev.status,
                "segments": len(ev.segments),
                "open_segment_words": seg.word_count if seg else 0,
                "last_on_topic_at": ev.last_on_topic_at,
                "paused_at": ev.paused_at,
            },
            "pending_jobs": len(self._jobs),
        }

    # -- inputs ---------------------------------------------------------------

    def record_chunk(self, chunk: UtteranceChunk) -> ChunkOutcome:
        """Feeds one screened utterance (chunk.categories must be set) into the lifecycle."""
        self.rehydrate()
        ts = to_epoch(chunk.timestamp) or self.clock()
        on_topic = "deep_topic" in (chunk.categories or [])
        pause_cue, closing_cue = detect_cues(chunk.text)
        applied: List[Transition] = []

        with self._lock:
            self._last_seen_ts = max(self._last_seen_ts, ts)
            sig = ChunkSignal(
                ts=ts,
                on_topic=on_topic,
                pause_cue=pause_cue,
                closing_cue=closing_cue,
                location_shift=self._location_shift_confirmed(chunk.location),
                transit=bool(chunk.location and chunk.location.get("semantic_zone") == "transit"),
            )

            for _ in range(6):
                t = next_pre_chunk_transition(self._snapshot(), sig, self.config)
                if not t:
                    break
                self._apply(t, chunk=chunk)
                applied.append(t)
                if t.rule == "R6":
                    # A location shift is consumed by the conclusion; the next event re-anchors
                    sig = replace(sig, location_shift=False)

            if self._current is not None:
                self._append(chunk, ts, on_topic)
                for _ in range(3):
                    t = next_post_chunk_transition(self._snapshot(), sig, self.config)
                    if not t:
                        break
                    self._apply(t, chunk=chunk)
                    applied.append(t)

            if self._current is not None:
                self._save(self._current)

            ev = self._current
            return ChunkOutcome(
                event_id=ev.session_id if ev else None,
                event_status=ev.status if ev else None,
                on_topic=on_topic,
                transitions=applied,
            )

    def tick(self, now: Optional[float] = None) -> List[Transition]:
        """Evaluates time-based rules (R1, R3, R5). Call periodically."""
        self.rehydrate()
        now = self.now() if now is None else now
        applied: List[Transition] = []
        with self._lock:
            for _ in range(4):
                if self._current is None:
                    break
                t = next_tick_transition(self._snapshot(), now, self.config)
                if not t:
                    break
                self._apply(t)
                applied.append(t)
            if self._current is not None and applied:
                self._save(self._current)
        return applied

    def on_location(self, location: Optional[dict], now: Optional[float] = None) -> List[Transition]:
        """Handles standalone GPS fixes (Bee update-location) so walking away closes a silent event."""
        self.rehydrate()
        if not location:
            return []
        now = self.now() if now is None else now
        applied: List[Transition] = []
        with self._lock:
            if self._current is None:
                return []
            if self._location_shift_confirmed(location):
                t = Transition("R6", "concluded", "location_shift", now, "Wearer moved away from the event location")
                self._apply(t)
                applied.append(t)
            elif self._current.status == "paused" and location.get("semantic_zone") == "transit":
                snap = self._snapshot()
                candidate = now + self.config.t_hard_transit
                if snap.hard_close_deadline is None or candidate < snap.hard_close_deadline:
                    t = Transition("R5", "paused", "transit_deadline", now,
                                   "Wearer is in transit: hard close brought forward", new_deadline=candidate)
                    self._apply(t)
                    applied.append(t)
            if self._current is not None and applied:
                self._save(self._current)
        return applied

    def conclude(self, session_id: str, now: Optional[float] = None) -> Optional[SessionDossier]:
        """Manual conclusion (R8). Works for the open event and for stray active/paused rows."""
        self.rehydrate()
        now = self.now() if now is None else now
        with self._lock:
            t = Transition("R8", "concluded", "manual", now, "Concluded manually")
            if self._current is not None and self._current.session_id == session_id:
                dossier = self._current
                self._apply(t)
                return dossier
            dossier = self.store.get_session_dossier(session_id)
            if dossier is None:
                return None
            if dossier.status != "concluded":
                self._conclude(dossier, t)
                self._save(dossier)
            elif dossier.segments and dossier.final_status in ("none", "failed"):
                dossier.final_status = "pending"
                self._save(dossier)
                self._enqueue(SynthesisJob("final", session_id))
            return dossier

    # -- state mutation -------------------------------------------------------

    def _snapshot(self) -> EventSnapshot:
        ev = self._current
        if ev is None:
            return EventSnapshot()
        seg = ev.open_segment
        return EventSnapshot(
            status=ev.status,
            last_on_topic_at=to_epoch(ev.last_on_topic_at),
            paused_at=to_epoch(ev.paused_at),
            hard_close_deadline=to_epoch(ev.hard_close_deadline),
            segment_start=to_epoch(seg.start_time) if seg else None,
            segment_words=seg.word_count if seg else 0,
        )

    def _apply(self, t: Transition, chunk: Optional[UtteranceChunk] = None) -> None:
        if t.rule == "R0":
            self._open(t, chunk)
            return

        ev = self._current
        if ev is None:
            return
        from_status = ev.status

        if t.to_status == "concluded":
            self._conclude(ev, t)
            self._save(ev)
            self._current = None
            return

        if t.rule in ("R1", "R2"):
            self._close_open_segment(ev, t.reason, t.at)
            ev.status = "paused"
            ev.paused_at = to_iso(t.at)
            if t.new_deadline is not None:
                ev.hard_close_deadline = to_iso(t.new_deadline)
            self._log(ev, from_status, t)
            self._emit("event_paused", self._summary(ev))
        elif t.rule == "R3":
            self._close_open_segment(ev, t.reason, t.at, kind="checkpoint")
            self._open_segment(ev, t.at)
            self._log(ev, from_status, t)
            self._emit("event_checkpoint", self._summary(ev))
        elif t.rule == "R4":
            ev.status = "active"
            ev.paused_at = None
            ev.hard_close_deadline = None
            ev.last_on_topic_at = to_iso(t.at)
            self._open_segment(ev, t.at)
            self._log(ev, from_status, t)
            self._emit("event_resumed", self._summary(ev))
        elif t.reason == "transit_deadline" and t.new_deadline is not None:
            ev.hard_close_deadline = to_iso(t.new_deadline)
            self._log(ev, from_status, t)

    def _open(self, t: Transition, chunk: Optional[UtteranceChunk]) -> None:
        start_iso = to_iso(t.at)
        location = chunk.location if chunk else None
        ev = SessionDossier(
            session_id=str(uuid.uuid4()),
            title=f"{_PLACEHOLDER_TITLE_PREFIX} ({datetime.fromtimestamp(t.at).strftime('%H:%M')})",
            domain="general",
            start_time=start_iso,
            last_updated_at=start_iso,
            status="active",
            location=location,
            anchor_location=location,
            last_on_topic_at=start_iso,
            conversation_uuids=[chunk.conversation_uuid] if chunk else [],
        )
        self._open_segment(ev, t.at)
        self._log(ev, None, t)
        self._current = ev
        self._shift_strikes = 0
        self._last_fix_key = self._fix_key(location) if location else None
        self._last_fix_verdict = False
        self._anchor_samples = [location] if location else []
        self._save(ev)
        self._emit("event_opened", self._summary(ev))

    def _open_segment(self, ev: SessionDossier, at: float) -> None:
        ev.segments.append(SessionSegment(index=len(ev.segments) + 1, start_time=to_iso(at)))

    def _close_open_segment(self, ev: SessionDossier, reason: str, at: float, kind: str = "segment") -> None:
        seg = ev.open_segment
        if seg is None:
            return
        seg.status = "closed"
        seg.kind = kind  # type: ignore[assignment]
        seg.close_reason = reason
        seg.end_time = seg.end_time or to_iso(at)
        self._enqueue(SynthesisJob("segment", ev.session_id, seg.segment_id))

    def _conclude(self, ev: SessionDossier, t: Transition) -> None:
        from_status = ev.status
        self._close_open_segment(ev, t.reason, t.at)
        ev.status = "concluded"
        ev.concluded_at = to_iso(t.at)
        ev.paused_at = None
        if ev.segments:
            ev.final_status = "pending"
            self._enqueue(SynthesisJob("final", ev.session_id))
        self._log(ev, from_status, t)
        self._emit("event_concluded", self._summary(ev))

    def _append(self, chunk: UtteranceChunk, ts: float, on_topic: bool) -> None:
        ev = self._current
        assert ev is not None
        seg = ev.open_segment if ev.status == "active" else None
        self.store.append_session_chunk(
            chunk, ev.session_id, seg.segment_id if seg else None, on_topic=on_topic and seg is not None
        )
        if seg is not None:
            seg.word_count += len(chunk.text.split())
            seg.end_time = to_iso(ts)
        if on_topic and ev.status == "active":
            ev.last_on_topic_at = to_iso(ts)
        if chunk.conversation_uuid and chunk.conversation_uuid not in ev.conversation_uuids:
            ev.conversation_uuids.append(chunk.conversation_uuid)
        if chunk.location:
            ev.location = chunk.location
            self._update_anchor(ev, chunk.location)
        ev.last_updated_at = datetime.now().isoformat()

    def _update_anchor(self, ev: SessionDossier, location: dict) -> None:
        """Anchor = median of fixes collected during the first segment (doc 01 §4.2)."""
        if len(ev.segments) != 1 or "latitude" not in location or "longitude" not in location:
            return
        if self._anchor_samples and self._fix_key(self._anchor_samples[-1]) == self._fix_key(location):
            return  # same fix repeated on consecutive utterances
        self._anchor_samples.append(location)
        try:
            lat = statistics.median(float(s["latitude"]) for s in self._anchor_samples)
            lon = statistics.median(float(s["longitude"]) for s in self._anchor_samples)
        except (KeyError, TypeError, ValueError):
            return
        accuracies = [float(s.get("accuracy_meters") or 0.0) for s in self._anchor_samples]
        ev.anchor_location = {
            "latitude": lat,
            "longitude": lon,
            "accuracy_meters": statistics.median(accuracies) if accuracies else None,
            "place_name": location.get("place_name"),
        }

    @staticmethod
    def _fix_key(location: dict) -> Tuple[Any, Any, Any]:
        return (location.get("latitude"), location.get("longitude"), location.get("accuracy_meters"))

    def _location_shift_confirmed(self, location: Optional[dict]) -> bool:
        ev = self._current
        if ev is None or not location:
            return False
        # Every chunk carries the latest known fix: only a *new* fix may add a strike, otherwise a
        # single bad fix repeated on two utterances would count as two confirmations.
        key = self._fix_key(location)
        if key == self._last_fix_key:
            return self._last_fix_verdict
        self._last_fix_key = key
        if not is_displaced(ev.anchor_location, location, self.config.location_shift_meters):
            self._shift_strikes = 0
            self._last_fix_verdict = False
            return False
        self._shift_strikes += 1
        # One displaced fix is enough when the wearer is clearly travelling
        self._last_fix_verdict = self._shift_strikes >= 2 or location.get("semantic_zone") == "transit"
        return self._last_fix_verdict

    def _log(self, ev: SessionDossier, from_status: Optional[str], t: Transition) -> None:
        ev.transitions.append(EventTransitionLog(
            at=to_iso(t.at),
            from_status=from_status,
            to_status=t.to_status,
            rule=t.rule,
            reason=t.reason,
            detail=t.detail or None,
        ))
        logger.info(f"[event {ev.session_id[:8]}] {t.rule} {from_status} -> {t.to_status} ({t.reason})")

    def _save(self, ev: SessionDossier) -> None:
        # Micro-events are linked by the pipeline directly in the store: merge them so the
        # engine's in-memory copy never drops links written in the meantime.
        try:
            persisted = self.store.get_session_dossier(ev.session_id)
        except NotImplementedError:
            persisted = None
        if persisted is not None:
            known = {(e.event_type, e.record_id) for e in ev.linked_micro_events}
            for ref in persisted.linked_micro_events:
                if (ref.event_type, ref.record_id) not in known:
                    ev.linked_micro_events.append(ref)
        self.store.save_session_dossier(ev)

    @staticmethod
    def _summary(ev: SessionDossier) -> Dict[str, Any]:
        return {
            "session_id": ev.session_id,
            "title": ev.title,
            "status": ev.status,
            "final_status": ev.final_status,
            "segments": [
                {"index": s.index, "status": s.status, "title": s.title, "start_time": s.start_time,
                 "end_time": s.end_time, "word_count": s.word_count, "briefing_id": s.briefing_id}
                for s in ev.segments
            ],
            "last_transition": ev.transitions[-1].model_dump() if ev.transitions else None,
        }

    # -- synthesis jobs ---------------------------------------------------------

    def _enqueue(self, job: SynthesisJob) -> None:
        if job.key in self._job_keys:
            return
        self._job_keys.add(job.key)
        self._jobs.append(job)

    def pending_jobs(self) -> int:
        return len(self._jobs)

    def pop_job(self) -> Optional[SynthesisJob]:
        with self._lock:
            if not self._jobs:
                return None
            job = self._jobs.popleft()
            self._job_keys.discard(job.key)
            return job

    def run_pending_jobs_sync(self, max_jobs: Optional[int] = None) -> int:
        """Runs queued synthesis jobs inline (tests, CLI tools). Returns jobs executed."""
        done = 0
        while max_jobs is None or done < max_jobs:
            job = self.pop_job()
            if job is None:
                break
            self.run_job(job)
            done += 1
        return done

    def run_job(self, job: SynthesisJob) -> None:
        """Executes one job; failures are retried up to config.max_job_attempts."""
        job.attempts += 1
        try:
            if job.kind == "segment":
                self._run_segment_job(job.session_id, job.segment_id or "")
            else:
                self._run_final_job(job.session_id)
        except Exception as e:
            logger.error(f"Synthesis job {job.key} failed (attempt {job.attempts}): {e}", exc_info=True)
            if job.attempts < self.config.max_job_attempts:
                with self._lock:
                    self._enqueue(job)
            else:
                self._mark_job_failed(job)

    def _load(self, session_id: str) -> Optional[SessionDossier]:
        if self._current is not None and self._current.session_id == session_id:
            return self._current
        return self.store.get_session_dossier(session_id)

    def _segment_text(self, session_id: str, segment_id: Optional[str]) -> str:
        chunks = self.store.list_session_chunks(
            session_id, segment_id=segment_id, in_segments_only=segment_id is None
        )
        return " ".join(c.text.strip() for c in chunks if c.text and c.text.strip())

    def _run_segment_job(self, session_id: str, segment_id: str) -> None:
        with self._lock:
            ev = self._load(session_id)
            seg = next((s for s in ev.segments if s.segment_id == segment_id), None) if ev else None
            if ev is None or seg is None or seg.status not in ("closed", "synthesizing", "failed"):
                return
            if seg.word_count < self.config.min_segment_words:
                seg.status = "skipped"
                self._save(ev)
                self._emit("segment_skipped", self._summary(ev))
                return
            seg.status = "synthesizing"
            self._save(ev)
        self._emit("segment_synthesizing", {"session_id": session_id, "segment_id": segment_id})

        text = _truncate_words(self._segment_text(session_id, segment_id), self.config.synthesis_max_words)
        briefing = self.synthesizer(text, session_id)
        if briefing is None:
            raise RuntimeError("Synthesizer returned no briefing")

        with self._lock:
            ev = self._load(session_id)
            seg = next((s for s in ev.segments if s.segment_id == segment_id), None) if ev else None
            if ev is None or seg is None:
                return
            briefing.id = None
            briefing.session_id = session_id
            briefing.segment_id = segment_id
            briefing.kind = "checkpoint" if seg.kind == "checkpoint" else "segment"
            seg.briefing_id = self.store.save_topic_briefing(briefing)
            seg.title = briefing.topic_title
            seg.status = "synthesized"
            self._adopt_title_and_domain(ev, briefing)
            if briefing.topic_title and briefing.topic_title not in ev.key_discussion_points:
                ev.key_discussion_points.append(briefing.topic_title)
            self._save(ev)
            payload = self._summary(ev)
        payload["briefing"] = briefing.model_dump()
        self._emit("segment_synthesized", payload)

    def _run_final_job(self, session_id: str) -> None:
        # Make sure every segment had its chance first (ordering guarantee, restart safety)
        ev = self._load(session_id)
        if ev is None:
            return
        for seg in list(ev.segments):
            if seg.status in ("closed", "synthesizing"):
                self._run_segment_job(session_id, seg.segment_id)

        with self._lock:
            ev = self._load(session_id)
            if ev is None or ev.status != "concluded" or ev.final_status == "ready":
                return
            ev.final_status = "synthesizing"
            self._save(ev)
            segments = list(ev.segments)

        synthesized = [s for s in segments if s.status == "synthesized" and s.briefing_id]
        unsynthesized_text = " ".join(
            self._segment_text(session_id, s.segment_id) for s in segments if s.status in ("skipped", "failed")
        ).strip()

        final: Optional[BriefingReport] = None
        if len(synthesized) == 1 and len(unsynthesized_text.split()) < self.config.min_segment_words:
            # Single-segment shortcut: promote the segment briefing, no extra LLM call
            final = self.store.get_topic_briefing(synthesized[0].briefing_id)
        elif synthesized:
            parts: List[str] = []
            for seg in synthesized:
                b = self.store.get_topic_briefing(seg.briefing_id)
                if not b:
                    continue
                bullets = " ".join(b.executive_summary)
                parts.append(f"Part {seg.index}: {b.topic_title}. {bullets} {b.explanatory_synthesis}")
            if unsynthesized_text:
                parts.append(unsynthesized_text)
            final = self.synthesizer(
                _truncate_words("\n".join(parts), self.config.synthesis_max_words), session_id
            )
        else:
            all_text = self._segment_text(session_id, None)
            if not all_text.strip():
                with self._lock:
                    ev = self._load(session_id)
                    if ev is not None:
                        ev.final_status = "none"
                        self._save(ev)
                return
            final = self.synthesizer(_truncate_words(all_text, self.config.synthesis_max_words), session_id)

        if final is None:
            raise RuntimeError("Synthesizer returned no final briefing")

        with self._lock:
            ev = self._load(session_id)
            if ev is None:
                return
            final = final.model_copy(deep=True)
            final.id = None
            final.session_id = session_id
            final.segment_id = None
            final.kind = "final"
            final.created_at = datetime.now().isoformat()
            final_id = self.store.save_topic_briefing(final)
            ev.final_briefing_id = final_id
            ev.briefing_report = final
            ev.final_status = "ready"
            ev.final_revision += 1
            self._adopt_title_and_domain(ev, final)
            self._save(ev)
            payload = self._summary(ev)
        payload["final_briefing"] = final.model_dump()
        self._emit("event_final_ready", payload)
        self._emit("session_concluded", payload)  # legacy alias (one release)

    def _mark_job_failed(self, job: SynthesisJob) -> None:
        with self._lock:
            ev = self._load(job.session_id)
            if ev is None:
                return
            if job.kind == "segment":
                for seg in ev.segments:
                    if seg.segment_id == job.segment_id:
                        seg.status = "failed"
            else:
                ev.final_status = "failed"
            self._save(ev)

    @staticmethod
    def _adopt_title_and_domain(ev: SessionDossier, briefing: BriefingReport) -> None:
        if briefing.topic_title and (not ev.title or ev.title.startswith(_PLACEHOLDER_TITLE_PREFIX)):
            ev.title = briefing.topic_title
        domain = _CONTEXT_TYPE_TO_DOMAIN.get(briefing.context_type)
        if domain and ev.domain == "general":
            ev.domain = domain  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Async runtime (tick loop + synthesis worker) and singletons
# ---------------------------------------------------------------------------

class EventEngineRuntime:
    """Drives an EventEngine inside an asyncio loop: periodic ticks and off-thread synthesis."""

    def __init__(self, engine: EventEngine):
        self.engine = engine
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tick_task: Optional[asyncio.Task] = None
        self._worker_task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return bool(self._tick_task and not self._tick_task.done())

    def ensure_started(self) -> bool:
        """Starts the background tasks on the running loop (idempotent). Returns True if running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        if self.running and self._loop is loop:
            return True
        self._loop = loop
        self.engine.rehydrate()
        self._tick_task = loop.create_task(self._tick_loop())
        self._worker_task = loop.create_task(self._worker_loop())
        return True

    def add_listener(self, listener: Listener) -> None:
        """Registers a listener that is always invoked on the event loop thread."""
        def _threadsafe(event_type: str, payload: Dict[str, Any]) -> None:
            loop = self._loop
            if loop is None or loop.is_closed():
                listener(event_type, payload)
                return
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                listener(event_type, payload)
            else:
                loop.call_soon_threadsafe(listener, event_type, payload)

        self.engine.add_listener(_threadsafe)

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(self.engine.config.tick_seconds)
            try:
                self.engine.tick()
            except Exception as e:
                logger.error(f"Event engine tick failed: {e}", exc_info=True)

    async def _worker_loop(self) -> None:
        while True:
            job = self.engine.pop_job()
            if job is None:
                await asyncio.sleep(0.5)
                continue
            await asyncio.to_thread(self.engine.run_job, job)

    def stop(self) -> None:
        for task in (self._tick_task, self._worker_task):
            if task and not task.done():
                task.cancel()


_engine: Optional[EventEngine] = None
_runtime: Optional[EventEngineRuntime] = None


def get_event_engine() -> EventEngine:
    global _engine
    if _engine is None:
        _engine = EventEngine()
    return _engine


def get_event_engine_runtime() -> EventEngineRuntime:
    global _runtime
    if _runtime is None:
        _runtime = EventEngineRuntime(get_event_engine())
    return _runtime
