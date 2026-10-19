"""Bee conversation history source for the history backfill (docs/next_steps/historical_backfill/01).

The live SSE stream is at-most-once; the REST history (wrapped by bee-cli) keeps every conversation
with its final transcript and per-utterance ``spoken_at``. v1 shells out to the bee binary, exactly
like the live ``BeeClient``, so authentication and proxy configuration stay inside bee-cli.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Protocol

from pydantic import BaseModel, Field

from src.core.config import settings
from src.ingestion.stream_convo import BeeClient, duration_ms

logger = logging.getLogger("examen.ingestion.bee_history")

# Observed: CAPTURING → PROCESSING → COMPLETED (docs/10_bee_cli_reference.md §5); others kept defensively
_IN_PROGRESS_STATES = {"capturing", "processing", "preparing", "analyzing", "recording", "in_progress"}


def epoch_ms(value: Any) -> Optional[int]:
    """Normalises Bee epoch seconds / milliseconds (bee-cli rule: >1e12 ms, >1e9 s)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1e12:
        return int(number)
    if number > 1e9:
        return int(number * 1000)
    return None


class BeeUtterance(BaseModel):
    id: Any = None
    text: str = ""
    speaker: Optional[str] = None  # a person's first name or "Unknown"
    spoken_at_ms: Optional[int] = None
    # Bee `start`/`end` are relative seconds with an unknown origin: only their difference is usable
    duration_ms: Optional[int] = None

    @property
    def ts_ms(self) -> Optional[int]:
        return self.spoken_at_ms

    @property
    def span_ms(self) -> Optional[tuple]:
        start = self.ts_ms
        if start is None:
            return None
        return start, start + max(0, self.duration_ms or 0)


class BeeTranscription(BaseModel):
    id: Any = None
    realtime: bool = False
    utterances: List[BeeUtterance] = Field(default_factory=list)

    def sorted_utterances(self) -> List[BeeUtterance]:
        return sorted(
            (u for u in self.utterances if u.text.strip()),
            key=lambda u: (u.ts_ms if u.ts_ms is not None else 0, str(u.id)),
        )


class BeeConversation(BaseModel):
    id: int
    uuid: Optional[str] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    created_at_ms: Optional[int] = None
    state: Optional[str] = None
    title: Optional[str] = None
    short_summary: Optional[str] = None
    summary: Optional[str] = None
    primary_location: Optional[Dict[str, Any]] = None
    transcriptions: List[BeeTranscription] = Field(default_factory=list)
    has_detail: bool = False

    @property
    def start_ms(self) -> Optional[int]:
        return self.start_time_ms or self.created_at_ms

    @property
    def conversation_key(self) -> str:
        """Identifier used as UtteranceChunk.conversation_uuid for replayed speech."""
        return self.uuid or f"bee-{self.id}"

    def final_transcription(self) -> Optional[BeeTranscription]:
        return next((t for t in self.transcriptions if not t.realtime and t.utterances), None)

    def realtime_transcription(self) -> Optional[BeeTranscription]:
        return next((t for t in self.transcriptions if t.realtime and t.utterances), None)

    def readiness(self, now_ms: int, grace_minutes: Optional[float] = None) -> str:
        """'ready' | 'realtime_fallback' | 'deferred' (doc 01 §2.2)."""
        grace = settings.backfill_final_transcript_grace_minutes if grace_minutes is None else grace_minutes
        if self.end_time_ms is None:
            return "deferred"
        if (self.state or "").strip().lower() in _IN_PROGRESS_STATES:
            return "deferred"
        if self.final_transcription() is not None:
            return "ready"
        if self.realtime_transcription() is not None and now_ms - self.end_time_ms >= grace * 60_000:
            return "realtime_fallback"
        return "deferred"

    def location_telemetry(self) -> Optional[Dict[str, Any]]:
        loc = self.primary_location or {}
        if loc.get("latitude") is None or loc.get("longitude") is None:
            return None
        from src.core.schemas import LocationTelemetry

        return LocationTelemetry(
            latitude=float(loc["latitude"]),
            longitude=float(loc["longitude"]),
            place_name=loc.get("address") or loc.get("name"),
        ).model_dump()

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "BeeConversation":
        """Parses a Bee conversation (list summary or `{conversation: …}` detail payload)."""
        data = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else payload
        transcriptions: List[BeeTranscription] = []
        for tx in data.get("transcriptions") or []:
            utterances = [
                BeeUtterance(
                    id=u.get("id"),
                    text=str(u.get("text") or ""),
                    speaker=u.get("speaker"),
                    spoken_at_ms=epoch_ms(u.get("spoken_at")),
                    duration_ms=duration_ms(u.get("start"), u.get("end")),
                )
                for u in tx.get("utterances") or []
                if isinstance(u, dict)
            ]
            transcriptions.append(BeeTranscription(id=tx.get("id"), realtime=bool(tx.get("realtime")), utterances=utterances))
        return cls(
            id=int(data["id"]),
            uuid=data.get("uuid") or data.get("conversation_uuid"),
            start_time_ms=epoch_ms(data.get("start_time")),
            end_time_ms=epoch_ms(data.get("end_time")),
            created_at_ms=epoch_ms(data.get("created_at")),
            state=data.get("state"),
            title=data.get("title"),
            short_summary=data.get("short_summary"),
            summary=data.get("summary"),
            primary_location=data.get("primary_location"),
            transcriptions=transcriptions,
            has_detail="transcriptions" in data,
        )


