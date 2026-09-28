"""Abstract interface for EXAMEN context storage."""

from abc import ABC, abstractmethod
from typing import List, Optional
from src.core.schemas import VerifiedAction, SocialEntity, BriefingReport


class AbstractContextStore(ABC):
    """Abstract Base Class for context and memory persistence."""

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
    def close(self) -> None:
        """Close database connection / resources."""
        pass
