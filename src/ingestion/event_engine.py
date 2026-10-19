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
from typing import Any, Callable, Deque, Dict, List, Optional, Protocol, Set, Tuple

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
from src.ingestion.topic_continuity import ContinuityConfig, SimilarityScore, TopicSimilarity

logger = logging.getLogger("examen.ingestion.event_engine")

Clock = Callable[[], float]
Listener = Callable[[str, Dict[str, Any]], None]


class Synthesizer(Protocol):
    """Produces event briefings. Implementations may return a BriefingReport or an object with
    `.briefing` and `.research` (ledger entries), e.g. topic_research.SynthesisOutcome."""

    def segment(self, text: str, session_id: str, outline: Any = None, kind: str = "segment") -> Any: ...

    def final(
        self, parts: List[BriefingReport], extra_text: str, session_id: str,
        outline: Any = None, micro_events: Optional[List[Any]] = None,
    ) -> Any: ...


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
    def from_settings(cls, cfg: Optional[Settings] = None, ignore_demo_profile: bool = False) -> "EngineConfig":
        """ignore_demo_profile: history replays real time, so compressed demo timers would split it."""
        s = cfg or settings
        if s.event_profile == "demo" and not ignore_demo_profile:
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

_RESUME_CUE_PATTERNS = [
    r"\briprendiamo\b",
    r"\bdove\s+eravamo(?:\s+rimasti)?\b",
    r"\btorniamo\s+(?:a|al|alla|allo|ai|agli|alle|all')\b",
    r"\blet'?s\s+get\s+back\b",
    r"\bwhere\s+were\s+we\b",
    r"\bback\s+to\s+(?:where\s+we|our)\b",
]

_OPENING_CUE_PATTERNS = [
    r"\boggi\s+parliamo\s+di\b",
    r"\bbenvenuti\s+(?:al|alla|nel)\s+(?:corso|lezione|seminario)\b",
    r"\bin\s+questa\s+lezione\s+(?:vedremo|parliamo|introduciamo)\b",
    r"\b(?:il\s+)?prossim[oa]\s+(?:relatore|relatrice|intervento|talk)\b",
    r"\btoday'?s\s+(?:topic|lecture)\s+is\b",
    r"\bnext\s+(?:speaker|talk)\b",
    r"\bwelcome\s+to\s+(?:the\s+)?(?:course|class|lecture|talk|session)\b",
]

