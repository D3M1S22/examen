"""Session Manager for EXAMEN Macro-Sessions & Micro-Event Decoupling (Milestone 3.2).

Tracks continuous conversation sessions (meetings, lectures, technical debates)
originating from wearable audio streams (e.g., Bee conversation_uuid).
Maintains session lifecycle (active -> finalizing -> concluded), buffers raw chunks
without triggering expensive redundant web research on each 15-30s chunk,
detects session boundaries (inactivity timeout, closing phrases, spatial location shifts),
and delegates holistic synthesis upon boundary triggers.
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.schemas import (
    BriefingReport,
    MicroEventRef,
    SessionDossier,
)
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore

logger = logging.getLogger("examen.ingestion.session_manager")

CLOSING_PHRASE_PATTERNS = [
    r"\bthat\s+concludes\b",
    r"\bconclude(?:s|d|ing)?\s+(?:the|our|this|today'?s)?\s*(?:meeting|session|call|discussion|review)?\b",
    r"\bwrap(?:s|ped|ping)?\s+up\s+(?:the|our|this|today'?s)?\s*(?:meeting|session|call|discussion|review)?\b",
    r"\bclose\s+(?:the|our|this)?\s*(?:meeting|session|call)\b",
    r"\badjourn(?:ed|ing)?\b",
    r"\bmeeting\s+is\s+adjourned\b",
    r"\blet'?s\s+call\s+it\s+a\s+day\b",
    r"\bsession\s+is\s+finished\b",
    r"\bend\s+of\s+(?:the\s+)?meeting\b",
    r"\bfine\s+riunione\b",
    r"\bconcludiamo\s+la\s+riunione\b",
    r"\bchiudiamo\s+la\s+riunione\b",
    r"\baggiorniamo\s+la\s+seduta\b",
]

COMPILED_CLOSING_REGEX = re.compile("|".join(CLOSING_PHRASE_PATTERNS), re.IGNORECASE)


def calculate_haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculates great-circle distance between two GPS coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class SessionManager:
    """Manages continuous audio session lifecycle, boundary triggers, and micro-event linking."""

    def __init__(
        self,
        inactivity_timeout_seconds: float = 180.0,
        location_distance_threshold_meters: float = 500.0,
        store: Optional[AbstractContextStore] = None,
    ):
        self.inactivity_timeout = inactivity_timeout_seconds
        self.location_threshold = location_distance_threshold_meters
        self._store = store
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    @property
    def store(self) -> AbstractContextStore:
        if self._store is None:
            self._store = get_storage_store()
        return self._store

    def is_closing_phrase(self, text: str) -> bool:
        """Determines if the utterance contains an explicit meeting/session concluding phrase."""
        if not text or not text.strip():
            return False
        return bool(COMPILED_CLOSING_REGEX.search(text.strip()))

    def check_location_shift(
        self, session_id: str, new_location: Optional[dict]
    ) -> bool:
        """Checks if new spatial telemetry represents a significant displacement (> threshold meters)."""
        if not new_location:
            return False

        new_lat = new_location.get("latitude")
        new_lon = new_location.get("longitude")
        if new_lat is None or new_lon is None:
            return False

        meta = self._active_sessions.get(session_id)
        if not meta or not meta.get("last_location"):
            return False

        old_loc = meta["last_location"]
        old_lat = old_loc.get("latitude")
        old_lon = old_loc.get("longitude")
        if old_lat is None or old_lon is None:
            return False

        dist = calculate_haversine_distance(
            float(old_lat), float(old_lon), float(new_lat), float(new_lon)
        )
        if dist >= self.location_threshold:
            logger.info(
                f"Session '{session_id}' location shift detected: {dist:.1f}m >= {self.location_threshold}m"
            )
            return True
        return False

    def record_chunk(
        self,
        session_id: str,
        text: str,
        timestamp: Optional[float] = None,
        location: Optional[dict] = None,
    ) -> Tuple[SessionDossier, bool]:
        """Appends a transcript chunk to the active session and evaluates boundary triggers.

        Returns (dossier, boundary_triggered).
        """
        now = timestamp if timestamp is not None else time.time()
        meta = self._active_sessions.get(session_id)

        inactivity_detected = False
        if meta and meta.get("last_active_time"):
            elapsed = now - meta["last_active_time"]
            if elapsed >= self.inactivity_timeout:
                inactivity_detected = True
                logger.info(
                    f"Session '{session_id}' inactivity detected: {elapsed:.1f}s >= {self.inactivity_timeout}s"
                )

        closing_detected = self.is_closing_phrase(text)
        location_shifted = self.check_location_shift(session_id, location)

        boundary_triggered = inactivity_detected or closing_detected or location_shifted

        # Append chunk to storage
        dossier = self.store.append_chunk_to_session(
            session_id=session_id, chunk_text=text, location=location
        )

        if boundary_triggered:
            dossier.status = "finalizing"
            self.store.save_session_dossier(dossier)

        # Update in-memory metadata
        self._active_sessions[session_id] = {
            "last_active_time": now,
            "last_location": location or (meta.get("last_location") if meta else None),
        }

        return dossier, boundary_triggered

    def check_inactivity_timeouts(
        self, current_time: Optional[float] = None
    ) -> List[str]:
        """Scans active sessions and transitions timed out sessions to finalizing."""
        now = current_time if current_time is not None else time.time()
        timed_out = []
        for sess_id, meta in list(self._active_sessions.items()):
            last_time = meta.get("last_active_time")
            if last_time and (now - last_time >= self.inactivity_timeout):
                timed_out.append(sess_id)
                dossier = self.store.get_session_dossier(sess_id)
                if dossier and dossier.status == "active":
                    dossier.status = "finalizing"
                    self.store.save_session_dossier(dossier)
        return timed_out

    def link_micro_event(
        self, session_id: str, event_ref: Union[MicroEventRef, dict]
    ) -> bool:
        """Links a decoupled micro-event (action, task, contact) to the active session dossier."""
        return self.store.link_micro_event_to_session(session_id, event_ref)

    def conclude_session(
        self, session_id: str, briefing_report_id: Optional[str] = None
    ) -> Optional[SessionDossier]:
        """Concludes the session and links an optional synthesized briefing report ID."""
        dossier = self.store.conclude_session_dossier(session_id, briefing_report_id)
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
        return dossier

    def get_session(self, session_id: Optional[str] = None) -> Optional[SessionDossier]:
        """Retrieves a session dossier by ID, or the most recent session if omitted."""
        return self.store.get_session_dossier(session_id)

    def list_sessions(
        self, status: Optional[str] = None, limit: int = 10
    ) -> List[SessionDossier]:
        """Lists stored session dossiers."""
        return self.store.list_session_dossiers(status=status, limit=limit)

    def synthesize_session_dossier(
        self, session_id: str, auto_conclude: bool = True
    ) -> Optional[BriefingReport]:
        """Executes holistic Stage 3C synthesis across all accumulated chunks of the session."""
        dossier = self.store.get_session_dossier(session_id)
        if not dossier or not dossier.transcript_chunks:
            return None

        # Build combined macro transcript
        combined_text = "\n".join(dossier.transcript_chunks)

        try:
            from src.pipeline.nodes.topic_research import node_topic_research
            synth_state = {
                "raw_transcript": combined_text,
                "session_id": session_id,
                "categories": ["deep_topic"],
            }
            synth_res = node_topic_research(synth_state)
            briefing = synth_res.get("briefing_report")
            if briefing:
                briefing_id = self.store.save_topic_briefing(briefing)
                if auto_conclude:
                    self.conclude_session(session_id, briefing_report_id=briefing_id)
                return briefing
        except Exception as e:
            logger.error(f"Failed holistic session synthesis for '{session_id}': {e}", exc_info=True)

        return None
