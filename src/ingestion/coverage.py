"""Ingestion coverage: what EXAMEN has actually analysed (docs/next_steps/historical_backfill/02).

- Coverage intervals are a cheap, conservative *hypothesis* of when the live stream was healthy.
- The utterance ledger is the *evidence* of what was received and analysed (noop included).
Both feed gap detection and the live/backfill de-duplication of the history backfill.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.core.config import settings
from src.core.schemas import CoverageGap, CoverageInterval, UtteranceChunk
from src.core.storage.base import AbstractContextStore
from src.core.time_utils import parse_local_iso

logger = logging.getLogger("examen.ingestion.coverage")

_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES_RE = re.compile(r"\s+")
TEXT_NORM_MAX_CHARS = 300


# ---------------------------------------------------------------------------
# Text normalisation & keys
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Lower-case, accent-folded, punctuation-free, single-spaced text (ASR comparison form)."""
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = _NON_WORD_RE.sub(" ", folded.lower())
    return _SPACES_RE.sub(" ", folded).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def token_jaccard(a: str, b: str) -> float:
    ta, tb = set(normalize_text(a).split()), set(normalize_text(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def live_source_key(conversation_uuid: Optional[str], chunk_id: str) -> str:
    return f"live:{conversation_uuid or 'unknown'}:{chunk_id}"


def bee_source_key(conversation_id: int, transcription_id: Any, utterance_id: Any) -> str:
    return f"bee:{conversation_id}:{transcription_id}:{utterance_id}"


def stable_chunk_id(conversation_uuid: Optional[str], received_at: Optional[str], text: str) -> str:
    """Fallback utterance id when the stream payload has none: stable across re-deliveries."""
    digest = hashlib.sha1(f"{conversation_uuid}|{received_at}|{text}".encode("utf-8")).hexdigest()
    return f"utt-{digest[:16]}"


def ledger_entry_for_chunk(
    chunk: UtteranceChunk,
    status: str,
    source: str = "live",
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds an ingest-ledger row for a processed utterance."""
    return {
        "source_key": chunk.source_key or live_source_key(chunk.conversation_uuid, chunk.chunk_id),
        "source": source,
        "bee_conversation_uuid": chunk.conversation_uuid if chunk.conversation_uuid != "default_session" else None,
        "bee_conversation_id": chunk.bee_conversation_id,
        "ts": chunk.timestamp,
        "received_at": chunk.received_at,
        "text_norm": normalize_text(chunk.text)[:TEXT_NORM_MAX_CHARS],
        "text_hash": text_hash(chunk.text),
        "status": status,
        "categories": list(chunk.categories or []),
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Interval arithmetic
# ---------------------------------------------------------------------------

Span = Tuple[float, float]


def to_epoch(value: Optional[str]) -> Optional[float]:
    parsed = parse_local_iso(value)
    return parsed.timestamp() if parsed else None


def to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).replace(microsecond=0).isoformat()


def merge_spans(spans: Iterable[Span], tolerance: float = 0.0) -> List[Span]:
    """Union of spans; spans closer than ``tolerance`` seconds are joined."""
    ordered = sorted((a, b) for a, b in spans if b >= a)
    merged: List[Span] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + tolerance:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract_spans(window: Span, covered: Iterable[Span]) -> List[Span]:
    """window − ⋃covered, as ordered disjoint spans."""
    start, end = window
    gaps: List[Span] = []
    cursor = start
    for c_start, c_end in merge_spans(covered):
        if c_end <= cursor:
            continue
        if c_start >= end:
            break
        if c_start > cursor:
            gaps.append((cursor, min(c_start, end)))
        cursor = max(cursor, c_end)
        if cursor >= end:
            break
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def interval_spans(intervals: Iterable[CoverageInterval]) -> List[Span]:
    spans: List[Span] = []
    for interval in intervals:
        s, e = to_epoch(interval.start), to_epoch(interval.end)
        if s is not None and e is not None:
            spans.append((s, e))
    return spans


def compute_gaps(
    window_from: str,
    window_to: str,
    intervals: Iterable[CoverageInterval],
    min_gap_seconds: float = 0.0,
) -> List[CoverageGap]:
    start, end = to_epoch(window_from), to_epoch(window_to)
    if start is None or end is None or end <= start:
        return []
    gaps = subtract_spans((start, end), interval_spans(intervals))
    return [
        CoverageGap(start=to_iso(a), end=to_iso(b), seconds=round(b - a, 1))
        for a, b in gaps
        if b - a >= min_gap_seconds
    ]


def coverage_summary(window_from: str, window_to: str, intervals: List[CoverageInterval]) -> Dict[str, float]:
    """Seconds of the window covered by live / backfill intervals and left uncovered."""
    start, end = to_epoch(window_from), to_epoch(window_to)
    if start is None or end is None or end <= start:
        return {"live_seconds": 0.0, "backfill_seconds": 0.0, "gap_seconds": 0.0}

    def _covered(source: str) -> float:
        spans = interval_spans(i for i in intervals if i.source == source)
        return sum(min(b, end) - max(a, start) for a, b in merge_spans(spans) if b > start and a < end)

    live = _covered("live")
    gap = sum(b - a for a, b in subtract_spans((start, end), interval_spans(intervals)))
    total = end - start
    return {
        "live_seconds": round(live, 1),
        "backfill_seconds": round(max(0.0, total - gap - live), 1),
        "gap_seconds": round(gap, 1),
    }


def coverage_buckets(
    window_from: str, window_to: str, intervals: List[CoverageInterval], bucket: str = "hour"
) -> List[Dict[str, Any]]:
    """Per-hour/day coverage strip for the UI timeline."""
    start, end = to_epoch(window_from), to_epoch(window_to)
    if start is None or end is None or end <= start:
        return []
    step = 3600.0 if bucket == "hour" else 86400.0
    first = datetime.fromtimestamp(start)
    first = first.replace(minute=0, second=0, microsecond=0) if bucket == "hour" else first.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    out: List[Dict[str, Any]] = []
    cursor = first.timestamp()
    while cursor < end and len(out) < 24 * 60:
        b_start, b_end = max(cursor, start), min(cursor + step, end)
        if b_end > b_start:
            summary = coverage_summary(to_iso(b_start), to_iso(b_end), intervals)
            out.append({"start": to_iso(b_start), "end": to_iso(b_end), **summary})
        cursor = (datetime.fromtimestamp(cursor) + timedelta(seconds=step)).timestamp()
    return out


# ---------------------------------------------------------------------------
# Live coverage tracker
# ---------------------------------------------------------------------------

class CoverageTracker:
    """Records live coverage intervals from stream liveness (doc 02 §2.1).

    Intervals open on the first proof of life, extend on every stream line, are flushed every
    ``flush_seconds`` and close at the *last* proof of life, so the error always leans towards
    "not covered" (the utterance ledger then prevents duplicates on the overlap).
    """

    def __init__(
        self,
        store_getter: Callable[[], AbstractContextStore],
        flush_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.time,
        on_gap: Optional[Callable[[CoverageGap], None]] = None,
        on_open: Optional[Callable[[CoverageInterval, Optional[CoverageGap]], None]] = None,
    ):
        self._store_getter = store_getter
        self.flush_seconds = settings.coverage_flush_seconds if flush_seconds is None else flush_seconds
        self.clock = clock
        self.on_gap = on_gap
        self.on_open = on_open
        self.current: Optional[CoverageInterval] = None
        self.last_closed_end: Optional[float] = None
        self._last_alive: Optional[float] = None
        self._last_flush: float = 0.0

    @property
    def store(self) -> AbstractContextStore:
        return self._store_getter()

    def recover_after_crash(self) -> None:
        """Closes intervals left open by a previous process and remembers where coverage ended."""
        try:
            self.store.close_open_coverage_intervals("live")
            last = self.store.last_coverage_end("live")
            self.last_closed_end = to_epoch(last) if last else None
        except NotImplementedError:
            pass
        except Exception as e:
            logger.warning(f"Coverage recovery failed: {e}")

    def mark_alive(self, now: Optional[float] = None) -> None:
        now = self.clock() if now is None else now
        self._last_alive = now
        if self.current is None:
            self._open(now)
            return
        self.current.end = to_iso(now)
        if now - self._last_flush >= self.flush_seconds:
            self._flush(now)

    def record_utterance(self, failed: bool = False) -> None:
        if self.current is None:
            self.mark_alive()
        assert self.current is not None
        self.current.utterances += 1
        if failed:
            self.current.errors += 1

    def mark_disconnected(self) -> None:
        """Closes the open interval at the last proof of life."""
        if self.current is None:
            return
        end = self._last_alive or to_epoch(self.current.end) or self.clock()
        self.current.end = to_iso(end)
        self.current.is_open = False
        n = self.current.utterances
        self.current.degraded = n > 0 and self.current.errors / n > settings.coverage_degraded_error_rate
        self._save(self.current)
        self.last_closed_end = end
        self.current = None

    def _open(self, now: float) -> None:
        gap: Optional[CoverageGap] = None
        if self.last_closed_end is not None and now - self.last_closed_end > 0:
            gap = CoverageGap(
                start=to_iso(self.last_closed_end), end=to_iso(now), seconds=round(now - self.last_closed_end, 1)
            )
        self.current = CoverageInterval(source="live", start=to_iso(now), end=to_iso(now), is_open=True)
        self._flush(now)
        if gap is not None and self.on_gap is not None:
            try:
                self.on_gap(gap)
            except Exception as e:
                logger.debug(f"Coverage gap listener error: {e}")
        if self.on_open is not None:
            try:
                self.on_open(self.current, gap)
            except Exception as e:
                logger.debug(f"Coverage open listener error: {e}")

    def _flush(self, now: float) -> None:
        self._last_flush = now
        if self.current is not None:
            self._save(self.current)

    def _save(self, interval: CoverageInterval) -> None:
        try:
            self.store.save_coverage_interval(interval)
        except NotImplementedError:
            pass
        except Exception as e:
            logger.warning(f"Failed to persist coverage interval: {e}")
