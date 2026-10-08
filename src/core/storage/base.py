"""Abstract interface for EXAMEN context storage."""

from abc import ABC, abstractmethod
from typing import List, Optional
from src.core.schemas import (
    BriefingReport,
    PlannedTask,
    SocialCommitment,
    SocialEntity,
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
    def list_topic_briefings(self, limit: int = 10) -> List[BriefingReport]:
        """List recently generated briefing reports ordered by created_at descending."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection / resources."""
        pass
