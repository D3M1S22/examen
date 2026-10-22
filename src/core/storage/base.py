"""Abstract interface for EXAMEN context storage.

Two backends implement it: ``SQLiteContextStore`` (one file per user) and ``DynamoContextStore``
(one DynamoDB partition per user, docs/next_steps/dynamodb_storage/). Every method is abstract so a
backend that forgets one fails at construction; ``tests/test_store_contract.py`` checks that both
backends keep these signatures.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.core.schemas import (
    BackfillRun,
    BriefingReport,
    CoverageInterval,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    SpeakerAttribution,
    UtteranceChunk,
    VerifiedAction,
)


class AbstractContextStore(ABC):
    """Abstract Base Class for context and memory persistence."""

    # --- Planned Tasks ---
    @abstractmethod
    def save_planned_task(self, task: PlannedTask) -> str:
        """Create or update a planned routine task. Returns record ID."""

    @abstractmethod
    def get_planned_task(self, task_id: str) -> Optional[PlannedTask]:
        """Retrieve a planned task by ID."""

    @abstractmethod
    def list_planned_tasks(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        origin: Optional[str] = None,
        ingest_source: Optional[str] = None,
    ) -> List[PlannedTask]:
        """List planned tasks (scheduled time first, unscheduled first), optionally filtered."""

    @abstractmethod
    def complete_planned_task(
        self, task_id: str, verified_action_id: str, completed_at: Optional[str] = None
    ) -> bool:
        """Mark a planned task as completed and link the verifying action."""

    @abstractmethod
    def update_planned_task(self, task: PlannedTask) -> bool:
        """Update an existing planned routine task. Returns True if updated."""

    @abstractmethod
    def delete_planned_task(self, task_id: str) -> bool:
        """Delete a planned routine task by ID. Returns True if deleted."""

    @abstractmethod
    def match_and_resolve_task(self, action: VerifiedAction) -> Optional[PlannedTask]:
        """Match an incoming verified action against pending tasks and resolve the match."""

    # --- Action State ---
    @abstractmethod
    def save_action(self, action: VerifiedAction) -> str:
        """Save or update a verified action. Returns record ID."""

    @abstractmethod
    def get_verified_action(self, action_id: str) -> Optional[VerifiedAction]:
        """Fetch a verified action by ID."""

    @abstractmethod
    def set_action_speaker(self, action_id: str, speaker: SpeakerAttribution, revoke: bool = False) -> bool:
        """Record who said an action (late speaker tag); ``revoke`` marks it as not the user's. True if found."""

    @abstractmethod
    def get_action_status(
        self, action_query: str, target_date: Optional[str] = None
    ) -> Optional[VerifiedAction]:
        """Find the latest verified status for a given action keyword (e.g. 'ferro', 'gas', 'porta')."""

    @abstractmethod
    def list_recent_actions(
        self, limit: int = 10, domain: Optional[str] = None, ingest_source: Optional[str] = None
    ) -> List[VerifiedAction]:
        """List recently verified actions ordered by timestamp descending."""

    # --- Social Recall ---
    @abstractmethod
    def save_social_contact(self, contact: SocialEntity) -> str:
        """Save or update a social contact. Returns record ID."""

    @abstractmethod
    def get_social_contact(self, contact_id_or_name: str) -> Optional[SocialEntity]:
        """Fetch a social contact by ID or exact name."""

    @abstractmethod
    def update_contact_web_profile(
        self, contact_id_or_name: str, profile: SocialWebProfile
    ) -> bool:
        """Update or attach an autonomous web profile to an existing contact. Returns True if updated."""

    @abstractmethod
    def search_social_contact(self, query: str) -> List[SocialEntity]:
        """Search contacts by name, company, or key topics."""

    @abstractmethod
    def save_social_commitment(self, commitment: SocialCommitment) -> str:
        """Save or update a structured bilateral commitment. Returns record ID."""

    @abstractmethod
    def get_social_commitment(self, commitment_id: str) -> Optional[SocialCommitment]:
        """Fetch a social commitment by its ID."""

    @abstractmethod
    def list_social_commitments(
        self,
        contact_name: Optional[str] = None,
        debtor: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SocialCommitment]:
        """List social commitments with optional filters."""

    @abstractmethod
    def update_social_commitment_status(self, commitment_id: str, status: str) -> bool:
        """Update status of a commitment ('open', 'fulfilled', 'cancelled'). Returns True if updated."""

    @abstractmethod
    def delete_social_commitment(self, commitment_id: str) -> bool:
        """Delete a commitment by ID. Returns True if deleted."""

    # --- Topic Intelligence ---
    @abstractmethod
    def save_topic_briefing(self, briefing: BriefingReport) -> str:
        """Save a synthesized briefing report. Returns record ID."""

    @abstractmethod
    def get_topic_briefing(self, query: Optional[str] = None) -> Optional[BriefingReport]:
        """Get the latest or matching briefing report."""

    @abstractmethod
    def list_topic_briefings(
        self, limit: int = 10, kind: Optional[str] = None, session_id: Optional[str] = None
    ) -> List[BriefingReport]:
        """List recently generated briefing reports ordered by created_at descending."""

    @abstractmethod
    def list_briefings_for_session(self, session_id: str) -> List[BriefingReport]:
        """List all briefings (segment, checkpoint, final, standalone) linked to an event."""

    @abstractmethod
    def delete_topic_briefing(self, briefing_id: str) -> bool:
        """Delete a briefing. Returns True if deleted."""

    @abstractmethod
    def reassign_briefings(self, briefing_ids: List[str], session_id: str) -> None:
        """Move briefings to another event."""

    @abstractmethod
    def patch_utterance_speaker(
        self, chunk_id: str, speaker_id: str, speaker_role: Optional[str] = None
    ) -> bool:
        """Records a late speaker identity (Bee `tagged-utterance`) for an utterance. Returns True if stored."""

    # --- Macro Session & Micro-Event Decoupling ---
    @abstractmethod
    def save_session_dossier(self, dossier: SessionDossier) -> str:
        """Save or update an aggregate SessionDossier. Returns session_id."""

    @abstractmethod
    def get_session_dossier(
        self, session_id: Optional[str] = None, include_chunks: bool = True
    ) -> Optional[SessionDossier]:
        """Fetch a SessionDossier (no id: the most recently updated one). ``include_chunks=False``
        skips loading the transcript from the per-chunk log."""

    @abstractmethod
    def list_session_dossiers(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        ingest_source: Optional[str] = None,
        ingest_run_id: Optional[str] = None,
    ) -> List[SessionDossier]:
        """List session dossiers, newest start first, with optional filters."""

    @abstractmethod
    def delete_session_dossier(self, session_id: str) -> bool:
        """Delete a dossier (not its chunks). Returns True if deleted."""

    @abstractmethod
    def append_chunk_to_session(
        self, session_id: str, chunk_text: str, location: Optional[dict] = None
    ) -> SessionDossier:
        """Append a transcript chunk to an active or newly initialized session dossier."""

    @abstractmethod
    def link_micro_event_to_session(self, session_id: str, event_ref: Any) -> bool:
        """Link a decoupled micro-event (action, task, contact) to the parent macro session."""

    @abstractmethod
    def conclude_session_dossier(
        self, session_id: str, briefing_report_id: Optional[str] = None
    ) -> Optional[SessionDossier]:
        """Mark a session dossier as concluded and link its synthesized briefing report ID."""

    # --- Deep Topic Event Engine ---
    @abstractmethod
    def get_open_event(self, ingest_source: str = "live", run_id: Optional[str] = None) -> Optional[SessionDossier]:
        """Return the most recent engine-managed event that is active or paused."""

    @abstractmethod
    def list_events_pending_final(
        self, limit: int = 20, ingest_source: Optional[str] = None, run_id: Optional[str] = None
    ) -> List[SessionDossier]:
        """Return concluded events whose final briefing is still pending."""

    @abstractmethod
    def append_session_chunk(
        self, chunk: UtteranceChunk, session_id: str, segment_id: Optional[str] = None, on_topic: bool = False
    ) -> None:
        """Append one utterance chunk to the per-chunk event log (idempotent on chunk_id)."""

    @abstractmethod
    def list_session_chunks(
        self,
        session_id: str,
        segment_id: Optional[str] = None,
        in_segments_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[UtteranceChunk]:
        """List logged chunks of an event in chronological order."""

    @abstractmethod
    def assign_chunks(
        self,
        chunk_ids: List[str],
        session_id: str,
        segment_id: Optional[str],
        on_topic: Optional[bool] = None,
    ) -> None:
        """Move logged chunks to an event/segment."""

    @abstractmethod
    def get_chunk_segments(self, session_id: str) -> Dict[str, Optional[str]]:
        """chunk_id -> segment_id for the chunks of an event."""

    # --- Web search cache ---
    @abstractmethod
    def get_cached_search(self, query_norm: str, max_age_seconds: int) -> Optional[dict]:
        """Return {'provider', 'results'} for a cached search younger than max_age_seconds."""

    @abstractmethod
    def put_cached_search(self, query_norm: str, provider: str, results: List[dict]) -> None:
        """Store web search results for a normalized query."""

    # --- Telemetry ---
    @abstractmethod
    def record_latency(
        self,
        event_type: str,
        latency_ms: float,
        model_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Records an execution latency sample (never raises)."""

    @abstractmethod
    def get_latency_metrics(self, event_type: Optional[str] = None, limit: int = 50) -> dict:
        """Aggregated latency metrics (average, latest, min, max, count) of the latest samples."""

    # --- Historical Transcript Backfill ---
    @abstractmethod
    def save_coverage_interval(self, interval: CoverageInterval) -> str: ...

    @abstractmethod
    def list_coverage(
        self, start: Optional[str] = None, end: Optional[str] = None, source: Optional[str] = None
    ) -> List[CoverageInterval]: ...

    @abstractmethod
    def close_open_coverage_intervals(self, source: str = "live") -> int: ...

    @abstractmethod
    def last_coverage_end(self, source: Optional[str] = None) -> Optional[str]: ...

    @abstractmethod
    def record_ingested_utterance(self, entry: Dict[str, Any]) -> None: ...

    @abstractmethod
    def get_ledger_entry(self, source_key: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def list_ledger_entries(
        self, t_from: str, t_to: str, source: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def purge_ingest_ledger(self, before: str) -> int: ...

    @abstractmethod
    def map_bee_conversation(self, conv_uuid: str, conv_id: Optional[int]) -> None: ...

    @abstractmethod
    def get_bee_conversation_uuid(self, conv_id: int) -> Optional[str]: ...

    @abstractmethod
    def save_backfill_run(self, run: BackfillRun) -> str: ...

    @abstractmethod
    def get_backfill_run(self, run_id: str) -> Optional[BackfillRun]: ...

    @abstractmethod
    def list_backfill_runs(self, statuses: Optional[List[str]] = None, limit: int = 20) -> List[BackfillRun]: ...

    @abstractmethod
    def purge_ingestion_history(self) -> None:
        """GDPR erasure of the backfill bookkeeping (coverage, ledger, conversation map, runs)."""

    # --- Whole store ---
    @abstractmethod
    def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """GDPR Art. 15 / 20: every record of this store as JSON-serialisable rows, by SQLite table name."""

    @abstractmethod
    def delete_all_data(self) -> None:
        """Erases every record of this store (GDPR erasure, reset)."""

    @abstractmethod
    def close(self) -> None:
        """Close database connection / resources."""
