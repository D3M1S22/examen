"""Backend-neutral storage rules shared by the SQLite and DynamoDB stores.

The domain rules that used to live inside ``SQLiteContextStore`` (task matching, commitment and
contact dedup keys, latency summaries) and the row → model mappers. Both backends call these, so a
rule changes in one place (docs/next_steps/dynamodb_storage/01_current_state.md §3).

A "row" is anything with ``keys()`` and ``[]``: ``sqlite3.Row`` or a plain dict.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

from src.core.schemas import (
    BriefingReport,
    CoverageInterval,
    EventTransitionLog,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SessionSegment,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    SpeakerAttribution,
    TopicProfile,
    VerifiedAction,
)

STOP_WORDS = frozenset({"the", "and", "for", "with", "this", "that", "from", "into", "over", "take", "make", "turn", "out"})
_WORD = re.compile(r"\b[a-zA-Z]{3,}\b")
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


# ---------------------------------------------------------------------------
# Matching rules
# ---------------------------------------------------------------------------

def keywords(text: str) -> List[str]:
    """Words of at least 3 letters minus the stop list (task titles, commitment descriptions, names)."""
    return [w for w in _WORD.findall((text or "").lower()) if w not in STOP_WORDS]


def action_text(action: VerifiedAction) -> str:
    return f"{action.action_type} {action.raw_statement}".lower()


def action_matches_task(text: str, task: PlannedTask) -> bool:
    words = keywords(task.title)
    return bool(words) and any(w in text for w in words)


def action_matches_commitment(text: str, commitment: SocialCommitment) -> bool:
    words = keywords(commitment.description)
    contact_words = keywords(commitment.contact_name)
    return bool(words) and any(w in text for w in words) and (
        not contact_words or any(cw in text for cw in contact_words)
    )


def contact_name_key(name: str) -> str:
    """``LOWER(person_name)`` of the SQLite dedup query."""
    return (name or "").strip().lower()


def commitment_key(contact_name: str, description: str, debtor: str) -> str:
    """Dedup key of ``save_social_commitment``: (LOWER(contact), LOWER(description), debtor)."""
    raw = f"{(contact_name or '').lower()}\x1f{(description or '').lower()}\x1f{debtor}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_action_type(text: str) -> str:
    """A user-edited action title in the pipeline's format: trimmed, lower case, ``_`` between words."""
    return re.sub(r"\s+", "_", (text or "").strip().lower())[:80]


# Fields the web profiler disambiguates a contact with: changing one invalidates the web profile
CONTACT_ANCHORS = ("person_name", "company_or_role")


def contact_cascade(store: Any, contact_name: str) -> List[SocialCommitment]:
    """The commitments that go with a contact (matched by name, as the stores do); each may carry
    the ``auto_scheduled_task_id`` it scheduled. Shared by the delete and its preview."""
    if not (contact_name or "").strip():
        return []
    return store.list_social_commitments(contact_name=contact_name, limit=10_000)


