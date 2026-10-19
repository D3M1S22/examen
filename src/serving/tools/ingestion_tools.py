"""Ingestion coverage tool for the Alexa+ MCP Serving layer (docs/next_steps/historical_backfill/04 §3.2).

Answers "did you miss anything yesterday?": when EXAMEN was offline and what the history backfill
recovered afterwards.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore
from src.ingestion.coverage import compute_gaps, coverage_summary

logger = logging.getLogger("examen.serving.tools.ingestion")


def _day_window(day: str, now: datetime) -> tuple:
    label = (day or "today").strip().lower()
    if label == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if label == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    start = datetime.fromisoformat(label).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, min(start + timedelta(days=1), now)


def _hhmm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except ValueError:
        return iso


def execute_get_ingestion_coverage(
    day: str = "today",
    store: Optional[AbstractContextStore] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Internal implementation: coverage, gaps and recovered entities for one day."""
    ctx_store = store or get_storage_store()
    now = (now or datetime.now()).replace(microsecond=0)
    try:
        start, end = _day_window(day, now)
    except ValueError:
        return {"found": False, "spoken_summary": f"I could not understand the day '{day}'."}
    w_from, w_to = start.isoformat(), end.isoformat()
    intervals = ctx_store.list_coverage(w_from, w_to)
    if not intervals:
        return {
            "found": False,
            "day": w_from[:10],
            "display_template": "INGESTION_COVERAGE_CARD",
            "ui_card_type": "INGESTION_COVERAGE_CARD",
            "spoken_summary": "I have no listening record for that day yet.",
        }
    first_start = max(w_from, min(i.start for i in intervals))
    gaps = compute_gaps(first_start, w_to, intervals, min_gap_seconds=60)
    summary = coverage_summary(w_from, w_to, intervals)

    recovered = {"actions": 0, "contacts": 0, "tasks": 0, "events": 0}
    for run in ctx_store.list_backfill_runs(statuses=["completed", "partial"], limit=50):
        if run.window_to >= w_from and run.window_from <= w_to:
            for key in recovered:
                recovered[key] += run.counters.get(key, 0)

    recovered_seconds = summary.get("backfill_seconds", 0.0)
    parts = []
    if gaps:
        spans = ", ".join(f"from {_hhmm(g.start)} to {_hhmm(g.end)}" for g in gaps[:3])
        parts.append(f"I could not analyse your conversations {spans}.")
    else:
        parts.append("Every Bee conversation of that day has been analysed.")
    if recovered_seconds > 0:
        details = [f"{v} {k}" for k, v in recovered.items() if v]
        parts.append(
            "Conversations recorded while I was offline were recovered afterwards"
            + (f": {', '.join(details)}." if details else ".")
        )
    return {
        "found": True,
        "day": w_from[:10],
        "coverage": summary,
        "gaps": [g.model_dump() for g in gaps],
        "recovered": recovered,
        "display_template": "INGESTION_COVERAGE_CARD",
        "ui_card_type": "INGESTION_COVERAGE_CARD",
        "card_payload": {"day": w_from[:10], "coverage": summary, "gaps": [g.model_dump() for g in gaps],
                         "recovered": recovered},
        "spoken_summary": " ".join(parts),
    }


def get_ingestion_coverage(day: str = "today") -> Dict[str, Any]:
    """Tell the user whether EXAMEN missed any conversation on a given day and what was recovered.

    Args:
        day: 'today', 'yesterday' or an ISO date (YYYY-MM-DD).
    """
    return execute_get_ingestion_coverage(day=day)
