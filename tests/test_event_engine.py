"""Tests for the Deep Topic Event Engine — Phase A (time, GPS and cue based lifecycle).

Spec: docs/next_steps/deep_topic_event_engine/ (01 state machine, 03 synthesis, 07 test plan).
All tests run offline with an injected clock and a fake synthesizer.
"""

from datetime import datetime
from typing import List, Optional

import pytest

from src.core.schemas import BriefingReport, PlannedTask, UtteranceChunk
from src.core.storage.sqlite_store import SQLiteContextStore
from src.ingestion.event_engine import (
    ChunkSignal,
    EngineConfig,
    EventEngine,
    EventSnapshot,
    detect_cues,
    is_displaced,
    next_post_chunk_transition,
    next_pre_chunk_transition,
    next_tick_transition,
    to_iso,
)
from src.pipeline.graph import route_categories
from src.pipeline.nodes.persist import node_persist

T0 = datetime(2026, 10, 13, 10, 0, 0).timestamp()

CFG = EngineConfig(
    t_soft=300.0,
    t_hard=1800.0,
    t_hard_after_close_cue=300.0,
    t_hard_transit=120.0,
    t_checkpoint=1200.0,
    min_segment_words=20,
    location_shift_meters=400.0,
)

LECTURE = "Il limite per x che tende a zero di sin x su x vale uno e lo dimostriamo con il confronto"

ROOM = {"latitude": 45.0628, "longitude": 7.6624, "accuracy_meters": 30.0, "place_name": "Aula 7"}
# ~2.7 km away
STATION = {"latitude": 45.0870, "longitude": 7.6900, "accuracy_meters": 20.0, "place_name": "Stazione"}


class FakeSynthesizer:
    def __init__(self, fail_times: int = 0):
        self.calls: List[str] = []
        self.fail_times = fail_times

    def __call__(self, text: str, session_id: str) -> Optional[BriefingReport]:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("synthesis backend unavailable")
        self.calls.append(text)
        n = len(self.calls)
        return BriefingReport(
            topic_title=f"Topic {n}",
            context_type="academic_lecture",
            executive_summary=[f"Point {n}.a", f"Point {n}.b"],
            explanatory_synthesis=f"Synthesis {n}",
        )


@pytest.fixture
def store(tmp_path):
    return SQLiteContextStore(str(tmp_path / "events.db"))


@pytest.fixture
def synth():
    return FakeSynthesizer()


@pytest.fixture
def engine(store, synth):
    clock = {"now": T0}
    eng = EventEngine(store=store, config=CFG, clock=lambda: clock["now"], synthesizer=synth)
    eng._test_clock = clock  # type: ignore[attr-defined]
    return eng


def chunk(text: str, offset: float, cats=("deep_topic",), conv="conv-1", location=None) -> UtteranceChunk:
    return UtteranceChunk(
        conversation_uuid=conv,
        text=text,
        timestamp=to_iso(T0 + offset),
        categories=list(cats),
        location=location,
    )


def lecture_block(engine: EventEngine, start: float, n: int = 3, step: float = 40.0, **kw) -> float:
    """Feeds n on-topic lecture chunks; returns the offset of the last one."""
    offset = start
    for i in range(n):
        offset = start + i * step
        engine.record_chunk(chunk(LECTURE, offset, **kw))
    return offset


# ---------------------------------------------------------------------------
# Pure decision functions
# ---------------------------------------------------------------------------

class TestCueDetection:
    def test_pause_cues(self):
        assert detect_cues("Ok ragazzi, facciamo una pausa di dieci minuti") == (True, False)
        assert detect_cues("Let's take a short break") == (True, False)

    def test_closing_cues(self):
        assert detect_cues("Per oggi è tutto, ci vediamo giovedì")[1] is True
        assert detect_cues("That concludes today's lecture")[1] is True
        assert detect_cues("Concludiamo qui la lezione")[1] is True

    def test_lecture_content_is_not_a_cue(self):
        # Must not end a lecture: the legacy regex matched "conclude" anywhere
        assert detect_cues("From this we can conclude that the limit exists") == (False, False)
        assert detect_cues("Possiamo concludere che la funzione è continua") == (False, False)