def latency_summary(values: List[float]) -> Dict[str, Any]:
    """Aggregate of the latest-first latency samples returned by ``get_latency_metrics``."""
    if not values:
        return {"sample_count": 0, "average_ms": 0.0, "latest_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
    return {
        "sample_count": len(values),
        "average_ms": round(sum(values) / len(values), 1),
        "latest_ms": round(values[0], 1),
        "min_ms": round(min(values), 1),
        "max_ms": round(max(values), 1),
    }


@lru_cache(maxsize=256)
def _like_regex(pattern: str) -> "re.Pattern[str]":
    parts = []
    for ch in pattern.translate(_ASCII_LOWER):
        if ch == "%":
            parts.append(".*")
        elif ch == "_":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.compile("".join(parts), re.DOTALL)


def ascii_lower(value: str) -> str:
    """SQLite's ``LOWER()`` without ICU: folds ASCII letters only."""
    return value.translate(_ASCII_LOWER)


def sql_like(value: Any, pattern: str) -> bool:
    """SQLite's default ``value LIKE pattern``: ASCII-only case folding, ``%`` and ``_`` wildcards,
    NULL never matches."""
    if value is None:
        return False
    return _like_regex(pattern).fullmatch(str(value).translate(_ASCII_LOWER)) is not None


# ---------------------------------------------------------------------------
# Row → model mappers
# ---------------------------------------------------------------------------

def _get(row: Any, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() and row[key] is not None else default


def _json(row: Any, key: str, default: Any) -> Any:
    raw = _get(row, key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def speaker_from_row(row: Any) -> Optional[SpeakerAttribution]:
    data = _json(row, "speaker_json", None)
    if not isinstance(data, dict):
        return None
    try:
        return SpeakerAttribution.model_validate(data)
    except ValueError:
        return None


def speaker_to_json(speaker: Optional[SpeakerAttribution]) -> Optional[str]:
    return speaker.model_dump_json() if speaker is not None else None


def row_to_planned_task(r: Any) -> PlannedTask:
    return PlannedTask(
        id=r["id"],
        title=r["title"],
        domain=r["domain"],
        scheduled_time=_get(r, "scheduled_time"),
        recurrence=r["recurrence"],
        status=r["status"],
        completed_at=_get(r, "completed_at"),
        verified_action_id=_get(r, "verified_action_id"),
        created_at=r["created_at"],
        origin=_get(r, "origin") or "manual",
        raw_statement=_get(r, "raw_statement"),
        confidence=_get(r, "confidence", 1.0),
        relative_time_anchor=_get(r, "relative_time_anchor"),
        session_id=_get(r, "session_id"),
        location=_json(r, "location_json", None),
        ingest_source=_get(r, "ingest_source") or "live",
        ingest_run_id=_get(r, "ingest_run_id"),
        source_key=_get(r, "source_key"),
        recovered=bool(_get(r, "recovered", 0)),
        speaker=speaker_from_row(r),
    )


def row_to_action(row: Any) -> VerifiedAction:
    return VerifiedAction(
        id=row["id"],
        action_type=row["action_type"],
        domain=row["domain"],
        raw_statement=row["raw_statement"],
        confidence=row["confidence"],
        timestamp=row["timestamp"],
        is_revoked=bool(_get(row, "is_revoked", 0)),
        matched_task_id=_get(row, "matched_task_id"),
        session_id=_get(row, "session_id"),
        location=_json(row, "location_json", None),
        ingest_source=_get(row, "ingest_source") or "live",
        ingest_run_id=_get(row, "ingest_run_id"),
        source_key=_get(row, "source_key"),
        speaker=speaker_from_row(row),
    )


def row_to_commitment(r: Any) -> SocialCommitment:
    return SocialCommitment(
        id=r["id"],
        contact_name=r["contact_name"],
        debtor=r["debtor"],
        description=r["description"],
        due_date_raw=_get(r, "due_date_raw"),
        normalized_deadline=_get(r, "normalized_deadline"),
        status=r["status"],
        auto_scheduled_task_id=_get(r, "auto_scheduled_task_id"),
        created_at=r["created_at"],
    )


def row_to_contact(row: Any, commitments: List[Any]) -> SocialEntity:
    """``commitments`` are the structured ones of this contact; the legacy JSON column is the fallback."""
    if not commitments:
        commitments = _json(row, "commitments_json", [])
    web_profile = None
    raw_profile = _get(row, "web_profile_json")
    if raw_profile:
        try:
            web_profile = SocialWebProfile.model_validate_json(raw_profile)
        except Exception:
            pass
    website_url = _get(row, "website_url") or None
    if not website_url and web_profile and web_profile.website_url:
        website_url = web_profile.website_url
    return SocialEntity(
        id=row["id"],
        person_name=row["person_name"],
        company_or_role=_get(row, "company_or_role"),
        contact_info=_get(row, "contact_info"),
        website_url=website_url,
        commitments=commitments,
        key_topics=_json(row, "key_topics_json", []),
        web_profile=web_profile,
        location_encountered=_get(row, "location_encountered") or None,
        session_id=_get(row, "session_id") or None,
        timestamp=row["timestamp"],
    )


def row_to_briefing(row: Any) -> BriefingReport:
    return BriefingReport(
        id=row["id"],
        topic_title=row["topic_title"],
        context_type=row["context_type"],
        executive_summary=_json(row, "executive_summary_json", []),
        explanatory_synthesis=_get(row, "explanatory_synthesis") or "",
        deep_dive_markdown=_get(row, "deep_dive_markdown") or "",
        web_sources=_json(row, "web_sources_json", []),
        action_items=_json(row, "action_items_json", []),
        created_at=row["created_at"],
        session_id=_get(row, "session_id"),
        segment_id=_get(row, "segment_id"),
        kind=_get(row, "kind") or "standalone",
    )


def _models(items: Iterable[Any], model: Any) -> List[Any]:
    out = []
    for item in items:
        try:
            out.append(model(**item) if isinstance(item, dict) else item)
        except Exception:
            pass
    return out


def row_to_dossier(row: Any, chunks: Optional[List[str]], briefing: Optional[BriefingReport]) -> SessionDossier:
    """``chunks`` are the texts of the per-chunk log (None or empty: the legacy JSON column)."""
    profile_raw = _json(row, "topic_profile_json", None)
    profile = None
    if profile_raw:
        try:
            profile = TopicProfile(**profile_raw)
        except Exception:
            profile = None
    status = row["status"]
    if status == "finalizing":
        status = "paused"
    return SessionDossier(
        session_id=row["session_id"],
        title=_get(row, "title"),
        domain=row["domain"],
        start_time=row["start_time"],
        last_updated_at=row["last_updated_at"],
        concluded_at=_get(row, "concluded_at"),
        status=status,
        location=_json(row, "location_json", None),
        transcript_chunks=chunks if chunks else _json(row, "transcript_chunks_json", []),
        key_discussion_points=_json(row, "key_discussion_points_json", []),
        linked_micro_events=_models(_json(row, "linked_micro_events_json", []), MicroEventRef),
        final_briefing_id=_get(row, "final_briefing_id"),
        briefing_report=briefing,
        conversation_uuids=_json(row, "conversation_uuids_json", []),
        segments=_models(_json(row, "segments_json", []), SessionSegment),
        anchor_location=_json(row, "anchor_location_json", None),
        last_on_topic_at=_get(row, "last_on_topic_at"),
        paused_at=_get(row, "paused_at"),
        hard_close_deadline=_get(row, "hard_close_deadline"),
        final_status=_get(row, "final_status") or "none",
        final_revision=_get(row, "final_revision") or 0,
        transitions=_models(_json(row, "transitions_json", []), EventTransitionLog),
        research_ledger=_json(row, "research_ledger_json", []),
        topic_profile=profile,
        pending_chunk_ids=_json(row, "pending_chunk_ids_json", []),
        ingest_source=_get(row, "ingest_source") or "live",
        ingest_run_id=_get(row, "ingest_run_id"),
    )


def dossier_columns(dossier: SessionDossier, chunks_json: Optional[str]) -> Dict[str, Any]:
    """The ``session_dossiers`` columns of a dossier (``chunks_json``: None when the per-chunk log is used)."""
    def _dump(value: Any) -> Optional[str]:
        return json.dumps(value, ensure_ascii=False) if value else None

    events_payload = [e.model_dump() if hasattr(e, "model_dump") else e for e in dossier.linked_micro_events]
    return {
        "session_id": dossier.session_id,
        "title": dossier.title,
        "domain": dossier.domain,
        "start_time": dossier.start_time,
        "last_updated_at": dossier.last_updated_at,
        "concluded_at": dossier.concluded_at,
        "status": dossier.status,
        "location_json": _dump(dossier.location),
        "transcript_chunks_json": chunks_json,
        "key_discussion_points_json": json.dumps(dossier.key_discussion_points, ensure_ascii=False),
        "linked_micro_events_json": json.dumps(events_payload, ensure_ascii=False),
        "final_briefing_id": dossier.final_briefing_id,
        "created_at": dossier.start_time,
        "conversation_uuids_json": _dump(dossier.conversation_uuids),
        "segments_json": _dump([seg.model_dump() for seg in dossier.segments]),
        "anchor_location_json": _dump(dossier.anchor_location),
        "last_on_topic_at": dossier.last_on_topic_at,
        "paused_at": dossier.paused_at,
        "hard_close_deadline": dossier.hard_close_deadline,
        "final_status": dossier.final_status,
        "final_revision": dossier.final_revision,
        "transitions_json": _dump([t.model_dump() for t in dossier.transitions]),
        "research_ledger_json": _dump(dossier.research_ledger),
        "topic_profile_json": dossier.topic_profile.model_dump_json() if dossier.topic_profile else None,
        "pending_chunk_ids_json": _dump(dossier.pending_chunk_ids),
        "ingest_source": dossier.ingest_source,
        "ingest_run_id": dossier.ingest_run_id,
    }


def row_to_coverage(row: Any) -> CoverageInterval:
    return CoverageInterval(
        id=row["id"],
        source=row["source"],
        start=row["start_ts"],
        end=row["end_ts"],
        is_open=bool(_get(row, "is_open", 0)),
        degraded=bool(_get(row, "degraded", 0)),
        run_id=_get(row, "run_id"),
        utterances=_get(row, "utterances") or 0,
        errors=_get(row, "errors") or 0,
    )


LEDGER_COLUMNS = ("source_key", "source", "bee_conversation_uuid", "bee_conversation_id", "ts", "received_at",
                  "text_norm", "text_hash", "status", "categories_json", "run_id", "duration_ms")


def row_to_ledger(row: Any) -> Dict[str, Any]:
    data = {key: (row[key] if key in row.keys() else None) for key in LEDGER_COLUMNS}
    try:
        data["categories"] = json.loads(data.pop("categories_json") or "[]")
    except (TypeError, ValueError):
        data["categories"] = []
    return data
