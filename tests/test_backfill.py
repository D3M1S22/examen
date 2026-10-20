"""Historical Transcript Backfill (docs/next_steps/historical_backfill/05 §2 test matrix).

Offline: fixture Bee history, fake gatekeeper, static synthesizer, heuristic (mock_ai) pipeline.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytest

import src.core.storage as storage_mod
from src.core.config import settings
from src.core.schemas import BriefingReport, ChunkClassification, CoverageInterval, PlannedTask, UtteranceChunk
from src.core.storage.sqlite_store import SQLiteContextStore
from src.core.time_utils import historical_action_may_resolve
from src.ingestion.backfill import BackfillPlanner, BackfillRequestError, BackfillService, ReplayExecutor
from src.ingestion.bee_history import BeeConversation, FixtureBeeHistorySource
from src.ingestion.coverage import (
    CoverageTracker,
    compute_gaps,
    ledger_entry_for_chunk,
    merge_spans,
    subtract_spans,
    to_epoch,
    to_iso,
)
from src.ingestion.event_engine import EngineConfig, EventEngine

NOW = datetime.now().replace(microsecond=0)
LECTURE = [
    "Today we study the fundamental theorem of calculus and definite integrals",
    "The derivative of the integral function equals the integrand under continuity",
    "Riemann sums approximate the area under the curve with rectangles",
    "As the partition gets finer the Riemann sum converges to the definite integral",
    "This theorem links differential calculus and integral calculus together",
]


class StaticSynthesizer:
    def segment(self, text, session_id, outline=None, kind="segment"):
        return BriefingReport(topic_title="Calculus part", context_type="academic_lecture")

    def final(self, parts, extra_text, session_id, outline=None, micro_events=None):
        return BriefingReport(topic_title="Calculus lecture", context_type="academic_lecture")


async def fake_classify(transcript, active_tasks=None, prior_context=None):
    t = transcript.lower()
    if "remind me" in t:
        cats = ["scheduled_task"]
    elif any(w in t for w in ("unplugged", "locked", "merged")):
        cats = ["action"]
    elif any(w in t for w in ("calculus", "integral", "riemann", "derivative", "theorem")):
        cats = ["deep_topic"]
    else:
        cats = ["noop"]
    return ChunkClassification(categories=cats, confidence=0.9, summary_hint="test")


def make_conv(conv_id: int, start: datetime, lines: List[Tuple[float, str]], *, uuid: Optional[str] = None,
              realtime: bool = True, final: bool = True, state: str = "processed", ended: bool = True,
              final_texts: Optional[Dict[int, str]] = None) -> dict:
    """Bee `conversations get --json` payload with the observed shape (docs/10 §4.3): epoch-ms `spoken_at`,
    `start`/`end` in relative seconds, speaker = first name or "Unknown". Realtime and final carry the same speech."""
    def utts(id_base: int, texts: Optional[Dict[int, str]] = None):
        out = []
        for i, (offset, text) in enumerate(lines):
            at = int((start + timedelta(seconds=offset)).timestamp() * 1000)
            out.append({"id": id_base + i, "text": (texts or {}).get(i, text), "speaker": "Unknown",
                        "spoken_at": at, "start": float(offset), "end": float(offset) + 4.0,
                        "realtime": id_base < 2000})
        return out

    end_ms = int((start + timedelta(seconds=lines[-1][0] + 5)).timestamp() * 1000)
    transcriptions = []
    if realtime:
        transcriptions.append({"id": conv_id * 10 + 1, "realtime": True, "utterances": utts(1000)})
    if final:
        transcriptions.append({"id": conv_id * 10 + 2, "realtime": False, "utterances": utts(2000, final_texts)})
    return {"conversation": {
        "id": conv_id, "uuid": uuid, "start_time": int(start.timestamp() * 1000),
        "end_time": end_ms if ended else None, "state": state, "short_summary": f"Conversation {conv_id}",
        "primary_location": {"latitude": 45.06, "longitude": 7.66, "address": "Politecnico, Aula 7"},
        "transcriptions": transcriptions,
    }}


def record_live(store, conv_uuid: str, start: datetime, lines, indexes, status="qualified", delay=2.0):
    """Live ledger evidence: the stream delivered these lines `delay` seconds after they were spoken."""
    for i in indexes:
        offset, text = lines[i]
        received = start + timedelta(seconds=offset + delay)
        chunk = UtteranceChunk(chunk_id=f"live-{conv_uuid}-{i}", conversation_uuid=conv_uuid, text=text,
                               timestamp=received.isoformat(), received_at=received.isoformat())
        store.record_ingested_utterance(ledger_entry_for_chunk(chunk, status))


def live_interval(store, start: datetime, end: datetime):
    store.save_coverage_interval(CoverageInterval(source="live", start=start.isoformat(), end=end.isoformat()))


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = SQLiteContextStore(str(tmp_path / "backfill.db"))
    monkeypatch.setattr(storage_mod, "_store_instance", s)
    monkeypatch.setattr(settings, "mock_ai", True)
    monkeypatch.setattr(settings, "backfill_startup_delay_seconds", 0.0)
    return s


def make_service(store, source, dispatch=None, **opts) -> BackfillService:
    options = dict(classify=fake_classify, synthesizer=StaticSynthesizer(), continuity=None,
                   engine_config=EngineConfig(min_segment_words=5))
    if dispatch is not None:
        options["dispatch"] = dispatch
    options.update(opts)
    return BackfillService(store_getter=lambda: store, source_factory=lambda: source, executor_options=options)


# ---------------------------------------------------------------------------
# Coverage arithmetic & live tracker (T-COV)
# ---------------------------------------------------------------------------

def test_span_arithmetic():
    assert merge_spans([(0, 10), (12, 20)], tolerance=5) == [(0, 20)]
    assert subtract_spans((0, 100), [(10, 20), (15, 30), (90, 120)]) == [(0, 10), (30, 90)]
    intervals = [CoverageInterval(source="live", start=to_iso(1_000_000), end=to_iso(1_000_600))]
    gaps = compute_gaps(to_iso(1_000_000), to_iso(1_003_600), intervals)
    assert len(gaps) == 1 and gaps[0].seconds == 3000


def test_tracker_closes_at_last_proof_of_life_and_reports_gap(store):
    clock = [1_000_000.0]
    gaps = []
    tracker = CoverageTracker(lambda: store, flush_seconds=30, clock=lambda: clock[0], on_gap=gaps.append)
    tracker.mark_alive()
    clock[0] += 100
    tracker.mark_alive()
    clock[0] += 330  # read timeout detected much later
    tracker.mark_disconnected()
    [interval] = store.list_coverage()
    assert to_epoch(interval.end) == 1_000_100 and not interval.is_open

    clock[0] += 200
    tracker.mark_alive()
    assert len(gaps) == 1 and gaps[0].seconds == pytest.approx(530, abs=1)


def test_tracker_crash_recovery_closes_open_interval(store):
    store.save_coverage_interval(CoverageInterval(source="live", start=to_iso(1_000_000), end=to_iso(1_000_060),
                                                  is_open=True))
    tracker = CoverageTracker(lambda: store)
    tracker.recover_after_crash()
    assert not store.list_coverage()[0].is_open
    assert tracker.last_closed_end == 1_000_060


@pytest.mark.asyncio
async def test_orchestrator_writes_ledger_for_noop_and_qualified(store, monkeypatch):
    import importlib
    import sys
    from src.ingestion.orchestrator import BeeStreamOrchestrator

    orch = BeeStreamOrchestrator(store=store, engine=EventEngine(store=store, synthesizer=StaticSynthesizer()))
    orch.engine_enabled = False
    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", fake_classify)
    importlib.import_module("src.pipeline.app")
    monkeypatch.setattr(sys.modules["src.pipeline.app"], "agent_invocation", lambda payload: {"status": "success"})

    await orch.process_incoming_utterance({"text": "nice weather today", "conversation_uuid": "c1",
                                           "received_at": "2026-10-18T10:00:00"})
    await orch.process_incoming_utterance({"text": "I unplugged the iron", "conversation_uuid": "c1",
                                           "received_at": "2026-10-18T10:00:05"})
    rows = store.list_ledger_entries("2026-10-18T09:00:00", "2026-10-18T11:00:00", source="live")
    assert [r["status"] for r in rows] == ["screened_noop", "qualified"]
    assert all(r["source_key"].startswith("live:c1:utt-") for r in rows)  # stable fallback ids


# ---------------------------------------------------------------------------
# Planner: de-duplication & readiness (T-DED, T-RDY)
# ---------------------------------------------------------------------------

def lines_every(seconds: int, texts: List[str]) -> List[Tuple[float, str]]:
    return [(i * seconds, t) for i, t in enumerate(texts)]


TEN = [f"sentence number {i} about the project roadmap and milestones" for i in range(10)]


@pytest.mark.asyncio
async def test_fully_live_conversation_selects_nothing(store):
    start = NOW - timedelta(hours=5)
    lines = lines_every(30, TEN[:5])
    record_live(store, "uuid-1", start, lines, range(5))
    live_interval(store, start - timedelta(minutes=1), start + timedelta(minutes=10))
    source = FixtureBeeHistorySource([make_conv(1, start, lines, uuid="uuid-1")])
    result = await BackfillPlanner(source, lambda: store).plan(
        (start - timedelta(minutes=10)).isoformat(), (start + timedelta(hours=1)).isoformat())
    assert result.plan.utterances["selected"] == 0
    assert result.plan.utterances["duplicate_live"] == 5
    assert result.plan.conversations["fully_covered"] == 1


@pytest.mark.asyncio
async def test_outage_mid_conversation_selects_only_the_tail(store):
    start = NOW - timedelta(hours=5)
    lines = lines_every(60, TEN)
    record_live(store, "uuid-2", start, lines, range(4))
    source = FixtureBeeHistorySource([make_conv(2, start, lines, uuid="uuid-2")])
    result = await BackfillPlanner(source, lambda: store).plan(
        (start - timedelta(minutes=10)).isoformat(), (start + timedelta(hours=1)).isoformat())
    assert [s.utterance.text for s in result.items] == TEN[4:]


@pytest.mark.asyncio
async def test_delayed_upload_inside_live_interval_is_selected(store):
    start = NOW - timedelta(hours=5)
    lines = lines_every(30, TEN[:4])
    live_interval(store, start - timedelta(hours=1), start + timedelta(hours=1))
    source = FixtureBeeHistorySource([make_conv(3, start, lines)])
    result = await BackfillPlanner(source, lambda: store).plan(
        (start - timedelta(minutes=10)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    assert result.plan.utterances["selected"] == 4


@pytest.mark.asyncio
async def test_fuzzy_match_without_realtime_transcription(store):
    start = NOW - timedelta(hours=5)
    live_lines = [(0, "we merged the pull request forty two today"), (30, "then we deployed to staging")]
    record_live(store, "uuid-4", start, live_lines, range(2))
    final_lines = [(0, "We merged the pull request 42 today."), (30, "Then we deployed to staging."),
                   (60, "Tomorrow we review the incident report")]
    source = FixtureBeeHistorySource([make_conv(4, start, final_lines, realtime=False)])
    result = await BackfillPlanner(source, lambda: store).plan(
        (start - timedelta(minutes=10)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    assert [s.utterance.text for s in result.items] == ["Tomorrow we review the incident report"]


@pytest.mark.asyncio
async def test_failed_live_utterances_are_retried_on_request(store):
    start = NOW - timedelta(hours=5)
    lines = lines_every(60, TEN[:3])
    record_live(store, "uuid-5", start, lines, [0, 2])
    record_live(store, "uuid-5", start, lines, [1], status="failed")
    source = FixtureBeeHistorySource([make_conv(5, start, lines, uuid="uuid-5")])
    window = ((start - timedelta(minutes=10)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    retried = await BackfillPlanner(source, lambda: store).plan(*window, retry_failed_live=True)
    assert [s.utterance.text for s in retried.items] == [TEN[1]]
    assert retried.plan.utterances["retry_failed"] == 1
    skipped = await BackfillPlanner(source, lambda: store).plan(*window, retry_failed_live=False)
    assert skipped.items == []


@pytest.mark.asyncio
async def test_readiness_defers_open_conversations_and_falls_back_to_realtime(store):
    open_start = NOW - timedelta(minutes=20)
    old_start = NOW - timedelta(hours=5)
    source = FixtureBeeHistorySource([
        make_conv(6, open_start, lines_every(30, TEN[:2]), ended=False, state="processing"),
        make_conv(7, old_start, lines_every(30, TEN[:2]), final=False),
    ])
    result = await BackfillPlanner(source, lambda: store).plan(
        (NOW - timedelta(hours=6)).isoformat(), NOW.isoformat())
    assert result.plan.deferred_conversation_ids == [6]
    assert result.plan.utterances["selected"] == 2
    assert any("realtime transcript used" in w for w in result.plan.warnings)
    assert result.deferred_spans and result.deferred_spans[0][0] >= to_epoch(open_start.isoformat()) - 1


def test_bee_conversation_parsing_normalises_epoch_seconds():
    conv = BeeConversation.from_payload({"conversation": {
        "id": 9, "start_time": 1_760_000_000, "end_time": 1_760_000_100, "state": "COMPLETED",
        "transcriptions": [{"id": 1, "realtime": False, "utterances": [
            {"id": 1, "text": "hi", "spoken_at": 1_760_000_001}]}],
    }})
    assert conv.start_ms == 1_760_000_000_000
    assert conv.final_transcription().utterances[0].ts_ms == 1_760_000_001_000


# ---------------------------------------------------------------------------
# Executor: isolation, idempotency, temporal guards, cancel (T-ISO, T-IDEM, T-TMP, T-CAN)
# ---------------------------------------------------------------------------

def lecture_conv(conv_id: int, start: datetime, uuid: Optional[str] = None) -> dict:
    return make_conv(conv_id, start, lines_every(40, LECTURE), uuid=uuid)


@pytest.mark.asyncio
async def test_backfill_engine_is_isolated_from_the_live_engine(store):
    live = EventEngine(store=store, config=EngineConfig(min_segment_words=5), synthesizer=StaticSynthesizer())
    chunk = UtteranceChunk(chunk_id="live-1", text=LECTURE[0], timestamp=datetime.now().isoformat(),
                           categories=["deep_topic"])
    live_id = live.record_chunk(chunk).event_id

    start = NOW - timedelta(hours=4)
    service = make_service(store, FixtureBeeHistorySource([lecture_conv(10, start)]))
    service.live_engine_getter = lambda: live
    run = await service.create_run((start - timedelta(minutes=5)).isoformat(), (start + timedelta(hours=1)).isoformat())
    assert await service.run_next()
    run = service.get_run(run.id)

    assert run.status == "completed" and run.counters["events"] == 1
    assert live.current_event_id() == live_id
    assert store.get_open_event("live").session_id == live_id
    [backfill_event] = store.list_session_dossiers(ingest_run_id=run.id)
    assert backfill_event.ingest_source == "backfill" and backfill_event.status == "concluded"
    assert backfill_event.final_status == "ready"
    assert to_epoch(backfill_event.start_time) == pytest.approx(start.timestamp(), abs=1)


@pytest.mark.asyncio
async def test_rerunning_a_window_produces_no_duplicates(store):
    from src.pipeline.app import agent_invocation

    start = NOW - timedelta(hours=3)
    conv = make_conv(11, start, [(0, "I unplugged the iron before leaving"), (30, "nice weather today")])
    service = make_service(store, FixtureBeeHistorySource([conv]), dispatch=agent_invocation)
    window = ((start - timedelta(minutes=5)).isoformat(), (start + timedelta(minutes=30)).isoformat())

    first = await service.create_run(*window)
    await service.run_next()
    first = service.get_run(first.id)
    assert first.counters["actions"] == 1 and first.counters["processed"] == 2

    second = await service.create_run(*window)
    assert second.plan.utterances["selected"] == 0
    await service.run_next()
    actions = store.list_recent_actions(limit=10)
    assert len(actions) == 1
    assert actions[0].ingest_source == "backfill" and actions[0].ingest_run_id == first.id
    assert to_epoch(actions[0].timestamp) == pytest.approx(start.timestamp(), abs=1)


@pytest.mark.asyncio
async def test_historical_action_never_completes_todays_routine(store):
    from src.pipeline.app import agent_invocation

    store.save_planned_task(PlannedTask(id="daily-iron", title="unplug the iron", domain="safety",
                                        recurrence="daily"))
    old_door = PlannedTask(id="door-once", title="lock the front door", domain="safety",
                           created_at=(NOW - timedelta(days=4)).isoformat())
    store.save_planned_task(old_door)
    start = NOW - timedelta(days=3)
    conv = make_conv(12, start, [(0, "I unplugged the iron, done"), (30, "I locked the front door")])
    service = make_service(store, FixtureBeeHistorySource([conv]), dispatch=agent_invocation)
    await service.create_run((start - timedelta(minutes=5)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    await service.run_next()

    assert store.get_planned_task("daily-iron").status == "pending"      # today's occurrence untouched
    door = store.get_planned_task("door-once")
    assert door.status == "completed"                                     # existed when it was said
    assert to_epoch(door.completed_at) == pytest.approx((start + timedelta(seconds=30)).timestamp(), abs=1)


@pytest.mark.asyncio
async def test_recovered_scheduled_task_is_anchored_on_spoken_time(store):
    from src.pipeline.app import agent_invocation

    start = (NOW - timedelta(days=3)).replace(hour=9, minute=0, second=0)
    conv = make_conv(13, start, [(0, "Remind me to call the dentist tomorrow at 3 pm")])
    service = make_service(store, FixtureBeeHistorySource([conv]), dispatch=agent_invocation)
    await service.create_run((start - timedelta(minutes=5)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    await service.run_next()

    [task] = store.list_planned_tasks(ingest_source="backfill")
    due = datetime.fromisoformat(task.scheduled_time)
    assert due.date() == (start + timedelta(days=1)).date() and due.hour == 15
    assert task.status == "overdue" and task.recovered
    assert to_epoch(task.created_at) == pytest.approx(start.timestamp(), abs=1)


def test_temporal_guard_rules():
    now = datetime(2026, 10, 19, 12, 0)
    assert not historical_action_may_resolve("2026-10-16T09:00:00", "2026-10-17T09:00:00")
    assert historical_action_may_resolve("2026-10-16T09:00:00", "2026-10-15T09:00:00")
    assert not historical_action_may_resolve("2026-10-16T09:00:00", "2026-10-15T09:00:00", "daily", now=now)
    assert historical_action_may_resolve("2026-10-19T08:00:00", "2026-10-15T09:00:00", "daily", now=now)


@pytest.mark.asyncio
async def test_cancel_commits_coverage_only_up_to_the_checkpoint(store):
    start = NOW - timedelta(hours=3)
    lines = lines_every(60, TEN)
    source = FixtureBeeHistorySource([make_conv(14, start, lines)])
    window = ((start - timedelta(minutes=5)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    from src.core.schemas import BackfillRun

    result = await BackfillPlanner(source, lambda: store).plan(*window)
    run = BackfillRun(window_from=result.plan.window_from, window_to=result.plan.window_to, plan=result.plan)
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return run.counters.get("processed", 0) >= 4

    executor = ReplayExecutor(run, result, store_getter=lambda: store, classify=fake_classify,
                              dispatch=lambda p: {"status": "success"}, synthesizer=StaticSynthesizer(),
                              continuity=None, is_cancelled=cancelled)
    run = await executor.execute()
    assert run.status == "cancelled" and run.counters["processed"] == 4
    [interval] = store.list_coverage(source="backfill")
    assert interval.end == to_iso(start.timestamp() + 180)

    again = await BackfillPlanner(source, lambda: store).plan(*window)
    assert [s.utterance.text for s in again.items] == TEN[4:]


# ---------------------------------------------------------------------------
# Live boundaries: hand-over & stitching (T-BND)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_startup_hands_the_open_live_event_to_the_catch_up_run(store):
    t_last = NOW - timedelta(minutes=20)
    live = EventEngine(store=store, config=EngineConfig(min_segment_words=5), synthesizer=StaticSynthesizer())
    for i, text in enumerate(LECTURE[:2]):
        live.record_chunk(UtteranceChunk(chunk_id=f"l{i}", text=text, categories=["deep_topic"],
                                         timestamp=(t_last - timedelta(seconds=40 * (1 - i))).isoformat()))
    event_id = live.current_event_id()
    live_interval(store, t_last - timedelta(hours=1), t_last)

    continuation = make_conv(15, t_last + timedelta(minutes=2), lines_every(40, LECTURE[2:]))
    service = make_service(store, FixtureBeeHistorySource([continuation]))
    run = service.prepare_startup(live)
    assert run is not None and run.trigger == "startup" and run.counters.get("handover") == 1
    assert live.current_event() is None

    await service.run_next()
    run = service.get_run(run.id)
    event = store.get_session_dossier(event_id)
    assert run.status == "completed"
    assert event.status == "concluded" and event.ingest_run_id == run.id
    assert len(store.list_session_chunks(event_id)) == len(LECTURE)
    assert any(t.rule == "B1" for t in event.transitions)


@pytest.mark.asyncio
async def test_event_continuing_into_live_is_stitched(store):
    gap_end = NOW - timedelta(minutes=10)
    live = EventEngine(store=store, config=EngineConfig(min_segment_words=5), synthesizer=StaticSynthesizer())
    live.record_chunk(UtteranceChunk(chunk_id="live-cont", text=LECTURE[4], categories=["deep_topic"],
                                     timestamp=(gap_end + timedelta(seconds=60)).isoformat()))
    live_id = live.current_event_id()

    conv = make_conv(16, gap_end - timedelta(minutes=4), lines_every(40, LECTURE[:4]))
    service = make_service(store, FixtureBeeHistorySource([conv]))
    service.live_engine_getter = lambda: live
    run = await service.create_run((gap_end - timedelta(minutes=30)).isoformat(), gap_end.isoformat())
    await service.run_next()
    run = service.get_run(run.id)

    assert run.counters.get("stitched") == 1
    merged = live.current_event()
    assert merged is not None and merged.ingest_source == "live" and merged.status == "active"
    assert store.get_session_dossier(live_id) is None or merged.session_id == live_id
    assert len(store.list_session_chunks(merged.session_id)) == 5
    assert any(t.rule == "B2" for t in merged.transitions)


# ---------------------------------------------------------------------------
# Service triggers, budget and window rules (T-TRG, T-BUD)
# ---------------------------------------------------------------------------

def test_first_run_ever_does_not_backfill_by_default(store):
    service = make_service(store, FixtureBeeHistorySource([]))
    assert service.prepare_startup(None) is None


def test_reconnect_gaps_are_debounced_and_delayed(store, monkeypatch):
    monkeypatch.setattr(settings, "backfill_reconnect_delay_seconds", 900.0)
    clock = [NOW.timestamp()]
    service = make_service(store, FixtureBeeHistorySource([]))
    service.clock = lambda: clock[0]
    from src.core.schemas import CoverageGap

    t = NOW.timestamp()
    interval = CoverageInterval(source="live", start=to_iso(t), end=to_iso(t))
    service.on_live_coverage_open(interval, CoverageGap(start=to_iso(t - 600), end=to_iso(t - 300), seconds=300))
    service.on_live_coverage_open(interval, CoverageGap(start=to_iso(t - 200), end=to_iso(t - 100), seconds=100))
    service.tick(now=t + 600)
    assert service.list_runs() == []
    service.tick(now=t + 901)
    [run] = service.list_runs()
    assert run.trigger == "reconnect"
    assert (run.window_from, run.window_to) == (to_iso(t - 600), to_iso(t - 100))


@pytest.mark.asyncio
async def test_budget_guard_requires_confirmation(store, monkeypatch):
    start = NOW - timedelta(hours=3)
    service = make_service(store, FixtureBeeHistorySource([make_conv(17, start, lines_every(30, TEN))]))
    monkeypatch.setattr(settings, "backfill_max_estimated_cost_usd", 1e-9)
    window = ((start - timedelta(minutes=5)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    with pytest.raises(BackfillRequestError) as err:
        await service.create_run(*window)
    assert err.value.code == "over_budget"
    run = await service.create_run(*window, confirm_over_budget=True)
    assert run.status == "planned"
    with pytest.raises(BackfillRequestError) as overlap:
        await service.create_run(*window, confirm_over_budget=True)
    assert overlap.value.status == 409


@pytest.mark.asyncio
async def test_window_end_is_clamped_to_the_live_connection(store):
    live_since = NOW - timedelta(hours=1)
    service = make_service(store, FixtureBeeHistorySource([]))
    service.live_since_getter = lambda: live_since.isoformat()
    result = await service.preview((NOW - timedelta(hours=4)).isoformat(), NOW.isoformat())
    assert result.plan.window_to == to_iso(live_since.timestamp())
    assert "live stream owns" in result.plan.warnings[0]
    with pytest.raises(BackfillRequestError):
        await service.preview((NOW - timedelta(minutes=30)).isoformat(), NOW.isoformat())


# ---------------------------------------------------------------------------
# Observed Bee contract (docs/10_bee_cli_reference.md): completed conversations have no uuid and only the
# final transcription; start/end are relative seconds; speakers are first names or "Unknown".
# ---------------------------------------------------------------------------

from src.ingestion import bee_identity  # noqa: E402
from src.ingestion.backfill import speaker_role_for  # noqa: E402


def record_live_spoken(store, conv_uuid: str, start: datetime, spans, delay=12.0):
    """Live ledger rows as the real orchestrator writes them: ts = spoken_at, duration_ms from start/end."""
    for i, (offset, seconds, text) in enumerate(spans):
        spoken = start + timedelta(seconds=offset)
        chunk = UtteranceChunk(chunk_id=f"live-{conv_uuid}-{i}", conversation_uuid=conv_uuid, text=text,
                               timestamp=spoken.isoformat(), spoken_at=spoken.isoformat(),
                               received_at=(spoken + timedelta(seconds=delay)).isoformat(),
                               duration_ms=int(seconds * 1000))
        store.record_ingested_utterance(ledger_entry_for_chunk(chunk, "qualified"))


def test_utterance_span_uses_relative_start_end_as_duration():
    spoken = int((NOW - timedelta(hours=1)).timestamp() * 1000)
    conv = BeeConversation.from_payload({"conversation": {
        "id": 10, "start_time": spoken, "end_time": spoken + 60_000, "state": "COMPLETED",
        "transcriptions": [{"id": 1, "realtime": False, "utterances": [
            {"id": 1, "text": "hi", "spoken_at": spoken, "start": 1747.12, "end": 2152.64, "speaker": "Unknown"},
            {"id": 2, "text": "no times", "spoken_at": spoken + 1000, "start": None, "end": 3.0}]}],
    }})
    first, second = conv.final_transcription().utterances
    assert first.span_ms == (spoken, spoken + 405_520)
    assert second.span_ms == (spoken + 1000, spoken + 1000)


@pytest.mark.parametrize("state,ended,expected", [
    ("CAPTURING", False, "deferred"), ("PROCESSING", True, "deferred"), ("COMPLETED", True, "ready"),
])
def test_readiness_with_observed_states(state, ended, expected):
    start = NOW - timedelta(hours=1)
    conv = BeeConversation.from_payload(make_conv(11, start, lines_every(30, TEN[:2]), realtime=False,
                                                  state=state, ended=ended))
    assert conv.readiness(int(NOW.timestamp() * 1000)) == expected


@pytest.mark.asyncio
async def test_reissued_final_is_matched_exactly_against_live(store):
    """Typical completed conversation: the final re-issues the realtime text with new ids, no uuid."""
    start = NOW - timedelta(hours=3)
    lines = lines_every(20, TEN[:6])
    record_live_spoken(store, "uuid-12", start, [(o, 4.0, t) for o, t in lines[:4]])
    source = FixtureBeeHistorySource([make_conv(12, start, lines, realtime=False)])
    result = await BackfillPlanner(source, lambda: store).plan(
        (start - timedelta(minutes=10)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    assert [s.utterance.text for s in result.items] == TEN[4:6]
    assert result.plan.utterances["duplicate_live"] == 4


@pytest.mark.asyncio
async def test_resegmented_final_covered_by_live_speech_is_a_duplicate(store, monkeypatch):
    """Bee sometimes collapses minutes of speech into one final utterance: text cannot match, time can."""
    start = NOW - timedelta(hours=3)
    live_spans = [(i * 30, 25.0, f"live sentence {i} about the quarterly plan") for i in range(10)]  # 0–295 s
    record_live_spoken(store, "uuid-13", start, live_spans)
    long_text = " ".join(f"word{i}" for i in range(600))
    at = int(start.timestamp() * 1000)
    payload = {"conversation": {
        "id": 13, "start_time": at, "end_time": at + 700_000, "state": "COMPLETED",
        "transcriptions": [{"id": 131, "realtime": False, "utterances": [
            {"id": 1, "text": long_text, "speaker": "Unknown", "spoken_at": at, "start": 0.0, "end": 300.0},
            {"id": 2, "text": long_text + " more", "speaker": "Unknown", "spoken_at": at + 400_000,
             "start": 400.0, "end": 650.0},
        ]}],
    }}
    store.map_bee_conversation("uuid-13", 13)
    result = await BackfillPlanner(FixtureBeeHistorySource([payload]), lambda: store).plan(
        (start - timedelta(minutes=10)).isoformat(), (start + timedelta(minutes=30)).isoformat())
    # First block: spoken live (fraction ≈ 0.98); second block: after live stopped → recovered
    assert [s.utterance.id for s in result.items] == [2]
    assert result.plan.utterances["duplicate_live"] == 1


def test_backfill_speaker_roles_use_the_wearer_name(monkeypatch):
    monkeypatch.setattr(bee_identity, "_identity", bee_identity.WearerIdentity("Ada"))
    assert speaker_role_for("Ada") == "user"
    assert speaker_role_for("Unknown") == "unknown"
    assert speaker_role_for("Marco") == "contact"
    assert speaker_role_for(None) == "unknown"


# ---------------------------------------------------------------------------
# Conversation windows (docs/next_steps/historical_backfill/07_conversation_windows.md)
# ---------------------------------------------------------------------------

CHATTER = [f"small talk line {i} about the weather and the coffee" for i in range(20)]


def counting_classifier():
    calls: List[Dict[str, Optional[str]]] = []

    async def classify(transcript, active_tasks=None, prior_context=None):
        calls.append({"transcript": transcript, "context": prior_context})
        return await fake_classify(transcript, active_tasks, prior_context)

    return classify, calls


@pytest.mark.asyncio
async def test_window_screening_drills_down_only_where_there_is_signal(store, monkeypatch):
    monkeypatch.setattr(settings, "backfill_screening", "window")
    monkeypatch.setattr(settings, "backfill_window_utterances", 10)
    start = NOW - timedelta(hours=3)
    texts = list(CHATTER)
    texts[13] = "I unplugged the iron before leaving"
    classify, calls = counting_classifier()
    service = make_service(store, FixtureBeeHistorySource([make_conv(30, start, lines_every(20, texts))]),
                           classify=classify)
    run = await service.create_run((start - timedelta(minutes=5)).isoformat(), (start + timedelta(hours=1)).isoformat())
    assert run.plan.utterances["windows"] == 2
    await service.run_next()
    run = service.get_run(run.id)

    # 2 window calls + 10 single calls for the window holding the action, instead of 20
    assert len(calls) == 12
    assert run.counters["windows"] == 2 and run.counters["windows_with_signal"] == 1
    assert run.counters["processed"] == 20 and run.counters["qualified"] == 1
    statuses = [r["status"] for r in store.list_ledger_entries(
        (start - timedelta(minutes=5)).isoformat(), (start + timedelta(hours=1)).isoformat(), source="backfill")]
    assert statuses.count("qualified") == 1 and statuses.count("screened_noop") == 19


@pytest.mark.asyncio
async def test_window_context_has_look_back_look_ahead_and_bee_summary(store, monkeypatch):
    monkeypatch.setattr(settings, "backfill_screening", "window")
    monkeypatch.setattr(settings, "backfill_window_utterances", 4)
    start = NOW - timedelta(hours=3)
    texts = ["Can you send me the audit report", "Sure I will email it", "I merged the fix",
             "Great thanks", "See you tomorrow", "Bye now"]
    classify, calls = counting_classifier()
    service = make_service(store, FixtureBeeHistorySource([make_conv(31, start, lines_every(20, texts))]),
                           classify=classify)
    await service.create_run((start - timedelta(minutes=5)).isoformat(), (start + timedelta(hours=1)).isoformat())
    await service.run_next()

    window_call = calls[0]
    assert window_call["transcript"].count("\n") == 3          # the 4-utterance window as one text
    assert "Bee conversation: Conversation 31" in window_call["context"]
    assert "What was said next" in window_call["context"]       # look-ahead
    assert "See you tomorrow" in window_call["context"]
    single = next(c for c in calls[1:] if c["transcript"] == "I merged the fix")
    assert "This part of the conversation" in single["context"] and "Great thanks" in single["context"]


@pytest.mark.asyncio
async def test_whole_conversation_is_analysed_even_before_the_window(store, monkeypatch):
    start = NOW - timedelta(hours=3)
    lines = lines_every(60, TEN)           # 10 minutes of speech, the window starts after minute 5
    source = FixtureBeeHistorySource([make_conv(32, start, lines, uuid="uuid-32")])
    window = ((start + timedelta(minutes=5, seconds=30)).isoformat(), (start + timedelta(hours=1)).isoformat())

    monkeypatch.setattr(settings, "backfill_whole_conversations", True)
    whole = await BackfillPlanner(source, lambda: store).plan(*window)
    assert len(whole.items) == 10 and whole.plan.conversations["missed"] == 1

    monkeypatch.setattr(settings, "backfill_whole_conversations", False)
    clipped = await BackfillPlanner(source, lambda: store).plan(*window)
    assert len(clipped.items) == 4


@pytest.mark.asyncio
async def test_whole_conversation_still_skips_what_live_analysed(store, monkeypatch):
    monkeypatch.setattr(settings, "backfill_whole_conversations", True)
    start = NOW - timedelta(hours=3)
    lines = lines_every(60, TEN)
    record_live(store, "uuid-33", start, lines, range(6))   # live heard the first 6 minutes
    source = FixtureBeeHistorySource([make_conv(33, start, lines, uuid="uuid-33")])
    result = await BackfillPlanner(source, lambda: store).plan(
        (start + timedelta(minutes=7)).isoformat(), (start + timedelta(hours=1)).isoformat())
    assert [s.utterance.text for s in result.items] == TEN[6:]
    assert result.plan.conversations["partial"] == 1


@pytest.mark.asyncio
async def test_utterance_screening_is_still_available(store, monkeypatch):
    monkeypatch.setattr(settings, "backfill_screening", "utterance")
    start = NOW - timedelta(hours=3)
    classify, calls = counting_classifier()
    service = make_service(store, FixtureBeeHistorySource([make_conv(34, start, lines_every(20, CHATTER[:12]))]),
                           classify=classify)
    await service.create_run((start - timedelta(minutes=5)).isoformat(), (start + timedelta(hours=1)).isoformat())
    await service.run_next()
    assert len(calls) == 12


def test_stop_survives_a_restart(store):
    from src.core.schemas import BackfillRun

    service = make_service(store, FixtureBeeHistorySource([]))
    running = BackfillRun(window_from=(NOW - timedelta(days=7)).isoformat(), window_to=NOW.isoformat(),
                          status="replaying")
    store.save_backfill_run(running)
    stopped = service.cancel(running.id)
    assert stopped.cancel_requested is True

    restarted = make_service(store, FixtureBeeHistorySource([]))   # new process
    restarted.rehydrate()
    assert store.get_backfill_run(running.id).status == "cancelled"
    assert restarted._next_runnable() is None

    queued = BackfillRun(window_from=(NOW - timedelta(days=2)).isoformat(), window_to=NOW.isoformat())
    store.save_backfill_run(queued)
    assert restarted.cancel(queued.id).status == "cancelled"
