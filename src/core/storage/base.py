"""Abstract interface for EXAMEN context storage."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.core.schemas import (
    BriefingReport,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    VerifiedAction,
)


class AbstractContextStore(ABC):
    """Abstract Base Class for context and memory persistence."""

    # --- Planned Tasks ---
    @abstractmethod
    def save_planned_task(self, task: PlannedTask) -> str:
        """Create or update a planned routine task. Returns record ID."""
        pass

    @abstractmethod
    def get_planned_task(self, task_id: str) -> Optional[PlannedTask]:
        """Retrieve a planned task by ID."""
        pass

    @abstractmethod
    def list_planned_tasks(
        self, status: Optional[str] = None, domain: Optional[str] = None, origin: Optional[str] = None
    ) -> List[PlannedTask]:
        """List planned tasks, optionally filtered by status, domain, or origin."""
        pass

    @abstractmethod
    def complete_planned_task(
        self, task_id: str, verified_action_id: str, completed_at: Optional[str] = None
    ) -> bool:
        """Mark a planned task as completed and link the verifying action."""
        pass

    @abstractmethod
    def update_planned_task(self, task: PlannedTask) -> bool:
        """Update an existing planned routine task. Returns True if updated."""
        pass

    @abstractmethod
    def delete_planned_task(self, task_id: str) -> bool:
        """Delete a planned routine task by ID. Returns True if deleted."""
        pass

    @abstractmethod
    def match_and_resolve_task(self, action: VerifiedAction) -> Optional[PlannedTask]:
        """Match an incoming verified action against pending tasks and resolve the match."""
        pass

    # --- Action State ---

    @abstractmethod
    def save_action(self, action: VerifiedAction) -> str:
        """Save or update a verified action. Returns record ID."""
        pass

    @abstractmethod
    def get_action_status(
        self, action_query: str, target_date: Optional[str] = None
    ) -> Optional[VerifiedAction]:
        """Find the latest verified status for a given action keyword (e.g. 'ferro', 'gas', 'porta')."""
        pass

    @abstractmethod
    def list_recent_actions(
        self, limit: int = 10, domain: Optional[str] = None
    ) -> List[VerifiedAction]:
        """List recently verified actions ordered by timestamp descending."""
        pass

    # --- Social Recall ---
    @abstractmethod
    def save_social_contact(self, contact: SocialEntity) -> str:
        """Save or update a social contact. Returns record ID."""
        pass

    @abstractmethod
    def get_social_contact(self, contact_id_or_name: str) -> Optional[SocialEntity]:
        """Fetch a social contact by ID or exact name."""
        pass

    @abstractmethod
    def update_contact_web_profile(
        self, contact_id_or_name: str, profile: SocialWebProfile
    ) -> bool:
        """Update or attach an autonomous web profile to an existing contact. Returns True if updated."""
        pass

    @abstractmethod
    def search_social_contact(self, query: str) -> List[SocialEntity]:
        """Search contacts by name, company, or key topics."""
        pass

    @abstractmethod
    def save_social_commitment(self, commitment: SocialCommitment) -> str:
        """Save or update a structured bilateral commitment. Returns record ID."""
        pass

    @abstractmethod
    def get_social_commitment(self, commitment_id: str) -> Optional[SocialCommitment]:
        """Fetch a social commitment by its ID."""
        pass

    @abstractmethod
    def list_social_commitments(
        self,
        contact_name: Optional[str] = None,
        debtor: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SocialCommitment]:
        """List social commitments with optional filters."""
        pass

    @abstractmethod
    def update_social_commitment_status(
        self, commitment_id: str, status: str
    ) -> bool:
        """Update status of a commitment ('open', 'fulfilled', 'cancelled'). Returns True if updated."""
        pass

    @abstractmethod
    def delete_social_commitment(self, commitment_id: str) -> bool:
        """Delete a commitment by ID. Returns True if deleted."""
        pass

    # --- Topic Intelligence ---
    @abstractmethod
    def save_topic_briefing(self, briefing: BriefingReport) -> str:
        """Save a synthesized briefing report. Returns record ID."""
        pass

    @abstractmethod
    def get_topic_briefing(self, query: Optional[str] = None) -> Optional[BriefingReport]:
        """Get the latest or matching briefing report."""
        pass

    @abstractmethod
    def list_topic_briefings(
        self, limit: int = 10, kind: Optional[str] = None, session_id: Optional[str] = None
    ) -> List[BriefingReport]:
        """List recently generated briefing reports ordered by created_at descending."""
        pass

    def list_briefings_for_session(self, session_id: str) -> List[BriefingReport]:
        """List all briefings (segment, checkpoint, final, standalone) linked to an event."""
        raise NotImplementedError

    def patch_utterance_speaker(
        self, chunk_id: str, speaker_id: str, speaker_role: Optional[str] = None
    ) -> bool:
        """Retrospectively patches speaker metadata on stored actions/tasks. Returns True if patched."""
        return False

    # --- Macro Session & Micro-Event Decoupling (Milestone 3.2) ---
    def save_session_dossier(self, dossier: Any) -> str:
        """Save or update an aggregate SessionDossier. Returns session_id."""
        raise NotImplementedError

    def get_session_dossier(self, session_id: str) -> Optional[Any]:
        """Fetch a SessionDossier by its session_id."""
        raise NotImplementedError

    def list_session_dossiers(
        self, status: Optional[str] = None, limit: int = 10
    ) -> List[Any]:
        """List session dossiers with optional status filter."""
        raise NotImplementedError

    def append_chunk_to_session(
        self, session_id: str, chunk_text: str, location: Optional[dict] = None
    ) -> Any:
        """Append a transcript chunk to an active or newly initialized session dossier."""
        raise NotImplementedError

    def link_micro_event_to_session(
        self, session_id: str, event_ref: Any
    ) -> bool:
        """Link a decoupled micro-event (action, task, contact) to the parent macro session."""
        raise NotImplementedError

    def conclude_session_dossier(
        self, session_id: str, briefing_report_id: Optional[str] = None
    ) -> Optional[Any]:
        """Mark a session dossier as concluded and link its synthesized briefing report ID."""
        raise NotImplementedError

    # --- Deep Topic Event Engine ---
    def get_open_event(self, ingest_source: str = "live", run_id: Optional[str] = None) -> Optional[Any]:
        """Return the most recent engine-managed event that is active or paused."""
        raise NotImplementedError

    def list_events_pending_final(
        self, limit: int = 20, ingest_source: Optional[str] = None, run_id: Optional[str] = None
    ) -> List[Any]:
        """Return concluded events whose final briefing is still pending."""
        raise NotImplementedError

    def append_session_chunk(
        self, chunk: Any, session_id: str, segment_id: Optional[str] = None, on_topic: bool = False
    ) -> None:
        """Append one utterance chunk to the per-chunk event log."""
        raise NotImplementedError

    def list_session_chunks(
        self,
        session_id: str,
        segment_id: Optional[str] = None,
        in_segments_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[Any]:
        """List logged chunks of an event in chronological order."""
        raise NotImplementedError

    def assign_chunks(
        self,
        chunk_ids: List[str],
        session_id: str,
        segment_id: Optional[str],
        on_topic: Optional[bool] = None,
    ) -> None:
        """Move logged chunks to an event/segment."""
        raise NotImplementedError

    def get_chunk_segments(self, session_id: str) -> Dict[str, Optional[str]]:
        raise NotImplementedError

    def delete_session_dossier(self, session_id: str) -> bool:
        raise NotImplementedError

    def delete_topic_briefing(self, briefing_id: str) -> bool:
        raise NotImplementedError

    def reassign_briefings(self, briefing_ids: List[str], session_id: str) -> None:
        raise NotImplementedError

    # --- Web search cache ---
    def get_cached_search(self, query_norm: str, max_age_seconds: int) -> Optional[dict]:
        """Return {'provider', 'results'} for a cached search younger than max_age_seconds."""
        return None

    def put_cached_search(self, query_norm: str, provider: str, results: List[dict]) -> None:
        """Store web search results for a normalized query."""
        return None

    def record_latency(
        self,
        event_type: str,
        latency_ms: float,
        model_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Records an execution latency sample for performance and telemetry metrics."""
        pass

    def get_latency_metrics(
        self, event_type: Optional[str] = None, limit: int = 50
    ) -> dict:
        """Retrieves aggregated execution latency metrics (average, latest, min, max, count)."""
        return {
            "sample_count": 0,
            "average_ms": 0.0,
            "latest_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
        }

    # -- Historical Transcript Backfill (optional for cloud backends) ---------------
    def get_verified_action(self, action_id: str) -> Optional[Any]:
        raise NotImplementedError

    def save_coverage_interval(self, interval: Any) -> str:
        raise NotImplementedError

    def list_coverage(
        self, start: Optional[str] = None, end: Optional[str] = None, source: Optional[str] = None
    ) -> List[Any]:
        raise NotImplementedError

    def close_open_coverage_intervals(self, source: str = "live") -> int:
        raise NotImplementedError

    def last_coverage_end(self, source: Optional[str] = None) -> Optional[str]:
        raise NotImplementedError

    def record_ingested_utterance(self, entry: Dict[str, Any]) -> None:
        raise NotImplementedError

    def get_ledger_entry(self, source_key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_ledger_entries(
        self, t_from: str, t_to: str, source: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def purge_ingest_ledger(self, before: str) -> int:
        raise NotImplementedError

    def map_bee_conversation(self, conv_uuid: str, conv_id: Optional[int]) -> None:
        raise NotImplementedError

    def get_bee_conversation_uuid(self, conv_id: int) -> Optional[str]:
        raise NotImplementedError

    def save_backfill_run(self, run: Any) -> str:
        raise NotImplementedError

    def get_backfill_run(self, run_id: str) -> Optional[Any]:
        raise NotImplementedError

    def list_backfill_runs(self, statuses: Optional[List[str]] = None, limit: int = 20) -> List[Any]:
        raise NotImplementedError

    def purge_ingestion_history(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close database connection / resources."""
        pass

