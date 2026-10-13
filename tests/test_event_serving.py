"""Tests for the Deep Topic Event Engine — Phase D (serving layer: manual operations, REST, MCP tools).

Spec: docs/next_steps/deep_topic_event_engine/06_serving_and_ui.md
"""

import os
import tempfile
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from src.core.schemas import BriefingReport, ChunkClassification, MicroEventRef, UtteranceChunk
from src.core.storage.sqlite_store import SQLiteContextStore
from src.ingestion.event_engine import EngineConfig, EventEngine, EventEngineRuntime, to_iso
from src.serving.tools.session_tools import execute_get_live_event_outline, execute_get_session_dossier

T0 = datetime(2026, 10, 13, 10, 0, 0).timestamp()
LECTURE = "Il limite per x che tende a zero di sin x su x vale uno e lo dimostriamo con il teorema del confronto"
CHEM = "Gli alcani sono idrocarburi saturi e la nomenclatura IUPAC individua la catena carboniosa più lunga"


class CountingSynth:
    def __init__(self):
        self.n = 0

    def _b(self, title):
        self.n += 1
        return BriefingReport(topic_title=f"{title} {self.n}", context_type="academic_lecture",
                              executive_summary=[f"point {self.n}"], explanatory_synthesis=f"synthesis {self.n}")

    def segment(self, text, session_id, outline=None, kind="segment"):
        return self._b("Segment")

    def final(self, parts, extra_text, session_id, outline=None, micro_events=None):
        return self._b("Final")


@pytest.fixture
def store(tmp_path):
    return SQLiteContextStore(str(tmp_path / "serving.db"))


@pytest.fixture
def engine(store):
    clock = {"now": T0}
    eng = EventEngine(store=store, config=EngineConfig(min_segment_words=10), clock=lambda: clock["now"],
                      synthesizer=CountingSynth())
    return eng


def say(engine, text, offset, cats=("deep_topic",)):
    return engine.record_chunk(UtteranceChunk(conversation_uuid="bee", text=text, timestamp=to_iso(T0 + offset),
                                              categories=list(cats)))


def lecture(engine, start, n=3, text=LECTURE):
    for i in range(n):
        say(engine, text, start + i * 30, )


# ---------------------------------------------------------------------------
# Engine manual operations
# ---------------------------------------------------------------------------

