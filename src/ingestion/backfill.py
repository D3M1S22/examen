"""Historical Transcript Backfill (docs/next_steps/historical_backfill/).

The live Bee stream is at-most-once: while EXAMEN is offline, speech is never screened. Bee keeps the
history, so this module recovers it:

- ``BackfillPlanner``: cost-free planning (REST only). Lists the Bee conversations of a window, picks
  the final transcription and selects only the utterances live never analysed (doc 02 §4).
- ``ReplayExecutor``: replays the selection through the gatekeeper → isolated EventEngine on a virtual
  clock → LangGraph pipeline, in chronological order, with utterance-time semantics (doc 03).
- ``BackfillService``: run queue, persistence/resume, startup & reconnect triggers, hand-over and
  stitching with the live engine, progress broadcasting.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from src.core.config import settings
from src.core.schemas import (
    BackfillEstimate,
    BackfillPlan,
    BackfillRun,
    ChunkClassification,
    CoverageGap,
    CoverageInterval,
    PlannedTask,
    UtteranceChunk,
)
from src.core.storage import get_storage_store
from src.core.storage.base import AbstractContextStore
from src.ingestion.bee_history import BeeConversation, BeeHistorySource, BeeUtterance, CliBeeHistorySource
from src.ingestion.bee_identity import get_wearer_identity
from src.ingestion.coverage import (
    Span,
    bee_source_key,
    compute_gaps,
    coverage_summary,
    interval_spans,
    ledger_entry_for_chunk,
    merge_spans,
    normalize_text,
    subtract_spans,
    text_hash,
    to_epoch,
    to_iso,
    token_jaccard,
)
from src.ingestion.event_engine import EngineConfig, EventEngine, build_continuity_from_settings

logger = logging.getLogger("examen.ingestion.backfill")

ACTIVE_STATUSES = ("planned", "fetching", "replaying", "synthesizing")
LIVE_MATCH_EARLY_SECONDS = 10.0
PREVIEW_CACHE_SECONDS = 300.0
DEFERRED_RECHECK_SECONDS = 900.0
DEFERRED_GIVE_UP_SECONDS = 86400.0
# Rough per-call latencies from the live benchmark (README): gatekeeper ~0.95 s, pipeline ~3.5 s
GATEKEEPER_SECONDS = 0.95
PIPELINE_SECONDS = 3.5
SYNTHESIS_SECONDS = 30.0
QUALIFIED_RATIO = 0.10


class BackfillRequestError(ValueError):
    """Invalid backfill request; ``code`` maps to the REST status (doc 04 §3)."""

    def __init__(self, code: str, message: str, status: int = 422, extra: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.extra = extra or {}


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

@dataclass
class SelectedUtterance:
    source_key: str
    conversation_id: int
    transcription_id: Any
    utterance: BeeUtterance
    ts: float                      # spoken time, epoch seconds
    prior_context: str = ""
    speaker_role: str = "unknown"


@dataclass
class PlanResult:
    plan: BackfillPlan
    items: List[SelectedUtterance] = field(default_factory=list)
    conversations: Dict[int, BeeConversation] = field(default_factory=dict)
    deferred_spans: List[Span] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


def speaker_role_for(speaker: Optional[str]) -> str:
    """REST speakers are first names or "Unknown": the wearer's name ⇒ user (docs/10 §8)."""
    return get_wearer_identity().role_for(speaker)


def _context_line(utt: BeeUtterance) -> str:
    role = speaker_role_for(utt.speaker)
    role_tag = f" ({role})" if role != "unknown" else ""
    return f"[{utt.speaker or 'Speaker'}{role_tag}]: {utt.text.strip()}"


class _LiveEvidence:
    """Live ledger rows used to decide which REST utterances live already analysed.

    Matching is one-to-one: a live row explains at most one REST utterance. Exact (hash) matches are
    assigned first, fuzzy ones only on the leftovers, so repetitive speech ("sentence 1 / sentence 2")
    cannot be explained twice by the same live row.
    """

    def __init__(self, rows: List[Dict[str, Any]], counted_statuses: Set[str]):
        self.rows: List[Dict[str, Any]] = []
        self.by_hash: Dict[str, List[int]] = {}
        # Speech spans live analysed ([spoken_at, spoken_at + duration]), for re-segmented finals
        spans: List[Tuple[Optional[str], Span]] = []
        for row in rows:
            if row.get("status") not in counted_statuses:
                continue
            t = to_epoch(row.get("received_at") or row.get("ts"))
            if t is None:
                continue
            idx = len(self.rows)
            self.rows.append({"t": t, "uuid": row.get("bee_conversation_uuid"),
                              "norm": row.get("text_norm") or "", "used": False})
            self.by_hash.setdefault(row["text_hash"], []).append(idx)
            spoken = to_epoch(row.get("ts"))
            if spoken is not None and row.get("duration_ms"):
                spans.append((row.get("bee_conversation_uuid"), (spoken, spoken + row["duration_ms"] / 1000.0)))
        self._spans = spans

    def covered_fraction(self, span: Span, conv_uuid: Optional[str], merge_tolerance: float) -> float:
        """Share of ``span`` covered by live speech of the same conversation (pauses ≤ tolerance bridged)."""
        start, end = span
        if end <= start:
            return 0.0
        live = merge_spans(
            [s for uuid, s in self._spans if self._uuid_ok(uuid, conv_uuid) and s[1] >= start and s[0] <= end],
            tolerance=merge_tolerance,
        )
        covered = sum(max(0.0, min(end, b) - max(start, a)) for a, b in live)
        return covered / (end - start)

    @staticmethod
    def _uuid_ok(row_uuid: Optional[str], conv_uuid: Optional[str]) -> bool:
        return not row_uuid or not conv_uuid or row_uuid == conv_uuid

    def match(self, utterances: List[Tuple[str, float]], conv_uuid: Optional[str],
              fuzzy_threshold: float, match_window: float) -> List[bool]:
        """For each (text, spoken_time) returns whether a live row explains it (rows are consumed)."""
        matched = [False] * len(utterances)
        windows = [(t - LIVE_MATCH_EARLY_SECONDS, t + match_window) for _, t in utterances]
        for i, (text, t) in enumerate(utterances):
            lo, hi = windows[i]
            candidates = [
                idx for idx in self.by_hash.get(text_hash(text), [])
                if not self.rows[idx]["used"] and lo <= self.rows[idx]["t"] <= hi
                and self._uuid_ok(self.rows[idx]["uuid"], conv_uuid)
            ]
            if candidates:
                best = min(candidates, key=lambda idx: abs(self.rows[idx]["t"] - t))
                self.rows[best]["used"] = True
                matched[i] = True
        for i, (text, t) in enumerate(utterances):
            if matched[i]:
                continue
            norm = normalize_text(text)
            if not norm:
                continue
            lo, hi = windows[i]
            best_idx, best_score = None, fuzzy_threshold
            for idx, row in enumerate(self.rows):
                if row["used"] or not (lo <= row["t"] <= hi) or not self._uuid_ok(row["uuid"], conv_uuid):
                    continue
                score = token_jaccard(norm, row["norm"])
                if score >= best_score:
                    best_idx, best_score = idx, score
            if best_idx is not None:
                self.rows[best_idx]["used"] = True
                matched[i] = True
        return matched