def overlaps_window(conv: BeeConversation, since_ms: int, until_ms: int, now_ms: Optional[int] = None) -> bool:
    start = conv.start_ms
    if start is None:
        return False
    end = conv.end_time_ms if conv.end_time_ms is not None else (now_ms or int(time.time() * 1000))
    return start <= until_ms and end >= since_ms


class BeeHistorySource(Protocol):
    async def list_conversations(self, since_ms: int, until_ms: int) -> List[BeeConversation]: ...

    async def get_conversations(self, ids: List[int]) -> List[BeeConversation]: ...


class BeeHistoryError(RuntimeError):
    pass


class CliBeeHistorySource:
    """v1 transport: `bee conversations list/get --json` subprocesses (doc 01 §4, option A)."""

    PAGE_SIZE = 100
    MAX_PAGES = 200

    def __init__(self, client: Optional[BeeClient] = None, concurrency: Optional[int] = None,
                 timeout_seconds: float = 60.0):
        self.client = client or BeeClient()
        self.concurrency = concurrency or settings.backfill_history_concurrency
        self.timeout_seconds = timeout_seconds

    async def _run_json(self, args: List[str]) -> Dict[str, Any]:
        cmd = self.client._build_cmd(args)
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=self.client.subprocess_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            raise BeeHistoryError(f"bee {' '.join(args)} timed out")
        if process.returncode != 0:
            raise BeeHistoryError(f"bee {' '.join(args)} failed: {stderr.decode('utf-8', 'replace').strip()[:300]}")
        try:
            return json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise BeeHistoryError(f"bee {' '.join(args)} returned invalid JSON: {e}")

    async def list_conversations(self, since_ms: int, until_ms: int) -> List[BeeConversation]:
        """Pages newest-first until conversations start before ``since_ms`` minus a safety margin,
        keeping those that overlap [since_ms, until_ms]."""
        margin_ms = int(settings.backfill_lookback_margin_hours * 3_600_000)
        now_ms = int(time.time() * 1000)
        found: Dict[int, BeeConversation] = {}
        cursor: Optional[str] = None
        for _ in range(self.MAX_PAGES):
            args = ["conversations", "list", "--limit", str(self.PAGE_SIZE), "--json"]
            if cursor:
                args += ["--cursor", cursor]
            payload = await self._run_json(args)
            items = payload.get("conversations") or []
            oldest: Optional[int] = None
            for item in items:
                try:
                    conv = BeeConversation.from_payload(item)
                except (KeyError, TypeError, ValueError):
                    continue
                if conv.start_ms is not None:
                    oldest = conv.start_ms if oldest is None else min(oldest, conv.start_ms)
                if overlaps_window(conv, since_ms, until_ms, now_ms):
                    found[conv.id] = conv
            cursor = payload.get("next_cursor")
            if not cursor or not items or (oldest is not None and oldest < since_ms - margin_ms):
                break
        return sorted(found.values(), key=lambda c: c.start_ms or 0)

    async def get_conversations(self, ids: List[int]) -> List[BeeConversation]:
        semaphore = asyncio.Semaphore(max(1, self.concurrency))

        async def _get(conv_id: int) -> Optional[BeeConversation]:
            async with semaphore:
                try:
                    return BeeConversation.from_payload(
                        await self._run_json(["conversations", "get", str(conv_id), "--json"])
                    )
                except (BeeHistoryError, KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to fetch Bee conversation {conv_id}: {e}")
                    return None

        results = await asyncio.gather(*(_get(i) for i in ids))
        return [r for r in results if r is not None]


class FixtureBeeHistorySource:
    """In-memory source (tests, demos): conversation detail payloads as returned by `bee conversations get`."""

    def __init__(self, payloads: Iterable[Dict[str, Any]]):
        self._conversations = {c.id: c for c in (BeeConversation.from_payload(p) for p in payloads)}

    def add(self, payload: Dict[str, Any]) -> None:
        conv = BeeConversation.from_payload(payload)
        self._conversations[conv.id] = conv

    async def list_conversations(self, since_ms: int, until_ms: int) -> List[BeeConversation]:
        now_ms = int(time.time() * 1000)
        return sorted(
            (c for c in self._conversations.values() if overlaps_window(c, since_ms, until_ms, now_ms)),
            key=lambda c: c.start_ms or 0,
        )

    async def get_conversations(self, ids: List[int]) -> List[BeeConversation]:
        return [self._conversations[i] for i in ids if i in self._conversations]