class TestManualOperations:
    def test_pause_synthesizes_now_and_resume(self, engine, store):
        lecture(engine, 0)
        event_id = engine.current_event_id()
        assert engine.pause("wrong-id") is None
        ev = engine.pause(event_id, now=T0 + 100)
        assert ev.status == "paused" and ev.segments[0].close_reason == "manual_pause"
        engine.run_pending_jobs_sync()
        assert store.get_session_dossier(event_id).segments[0].status == "synthesized"
        ev = engine.resume(event_id, now=T0 + 200)
        assert ev.status == "active" and len(ev.segments) == 2
        assert engine.resume(event_id) is None  # already active

    def test_advance_clock_runs_timers(self, engine):
        lecture(engine, 0)
        engine.clock_offset = 0.0
        transitions = engine.advance_clock(400)
        assert [t.rule for t in transitions] == ["R1"]
        assert engine.clock_offset == 400

    def test_split_concluded_event(self, engine, store):
        lecture(engine, 0)                         # segment 1 (calculus)
        engine.tick(now=T0 + 400)                  # pause
        lecture(engine, 900, text=CHEM)            # segment 2 (wrongly resumed: chemistry)
        event_id = engine.current_event_id()
        engine.conclude(event_id, now=T0 + 1000)
        engine.run_pending_jobs_sync()
        before = store.get_session_dossier(event_id)
        assert before.final_status == "ready" and len(before.segments) == 2
        old_final_id = before.final_briefing_id

        old, new = engine.split(event_id, at_time=before.segments[1].start_time)
        assert [s.index for s in old.segments] == [1] and [s.index for s in new.segments] == [1]
        assert all(c.text == CHEM for c in store.list_session_chunks(new.session_id))
        assert all(c.text == LECTURE for c in store.list_session_chunks(old.session_id))
        assert store.get_topic_briefing(old_final_id) is None or store.get_topic_briefing(old_final_id).id != old_final_id
        # the moved segment kept its briefing, now owned by the new event
        moved_briefing = store.get_topic_briefing(new.segments[0].briefing_id)
        assert moved_briefing.session_id == new.session_id

        engine.run_pending_jobs_sync()
        assert store.get_session_dossier(old.session_id).final_status == "ready"
        assert store.get_session_dossier(new.session_id).final_status == "ready"

    def test_split_inside_open_segment_of_current_event(self, engine, store):
        lecture(engine, 0, n=4)
        event_id = engine.current_event_id()
        old, new = engine.split(event_id, at_time=to_iso(T0 + 60))
        assert old.status == "concluded" and new.status == "active"
        assert engine.current_event_id() == new.session_id
        assert new.segments[0].status == "open" and new.segments[0].word_count > 0
        assert old.segments[0].status == "closed" and old.segments[0].close_reason == "manual_split"
        assert len(store.list_session_chunks(new.session_id)) == 2

    def test_split_moves_micro_events_by_time(self, engine, store):
        lecture(engine, 0, n=4)
        event_id = engine.current_event_id()
        store.link_micro_event_to_session(event_id, MicroEventRef(
            event_type="action", record_id="early", headline="early", timestamp=to_iso(T0 + 10)))
        store.link_micro_event_to_session(event_id, MicroEventRef(
            event_type="action", record_id="late", headline="late", timestamp=to_iso(T0 + 80)))
        engine._current.linked_micro_events = store.get_session_dossier(event_id).linked_micro_events
        old, new = engine.split(event_id, at_time=to_iso(T0 + 60))
        assert [r.record_id for r in old.linked_micro_events] == ["early"]
        assert [r.record_id for r in new.linked_micro_events] == ["late"]

    def test_split_rejects_empty_sides(self, engine):
        lecture(engine, 0)
        event_id = engine.current_event_id()
        assert engine.split(event_id, at_time=to_iso(T0 - 100)) is None
        assert engine.split(event_id, at_time=to_iso(T0 + 10_000)) is None

    def test_merge_two_events(self, engine, store):
        lecture(engine, 0)
        first = engine.current_event_id()
        engine.conclude(first, now=T0 + 100)
        lecture(engine, 200)
        second = engine.current_event_id()
        engine.conclude(second, now=T0 + 300)
        engine.run_pending_jobs_sync()

        merged = engine.merge([second, first])
        assert merged.session_id == first
        assert [s.index for s in merged.segments] == [1, 2]
        assert store.get_session_dossier(second) is None
        assert len(store.list_session_chunks(first)) == 6
        assert merged.final_status == "pending"
        finals = [b for b in store.list_briefings_for_session(first) if b.kind == "final"]
        assert finals == []                                   # stale finals removed
        engine.run_pending_jobs_sync()
        assert store.get_session_dossier(first).final_status == "ready"

    def test_merge_with_open_event_keeps_it_current(self, engine, store):
        lecture(engine, 0)
        first = engine.current_event_id()
        engine.conclude(first, now=T0 + 100)
        lecture(engine, 200)
        second = engine.current_event_id()
        merged = engine.merge([first, second])
        assert merged.session_id == first and merged.status == "active"
        assert engine.current_event_id() == first


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

class TestSessionTools:
    def test_dossier_falls_back_to_latest_segment_briefing(self, engine, store):
        lecture(engine, 0)
        event_id = engine.current_event_id()
        engine.tick(now=T0 + 400)
        engine.run_pending_jobs_sync()
        res = execute_get_session_dossier(session_id=event_id, store=store)
        assert res["is_final"] is False and res["display_briefing"]["kind"] == "segment"
        assert res["segments"][0]["briefing"]["topic_title"].startswith("Segment")
        assert res["transitions"][0]["rule"] == "R0"
        assert "still paused" in res["spoken_summary"] and "First part" in res["spoken_summary"]
        card = res["card_payload"]
        assert card["is_final"] is False and card["segments"][0]["status"] == "synthesized"

    def test_dossier_with_final(self, engine, store):
        lecture(engine, 0)
        event_id = engine.current_event_id()
        engine.conclude(event_id, now=T0 + 100)
        engine.run_pending_jobs_sync()
        res = execute_get_session_dossier(session_id=event_id, store=store)
        assert res["is_final"] is True and res["final_status"] == "ready"
        assert "Here is the recap" in res["spoken_summary"]

    def test_live_event_outline(self, engine):
        assert execute_get_live_event_outline(engine)["found"] is False
        lecture(engine, 0)
        outline = execute_get_live_event_outline(engine)
        assert outline["found"] is True and outline["status"] == "active"
        assert outline["segments"][0]["status"] == "open"


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch):
    import src.core.storage as storage_mod
    import src.ingestion.event_engine as engine_mod
    import src.serving.mcp_server as server_mod

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    temp_store = SQLiteContextStore(db_path=db_path)
    monkeypatch.setattr(storage_mod, "_store_instance", temp_store)
    clock = {"now": T0}
    eng = EventEngine(store=temp_store, config=EngineConfig(min_segment_words=10),
                      clock=lambda: clock["now"], synthesizer=CountingSynth())
    runtime = EventEngineRuntime(eng)
    monkeypatch.setattr(runtime, "ensure_started", lambda: True)
    monkeypatch.setattr(engine_mod, "_engine", eng)
    monkeypatch.setattr(engine_mod, "_runtime", runtime)
    monkeypatch.setattr(server_mod, "_engine_listener_registered", False)
    monkeypatch.setattr(server_mod, "agent_invocation", lambda payload: {"status": "ok", "categories": payload.get("categories")})

    async def _classify(transcript, active_tasks=None, prior_context=None):
        return ChunkClassification(categories=["noop"], confidence=0.9, summary_hint="")
    monkeypatch.setattr("src.ingestion.gatekeeper.aclassify_chunk", _classify)

    client = TestClient(server_mod.create_app())
    yield client, eng, temp_store
    if os.path.exists(db_path):
        os.remove(db_path)