class BackfillPlanner:
    """Cost-free planning: REST calls to Bee only, no LLM (doc 02 §4)."""

    def __init__(
        self,
        source: BeeHistorySource,
        store_getter: Callable[[], AbstractContextStore] = get_storage_store,
        clock: Callable[[], float] = time.time,
    ):
        self.source = source
        self._store_getter = store_getter
        self.clock = clock

    @property
    def store(self) -> AbstractContextStore:
        return self._store_getter()

    async def plan(self, window_from: str, window_to: str, retry_failed_live: bool = True) -> PlanResult:
        start, end = to_epoch(window_from), to_epoch(window_to)
        if start is None or end is None or end <= start:
            raise BackfillRequestError("invalid_window", "window_from must be before window_to")
        now = self.clock()
        match_window = settings.backfill_match_window_seconds
        warnings: List[str] = []

        intervals = self.store.list_coverage(to_iso(start - match_window), to_iso(end + match_window))
        backfill_spans = merge_spans(interval_spans(i for i in intervals if i.source == "backfill"))
        live_spans = merge_spans(interval_spans(i for i in intervals if i.source == "live"))

        counted = {"screened_noop", "qualified"} | (set() if retry_failed_live else {"failed"})
        live_rows = self.store.list_ledger_entries(
            to_iso(start - match_window - 60), to_iso(end + match_window + 60), source="live"
        )
        evidence = _LiveEvidence(live_rows, counted)
        retry_failed = sum(1 for r in live_rows if r.get("status") == "failed") if retry_failed_live else 0
        done_backfill = {
            r["source_key"]
            for r in self.store.list_ledger_entries(to_iso(start - 86400), to_iso(end + 86400), source="backfill")
            if r.get("status") != "failed"
        }
        horizon = now - settings.backfill_ledger_retention_days * 86400
        if start < horizon:
            warnings.append(
                f"Live ledger retention ({settings.backfill_ledger_retention_days:g} days) exceeded before "
                f"{to_iso(horizon)}: older speech is de-duplicated by coverage time only"
            )

        summaries = await self.source.list_conversations(int(start * 1000), int(end * 1000))
        need_detail = [c.id for c in summaries if not c.has_detail and c.end_time_ms is not None]
        details = {c.id: c for c in summaries if c.has_detail}
        if need_detail:
            for conv in await self.source.get_conversations(need_detail):
                details[conv.id] = conv

        counts = {"total": len(summaries), "ready": 0, "deferred": 0, "fully_covered": 0, "to_process": 0}
        utt_counts = {"total": 0, "duplicate_live": 0, "already_backfilled": 0, "selected": 0,
                      "retry_failed": retry_failed}
        result = PlanResult(plan=BackfillPlan(window_from=to_iso(start), window_to=to_iso(end),
                                              retry_failed_live=retry_failed_live))
        deferred_ids: List[int] = []
        fallback_used = 0
        now_ms = int(now * 1000)

        for summary in summaries:
            conv = details.get(summary.id, summary)
            status = conv.readiness(now_ms) if conv.has_detail else "deferred"
            if status == "deferred":
                counts["deferred"] += 1
                deferred_ids.append(conv.id)
                c_start = (conv.start_ms or 0) / 1000.0
                c_end = (conv.end_time_ms / 1000.0) if conv.end_time_ms else end
                result.deferred_spans.append((max(start, c_start), min(end, c_end)))
                continue
            counts["ready"] += 1
            if status == "realtime_fallback":
                fallback_used += 1
            if conv.uuid:
                try:
                    self.store.map_bee_conversation(conv.uuid, conv.id)
                except NotImplementedError:
                    pass
            conv_uuid = conv.uuid or self.store.get_bee_conversation_uuid(conv.id)

            final = conv.final_transcription() or conv.realtime_transcription()
            realtime = conv.realtime_transcription()
            seen: List[Span] = []
            if realtime is not None:
                rt_utts = [r for r in realtime.sorted_utterances() if r.span_ms]
                hits = evidence.match([(r.text, r.span_ms[0] / 1000.0) for r in rt_utts], conv_uuid,
                                      settings.backfill_fuzzy_threshold, match_window)
                seen = [(r.span_ms[0] / 1000.0, r.span_ms[1] / 1000.0) for r, hit in zip(rt_utts, hits) if hit]
            seen = merge_spans(seen, tolerance=settings.backfill_span_merge_seconds)
            final_hits: Dict[Any, bool] = {}
            if realtime is None and final is not None:
                f_utts = [u for u in final.sorted_utterances() if u.span_ms]
                hits = evidence.match([(u.text, u.span_ms[0] / 1000.0) for u in f_utts], conv_uuid,
                                      settings.backfill_fuzzy_threshold, match_window)
                final_hits = {id(u): hit for u, hit in zip(f_utts, hits)}

            history: List[BeeUtterance] = []
            selected_here = 0
            for utt in final.sorted_utterances() if final else []:
                prior = "\n".join(_context_line(h) for h in history[-3:])[-1000:]
                history.append(utt)
                span = utt.span_ms
                if span is None:
                    continue
                t, t_end = span[0] / 1000.0, span[1] / 1000.0
                if not (start <= t <= end):
                    continue
                utt_counts["total"] += 1
                key = bee_source_key(conv.id, final.id, utt.id)
                if key in done_backfill or any(a <= t <= b for a, b in backfill_spans):
                    utt_counts["already_backfilled"] += 1
                    continue
                mid = (t + t_end) / 2.0
                if any(a - 1.0 <= mid <= b + 1.0 for a, b in seen):
                    utt_counts["duplicate_live"] += 1
                    continue
                if final_hits.get(id(utt)):
                    utt_counts["duplicate_live"] += 1
                    continue
                # Re-segmented final (minutes-long utterances): no text match, but live heard that speech
                if evidence.covered_fraction((t, t_end), conv_uuid, settings.backfill_span_merge_seconds) \
                        >= settings.backfill_live_coverage_fraction:
                    utt_counts["duplicate_live"] += 1
                    continue
                if t < horizon and any(a <= t <= b for a, b in live_spans):
                    utt_counts["duplicate_live"] += 1
                    continue
                result.items.append(SelectedUtterance(
                    source_key=key,
                    conversation_id=conv.id,
                    transcription_id=final.id,
                    utterance=utt,
                    ts=t,
                    prior_context=prior,
                    speaker_role=speaker_role_for(utt.speaker),
                ))
                selected_here += 1
            if selected_here:
                counts["to_process"] += 1
                result.conversations[conv.id] = conv
            else:
                counts["fully_covered"] += 1

        result.items.sort(key=lambda s: (s.ts, s.conversation_id, str(s.utterance.id)))
        utt_counts["selected"] = len(result.items)
        if fallback_used:
            warnings.append(f"{fallback_used} conversation(s) have no final transcript yet: realtime transcript used")
        if deferred_ids:
            warnings.append(f"{len(deferred_ids)} conversation(s) are still being processed by Bee and will be retried later")

        plan = result.plan
        plan.coverage = coverage_summary(plan.window_from, plan.window_to, intervals)
        plan.gaps = compute_gaps(plan.window_from, plan.window_to, intervals)
        plan.conversations = counts
        plan.utterances = utt_counts
        plan.estimate = estimate_cost(result)
        plan.warnings = warnings
        plan.deferred_conversation_ids = deferred_ids
        return result