class TestPureTransitions:
    def test_open_on_first_on_topic(self):
        t = next_pre_chunk_transition(EventSnapshot(), ChunkSignal(ts=T0, on_topic=True), CFG)
        assert t.rule == "R0" and t.to_status == "active"

    def test_no_open_on_off_topic(self):
        assert next_pre_chunk_transition(EventSnapshot(), ChunkSignal(ts=T0, on_topic=False), CFG) is None

    def test_late_soft_timeout_backdates_pause(self):
        snap = EventSnapshot(status="active", last_on_topic_at=T0)
        t = next_pre_chunk_transition(snap, ChunkSignal(ts=T0 + 400, on_topic=True), CFG)
        assert t.rule == "R1" and t.at == T0 + CFG.t_soft

    def test_resume_while_paused(self):
        snap = EventSnapshot(status="paused", paused_at=T0)
        t = next_pre_chunk_transition(snap, ChunkSignal(ts=T0 + 600, on_topic=True), CFG)
        assert t.rule == "R4" and t.to_status == "active"

    def test_hard_timeout_beats_resume(self):
        snap = EventSnapshot(status="paused", paused_at=T0)
        t = next_pre_chunk_transition(snap, ChunkSignal(ts=T0 + 1900, on_topic=True), CFG)
        assert t.rule == "R5" and t.to_status == "concluded" and t.at == T0 + CFG.t_hard

    def test_location_shift_concludes(self):
        snap = EventSnapshot(status="active", last_on_topic_at=T0)
        t = next_pre_chunk_transition(snap, ChunkSignal(ts=T0 + 10, on_topic=True, location_shift=True), CFG)
        assert t.rule == "R6"

    def test_post_chunk_cues_and_checkpoint(self):
        snap = EventSnapshot(status="active", last_on_topic_at=T0, segment_start=T0, segment_words=500)
        closing = next_post_chunk_transition(snap, ChunkSignal(ts=T0 + 10, on_topic=False, closing_cue=True), CFG)
        assert closing.rule == "R2" and closing.new_deadline == T0 + 10 + CFG.t_hard_after_close_cue
        checkpoint = next_post_chunk_transition(snap, ChunkSignal(ts=T0 + 1300, on_topic=True), CFG)
        assert checkpoint.rule == "R3"

    def test_tick_rules(self):
        active = EventSnapshot(status="active", last_on_topic_at=T0)
        assert next_tick_transition(active, T0 + 299, CFG) is None
        assert next_tick_transition(active, T0 + 300, CFG).rule == "R1"
        paused = EventSnapshot(status="paused", paused_at=T0, hard_close_deadline=T0 + 100)
        assert next_tick_transition(paused, T0 + 99, CFG) is None
        assert next_tick_transition(paused, T0 + 100, CFG).rule == "R5"

    def test_displacement_is_accuracy_aware(self):
        assert is_displaced(ROOM, STATION, 400.0) is True
        near = {"latitude": 45.0655, "longitude": 7.6624, "accuracy_meters": 30.0}  # ~300 m
        assert is_displaced(ROOM, near, 400.0) is False
        jittery = {"latitude": 45.0680, "longitude": 7.6624, "accuracy_meters": 300.0}  # ~580 m, poor fix
        assert is_displaced(ROOM, jittery, 400.0) is False


# ---------------------------------------------------------------------------
# Engine lifecycle (store + fake synthesizer + virtual clock)
# ---------------------------------------------------------------------------