def _simulate(client, text, cats=("deep_topic",)):
    return client.post("/api/simulate", json={"transcript_chunk": text, "event_mode": True, "categories": list(cats)})


class TestEventEndpoints:
    def test_simulate_with_scenario_labels_and_virtual_clock(self, api):
        client, eng, store = api
        res = _simulate(client, LECTURE)
        assert res.json()["result"]["event"]["status"] == "active"   # labels override the (noop) gatekeeper
        tick = client.post("/api/simulate/tick", json={"seconds": 400}).json()
        assert [t["rule"] for t in tick["transitions"]] == ["R1"] and tick["clock_offset_seconds"] == 400
        status = client.get("/api/event-engine/status").json()
        assert status["active_event"]["status"] == "paused" and status["clock_offset_seconds"] == 400
        assert client.post("/api/simulate/tick", json={"reset": True}).json()["clock_offset_seconds"] == 0

    def test_sessions_list_events_only_and_detail(self, api):
        client, eng, store = api
        store.append_chunk_to_session("legacy-conv", "a legacy session without segments")
        for _ in range(3):
            _simulate(client, LECTURE)
        listing = client.get("/api/sessions?events_only=true").json()
        assert listing["count"] == 1
        item = listing["sessions"][0]
        assert item["status"] == "active" and item["segments"][0]["status"] == "open"
        assert "transcript_chunks" not in item and "topic_profile" not in item
        assert client.get("/api/sessions").json()["count"] == 2
        detail = client.get(f"/api/sessions/{item['session_id']}").json()
        assert detail["found"] is True and detail["segments"] and detail["transitions"]
        chunks = client.get(f"/api/sessions/{item['session_id']}/chunks").json()
        assert chunks["count"] == 3 and chunks["chunks"][0]["segment_id"] == item["segments"][0]["segment_id"]

    def test_pause_resume_endpoints(self, api):
        client, eng, store = api
        for _ in range(3):
            _simulate(client, LECTURE)
        event_id = eng.current_event_id()
        assert client.post(f"/api/sessions/{event_id}/resume").status_code == 409
        paused = client.post(f"/api/sessions/{event_id}/pause").json()
        assert paused["success"] and paused["event"]["status"] == "paused"
        resumed = client.post(f"/api/sessions/{event_id}/resume").json()
        assert resumed["event"]["status"] == "active" and len(resumed["event"]["segments"]) == 2

    def test_split_and_merge_endpoints(self, api):
        client, eng, store = api
        for _ in range(4):
            _simulate(client, LECTURE)
            client.post("/api/simulate/tick", json={"seconds": 20})
        event_id = eng.current_event_id()
        chunks = client.get(f"/api/sessions/{event_id}/chunks").json()["chunks"]
        split = client.post(f"/api/sessions/{event_id}/split", json={"at_chunk_id": chunks[2]["chunk_id"]}).json()
        assert split["success"] and split["old"]["status"] == "concluded" and split["new"]["status"] == "active"
        merged = client.post("/api/sessions/merge",
                             json={"session_ids": [split["old"]["session_id"], split["new"]["session_id"]]}).json()
        assert merged["success"] and merged["event"]["session_id"] == event_id
        assert client.post("/api/sessions/merge", json={"session_ids": [event_id]}).status_code == 409

    def test_event_scenarios_endpoint(self, api):
        client, _, _ = api
        data = client.get("/api/event-scenarios").json()
        assert data["count"] >= 5 and data["scenarios"][0]["utterances"]
