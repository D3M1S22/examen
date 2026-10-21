"""Unit tests for BeeStreamOrchestrator: screening, event engine feeding and pipeline dispatch."""

import importlib
import sys
from datetime import datetime

import pytest

from src.core.schemas import BriefingReport, ChunkClassification
from src.ingestion.event_engine import EngineConfig, EventEngine
from src.ingestion.orchestrator import BeeStreamOrchestrator
from src.ingestion.stream_convo import normalize_bee_time

class StaticSynthesizer:
    def __init__(self, briefing):
        self.briefing = briefing

    def segment(self, text, session_id, outline=None, kind="segment"):
        return self.briefing.model_copy()

    def final(self, parts, extra_text, session_id, outline=None, micro_events=None):
        return self.briefing.model_copy()


LECTURE = "Il teorema fondamentale del calcolo collega derivata e integrale definito"


@pytest.fixture
def store(tmp_path):
    return new_store(str(tmp_path / "orchestrator.db"))


@pytest.fixture
def orchestrator(store, monkeypatch):
    engine = EventEngine(
        store=store,
        config=EngineConfig(min_segment_words=5),
        synthesizer=StaticSynthesizer(BriefingReport(topic_title="Calculus", context_type="academic_lecture")),
    )
    orch = BeeStreamOrchestrator(store=store, engine=engine)
    orch.engine_enabled = True

    dispatched = []
    # src.pipeline exposes an `app` object that shadows the module path, so patch via sys.modules
    importlib.import_module("src.pipeline.app")
    pipeline_app_module = sys.modules["src.pipeline.app"]
    monkeypatch.setattr(pipeline_app_module, "agent_invocation", lambda payload: dispatched.append(payload) or {"ok": True})
    orch._dispatched = dispatched  # type: ignore[attr-defined]
    return orch


def _fake_gatekeeper(monkeypatch, categories):
    async def _classify(transcript, active_tasks=None, prior_context=None):
        return ChunkClassification(categories=categories, confidence=0.9, summary_hint="test")
    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", _classify)


@pytest.mark.asyncio
async def test_deep_topic_utterance_opens_event_and_is_event_managed(orchestrator, monkeypatch):
    _fake_gatekeeper(monkeypatch, ["deep_topic"])
    await orchestrator.process_incoming_utterance({
        "id": "u1", "text": LECTURE, "conversation_uuid": "bee-1",
        "received_at": "2026-10-13T10:00:00",
    })
    event_id = orchestrator.engine.current_event_id()
    assert event_id is not None and event_id != "bee-1"

    payload = orchestrator._dispatched[0]
    assert payload["event_managed"] is True
    assert payload["session_id"] == event_id
    assert payload["timestamp"] == "2026-10-13T10:00:00"  # receive time, not processing time


@pytest.mark.asyncio
async def test_noop_is_logged_in_open_event_but_not_dispatched(orchestrator, store, monkeypatch):
    _fake_gatekeeper(monkeypatch, ["deep_topic"])
    await orchestrator.process_incoming_utterance({"id": "u1", "text": LECTURE, "received_at": "2026-10-13T10:00:00"})
    _fake_gatekeeper(monkeypatch, ["noop"])
    result = await orchestrator.process_incoming_utterance(
        {"id": "u2", "text": "quindi qui sostituiamo", "received_at": "2026-10-13T10:00:20"}
    )
    assert result is None
    assert len(orchestrator._dispatched) == 1
    assert len(store.list_session_chunks(orchestrator.engine.current_event_id())) == 2


@pytest.mark.asyncio
async def test_action_without_event_uses_conversation_session(orchestrator, monkeypatch):
    _fake_gatekeeper(monkeypatch, ["action"])
    await orchestrator.process_incoming_utterance({
        "id": "u1", "text": "Ho spento la luce della camera", "conversation_uuid": "bee-9",
        "received_at": "2026-10-13T10:00:00",
    })
    payload = orchestrator._dispatched[0]
    assert payload["event_managed"] is False and payload["session_id"] == "bee-9"
    assert orchestrator.engine.current_event_id() is None


@pytest.mark.asyncio
async def test_handle_event_counts_utterances(orchestrator, monkeypatch):
    _fake_gatekeeper(monkeypatch, ["noop"])
    await orchestrator.handle_event({"event": "new-utterance", "data": {"id": "u1", "text": "ciao"}})
    status = orchestrator.get_status_dict()
    assert status["utterances_received"] == 1 and status["chunks_screened"] == 1
    assert status["event_engine"]["active_event"] is None


def test_location_update_reaches_engine(orchestrator):
    calls = []
    orchestrator.engine.on_location = lambda loc, now=None: calls.append(loc) or []
    orchestrator.update_location({"latitude": 45.06, "longitude": 7.66, "name": "Politecnico"})
    assert calls and calls[0]["place_name"] == "Politecnico"