def estimate_cost(result: PlanResult) -> BackfillEstimate:
    selected = len(result.items)
    qualified = math.ceil(selected * QUALIFIED_RATIO)
    words: Dict[int, int] = {}
    for item in result.items:
        words[item.conversation_id] = words.get(item.conversation_id, 0) + len(item.utterance.text.split())
    events = sum(1 for w in words.values() if w >= settings.event_min_segment_words)
    concurrency = max(1, settings.backfill_screen_concurrency)
    return BackfillEstimate(
        gatekeeper_calls=selected,
        expected_qualified=qualified,
        events_expected=events,
        cost_usd=round(
            selected * settings.backfill_cost_per_gatekeeper_call
            + qualified * settings.backfill_cost_per_pipeline_call
            + events * settings.backfill_cost_per_event,
            4,
        ),
        duration_s=round(
            selected * GATEKEEPER_SECONDS / concurrency + qualified * PIPELINE_SECONDS + events * SYNTHESIS_SECONDS, 1
        ),
    )


def over_budget(plan: BackfillPlan) -> bool:
    return (
        plan.utterances.get("selected", 0) > settings.backfill_max_utterances_per_run
        or plan.estimate.cost_usd > settings.backfill_max_estimated_cost_usd
    )


def trim_to_budget(result: PlanResult) -> PlanResult:
    """Automatic runs keep the most recent part of the window that fits the budget (doc 03 §8)."""
    plan = result.plan
    selected = len(result.items)
    if selected == 0 or not over_budget(plan):
        return result
    per_item = plan.estimate.cost_usd / selected if selected else 0.0
    by_cost = int(settings.backfill_max_estimated_cost_usd / per_item) if per_item > 0 else selected
    keep = max(0, min(settings.backfill_max_utterances_per_run, by_cost, selected))
    dropped = result.items[: selected - keep]
    result.items = result.items[selected - keep:]
    if result.items:
        plan.window_from = to_iso(result.items[0].ts)
    plan.utterances["selected"] = len(result.items)
    plan.estimate = estimate_cost(result)
    plan.warnings.append(
        f"Budget guard: {len(dropped)} older utterance(s) skipped; the start of the window stays uncovered"
    )
    return result


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

Classifier = Callable[..., Awaitable[ChunkClassification]]
Dispatcher = Callable[[Dict[str, Any]], Dict[str, Any]]


def _default_classifier() -> Classifier:
    from src.ingestion.gatekeeper import aclassify_chunk

    return aclassify_chunk


def _default_dispatcher() -> Dispatcher:
    from src.pipeline.app import agent_invocation

    return agent_invocation


def _is_noop(classification: ChunkClassification) -> bool:
    from src.ingestion.gatekeeper import is_noop

    return is_noop(classification)


