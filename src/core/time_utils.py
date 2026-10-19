"""Time helpers shared by storage and pipeline (utterance-time semantics for history backfill)."""

from datetime import datetime
from typing import Optional


def parse_local_iso(value: Optional[str]) -> Optional[datetime]:
    """Parses an ISO timestamp into a naive local datetime (None when missing or invalid)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def historical_action_may_resolve(
    action_ts: Optional[str], created_at: Optional[str], recurrence: str = "none", now: Optional[datetime] = None
) -> bool:
    """Temporal guard for actions recovered from history (docs/next_steps/historical_backfill/03 §4.1).

    A past action can only resolve a task/commitment that already existed when it was spoken, and a
    recurring routine only when the action falls inside the routine's *current* occurrence.
    """
    when = parse_local_iso(action_ts)
    if when is None:
        return False
    created = parse_local_iso(created_at)
    if created is not None and created > when:
        return False
    if recurrence in ("daily", "weekdays", "weekly"):
        today = (now or datetime.now()).date()
        if recurrence == "weekly":
            return when.date().isocalendar()[:2] == today.isocalendar()[:2]
        return when.date() == today
    return True