def test_utterance_timestamp_priority(orchestrator):
    spoken = orchestrator.buffer_incoming_utterance({
        "id": "a", "text": "x", "spoken_at": "2026-10-13T09:59:58", "received_at": "2026-10-13T10:00:00",
    })
    assert spoken.timestamp == "2026-10-13T09:59:58"
    received = orchestrator.buffer_incoming_utterance({"id": "b", "text": "y", "received_at": "2026-10-13T10:00:00"})
    assert received.timestamp == "2026-10-13T10:00:00" and received.spoken_at is None


def test_normalize_bee_time():
    epoch_ms = datetime(2026, 10, 13, 10, 0, 0).timestamp() * 1000
    assert normalize_bee_time(epoch_ms) == "2026-10-13T10:00:00"
    assert normalize_bee_time(epoch_ms / 1000) == "2026-10-13T10:00:00"
    assert normalize_bee_time(None) is None and normalize_bee_time("not a date") is None


@pytest.mark.asyncio
async def test_active_event_hint_reaches_gatekeeper(orchestrator, monkeypatch):
    seen = []

    async def _classify(transcript, active_tasks=None, prior_context=None):
        seen.append(prior_context)
        return ChunkClassification(categories=["deep_topic"], confidence=0.9, summary_hint="")

    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", _classify)
    monkeypatch.setattr(orchestrator.engine, "active_event_hint", lambda: "ONGOING EVENT: a lecture about 'Calculus'")
    await orchestrator.process_incoming_utterance({"id": "u1", "text": LECTURE, "received_at": "2026-10-13T10:00:00"})
    assert seen and "ONGOING EVENT" in seen[0]


@pytest.mark.asyncio
async def test_bee_conversation_events_are_forwarded(orchestrator):
    calls = []
    orchestrator.engine.on_bee_conversation = lambda event_type, data: calls.append((event_type, data))
    await orchestrator.handle_event({"event": "update-conversation", "data": {"conversation": {"id": 3, "title": "Analisi"}}})
    assert calls == [("update-conversation", {"conversation": {"id": 3, "title": "Analisi"}})]


# ---------------------------------------------------------------------------
# Real Bee contract (docs/10_bee_cli_reference.md): speaker tags, uuid ↔ id, location polling,
# liveness. Synthetic values, real payload shapes.
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

from src.core.schemas import VerifiedAction  # noqa: E402
from src.ingestion.bee_identity import WearerIdentity, role_for_person  # noqa: E402
from tests.store_backend import new_store


def _now_iso():
    return datetime.now().isoformat()


@pytest.mark.parametrize("name,wearer,expected", [
    ("Ada", "Ada", "user"), ("ada", "Ada", "user"), ("Marco", "Ada", "contact"),
    ("Unknown", "Ada", "unknown"), (None, "Ada", "unknown"), ("Ada", None, "unknown"), ("user", None, "user"),
])
def test_role_for_person(name, wearer, expected):
    assert role_for_person(name, wearer) == expected


async def _process_with_tag(orchestrator, monkeypatch, tag_name, delay=0.05):
    _fake_gatekeeper(monkeypatch, ["action"])
    orchestrator.identity = WearerIdentity("Ada")
    orchestrator._concurrent_reader = True
    data = {"id": "3700000001", "text": "I just unplugged the iron.", "conversation_uuid": "uuid-1",
            "received_at": _now_iso()}
    task = asyncio.create_task(orchestrator.process_incoming_utterance(data))
    if tag_name:
        await asyncio.sleep(delay)
        orchestrator.on_tagged_utterance({"utterance_id": "3700000001", "person_first_name": tag_name,
                                          "speaker_score": 0.8, "conversation_uuid": "uuid-1"})
    await task
    return orchestrator._dispatched[-1]


@pytest.mark.asyncio
async def test_wearer_tag_during_wait_marks_user(orchestrator, monkeypatch):
    payload = await _process_with_tag(orchestrator, monkeypatch, "Ada")
    assert payload["speaker"] == "Ada" and payload["speaker_role"] == "user"


@pytest.mark.asyncio
async def test_other_person_tag_marks_contact(orchestrator, monkeypatch):
    payload = await _process_with_tag(orchestrator, monkeypatch, "Marco")
    assert payload["speaker_role"] == "contact"


@pytest.mark.asyncio
async def test_untagged_utterance_is_unknown_after_bounded_wait(orchestrator, monkeypatch):
    orchestrator.speaker_tag_wait = 0.2
    started = asyncio.get_running_loop().time()
    payload = await _process_with_tag(orchestrator, monkeypatch, None)
    assert payload["speaker_role"] == "unknown" and payload["speaker"] is None
    assert asyncio.get_running_loop().time() - started < 1.0


@pytest.mark.asyncio
async def test_late_tag_patches_buffer_without_touching_actions(orchestrator, store, monkeypatch):
    _fake_gatekeeper(monkeypatch, ["action"])
    orchestrator.identity = WearerIdentity("Ada")
    store.save_action(VerifiedAction(id="3700000002", action_type="iron_unplugged", domain="safety",
                                     raw_statement="I unplugged the iron", confidence=0.9, matched_task_id="task-1",
                                     session_id="uuid-2"))
    await orchestrator.process_incoming_utterance({"id": "3700000002", "text": "I unplugged the iron",
                                                   "conversation_uuid": "uuid-2", "received_at": _now_iso()})
    assert orchestrator._dispatched[-1]["speaker_role"] == "unknown"  # no concurrent reader: no wait
    orchestrator.on_tagged_utterance({"utterance_id": "3700000002", "person_first_name": "Ada",
                                      "conversation_uuid": "uuid-2"})
    chunk = orchestrator.ring_buffer.get_last_chunk("uuid-2")
    assert chunk.speaker_id == "Ada" and chunk.speaker_role == "user"
    action = store.get_verified_action("3700000002")
    assert action.matched_task_id == "task-1" and action.session_id == "uuid-2"


