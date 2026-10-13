"""Unit tests for BeeStreamOrchestrator: screening, event engine feeding and pipeline dispatch."""

import importlib
import sys
from datetime import datetime

import pytest

from src.core.schemas import BriefingReport, ChunkClassification
from src.core.storage.sqlite_store import SQLiteContextStore
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
    return SQLiteContextStore(str(tmp_path / "orchestrator.db"))


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