class TestEventLifecycle:
    def test_open_on_first_deep_topic(self, engine, store):
        out = engine.record_chunk(chunk(LECTURE, 0))
        assert out.event_managed and out.event_status == "active"
        assert out.event_id != "conv-1"  # event identity is decoupled from Bee conversations
        ev = store.get_session_dossier(out.event_id)
        assert ev.status == "active" and len(ev.segments) == 1 and ev.segments[0].status == "open"
        assert ev.conversation_uuids == ["conv-1"]
        assert ev.transitions[0].rule == "R0"
        assert len(store.list_session_chunks(out.event_id)) == 1

    def test_off_topic_without_event_is_not_logged(self, engine, store):
        out = engine.record_chunk(chunk("Che bella giornata oggi", 0, cats=("noop",)))
        assert out.event_id is None and not out.event_managed
        assert store.list_session_dossiers() == []

    def test_soft_pause_on_tick(self, engine, store):
        lecture_block(engine, 0)
        assert engine.tick(now=T0 + 80 + 299) == []
        transitions = engine.tick(now=T0 + 80 + 300)
        assert [t.rule for t in transitions] == ["R1"]
        ev = engine.current_event()
        assert ev.status == "paused" and ev.segments[0].status == "closed"
        assert engine.pending_jobs() == 1

    def test_off_topic_chatter_does_not_reset_pause_timer(self, engine):
        lecture_block(engine, 0, n=1)
        engine.record_chunk(chunk("Prendi un caffè?", 100, cats=("noop",)))
        engine.record_chunk(chunk("Sì al bar del secondo piano", 200, cats=("social",)))
        assert [t.rule for t in engine.tick(now=T0 + 300)] == ["R1"]

    def test_break_chatter_is_logged_outside_segments(self, engine, store):
        lecture_block(engine, 0)
        engine.tick(now=T0 + 400)
        out = engine.record_chunk(chunk("Prendi un caffè?", 500, cats=("noop",)))
        assert out.event_status == "paused"
        all_chunks = store.list_session_chunks(out.event_id)
        in_segments = store.list_session_chunks(out.event_id, in_segments_only=True)
        assert len(all_chunks) == 4 and len(in_segments) == 3

    def test_resume_within_t_hard_opens_new_segment(self, engine):
        lecture_block(engine, 0)
        engine.tick(now=T0 + 400)
        out = engine.record_chunk(chunk(LECTURE, 1200))
        assert [t.rule for t in out.transitions] == ["R4"]
        ev = engine.current_event()
        assert ev.status == "active" and len(ev.segments) == 2 and ev.segments[1].status == "open"

    def test_late_chunk_after_silence_pauses_then_resumes(self, engine):
        lecture_block(engine, 0, n=1)
        out = engine.record_chunk(chunk(LECTURE, 1000))  # no tick ran in between
        assert [t.rule for t in out.transitions] == ["R1", "R4"]
        assert len(engine.current_event().segments) == 2

    def test_lecture_with_break_full_flow(self, engine, store, synth):
        lecture_block(engine, 0)                       # segment 1
        engine.tick(now=T0 + 400)                      # break -> R1
        engine.record_chunk(chunk("Prendi un caffè?", 500, cats=("noop",)))
        lecture_block(engine, 1500)                    # resume -> segment 2
        engine.tick(now=T0 + 1580 + 300)               # end of lecture -> R1
        event_id = engine.current_event_id()
        engine.tick(now=T0 + 1580 + 300 + 1800)        # -> R5 hard close
        assert engine.current_event() is None

        engine.run_pending_jobs_sync()
        ev = store.get_session_dossier(event_id)
        assert ev.status == "concluded" and ev.final_status == "ready"
        assert [s.status for s in ev.segments] == ["synthesized", "synthesized"]
        assert len(synth.calls) == 3                    # 2 segments + 1 consolidated final
        assert "Part 1: Topic 1" in synth.calls[2] and "Part 2: Topic 2" in synth.calls[2]
        assert ev.title == "Topic 1" and ev.domain == "lecture"
        kinds = sorted(b.kind for b in store.list_briefings_for_session(event_id))
        assert kinds == ["final", "segment", "segment"]
        assert ev.briefing_report is not None and ev.briefing_report.kind == "final"
        # Break chatter is not part of any synthesis input
        assert all("caffè" not in text for text in synth.calls)

    def test_single_segment_final_is_promoted(self, engine, store, synth):
        lecture_block(engine, 0)
        event_id = engine.current_event_id()
        engine.conclude(event_id)
        engine.run_pending_jobs_sync()
        ev = store.get_session_dossier(event_id)
        assert ev.final_status == "ready"
        assert len(synth.calls) == 1                    # no extra LLM call for the final
        assert ev.briefing_report.kind == "final" and ev.briefing_report.topic_title == "Topic 1"

    def test_short_event_skips_segment_but_gets_final(self, engine, store, synth):
        engine.record_chunk(chunk("Cos'è una derivata parziale?", 0))  # 4 words < min_segment_words
        event_id = engine.current_event_id()
        engine.tick(now=T0 + 300)
        engine.tick(now=T0 + 300 + 1800)
        engine.run_pending_jobs_sync()
        ev = store.get_session_dossier(event_id)
        assert ev.segments[0].status == "skipped"
        assert ev.final_status == "ready" and len(synth.calls) == 1
        assert "derivata parziale" in synth.calls[0]

    def test_closing_cue_pauses_and_shortens_hard_close(self, engine):
        lecture_block(engine, 0)
        out = engine.record_chunk(chunk("Per oggi è tutto, ci vediamo giovedì", 100, cats=("noop",)))
        assert [t.reason for t in out.transitions] == ["closing_cue"]
        assert engine.current_event().status == "paused"
        assert engine.tick(now=T0 + 100 + 299) == []
        assert [t.rule for t in engine.tick(now=T0 + 100 + 300)] == ["R5"]

    def test_pause_cue(self, engine):
        lecture_block(engine, 0)
        out = engine.record_chunk(chunk("Facciamo una pausa di dieci minuti", 100, cats=("noop",)))
        assert [t.reason for t in out.transitions] == ["pause_cue"]
        assert engine.current_event().hard_close_deadline is None

    def test_checkpoint_on_long_segment(self, engine, store):
        offset = lecture_block(engine, 0, n=31, step=40.0)  # 1200 s of continuous lecture
        ev = engine.current_event()
        assert ev.status == "active" and len(ev.segments) == 2
        assert ev.segments[0].kind == "checkpoint" and ev.segments[0].status == "closed"
        assert offset == 1200.0

    def test_location_shift_needs_two_distinct_fixes(self, engine):
        lecture_block(engine, 0, location=ROOM)
        out1 = engine.record_chunk(chunk(LECTURE, 200, location=STATION))
        assert out1.event_status == "active"  # single displaced fix: could be GPS noise
        first_id = out1.event_id
        # The same fix repeated on the next utterance is not a second confirmation
        out_repeat = engine.record_chunk(chunk(LECTURE, 220, location=STATION))
        assert out_repeat.transitions == [] and out_repeat.event_id == first_id
        station_2 = dict(STATION, latitude=STATION["latitude"] + 0.0002)
        out2 = engine.record_chunk(chunk(LECTURE, 240, location=station_2))
        assert [t.rule for t in out2.transitions] == ["R6", "R0"]
        assert out2.event_id != first_id  # on-topic speech at the new place opens a new event

    def test_gps_glitch_followed_by_good_fix_resets(self, engine):
        lecture_block(engine, 0, location=ROOM)
        engine.record_chunk(chunk(LECTURE, 200, location=STATION))       # glitch
        engine.record_chunk(chunk(LECTURE, 240, location=dict(ROOM, latitude=ROOM["latitude"] + 0.0001)))
        out = engine.record_chunk(chunk(LECTURE, 280, location=dict(STATION, latitude=STATION["latitude"] + 0.0003)))
        assert out.transitions == []  # strikes were reset by the good fix in between

    def test_transit_fix_concludes_immediately(self, engine):
        lecture_block(engine, 0, location=ROOM)
        transit = dict(STATION, semantic_zone="transit")
        assert [t.rule for t in engine.on_location(transit, now=T0 + 200)] == ["R6"]
        assert engine.current_event() is None

    def test_transit_while_paused_brings_hard_close_forward(self, engine):
        lecture_block(engine, 0, location=ROOM)
        engine.tick(now=T0 + 400)
        nearby_transit = dict(ROOM, semantic_zone="transit")
        assert [t.reason for t in engine.on_location(nearby_transit, now=T0 + 500)] == ["transit_deadline"]
        assert [t.rule for t in engine.tick(now=T0 + 500 + 120)] == ["R5"]

    def test_single_open_event_invariant(self, engine, store):
        lecture_block(engine, 0)
        first = engine.current_event_id()
        engine.conclude(first)
        out = engine.record_chunk(chunk(LECTURE, 100))
        assert out.event_id != first
        open_events = [d for d in store.list_session_dossiers() if d.status in ("active", "paused")]
        assert len(open_events) == 1

    def test_spans_multiple_conversation_uuids(self, engine):
        lecture_block(engine, 0, conv="bee-conv-A")
        engine.tick(now=T0 + 400)
        engine.record_chunk(chunk(LECTURE, 1300, conv="bee-conv-B"))  # Bee split the lecture
        ev = engine.current_event()
        assert ev.conversation_uuids == ["bee-conv-A", "bee-conv-B"] and len(ev.segments) == 2

    def test_manual_conclude_of_unknown_session(self, engine):
        assert engine.conclude("does-not-exist") is None

    def test_job_retry_then_success(self, store):
        synth = FakeSynthesizer(fail_times=1)
        eng = EventEngine(store=store, config=CFG, clock=lambda: T0, synthesizer=synth)
        lecture_block(eng, 0)
        event_id = eng.current_event_id()
        eng.conclude(event_id, now=T0 + 100)
        eng.run_pending_jobs_sync()
        ev = store.get_session_dossier(event_id)
        assert ev.final_status == "ready" and ev.segments[0].status == "synthesized"

    def test_job_failure_after_max_attempts(self, store):
        synth = FakeSynthesizer(fail_times=99)
        eng = EventEngine(store=store, config=CFG, clock=lambda: T0, synthesizer=synth)
        lecture_block(eng, 0)
        event_id = eng.current_event_id()
        eng.tick(now=T0 + 400)
        eng.run_pending_jobs_sync()
        assert store.get_session_dossier(event_id).segments[0].status == "failed"

    def test_rehydration_reenqueues_unsynthesized_work(self, store, synth):
        eng1 = EventEngine(store=store, config=CFG, clock=lambda: T0, synthesizer=synth)
        lecture_block(eng1, 0)
        eng1.tick(now=T0 + 400)  # segment closed, job queued but never run (simulated crash)
        event_id = eng1.current_event_id()

        eng2 = EventEngine(store=store, config=CFG, clock=lambda: T0 + 500, synthesizer=synth)
        assert eng2.current_event_id() == event_id
        assert eng2.pending_jobs() == 1
        eng2.run_pending_jobs_sync()
        assert store.get_session_dossier(event_id).segments[0].status == "synthesized"

    def test_listeners_receive_lifecycle_events(self, engine):
        seen = []
        engine.add_listener(lambda event_type, payload: seen.append(event_type))
        lecture_block(engine, 0)
        engine.tick(now=T0 + 400)
        engine.run_pending_jobs_sync()
        assert seen[0] == "event_opened"
        assert "event_paused" in seen and "segment_synthesized" in seen