_PAUSE_CUE_RE = re.compile("|".join(_PAUSE_CUE_PATTERNS), re.IGNORECASE)
_CLOSING_CUE_RE = re.compile("|".join(_CLOSING_CUE_PATTERNS), re.IGNORECASE)
_RESUME_CUE_RE = re.compile("|".join(_RESUME_CUE_PATTERNS), re.IGNORECASE)
_OPENING_CUE_RE = re.compile("|".join(_OPENING_CUE_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class Cues:
    pause: bool = False
    closing: bool = False
    resume: bool = False
    opening: bool = False


def detect_cue_flags(text: str) -> Cues:
    """All lifecycle cues of an utterance (pause/closing drive R2; resume/opening bias doc 02 §4)."""
    if not text:
        return Cues()
    closing = bool(_CLOSING_CUE_RE.search(text))
    return Cues(
        pause=bool(_PAUSE_CUE_RE.search(text)) and not closing,
        closing=closing,
        resume=bool(_RESUME_CUE_RE.search(text)),
        opening=bool(_OPENING_CUE_RE.search(text)),
    )


def detect_cues(text: str) -> Tuple[bool, bool]:
    """Returns (pause_cue, closing_cue) for an utterance."""
    cues = detect_cue_flags(text)
    return cues.pause, cues.closing


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
    defer_resume: bool = False   # topic continuity decides resume vs. split on a pending window


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
        if sig.on_topic and not sig.defer_resume:
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


def _unpack_outcome(outcome: Any) -> Tuple[Optional[BriefingReport], List[Dict[str, Any]]]:
    if outcome is None:
        return None, []
    if isinstance(outcome, BriefingReport):
        return outcome, []
    return getattr(outcome, "briefing", None), list(getattr(outcome, "research", []) or [])


_CONTEXT_TYPE_TO_DOMAIN = {
    "academic_lecture": "lecture",
    "general_meeting": "meeting",
    "feature_discussion": "technical_debate",
    "tech_stack": "technical_debate",
    "bug": "technical_debate",
    "system_incident": "technical_debate",
}

_PLACEHOLDER_TITLE_PREFIX = "Ongoing session"


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
        continuity: Optional[TopicSimilarity] = None,
        ingest_source: str = "live",
        run_id: Optional[str] = None,
    ):
        """continuity: topic similarity for Phase C decisions (resume vs. split, drift, on-topic
        windows). None keeps Phase A behaviour (resume on the first on-topic chunk).

        ingest_source / run_id scope the events this engine owns: a history backfill runs its own
        engine on a virtual clock and must never adopt (or be adopted by) the live open event."""
        self._store = store
        self.ingest_source = ingest_source
        self.run_id = run_id
        self.continuity = continuity
        self.config = config or EngineConfig.from_settings()
        self.clock: Clock = clock or time.time
        self.clock_offset: float = 0.0   # simulator virtual time (POST /api/simulate/tick)
        self._synthesizer: Optional[Synthesizer] = synthesizer
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
        # Topic continuity state (Phase C)
        self._window: List[UtteranceChunk] = []
        self._drift: List[Tuple[List[UtteranceChunk], SimilarityScore]] = []
        self._prev_window: Optional[Tuple[List[UtteranceChunk], str]] = None   # (chunks, verdict)
        self._drift_prelude: List[UtteranceChunk] = []   # undecided window right before the drift
        self._pending: List[UtteranceChunk] = []
        self._pending_started: Optional[float] = None
        self._pending_ext = 0
        self._pending_resume_cue = False
        self._pending_opening_cue = False
        self._bee_boundary_since_pause = False
        self._bee_conv_ids: Dict[str, str] = {}

    # -- infrastructure ------------------------------------------------------

    @property
    def store(self) -> AbstractContextStore:
        # Resolve the global store lazily on every access unless one was injected, so that a
        # replaced store singleton (tests, /reset-db) is picked up.
        return self._store if self._store is not None else get_storage_store()

    @property
    def synthesizer(self) -> Synthesizer:
        if self._synthesizer is None:
            from src.pipeline.nodes.topic_research import PipelineEventSynthesizer

            self._synthesizer = PipelineEventSynthesizer(
                store_getter=lambda: self.store, max_words=self.config.synthesis_max_words
            )
        return self._synthesizer

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
        return max(self.clock() + self.clock_offset, self._last_seen_ts)

    def rehydrate(self) -> None:
        """Restores the open event and re-enqueues interrupted synthesis jobs after a restart."""
        with self._lock:
            if self._rehydrated:
                return
            self._rehydrated = True
            try:
                self._current = self.store.get_open_event(ingest_source=self.ingest_source, run_id=self.run_id)
            except NotImplementedError:
                self._current = None
            if self._current:
                for seg in self._current.segments:
                    if seg.status in ("closed", "synthesizing"):
                        self._enqueue(SynthesisJob("segment", self._current.session_id, seg.segment_id))
                if self._current.pending_chunk_ids:
                    ids = set(self._current.pending_chunk_ids)
                    self._pending = [
                        c for c in self.store.list_session_chunks(self._current.session_id) if c.chunk_id in ids
                    ]
                    self._pending_started = to_epoch(self._pending[0].timestamp) if self._pending else None
            try:
                for ev in self.store.list_events_pending_final(ingest_source=self.ingest_source, run_id=self.run_id):
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
            return {
                "active_event": None,
                "pending_jobs": len(self._jobs),
                "continuity_backend": self.continuity.config.backend if self.continuity else None,
            }
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
                "pending_chunks": len(self._pending),
                "top_terms": [
                    t for t, _ in sorted((ev.topic_profile.keywords if ev.topic_profile else {}).items(),
                                         key=lambda kv: (-kv[1], kv[0]))[:8]
                ],
            },
            "pending_jobs": len(self._jobs),
            "continuity_backend": self.continuity.config.backend if self.continuity else None,
        }

    def active_event_hint(self) -> str:
        """One-line gatekeeper context while an event is open (doc 02 §3): raises deep_topic recall
        for terse lecture sentences."""
        ev = self._current
        if ev is None:
            return ""
        title = ev.title if ev.title and not ev.title.startswith(_PLACEHOLDER_TITLE_PREFIX) else None
        kind = ev.domain if ev.domain and ev.domain != "general" else "lecture or meeting"
        if title:
            subject = f"about '{title}'"
        elif ev.topic_profile and ev.topic_profile.keywords:
            terms = sorted(ev.topic_profile.keywords.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
            subject = "(frequent terms: " + ", ".join(t for t, _ in terms) + ")"
        else:
            return ""
        state = "is in progress" if ev.status == "active" else "is paused and may resume"
        return (
            f"ONGOING EVENT: a {kind} {subject} {state}. Utterances that continue explaining this subject "
            f"are deep_topic, even when short or informal."
        )

    # -- inputs ---------------------------------------------------------------

    def record_chunk(self, chunk: UtteranceChunk) -> ChunkOutcome:
        """Feeds one screened utterance (chunk.categories must be set) into the lifecycle."""
        self.rehydrate()
        ts = to_epoch(chunk.timestamp) or self.clock()
        on_topic = "deep_topic" in (chunk.categories or [])
        cues = detect_cue_flags(chunk.text)
        pause_cue, closing_cue = cues.pause, cues.closing
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
                defer_resume=self.continuity is not None,
            )

            for _ in range(6):
                t = next_pre_chunk_transition(self._snapshot(), sig, self.config)
                if not t:
                    break
                applied.append(t)
                applied.extend(self._apply(t, chunk=chunk))
                if t.rule == "R6":
                    # A location shift is consumed by the conclusion; the next event re-anchors
                    sig = replace(sig, location_shift=False)

            if self._current is not None:
                self._append(chunk, ts, on_topic)
                if self.continuity is not None:
                    applied.extend(self._continuity_on_chunk(chunk, ts, on_topic, cues))
            if self._current is not None:
                for _ in range(3):
                    t = next_post_chunk_transition(self._snapshot(), sig, self.config)
                    if not t:
                        break
                    applied.append(t)
                    applied.extend(self._apply(t, chunk=chunk))

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
                applied.append(t)
                applied.extend(self._apply(t))
            if (
                self.continuity is not None and self._current is not None
                and self._current.status == "paused" and self._pending
            ):
                applied.extend(self._maybe_decide_pending(now))
            if self._current is not None and applied:
                self._save(self._current)
        return applied

    def next_deadline(self) -> Optional[float]:
        """Earliest engine time at which a timer rule (R1/R3/R5 or the pending-window decision) may fire."""
        with self._lock:
            snap = self._snapshot()
            candidates: List[float] = []
            if snap.status == "active":
                if snap.last_on_topic_at is not None:
                    candidates.append(snap.last_on_topic_at + self.config.t_soft)
                if snap.segment_start is not None and snap.segment_words >= self.config.min_segment_words:
                    candidates.append(snap.segment_start + self.config.t_checkpoint)
            elif snap.status == "paused":
                deadline = snap.effective_deadline(self.config)
                if deadline is not None:
                    candidates.append(deadline)
                if self.continuity is not None and self._pending and self._pending_started is not None:
                    candidates.append(self._pending_started + self.continuity.config.pending_max_age)
            return min(candidates) if candidates else None

    def advance_to(self, ts: float, max_steps: int = 64) -> List[Transition]:
        """Virtual-clock replay (history backfill): fires every timer due up to ``ts`` at its own
        deadline instead of ticking every ``tick_seconds``, then ticks at ``ts``."""
        applied: List[Transition] = []
        last: Optional[float] = None
        for _ in range(max_steps):
            nxt = self.next_deadline()
            if nxt is None or nxt > ts or (last is not None and nxt <= last):
                break
            last = nxt
            applied.extend(self.tick(now=nxt))
        applied.extend(self.tick(now=ts))
        with self._lock:
            self._last_seen_ts = max(self._last_seen_ts, ts)
        return applied

    def release_open_event(
        self,
        ingest_source: str,
        run_id: Optional[str],
        rule: str = "B1",
        reason: str = "handover",
        detail: Optional[str] = None,
    ) -> Optional[SessionDossier]:
        """Hands the open event over to another engine scope (history backfill, doc 03 §7).

        B1: the live engine hands its open event to the startup backfill run that replays the gap.
        The event keeps its state; this engine forgets it and its in-memory continuity windows."""
        self.rehydrate()
        with self._lock:
            ev = self._current
            if ev is None:
                return None
            ev.ingest_source = ingest_source  # type: ignore[assignment]
            ev.ingest_run_id = run_id
            self._log(ev, ev.status, Transition(
                rule, ev.status, reason, self.now(),
                detail or f"Handed over to {ingest_source} ingestion (run {run_id})"))
            self._save(ev)
            self._current = None
            self._reset_continuity_state()
            return ev

    def log_transition(self, session_id: str, rule: str, reason: str, detail: str = "") -> None:
        """Appends an audit-trail entry (e.g. B2 backfill stitching) without changing the status."""
        with self._lock:
            ev = self._load(session_id)
            if ev is None:
                return
            self._log(ev, ev.status, Transition(rule, ev.status, reason, self.now(), detail))
            self._save(ev)

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
                applied.append(t)
                applied.extend(self._apply(t))
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
                self._reset_continuity_state(dossier)
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

    # -- manual operations (Web UI / Alexa, doc 06 §1) ------------------------

    def advance_clock(self, seconds: float) -> List[Transition]:
        """Simulator only: moves the virtual clock forward and runs the timers."""
        with self._lock:
            self.clock_offset += max(0.0, float(seconds))
        return self.tick()

    def pause(self, session_id: str, now: Optional[float] = None) -> Optional[SessionDossier]:
        """Manual soft close: closes and synthesizes the current segment now ("Synthesize now")."""
        self.rehydrate()
        now = self.now() if now is None else now
        with self._lock:
            ev = self._current
            if ev is None or ev.session_id != session_id or ev.status != "active":
                return None
            self._apply(Transition("R2", "paused", "manual_pause", now, "Paused manually (synthesize now)"))
            self._save(ev)
            return ev

    def resume(self, session_id: str, now: Optional[float] = None) -> Optional[SessionDossier]:
        """Manual resume of the paused current event (overrides a pending split decision)."""
        self.rehydrate()
        now = self.now() if now is None else now
        with self._lock:
            ev = self._current
            if ev is None or ev.session_id != session_id or ev.status != "paused":
                return None
            if self._pending and self.continuity is not None:
                self._resume_with_pending(self._join(self._pending), None, "Resumed manually")
            else:
                self._reset_continuity_state(ev)
                self._apply(Transition("R4", "active", "manual_resume", now, "Resumed manually"))
            self._save(ev)
            return ev

    def split(
        self, session_id: str, at_time: Optional[str] = None, at_chunk_id: Optional[str] = None
    ) -> Optional[Tuple[SessionDossier, SessionDossier]]:
        """Manual split: chunks from the split point onward move to a new event (doc 06 §1, doc 03 §7)."""
        self.rehydrate()
        with self._lock:
            ev = self._load(session_id)
            if ev is None or not ev.segments:
                return None
            chunks = self.store.list_session_chunks(session_id)
            split_ts: Optional[float] = None
            if at_chunk_id:
                split_ts = next((to_epoch(c.timestamp) for c in chunks if c.chunk_id == at_chunk_id), None)
            elif at_time:
                split_ts = to_epoch(at_time)
            if split_ts is None:
                return None
            moved = [c for c in chunks if (to_epoch(c.timestamp) or 0.0) >= split_ts]
            kept = [c for c in chunks if (to_epoch(c.timestamp) or 0.0) < split_ts]
            if not moved or not any(c for c in kept):
                return None

            is_current = self._current is ev
            new = SessionDossier(
                session_id=str(uuid.uuid4()),
                title=f"{_PLACEHOLDER_TITLE_PREFIX} ({datetime.fromtimestamp(split_ts).strftime('%H:%M')})",
                domain=ev.domain,
                start_time=to_iso(split_ts),
                last_updated_at=datetime.now().isoformat(),
                status="concluded",
                location=ev.location,
                anchor_location=ev.anchor_location,
                ingest_source=ev.ingest_source,
                ingest_run_id=ev.ingest_run_id,
            )
            for c in moved:
                if c.conversation_uuid and c.conversation_uuid not in new.conversation_uuids:
                    new.conversation_uuids.append(c.conversation_uuid)

            seg_of = self.store.get_chunk_segments(session_id)
            by_seg_moved: Dict[Optional[str], List[UtteranceChunk]] = {}
            by_seg_kept: Dict[Optional[str], List[UtteranceChunk]] = {}
            for c in moved:
                by_seg_moved.setdefault(seg_of.get(c.chunk_id), []).append(c)
            for c in kept:
                by_seg_kept.setdefault(seg_of.get(c.chunk_id), []).append(c)

            old_segments: List[SessionSegment] = []
            new_segments: List[SessionSegment] = []
            stale_briefings: List[str] = []
            for seg in ev.segments:
                m = by_seg_moved.get(seg.segment_id, [])
                k = by_seg_kept.get(seg.segment_id, [])
                seg_start = to_epoch(seg.start_time) or 0.0
                if not m and (k or seg_start < split_ts):
                    old_segments.append(seg)
                elif not k and seg_start >= split_ts:
                    new_segments.append(seg)          # whole segment moves, briefing included
                    if seg.briefing_id:
                        self.store.reassign_briefings([seg.briefing_id], new.session_id)
                    self.store.assign_chunks([c.chunk_id for c in m], new.session_id, seg.segment_id)
                else:
                    was_open = seg.status == "open"
                    if seg.briefing_id:
                        stale_briefings.append(seg.briefing_id)
                    seg.briefing_id = None
                    seg.title = None
                    seg.status = "closed"
                    seg.close_reason = "manual_split"
                    seg.word_count = sum(len(c.text.split()) for c in k)
                    seg.end_time = k[-1].timestamp if k else seg.end_time
                    part = SessionSegment(
                        start_time=m[0].timestamp,
                        end_time=m[-1].timestamp,
                        word_count=sum(len(c.text.split()) for c in m),
                        status="open" if (was_open and is_current) else "closed",
                        close_reason=None if (was_open and is_current) else "manual_split",
                    )
                    self.store.assign_chunks([c.chunk_id for c in m], new.session_id, part.segment_id)
                    old_segments.append(seg)
                    new_segments.append(part)
            off_segment = by_seg_moved.get(None, [])
            if off_segment:
                self.store.assign_chunks([c.chunk_id for c in off_segment], new.session_id, None)
            for idx, seg in enumerate(old_segments, 1):
                seg.index = idx
            for idx, seg in enumerate(new_segments, 1):
                seg.index = idx
            ev.segments = old_segments
            new.segments = new_segments

            # Micro-events follow their timestamp
            ev_refs, new_refs = [], []
            for ref in ev.linked_micro_events:
                (new_refs if (to_epoch(str(ref.timestamp)) or 0.0) >= split_ts else ev_refs).append(ref)
            ev.linked_micro_events, new.linked_micro_events = ev_refs, new_refs

            for briefing_id in stale_briefings:
                self.store.delete_topic_briefing(briefing_id)
            mark = Transition("MANUAL", "concluded", "manual_split", split_ts, f"Split manually at {to_iso(split_ts)}")

            if is_current:
                new.status = ev.status
                new.paused_at = ev.paused_at
                new.hard_close_deadline = ev.hard_close_deadline
                new.last_on_topic_at = ev.last_on_topic_at
                new.pending_chunk_ids = list(ev.pending_chunk_ids)
                ev.pending_chunk_ids = []
                self._window, self._drift = [], []
                self._conclude(ev, Transition("R8", "concluded", "manual_split", split_ts, "Split manually"))
                self._current = new
            else:
                new.concluded_at = ev.concluded_at or datetime.now().isoformat()
                self._invalidate_final(ev)
                self._log(ev, ev.status, mark)
            self._log(new, None, Transition("MANUAL", new.status, "manual_split", split_ts,
                                            f"Created by a manual split of {ev.session_id[:8]}"))
            if new.status == "concluded":
                new.final_status = "pending"
                self._enqueue(SynthesisJob("final", new.session_id))
            for target in (ev, new):
                for seg in target.segments:
                    if seg.status == "closed":
                        self._enqueue(SynthesisJob("segment", target.session_id, seg.segment_id))
            if self.continuity is not None:
                new.topic_profile = self.continuity.update(None, self._join(moved))
            self.store.save_session_dossier(ev)
            self.store.save_session_dossier(new)
            self._emit("event_split", {"old": self._summary(ev), "new": self._summary(new)})
            return ev, new

    def merge(self, session_ids: List[str]) -> Optional[SessionDossier]:
        """Manual merge of events into the earliest one; final briefings are regenerated."""
        self.rehydrate()
        with self._lock:
            events = [self._load(sid) for sid in dict.fromkeys(session_ids)]
            if len(events) < 2 or any(e is None or not e.segments for e in events):
                return None
            events.sort(key=lambda e: to_epoch(e.start_time) or 0.0)
            target = events[0]
            for other in events[1:]:
                for seg_id, group in self._group_chunks_by_segment(other.session_id).items():
                    self.store.assign_chunks([c.chunk_id for c in group], target.session_id, seg_id)
                target.segments.extend(other.segments)
                known = {(r.event_type, r.record_id) for r in target.linked_micro_events}
                target.linked_micro_events.extend(
                    r for r in other.linked_micro_events if (r.event_type, r.record_id) not in known
                )
                target.conversation_uuids.extend(u for u in other.conversation_uuids if u not in target.conversation_uuids)
                target.research_ledger.extend(other.research_ledger)
                target.key_discussion_points.extend(p for p in other.key_discussion_points if p not in target.key_discussion_points)
                target.transitions.extend(other.transitions)
                for briefing in self.store.list_briefings_for_session(other.session_id):
                    if briefing.kind == "final":
                        self.store.delete_topic_briefing(briefing.id)
                    else:
                        self.store.reassign_briefings([briefing.id], target.session_id)
                if self._current is other:
                    target.status = other.status
                    target.paused_at = other.paused_at
                    target.hard_close_deadline = other.hard_close_deadline
                    target.last_on_topic_at = other.last_on_topic_at
                    target.pending_chunk_ids = list(other.pending_chunk_ids)
                    target.concluded_at = None
                    if self.continuity is not None and other.topic_profile is not None:
                        target.topic_profile = other.topic_profile
                    self._current = target
                self.store.delete_session_dossier(other.session_id)
            target.segments.sort(key=lambda s: to_epoch(s.start_time) or 0.0)
            for idx, seg in enumerate(target.segments, 1):
                seg.index = idx
            self._log(target, target.status, Transition(
                "MANUAL", target.status, "manual_merge", self.now(),
                f"Merged {len(events) - 1} event(s) into this one"))
            if target.status == "concluded":
                self._invalidate_final(target)
            self.store.save_session_dossier(target)
            self._emit("event_merged", {"event": self._summary(target), "merged": [e.session_id for e in events[1:]]})
            return target

    def _invalidate_final(self, ev: SessionDossier) -> None:
        """Drops a stale consolidated briefing and schedules a new one (doc 03 §7)."""
        if ev.final_briefing_id:
            self.store.delete_topic_briefing(ev.final_briefing_id)
        ev.final_briefing_id = None
        ev.briefing_report = None
        if ev.status == "concluded":
            ev.final_status = "pending"
            self._enqueue(SynthesisJob("final", ev.session_id))

    def _group_chunks_by_segment(self, session_id: str) -> Dict[Optional[str], List[UtteranceChunk]]:
        seg_of = self.store.get_chunk_segments(session_id)
        groups: Dict[Optional[str], List[UtteranceChunk]] = {}
        for c in self.store.list_session_chunks(session_id):
            groups.setdefault(seg_of.get(c.chunk_id), []).append(c)
        return groups

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

    def _apply(self, t: Transition, chunk: Optional[UtteranceChunk] = None) -> List[Transition]:
        """Applies a transition; returns follow-up transitions it triggered (e.g. carried pending speech)."""
        if t.rule == "R0":
            self._open(t, chunk)
            return []

        ev = self._current
        if ev is None:
            return []
        from_status = ev.status

        if t.to_status == "concluded":
            # On a hard timeout, speech waiting for the resume decision belongs to the next event
            carry = list(self._pending) if t.rule == "R5" else []
            self._reset_continuity_state(ev)
            self._conclude(ev, t)
            self._save(ev)
            self._current = None
            if carry:
                follow = Transition("R0", "active", "open_from_pending", to_epoch(carry[0].timestamp) or t.at,
                                    "On-topic speech that arrived during the expired pause")
                self._open_from_chunks(carry, follow)
                return [follow]
            return []

        if t.rule in ("R1", "R2"):
            self._close_open_segment(ev, t.reason, t.at)
            self._window = []
            self._drift = []
            self._bee_boundary_since_pause = False
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
        return []

    def _reset_continuity_state(self, ev: Optional[SessionDossier] = None) -> None:
        self._window = []
        self._drift = []
        self._prev_window = None
        self._drift_prelude = []
        self._pending = []
        self._pending_started = None
        self._pending_ext = 0
        self._pending_resume_cue = False
        self._pending_opening_cue = False
        self._bee_boundary_since_pause = False
        if ev is not None:
            ev.pending_chunk_ids = []

    # -- topic continuity (Phase C, doc 02) -------------------------------------------

    def _window_ready(self, chunks: List[UtteranceChunk], extensions: int = 0) -> bool:
        cfg = self.continuity.config
        words = sum(len(c.text.split()) for c in chunks)
        factor = 1 + extensions
        return len(chunks) >= cfg.window_min_chunks * factor and words >= cfg.window_min_words * factor

    @staticmethod
    def _join(chunks: List[UtteranceChunk]) -> str:
        return " ".join(c.text.strip() for c in chunks if c.text and c.text.strip())

    def _continuity_on_chunk(self, chunk: UtteranceChunk, ts: float, on_topic: bool, cues: Cues) -> List[Transition]:
        ev = self._current
        if ev is None:
            return []
        if ev.status == "active":
            self._window.append(chunk)
            if self._window_ready(self._window):
                return self._evaluate_window()
            return []
        if ev.status == "paused" and (self._pending or on_topic):
            if not self._pending:
                self._pending_started = ts
                self._pending_ext = 0
                self._pending_resume_cue = False
                self._pending_opening_cue = False
            self._pending.append(chunk)
            ev.pending_chunk_ids.append(chunk.chunk_id)
            self._pending_resume_cue = self._pending_resume_cue or cues.resume
            self._pending_opening_cue = self._pending_opening_cue or cues.opening
            return self._maybe_decide_pending(ts)
        return []

    def _evaluate_window(self) -> List[Transition]:
        """Scores a micro-window of the ACTIVE event: on-topic windows keep the event alive (even if the
        gatekeeper said noop) and feed the profile; sustained different-topic windows split it (R9)."""
        ev = self._current
        chunks, self._window = self._window, []
        text = self._join(chunks)
        has_deep = any("deep_topic" in (c.categories or []) for c in chunks)
        score, vec = self.continuity.score(text, ev.topic_profile)
        if score is None or not self.continuity.is_mature(ev.topic_profile):
            # The profile is still being built from the opening windows: no drift decisions yet
            verdict = "same" if has_deep or (score is not None and score.verdict() == "same") else "undecided"
        else:
            verdict = score.verdict()
            if verdict == "same" and len(chunks) >= 4:
                # A window straddling a subject change can still look "same" overall: if its second
                # half alone is clearly different, treat it as a boundary (no profile update).
                tail = chunks[len(chunks) // 2:]
                tail_score, _ = self.continuity.score(self._join(tail), ev.topic_profile)
                if tail_score is not None and tail_score.verdict() == "different":
                    verdict = "undecided"

        drifting = bool(self._drift)
        prev_window, self._prev_window = self._prev_window, (chunks, verdict)
        if verdict == "same" or (verdict == "undecided" and has_deep and not drifting):
            last_ts = max(to_epoch(c.timestamp) or 0.0 for c in chunks)
            current_last = to_epoch(ev.last_on_topic_at) or 0.0
            if last_ts > current_last:
                ev.last_on_topic_at = to_iso(last_ts)
            # Only clearly on-topic windows (or the opening ones) shape the profile: an undecided
            # window may straddle a subject change and would contaminate it.
            if verdict == "same" or not self.continuity.is_mature(ev.topic_profile):
                ev.topic_profile = self.continuity.update(ev.topic_profile, text, vec)
            if verdict == "same":
                self._drift = []
            return []

        # Drift evidence: clearly different topical windows start/extend a drift sequence; undecided
        # windows extend an ongoing one (without touching the profile) but never start it.
        if (verdict == "different" and has_deep) or (verdict == "undecided" and drifting):
            if not drifting:
                # A window straddling the subject change is usually undecided: keep it to refine the
                # split point at chunk level if the drift is confirmed.
                self._drift_prelude = list(prev_window[0]) if prev_window and prev_window[1] == "undecided" else []
            self._drift.append((chunks, score))
            cfg = self.continuity.config
            clear = sum(1 for _, s in self._drift if s is not None and s.verdict() == "different")
            first = to_epoch(self._drift[0][0][0].timestamp) or 0.0
            last = to_epoch(self._drift[-1][0][-1].timestamp) or 0.0
            if (
                len(self._drift) >= cfg.drift_windows
                and clear >= min(2, cfg.drift_windows)
                and last - first >= cfg.drift_min_seconds
            ):
                return self._split_on_drift()
        return []

    def _split_on_drift(self) -> List[Transition]:
        """R9: a new subject took over without a pause. Chunks from the first drifting window move to
        a new event; the old event concludes."""
        ev = self._current
        drift_chunks = [c for window, _ in self._drift for c in window]
        last_score = self._drift[-1][1]
        drift_chunks = self._refine_split(ev, drift_chunks) + drift_chunks
        split_at = to_epoch(drift_chunks[0].timestamp) or self.now()
        seg = ev.open_segment
        if seg is not None:
            seg.word_count = max(0, seg.word_count - sum(len(c.text.split()) for c in drift_chunks))
            seg.end_time = to_iso(split_at)
        t = Transition("R9", "concluded", "topic_drift", split_at,
                       f"{len(self._drift)} consecutive windows on a different subject; {last_score.describe()}")
        self._apply(t)
        follow = Transition("R0", "active", "open_from_drift", split_at, "New subject detected without a pause")
        self._open_from_chunks(drift_chunks, follow)
        return [t, follow]

    def _refine_split(self, ev: SessionDossier, drift_chunks: List[UtteranceChunk]) -> List[UtteranceChunk]:
        """Chunk-level split refinement: trailing chunks of the straddling window that are closer to
        the new subject than to the old profile move to the new event."""
        if not self._drift_prelude or ev.topic_profile is None:
            return []
        # An explicit opening cue ("il prossimo intervento è...", "next speaker") marks the boundary
        for idx, chunk in enumerate(self._drift_prelude):
            if detect_cue_flags(chunk.text).opening:
                return list(self._drift_prelude[idx:])
        new_profile = self.continuity.update(None, self._join(drift_chunks))
        margin = self.continuity.config.split_refine_margin
        moved: List[UtteranceChunk] = []
        for chunk in reversed(self._drift_prelude):
            s_new, _ = self.continuity.score(chunk.text, new_profile)
            s_old, _ = self.continuity.score(chunk.text, ev.topic_profile)
            if s_new is None or s_old is None or s_new.value - s_old.value < margin:
                break
            moved.insert(0, chunk)
        return moved

    def _maybe_decide_pending(self, now: float) -> List[Transition]:
        """Resume (R4) vs. new event (R7) once the pending window is informative enough (doc 02 §4)."""
        ev = self._current
        cfg = self.continuity.config
        age = now - (self._pending_started or now)
        aged_out = age >= cfg.pending_max_age
        if not (self._window_ready(self._pending, self._pending_ext) or aged_out):
            return []

        text = self._join(self._pending)
        score, vec = self.continuity.score(text, ev.topic_profile)
        if score is None:
            verdict, detail = "same", "No topic profile yet: resuming"
        else:
            resume_bias = cfg.resume_cue_bias if self._pending_resume_cue else 0.0
            split_bias = (cfg.opening_cue_bias if self._pending_opening_cue else 0.0) + (
                cfg.bee_boundary_bias if self._bee_boundary_since_pause else 0.0
            )
            verdict = score.verdict(resume_bias=resume_bias, split_bias=split_bias)
            detail = score.describe()
            if resume_bias or split_bias:
                detail += f"; cue bias resume={resume_bias:.2f} split={split_bias:.2f}"
            if verdict == "undecided":
                if self._pending_ext < cfg.pending_max_extensions and not aged_out:
                    self._pending_ext += 1
                    return []
                title = ev.title if ev.title and not ev.title.startswith(_PLACEHOLDER_TITLE_PREFIX) else None
                judged = self.continuity.judge(text, ev.topic_profile, self._previous_text(ev), title)
                verdict = judged if judged in ("same", "different") else "same"
                detail += f"; judge={judged or 'n/a'} -> {verdict}"

        if verdict == "same":
            return [self._resume_with_pending(text, vec, detail)]
        return self._split_after_pause(detail)

    def _previous_text(self, ev: SessionDossier, words: int = 150) -> str:
        chunks = self.store.list_session_chunks(ev.session_id, in_segments_only=True)
        return " ".join(" ".join(c.text for c in chunks).split()[-words:])

    def _resume_with_pending(self, text: str, vec: Optional[List[float]], detail: str) -> Transition:
        ev = self._current
        pending = list(self._pending)
        first_ts = to_epoch(pending[0].timestamp) or self.now()
        last_ts = to_epoch(pending[-1].timestamp) or first_ts
        t = Transition("R4", "active", "resume_same_topic", first_ts, detail)
        self._reset_continuity_state(ev)
        self._apply(t)
        seg = ev.open_segment
        self.store.assign_chunks([c.chunk_id for c in pending], ev.session_id, seg.segment_id, on_topic=True)
        seg.word_count += sum(len(c.text.split()) for c in pending)
        seg.end_time = to_iso(last_ts)
        ev.last_on_topic_at = to_iso(last_ts)
        ev.topic_profile = self.continuity.update(ev.topic_profile, text, vec)
        return t

    def _split_after_pause(self, detail: str) -> List[Transition]:
        ev = self._current
        pending = list(self._pending)
        at = to_epoch(pending[0].timestamp) or self.now()
        self._reset_continuity_state(ev)
        t = Transition("R7", "concluded", "new_topic_after_pause", at, detail)
        self._apply(t)
        follow = Transition("R0", "active", "open_from_pending", at, "Different subject after the pause")
        self._open_from_chunks(pending, follow)
        return [t, follow]

    def _open_from_chunks(self, chunks: List[UtteranceChunk], t: Transition) -> None:
        """Opens a new event whose first segment is made of already-logged chunks (R7/R9/R5 carry)."""
        self._open(t, chunks[0])
        ev = self._current
        seg = ev.open_segment
        self.store.assign_chunks([c.chunk_id for c in chunks], ev.session_id, seg.segment_id, on_topic=True)
        seg.word_count = sum(len(c.text.split()) for c in chunks)
        last_ts = to_epoch(chunks[-1].timestamp) or t.at
        seg.end_time = to_iso(last_ts)
        ev.last_on_topic_at = to_iso(last_ts)
        for c in chunks:
            if c.conversation_uuid and c.conversation_uuid not in ev.conversation_uuids:
                ev.conversation_uuids.append(c.conversation_uuid)
        if self.continuity is not None:
            ev.topic_profile = self.continuity.update(None, self._join(chunks))
        self._save(ev)

    def register_bee_conversation(self, conv_id: Any, conv_uuid: Optional[str]) -> None:
        """Records a Bee REST id ↔ stream uuid pair (e.g. from `new-utterance-chunks`), so that later
        `update-conversation-summary` events (which carry only the id) can enrich the open event."""
        if conv_id is None or not conv_uuid:
            return
        with self._lock:
            self._bee_conv_ids[str(conv_id)] = conv_uuid

    def on_bee_conversation(self, event_type: str, data: Dict[str, Any]) -> None:
        """Bee conversation lifecycle (doc 05 §2.4): a new conversation during a pause slightly favours a
        split; titles/summaries of conversations belonging to the open event enrich its topic profile."""
        self.rehydrate()
        conv = data.get("conversation") or {}
        conv_id = conv.get("id") or data.get("conversation_id")
        conv_uuid = conv.get("uuid")
        with self._lock:
            if conv_id is not None and conv_uuid:
                self._bee_conv_ids[str(conv_id)] = conv_uuid
            ev = self._current
            if ev is None:
                return
            if event_type == "new-conversation":
                if ev.status == "paused":
                    self._bee_boundary_since_pause = True
                return
            conv_uuid = conv_uuid or self._bee_conv_ids.get(str(conv_id))
            if self.continuity is None or not conv_uuid or conv_uuid not in ev.conversation_uuids:
                return
            texts = [x for x in (conv.get("title"), conv.get("short_summary"), data.get("short_summary")) if x]
        for text in texts:
            vec = self.continuity.embed(text)
            with self._lock:
                ev = self._current
                if ev is None or conv_uuid not in ev.conversation_uuids:
                    return
                from src.core.schemas import TopicProfile

                ev.topic_profile = self.continuity.blend_title(ev.topic_profile or TopicProfile(), text, vec, source="bee")
                self._save(ev)

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
            ingest_source=self.ingest_source,
            ingest_run_id=self.run_id,
        )
        self._open_segment(ev, t.at)
        self._log(ev, None, t)
        self._current = ev
        self._window = []
        self._drift = []
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

        with self._lock:
            ev = self._load(session_id)
            seg = next((s for s in ev.segments if s.segment_id == segment_id), None) if ev else None
            if ev is None or seg is None:
                return
            outline = self._outline(ev, part_index=seg.index)
            kind = "checkpoint" if seg.kind == "checkpoint" else "segment"

        text = self._segment_text(session_id, segment_id)
        briefing, research = _unpack_outcome(self.synthesizer.segment(text, session_id, outline=outline, kind=kind))
        if briefing is None:
            raise RuntimeError("Synthesizer returned no briefing")
        title_vec = (
            self.continuity.embed(briefing.topic_title)
            if self.continuity is not None and briefing.topic_title else None
        )

        with self._lock:
            ev = self._load(session_id)
            seg = next((s for s in ev.segments if s.segment_id == segment_id), None) if ev else None
            if ev is None or seg is None:
                return
            briefing.id = None
            briefing.session_id = session_id
            briefing.segment_id = segment_id
            briefing.kind = kind  # type: ignore[assignment]
            seg.briefing_id = self.store.save_topic_briefing(briefing)
            seg.title = briefing.topic_title
            seg.status = "synthesized"
            self._adopt_title_and_domain(ev, briefing)
            if briefing.topic_title and briefing.topic_title not in ev.key_discussion_points:
                ev.key_discussion_points.append(briefing.topic_title)
            self._record_research(ev, research, segment_id=segment_id, kind=kind)
            if self.continuity is not None and briefing.topic_title and ev.topic_profile is not None:
                ev.topic_profile = self.continuity.blend_title(ev.topic_profile, briefing.topic_title, title_vec)
            self._save(ev)
            payload = self._summary(ev)
        payload["briefing"] = briefing.model_dump()
        self._emit("segment_synthesized", payload)

    def _outline(self, ev: SessionDossier, part_index: Optional[int] = None) -> Any:
        """Event context handed to the synthesizer (doc 03 §2)."""
        from src.pipeline.nodes.topic_research import EventOutline

        title = ev.title if ev.title and not ev.title.startswith(_PLACEHOLDER_TITLE_PREFIX) else None
        context_type = next(
            (k for k, v in _CONTEXT_TYPE_TO_DOMAIN.items() if v == ev.domain and ev.domain != "general"), None
        )
        return EventOutline(
            event_title=title,
            context_type=context_type,
            part_index=part_index,
            previous_parts=[
                s.title for s in ev.segments
                if s.title and s.status == "synthesized" and (part_index is None or s.index < part_index)
            ],
            key_points=list(ev.key_discussion_points),
            researched_queries=[e.get("query") for e in ev.research_ledger if e.get("query")],
        )

    @staticmethod
    def _record_research(
        ev: SessionDossier, entries: List[Dict[str, Any]], segment_id: Optional[str], kind: str
    ) -> None:
        known = {e.get("query") for e in ev.research_ledger}
        for entry in entries:
            query = entry.get("query")
            if not query or query in known:
                continue
            known.add(query)
            ev.research_ledger.append({
                "query": query,
                "sources": list(entry.get("sources") or []),
                "segment_id": segment_id,
                "kind": kind,
            })

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
        with self._lock:
            ev = self._load(session_id)
            outline = self._outline(ev) if ev else None
            micro_events = list(ev.linked_micro_events) if ev else []

        final: Optional[BriefingReport] = None
        research: List[Dict[str, Any]] = []
        if len(synthesized) == 1 and len(unsynthesized_text.split()) < self.config.min_segment_words:
            # Single-segment shortcut: promote the segment briefing, no extra LLM call
            final = self.store.get_topic_briefing(synthesized[0].briefing_id)
            if final is not None:
                from src.pipeline.nodes.topic_research import append_micro_events_section

                final = append_micro_events_section(final.model_copy(deep=True), micro_events)
        else:
            parts = [b for b in (self.store.get_topic_briefing(s.briefing_id) for s in synthesized) if b]
            extra_text = unsynthesized_text if parts else self._segment_text(session_id, None)
            if not parts and not extra_text.strip():
                with self._lock:
                    ev = self._load(session_id)
                    if ev is not None:
                        ev.final_status = "none"
                        self._save(ev)
                return
            final, research = _unpack_outcome(self.synthesizer.final(
                parts, extra_text, session_id, outline=outline, micro_events=micro_events
            ))

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
            self._record_research(ev, research, segment_id=None, kind="final")
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
                # Ticks may call the embedding model / LLM judge: keep them off the event loop
                await asyncio.to_thread(self.engine.tick)
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