@pytest.mark.asyncio
async def test_utterance_chunks_map_uuid_to_rest_id(orchestrator, store, monkeypatch):
    _fake_gatekeeper(monkeypatch, ["noop"])
    await orchestrator.handle_event({"event": "new-utterance", "data": {
        "id": "3700000003", "text": "ciao", "conversation_uuid": "uuid-3", "received_at": _now_iso()}})
    await orchestrator.handle_event({"event": "new-utterance-chunks", "data": {
        "conversation_id": 11400000, "transcription_id": 1, "utterance_ids": ["3700000003"]}})
    assert store.get_bee_conversation_uuid(11400000) == "uuid-3"
    assert orchestrator.engine._bee_conv_ids["11400000"] == "uuid-3"
    chunk = orchestrator.buffer_incoming_utterance({"id": "3700000004", "text": "dopo", "conversation_uuid": "uuid-3"})
    assert chunk.bee_conversation_id == 11400000


@pytest.mark.asyncio
async def test_location_poll_accepts_only_new_recent_fixes(orchestrator, monkeypatch):
    fixes = iter([
        {"id": 1, "latitude": 45.07, "longitude": 7.68, "address": "1 Via Roma, Torino",
         "created_at": 1792416558579, "is_recent": True, "age_ms": 5000},
        {"id": 1, "latitude": 45.07, "longitude": 7.68, "address": "1 Via Roma, Torino",
         "created_at": 1792416558579, "is_recent": True, "age_ms": 65000},
        {"id": 2, "latitude": 45.10, "longitude": 7.70, "address": "2 Corso Carlo Alberto, Torino",
         "created_at": 1792419000000, "is_recent": False, "age_ms": 3_600_000},
        None,
    ])

    async def fake_fetch():
        return next(fixes)

    monkeypatch.setattr(orchestrator, "_fetch_location", fake_fetch)
    first = await orchestrator.poll_location()
    assert first is not None and first.place_name == "1 Via Roma, Torino"
    assert first.captured_at == normalize_bee_time(1792416558579)
    assert await orchestrator.poll_location() is None  # same fix id
    assert await orchestrator.poll_location() is None  # stale fix
    assert await orchestrator.poll_location() is None  # CLI failure
    assert orchestrator.latest_telemetry.place_name == "1 Via Roma, Torino"
    chunk = orchestrator.buffer_incoming_utterance({"id": "x", "text": "hello"})
    assert chunk.location["place_name"] == "1 Via Roma, Torino"


class _FakeBeeStream:
    """Stands in for BeeClient in run(): yields scripted events, then idles until cancelled."""

    def __init__(self, events):
        self.events = events
        self.active_transport = "proxy"

    async def stream_events(self):
        for event in self.events:
            yield event
            await asyncio.sleep(0)
        await asyncio.Event().wait()

    def stop(self):
        pass


@pytest.mark.asyncio
async def test_run_applies_tag_that_follows_utterance_and_tracks_pings(orchestrator, monkeypatch):
    async def slow_gatekeeper(transcript, active_tasks=None, prior_context=None):
        await asyncio.sleep(0.1)  # the tag is read while the utterance is being screened
        return ChunkClassification(categories=["action"], confidence=0.9, summary_hint="test")

    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", slow_gatekeeper)
    events = [
        {"event": "stream-connected", "data": {"timestamp": 1}},
        {"event": "new-utterance", "data": {"id": "3700000005", "text": "I locked the door.",
                                            "conversation_uuid": "uuid-5", "received_at": _now_iso()}},
        {"event": "tagged-utterance", "data": {"utterance_id": "3700000005", "person_first_name": "Ada",
                                               "conversation_uuid": "uuid-5"}},
        {"event": "stream-ping", "data": {}},
    ]
    monkeypatch.setattr("src.ingestion.orchestrator.BeeClient", lambda debug_mode="none": _FakeBeeStream(events))
    orchestrator.identity = WearerIdentity("Ada")
    orchestrator.engine_enabled = False
    orchestrator.location_poll_seconds = 0
    gaps = []
    orchestrator.on_coverage_gap = gaps.append

    task = asyncio.create_task(orchestrator.run())
    for _ in range(100):
        if orchestrator._dispatched:
            break
        await asyncio.sleep(0.02)
    status = orchestrator.get_status_dict()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert orchestrator._dispatched[-1]["speaker_role"] == "user"
    assert orchestrator.last_heartbeat_time is not None and not gaps
    assert status["stream_transport"] == "proxy" and status["coverage"]["connected"] is True