def tasks_active_at(tasks: List[PlannedTask], ts: float) -> List[str]:
    """Titles of tasks that were pending when the utterance was spoken (gatekeeper task injection)."""
    titles: List[str] = []
    for task in tasks:
        if task.status not in ("pending", "completed", "overdue") or not task.title:
            continue
        created = to_epoch(task.created_at)
        completed = to_epoch(task.completed_at) if task.completed_at else None
        if created is not None and created > ts:
            continue
        if completed is not None and completed <= ts:
            continue
        titles.append(task.title)
    return titles


class ReplayExecutor:
    """Replays a plan on an isolated, virtual-clock EventEngine (doc 03 §2–§5)."""

    def __init__(
        self,
        run: BackfillRun,
        result: PlanResult,
        store_getter: Callable[[], AbstractContextStore] = get_storage_store,
        classify: Optional[Classifier] = None,
        dispatch: Optional[Dispatcher] = None,
        synthesizer: Any = None,
        continuity: Any = "settings",
        engine_config: Optional[EngineConfig] = None,
        on_progress: Optional[Callable[[BackfillRun], None]] = None,
        is_cancelled: Callable[[], bool] = lambda: False,
        live_busy: Callable[[], bool] = lambda: False,
        live_engine_getter: Optional[Callable[[], Optional[EventEngine]]] = None,
    ):
        self.run = run
        self.result = result
        self._store_getter = store_getter
        self.classify = classify or _default_classifier()
        self.dispatch = dispatch or _default_dispatcher()
        self.on_progress = on_progress
        self.is_cancelled = is_cancelled
        self.live_busy = live_busy
        self.live_engine_getter = live_engine_getter
        self._vnow = to_epoch(run.window_from) or time.time()
        self.engine = EventEngine(
            store=store_getter(),
            config=engine_config or EngineConfig.from_settings(ignore_demo_profile=True),
            clock=lambda: self._vnow,
            synthesizer=synthesizer,
            continuity=build_continuity_from_settings() if continuity == "settings" else continuity,
            ingest_source="backfill",
            run_id=run.id,
        )
        self._events_opened: Set[str] = set()
        self.engine.add_listener(self._on_engine_event)
        self._worker_busy = False

    @property
    def store(self) -> AbstractContextStore:
        return self._store_getter()

    def _on_engine_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if event_type == "event_opened" and isinstance(payload, dict) and payload.get("session_id"):
            self._events_opened.add(payload["session_id"])

    def _count(self, key: str, n: int = 1) -> None:
        self.run.counters[key] = self.run.counters.get(key, 0) + n

    def _save(self) -> None:
        self.store.save_backfill_run(self.run)
        if self.on_progress:
            self.on_progress(self.run)

    async def _synthesis_worker(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            job = self.engine.pop_job()
            if job is None:
                await asyncio.sleep(0.05)
                continue
            self._worker_busy = True
            try:
                await asyncio.to_thread(self.engine.run_job, job)
            finally:
                self._worker_busy = False

    async def _advance(self, ts: float) -> None:
        self._vnow = max(self._vnow, ts)
        await asyncio.to_thread(self.engine.advance_to, ts)

    async def _screen(self, item: SelectedUtterance, tasks: List[PlannedTask]) -> Optional[ChunkClassification]:
        prior = item.prior_context
        if settings.backfill_screen_with_event_hint:
            hint = self.engine.active_event_hint()
            prior = "\n".join(p for p in (prior, hint) if p)
        active = tasks_active_at(tasks, item.ts)
        try:
            return await self.classify(
                transcript=item.utterance.text,
                active_tasks=active or None,
                prior_context=prior or None,
            )
        except Exception as e:
            logger.warning(f"Backfill screening failed for {item.source_key}: {e}")
            return None

    async def execute(self) -> BackfillRun:
        run = self.run
        run.status = "replaying"
        run.started_at = run.started_at or datetime.now().isoformat()
        run.counters.setdefault("processed", 0)
        self._save()
        self.engine.rehydrate()   # adopts an event handed over by the live engine (B1)

        tasks = self.store.list_planned_tasks()
        stop = asyncio.Event()
        worker = asyncio.create_task(self._synthesis_worker(stop))
        failed_spans: List[Span] = []
        last_ts: Optional[float] = None
        last_save = 0.0
        cancelled = False
        current_conv: Optional[int] = None
        conv_started: Set[int] = set()
        items = self.result.items
        concurrency = 1 if settings.backfill_screen_with_event_hint else max(1, settings.backfill_screen_concurrency)
        batch_size = concurrency * 4

        try:
            for batch_start in range(0, len(items), batch_size):
                if self.is_cancelled():
                    cancelled = True
                    break
                batch = items[batch_start: batch_start + batch_size]
                semaphore = asyncio.Semaphore(concurrency)

                async def _bounded(item: SelectedUtterance) -> Optional[ChunkClassification]:
                    async with semaphore:
                        return await self._screen(item, tasks)

                classifications = await asyncio.gather(*(_bounded(i) for i in batch))
                for item, classification in zip(batch, classifications):
                    if self.is_cancelled():
                        cancelled = True
                        break
                    conv = self.result.conversations[item.conversation_id]
                    if item.conversation_id != current_conv:
                        current_conv = item.conversation_id
                        conv_start = (conv.start_ms or int(item.ts * 1000)) / 1000.0
                        await self._advance(min(conv_start, item.ts))
                        location = conv.location_telemetry()
                        if location:
                            await asyncio.to_thread(self.engine.on_location, location, self._vnow)
                        await asyncio.to_thread(
                            self.engine.on_bee_conversation, "new-conversation",
                            {"conversation": {"id": conv.id, "uuid": conv.conversation_key}},
                        )
                    status = await self._process(item, conv, classification)
                    if item.conversation_id not in conv_started:
                        conv_started.add(item.conversation_id)
                        title = conv.title or conv.short_summary
                        if title:
                            await asyncio.to_thread(
                                self.engine.on_bee_conversation, "update-conversation",
                                {"conversation": {"id": conv.id, "uuid": conv.conversation_key,
                                                  "title": conv.title, "short_summary": conv.short_summary}},
                            )
                    if status == "failed":
                        failed_spans.append((item.ts - 1.0, item.ts + 1.0))
                    last_ts = item.ts
                    run.last_source_key = item.source_key
                    run.last_ts = to_iso(item.ts)
                    if time.time() - last_save >= 2.0:
                        last_save = time.time()
                        self._save()
                if cancelled:
                    break

            if not cancelled and self.engine.current_event() is not None:
                await self._stitch_with_live()

            run.status = "synthesizing"
            self._save()
            end_ts = (last_ts or to_epoch(run.window_to) or self._vnow)
            cfg = self.engine.config
            await self._advance(end_ts + cfg.t_soft + cfg.t_hard + 2 * cfg.tick_seconds)
            while self.engine.pending_jobs() or self._worker_busy:
                await asyncio.sleep(0.05)
        finally:
            stop.set()
            await worker

        try:
            owned = {d.session_id for d in self.store.list_session_dossiers(limit=1000, ingest_run_id=run.id)}
        except (NotImplementedError, TypeError):
            owned = set()
        run.counters["events"] = len(owned | self._events_opened)
        self._commit_coverage(last_ts, cancelled, failed_spans)
        if cancelled:
            run.status = "cancelled"
        elif run.counters.get("failed", 0):
            run.status = "partial"
        else:
            run.status = "completed"
        run.finished_at = datetime.now().isoformat()
        self._save()
        return run

    async def _process(
        self, item: SelectedUtterance, conv: BeeConversation, classification: Optional[ChunkClassification]
    ) -> str:
        run = self.run
        await self._advance(item.ts)
        chunk = UtteranceChunk(
            chunk_id=item.source_key,
            conversation_uuid=conv.conversation_key,
            text=item.utterance.text.strip(),
            speaker_id=item.utterance.speaker,
            speaker_role=item.speaker_role,  # type: ignore[arg-type]
            timestamp=to_iso(item.ts),
            spoken_at=to_iso(item.ts),
            categories=list(classification.categories) if classification else [],
            location=conv.location_telemetry(),
            source_key=item.source_key,
            bee_conversation_id=conv.id,
        )
        if classification is None:
            status = "failed"
        else:
            outcome = await asyncio.to_thread(self.engine.record_chunk, chunk)
            if _is_noop(classification):
                status = "screened_noop"
            else:
                while self.live_busy():
                    await asyncio.sleep(0.25)
                payload = {
                    "raw_transcript": chunk.text,
                    "historical_context": item.prior_context,
                    "categories": classification.categories,
                    "confidence": classification.confidence,
                    "summary_hint": classification.summary_hint,
                    "location": chunk.location,
                    "speaker": chunk.speaker_id,
                    "speaker_role": chunk.speaker_role,
                    "utterance_id": chunk.chunk_id,
                    "session_id": outcome.event_id or chunk.conversation_uuid,
                    "timestamp": chunk.timestamp,
                    "event_managed": outcome.event_id is not None,
                    "source_key": item.source_key,
                    "ingest_source": "backfill",
                    "ingest_run_id": run.id,
                }
                try:
                    result = await asyncio.to_thread(self.dispatch, payload)
                except Exception as e:
                    logger.warning(f"Backfill dispatch failed for {item.source_key}: {e}")
                    result = {"status": "error"}
                if isinstance(result, dict) and result.get("status") == "error":
                    status = "failed"
                else:
                    status = "qualified"
                    self._count("qualified")
                    if isinstance(result, dict):
                        for key, counter in (("action_data", "actions"), ("social_data", "contacts"),
                                             ("scheduled_task", "tasks")):
                            if result.get(key):
                                self._count(counter)
        self._count("processed")
        if status == "failed":
            self._count("failed")
        try:
            self.store.record_ingested_utterance(
                ledger_entry_for_chunk(chunk, status, source="backfill", run_id=run.id)
            )
        except NotImplementedError:
            pass
        return status

    async def _stitch_with_live(self) -> None:
        """S2 (doc 03 §7): the event the run ends inside continues in the live event → merge them."""
        if self.live_engine_getter is None:
            return
        live = self.live_engine_getter()
        ev_b = self.engine.current_event()
        live_ev = live.current_event() if live is not None else None
        if ev_b is None or live_ev is None or live_ev.ingest_source != "live":
            return
        last_on = to_epoch(ev_b.last_on_topic_at) or to_epoch(ev_b.last_updated_at)
        live_start = to_epoch(live_ev.start_time)
        if last_on is None or live_start is None:
            return
        if not (0 <= live_start - last_on <= self.engine.config.t_hard):
            return
        detail = f"Live event started {live_start - last_on:.0f}s after the recovered speech"
        if self.engine.continuity is not None and ev_b.topic_profile is not None:
            chunks = self.store.list_session_chunks(live_ev.session_id)
            text = " ".join(" ".join(c.text for c in chunks).split()[:200])
            if text:
                score, _ = await asyncio.to_thread(self.engine.continuity.score, text, ev_b.topic_profile)
                if score is not None and score.verdict() == "different":
                    return
                if score is not None:
                    detail += f"; {score.describe()}"
        await asyncio.to_thread(
            self.engine.release_open_event, "live", self.run.id, "B2", "backfill_stitch", detail
        )
        merged = await asyncio.to_thread(live.merge, [live_ev.session_id, ev_b.session_id])
        if merged is not None:
            await asyncio.to_thread(live.log_transition, merged.session_id, "B2", "backfill_stitch", detail)
            self._count("stitched")

    def _commit_coverage(self, last_ts: Optional[float], cancelled: bool, failed_spans: List[Span]) -> None:
        start = to_epoch(self.run.window_from)
        end = to_epoch(self.run.window_to)
        if start is None or end is None:
            return
        if cancelled:
            if last_ts is None:
                return
            end = min(end, last_ts)
        excluded = list(self.result.deferred_spans) + failed_spans
        for a, b in subtract_spans((start, end), excluded):
            if b - a < 1.0:
                continue
            try:
                self.store.save_coverage_interval(CoverageInterval(
                    source="backfill", start=to_iso(a), end=to_iso(b), run_id=self.run.id,
                    utterances=self.run.counters.get("processed", 0),
                    errors=self.run.counters.get("failed", 0),
                ))
            except NotImplementedError:
                return


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BackfillService:
    """Run queue, triggers and lifecycle of history backfill runs (doc 03 §1, §5, §6)."""

    def __init__(
        self,
        store_getter: Callable[[], AbstractContextStore] = get_storage_store,
        source_factory: Optional[Callable[[], BeeHistorySource]] = None,
        executor_options: Optional[Dict[str, Any]] = None,
        clock: Callable[[], float] = time.time,
    ):
        self._store_getter = store_getter
        self.source_factory = source_factory or CliBeeHistorySource
        self.executor_options = executor_options or {}
        self.clock = clock
        # Wired by the serving layer
        self.live_engine_getter: Optional[Callable[[], Optional[EventEngine]]] = None
        self.live_since_getter: Callable[[], Optional[str]] = lambda: None
        self.live_busy: Callable[[], bool] = lambda: False
        self.broadcast: Callable[[str, Dict[str, Any]], None] = lambda event_type, payload: None

        self._previews: Dict[Tuple[str, str, bool], PlanResult] = {}
        self._run_plans: Dict[str, PlanResult] = {}
        self._cancelled: Set[str] = set()
        self._pending_reconnect: Optional[Dict[str, float]] = None
        self._last_purge: float = 0.0
        self._last_progress: Dict[str, float] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running_run: Optional[str] = None
        self._rehydrated = False

    @property
    def store(self) -> AbstractContextStore:
        return self._store_getter()

    # -- lifecycle -------------------------------------------------------------

    def ensure_started(self) -> bool:
        if not settings.backfill_enabled:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        if self._loop_task is not None and not self._loop_task.done() and self._loop is loop:
            return True
        self._loop = loop
        self.rehydrate()
        self._loop_task = loop.create_task(self._main_loop())
        return True

    def stop(self) -> None:
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

    def rehydrate(self) -> None:
        """Runs interrupted by a restart go back to the queue; they resume from their checkpoint."""
        if self._rehydrated:
            return
        self._rehydrated = True
        try:
            for run in self.store.list_backfill_runs(statuses=list(ACTIVE_STATUSES), limit=50):
                if run.status != "planned":
                    run.status = "planned"
                    self.store.save_backfill_run(run)
        except NotImplementedError:
            pass

    async def _main_loop(self) -> None:
        while True:
            try:
                self.tick()
                ran = await self.run_next()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Backfill service loop error: {e}", exc_info=True)
                ran = False
            await asyncio.sleep(0.2 if ran else 2.0)

    # -- queries ----------------------------------------------------------------

    def list_runs(self, statuses: Optional[List[str]] = None, limit: int = 20) -> List[BackfillRun]:
        return self.store.list_backfill_runs(statuses=statuses, limit=limit)

    def get_run(self, run_id: str) -> Optional[BackfillRun]:
        return self.store.get_backfill_run(run_id)

    def active_run(self) -> Optional[BackfillRun]:
        runs = self.store.list_backfill_runs(statuses=list(ACTIVE_STATUSES), limit=50)
        running = [r for r in runs if r.status != "planned"]
        return running[0] if running else None

    def status_summary(self) -> Dict[str, Any]:
        try:
            runs = self.store.list_backfill_runs(statuses=list(ACTIVE_STATUSES), limit=50)
        except NotImplementedError:
            return {"enabled": settings.backfill_enabled, "active_run": None, "queued": 0}
        active = next((r for r in runs if r.status != "planned"), None)
        return {
            "enabled": settings.backfill_enabled,
            "active_run": self.progress_payload(active) if active else None,
            "queued": sum(1 for r in runs if r.status == "planned"),
        }

    @staticmethod
    def progress_payload(run: BackfillRun) -> Dict[str, Any]:
        selected = (run.plan.utterances.get("selected", 0) if run.plan else 0) or 0
        processed = run.counters.get("processed", 0)
        eta = None
        if run.plan and selected:
            eta = round(run.plan.estimate.duration_s * max(0, selected - processed) / selected, 1)
        return {
            "run_id": run.id,
            "trigger": run.trigger,
            "status": run.status,
            "window_from": run.window_from,
            "window_to": run.window_to,
            "processed": processed,
            "selected": selected,
            "qualified": run.counters.get("qualified", 0),
            "failed": run.counters.get("failed", 0),
            "events": run.counters.get("events", 0),
            "progress": round(processed / selected, 3) if selected else (1.0 if run.is_terminal else 0.0),
            "eta_s": eta,
        }

    # -- planning & creation -------------------------------------------------------

    def _max_window_to(self) -> float:
        live_since = to_epoch(self.live_since_getter() or "")
        return live_since if live_since is not None else self.clock()

    async def preview(self, window_from: str, window_to: str, retry_failed_live: bool = True) -> PlanResult:
        start, end, clamped = self._validate_window(window_from, window_to)
        key = (to_iso(start), to_iso(end), retry_failed_live)
        cached = self._previews.get(key)
        if cached is not None and self.clock() - cached.created_at < PREVIEW_CACHE_SECONDS:
            return cached
        planner = BackfillPlanner(self.source_factory(), self._store_getter, self.clock)
        result = await planner.plan(key[0], key[1], retry_failed_live)
        if clamped:
            result.plan.warnings.insert(
                0, f"Window end moved to {key[1]}: the live stream owns everything after the current connection started"
            )
        result.created_at = self.clock()
        self._previews[key] = result
        return result

    def _validate_window(self, window_from: str, window_to: str) -> Tuple[float, float, bool]:
        """Validates a manual window; its end is clamped to the start of the current live coverage."""
        start, end = to_epoch(window_from), to_epoch(window_to)
        if start is None or end is None or end <= start:
            raise BackfillRequestError("invalid_window", "Provide ISO 'from' < 'to'")
        if end - start > settings.backfill_max_window_days * 86400:
            raise BackfillRequestError(
                "window_too_large", f"Window exceeds BACKFILL_MAX_WINDOW_DAYS={settings.backfill_max_window_days:g}"
            )
        max_to = self._max_window_to()
        clamped = end > max_to + 1
        if clamped:
            end = max_to
            if end <= start:
                raise BackfillRequestError(
                    "window_covered_by_live",
                    "The whole window falls inside the current live connection: nothing to recover",
                    extra={"max_to": to_iso(max_to)},
                )
        return start, end, clamped

    def _overlapping_active(self, start: float, end: float) -> List[BackfillRun]:
        out = []
        for run in self.store.list_backfill_runs(statuses=list(ACTIVE_STATUSES), limit=50):
            a, b = to_epoch(run.window_from), to_epoch(run.window_to)
            if a is not None and b is not None and a < end and b > start:
                out.append(run)
        return out

    async def create_run(
        self,
        window_from: str,
        window_to: str,
        retry_failed_live: bool = True,
        confirm_over_budget: bool = False,
        requested_by: Optional[str] = None,
    ) -> BackfillRun:
        """Manual run (UI / API): validated, planned (preview cache) and budget-checked up front."""
        if not settings.backfill_enabled:
            raise BackfillRequestError("disabled", "History backfill is disabled (BACKFILL_ENABLED=false)", 404)
        start, end, _ = self._validate_window(window_from, window_to)
        if self._overlapping_active(start, end):
            raise BackfillRequestError("overlapping_run", "A queued or running backfill already covers this window", 409)
        result = await self.preview(window_from, window_to, retry_failed_live)
        if over_budget(result.plan) and not confirm_over_budget:
            raise BackfillRequestError(
                "over_budget", "Estimated cost or volume exceeds the configured budget",
                extra={"estimate": result.plan.estimate.model_dump(), "utterances": result.plan.utterances},
            )
        run = BackfillRun(
            trigger="manual", window_from=result.plan.window_from, window_to=result.plan.window_to,
            retry_failed_live=retry_failed_live, plan=result.plan, requested_by=requested_by,
            confirm_over_budget=confirm_over_budget,
        )
        self.store.save_backfill_run(run)
        self._run_plans[run.id] = result
        self.broadcast("backfill_queued", self.progress_payload(run))
        return run

    def _create_auto_run(self, trigger: str, start: float, end: float, not_before: Optional[float] = None
                         ) -> Optional[BackfillRun]:
        """Automatic run for the part of [start, end] no active run already owns."""
        if not settings.backfill_enabled or end <= start:
            return None
        owned = [(to_epoch(r.window_from) or 0.0, to_epoch(r.window_to) or 0.0) for r in self._overlapping_active(start, end)]
        try:
            owned += interval_spans(self.store.list_coverage(to_iso(start), to_iso(end)))
        except NotImplementedError:
            pass
        remainder = subtract_spans((start, end), owned)
        remainder = [(a, b) for a, b in remainder if b - a >= settings.backfill_min_gap_seconds]
        if not remainder:
            return None
        run = BackfillRun(
            trigger=trigger,  # type: ignore[arg-type]
            window_from=to_iso(remainder[0][0]),
            window_to=to_iso(remainder[-1][1]),
            not_before=to_iso(not_before) if not_before else None,
        )
        self.store.save_backfill_run(run)
        self.broadcast("backfill_queued", self.progress_payload(run))
        logger.info(f"Backfill run {run.id[:8]} queued ({trigger}): {run.window_from} → {run.window_to}")
        return run

    def cancel(self, run_id: str) -> Optional[BackfillRun]:
        run = self.store.get_backfill_run(run_id)
        if run is None or run.is_terminal:
            return run
        if run.status == "planned":
            run.status = "cancelled"
            run.finished_at = datetime.now().isoformat()
            self.store.save_backfill_run(run)
            self.broadcast("backfill_completed", self.progress_payload(run))
        else:
            self._cancelled.add(run_id)
        return run

    # -- triggers -----------------------------------------------------------------

    def prepare_startup(self, live_engine: Optional[EventEngine] = None) -> Optional[BackfillRun]:
        """Startup catch-up (doc 03 §6) and open-event hand-over (doc 03 §7 S1).

        Must run before the live engine starts ticking, otherwise the rehydrated open event would be
        hard-closed on the wall clock while the rest of it still sits in the gap."""
        if not (settings.backfill_enabled and settings.backfill_auto_on_startup):
            return None
        now = self.clock()
        try:
            last_end = self.store.last_coverage_end()
        except NotImplementedError:
            return None
        if last_end is None:
            if settings.backfill_first_run_days <= 0:
                return None
            start = now - settings.backfill_first_run_days * 86400
        else:
            start = max(to_epoch(last_end) or now, now - settings.backfill_lookback_days * 86400)
        if now - start < settings.backfill_min_gap_seconds:
            return None
        run = self._create_auto_run("startup", start, now, not_before=now + settings.backfill_startup_delay_seconds)
        if run is not None and live_engine is not None:
            released = live_engine.release_open_event("backfill", run.id)
            if released is not None:
                run.counters["handover"] = 1
                self.store.save_backfill_run(run)
                logger.info(f"Live event {released.session_id[:8]} handed over to backfill run {run.id[:8]}")
        return run

    def on_live_coverage_open(self, interval: CoverageInterval, gap: Optional[CoverageGap]) -> None:
        """Reconnect catch-up: coalesce holes within the debounce window, start after a delay."""
        if gap is None or not (settings.backfill_enabled and settings.backfill_auto_on_reconnect):
            return
        g_start, g_end = to_epoch(gap.start), to_epoch(gap.end)
        if g_start is None or g_end is None or g_end - g_start < settings.backfill_min_gap_seconds:
            return
        now = self.clock()
        pending = self._pending_reconnect
        if pending and g_start - pending["end"] <= settings.backfill_reconnect_debounce_seconds:
            pending["end"] = max(pending["end"], g_end)
            pending["start"] = min(pending["start"], g_start)
            pending["due"] = now + settings.backfill_reconnect_delay_seconds
        else:
            self._pending_reconnect = {
                "start": g_start, "end": g_end, "due": now + settings.backfill_reconnect_delay_seconds,
            }

    def tick(self, now: Optional[float] = None) -> None:
        """Housekeeping: due reconnect runs, deferred-conversation rechecks, ledger retention."""
        now = self.clock() if now is None else now
        pending = self._pending_reconnect
        if pending and now >= pending["due"]:
            self._pending_reconnect = None
            self._create_auto_run("reconnect", pending["start"], pending["end"])

        try:
            recent = self.store.list_backfill_runs(statuses=["completed", "partial"], limit=20)
        except NotImplementedError:
            recent = []
        for run in recent:
            deferred = run.plan.deferred_conversation_ids if run.plan else []
            if not deferred or run.counters.get("superseded"):
                continue
            window_to = to_epoch(run.window_to) or now
            finished = to_epoch(run.finished_at) or now
            if now - window_to > DEFERRED_GIVE_UP_SECONDS:
                run.counters["superseded"] = 1
                run.counters["deferred_expired"] = len(deferred)
                self.store.save_backfill_run(run)
                continue
            if now - finished < DEFERRED_RECHECK_SECONDS:
                continue
            start = to_epoch(run.window_from)
            if start is None or self._overlapping_active(start, window_to):
                continue
            recheck = BackfillRun(trigger="deferred_recheck", window_from=run.window_from, window_to=run.window_to)
            self.store.save_backfill_run(recheck)
            run.counters["superseded"] = 1
            self.store.save_backfill_run(run)

        if now - self._last_purge >= 86400:
            self._last_purge = now
            try:
                purged = self.store.purge_ingest_ledger(to_iso(now - settings.backfill_ledger_retention_days * 86400))
                if purged:
                    logger.info(f"Purged {purged} ingest ledger rows past retention")
            except NotImplementedError:
                pass

    # -- execution -----------------------------------------------------------------

    def _next_runnable(self) -> Optional[BackfillRun]:
        now = self.clock()
        planned = [
            r for r in self.store.list_backfill_runs(statuses=["planned"], limit=50)
            if not r.not_before or (to_epoch(r.not_before) or 0.0) <= now
        ]
        if not planned:
            return None
        planned.sort(key=lambda r: (r.trigger != "manual", r.created_at))
        return planned[0]

    async def run_next(self) -> bool:
        """Executes the next runnable run, if any. Returns True when a run was executed."""
        if self._running_run is not None:
            return False
        run = self._next_runnable()
        if run is None:
            return False
        self._running_run = run.id
        try:
            await self._execute(run)
        finally:
            self._running_run = None
        return True

    def _progress(self, run: BackfillRun) -> None:
        now = time.time()
        if run.is_terminal or now - self._last_progress.get(run.id, 0.0) >= 2.0:
            self._last_progress[run.id] = now
            if not run.is_terminal:
                self.broadcast("backfill_progress", self.progress_payload(run))

    async def _execute(self, run: BackfillRun) -> BackfillRun:
        run.status = "fetching"
        run.started_at = run.started_at or datetime.now().isoformat()
        self.store.save_backfill_run(run)
        self.broadcast("backfill_started", self.progress_payload(run))
        try:
            result = self._run_plans.pop(run.id, None)
            if result is None or self.clock() - result.created_at >= PREVIEW_CACHE_SECONDS:
                planner = BackfillPlanner(self.source_factory(), self._store_getter, self.clock)
                result = await planner.plan(run.window_from, run.window_to, run.retry_failed_live)
            if over_budget(result.plan) and not (run.trigger == "manual" and run.confirm_over_budget):
                result = trim_to_budget(result)
            resumed_after = run.counters.get("processed", 0)
            if resumed_after:
                # Resumed run: utterances committed before the restart are no longer selected
                result.plan.utterances["resumed_after"] = resumed_after
                result.plan.utterances["selected"] = result.plan.utterances.get("selected", 0) + resumed_after
            run.plan = result.plan
            run.window_from = result.plan.window_from
            executor = ReplayExecutor(
                run, result, store_getter=self._store_getter,
                on_progress=self._progress,
                is_cancelled=lambda: run.id in self._cancelled,
                live_busy=self.live_busy,
                live_engine_getter=self.live_engine_getter,
                **self.executor_options,
            )
            run = await executor.execute()
        except Exception as e:
            logger.error(f"Backfill run {run.id[:8]} failed: {e}", exc_info=True)
            run.status = "failed"
            run.error = str(e)[:500]
            run.finished_at = datetime.now().isoformat()
            self.store.save_backfill_run(run)
            self.broadcast("backfill_failed", {"run_id": run.id, "error": run.error})
            return run
        finally:
            self._cancelled.discard(run.id)
        self._previews.clear()
        payload = self.progress_payload(run)
        payload["counters"] = dict(run.counters)
        self.broadcast("backfill_completed", payload)
        logger.info(f"Backfill run {run.id[:8]} {run.status}: {run.counters}")
        return run


_service: Optional[BackfillService] = None


def get_backfill_service() -> BackfillService:
    global _service
    if _service is None:
        _service = BackfillService()
    return _service