# ---------------------------------------------------------------------------
# Storage & pipeline integration
# ---------------------------------------------------------------------------

class TestStorageAndPipelineIntegration:
    def test_concluded_session_rejects_legacy_append(self, store):
        store.append_chunk_to_session("legacy-1", "first chunk")
        store.conclude_session_dossier("legacy-1")
        dossier = store.append_chunk_to_session("legacy-1", "late chunk")
        assert dossier.status == "concluded" and dossier.transcript_chunks == ["first chunk"]

    def test_legacy_finalizing_status_reads_as_paused(self, store):
        store.append_chunk_to_session("legacy-2", "chunk")
        with store._get_connection() as conn:
            conn.execute("UPDATE session_dossiers SET status = 'finalizing' WHERE session_id = 'legacy-2'")
            conn.commit()
        assert store.get_session_dossier("legacy-2").status == "paused"

    def test_briefing_kind_filters(self, store):
        store.save_topic_briefing(BriefingReport(topic_title="A", context_type="bug"))
        store.save_topic_briefing(BriefingReport(topic_title="B", context_type="bug", kind="final", session_id="ev-1"))
        assert [b.topic_title for b in store.list_topic_briefings(kind="final")] == ["B"]
        assert [b.topic_title for b in store.list_topic_briefings(session_id="ev-1")] == ["B"]
        assert len(store.list_topic_briefings()) == 2

    def test_event_managed_deep_topic_skips_research(self):
        assert route_categories({"categories": ["deep_topic"], "event_managed": True}) == ["__end__"]
        assert route_categories({"categories": ["deep_topic"]}) == ["topic_research"]
        assert route_categories({"categories": ["deep_topic", "action"], "event_managed": True}) == ["extract_action"]

    def test_persist_no_longer_concludes_sessions(self, monkeypatch, store):
        monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: store)
        store.append_chunk_to_session("sess-x", "talking about raft")
        node_persist({
            "session_id": "sess-x",
            "briefing_report": BriefingReport(topic_title="Raft", context_type="tech_stack"),
        })
        assert store.get_session_dossier("sess-x").status == "active"
        saved = store.list_topic_briefings(session_id="sess-x")
        assert len(saved) == 1 and saved[0].kind == "standalone"

    def test_micro_events_link_to_event(self, monkeypatch, engine, store):
        monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: store)
        out = engine.record_chunk(chunk(LECTURE, 0))
        node_persist({
            "session_id": out.event_id,
            "scheduled_task": PlannedTask(title="Send notes to Marco", domain="work_task", origin="ambient_voice"),
        })
        ev = store.get_session_dossier(out.event_id)
        assert [e.event_type for e in ev.linked_micro_events] == ["task_scheduled"]
        assert ev.segments and ev.status == "active"  # linking did not clobber engine fields