# One live engine per user (docs/next_steps/multi_user/03 §3): keyed by user_id
_engines: Dict[str, EventEngine] = {}
_runtimes: Dict[str, EventEngineRuntime] = {}
_registry_lock = threading.Lock()


def build_continuity_from_settings() -> Optional[TopicSimilarity]:
    """Topic continuity configured from settings (None when TOPIC_SIMILARITY_BACKEND=none)."""
    cfg = ContinuityConfig.from_settings()
    return TopicSimilarity(cfg) if cfg else None


def _resolve_user_id(user_id: Optional[str]) -> str:
    if user_id:
        return user_id
    from src.core.identity import require_user

    return require_user().user_id


def get_event_engine(user_id: Optional[str] = None) -> EventEngine:
    """The live Event Engine of ``user_id`` (default: the user in the current context)."""
    uid = _resolve_user_id(user_id)
    with _registry_lock:
        engine = _engines.get(uid)
        if engine is None:
            from src.core.storage import get_storage_store

            engine = EventEngine(store=get_storage_store(user_id=uid), continuity=build_continuity_from_settings())
            _engines[uid] = engine
        return engine


def get_event_engine_runtime(user_id: Optional[str] = None) -> EventEngineRuntime:
    uid = _resolve_user_id(user_id)
    engine = get_event_engine(uid)
    with _registry_lock:
        runtime = _runtimes.get(uid)
        if runtime is None:
            runtime = EventEngineRuntime(engine)
            _runtimes[uid] = runtime
        return runtime


def drop_event_engine(user_id: str) -> None:
    """Forgets a user's engine (runtime stopped by the caller): unlink / erasure."""
    with _registry_lock:
        _runtimes.pop(user_id, None)
        _engines.pop(user_id, None)
