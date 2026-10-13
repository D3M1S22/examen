"""Tests for the Deep Topic Event Engine — Phase C (topic continuity).

Spec: docs/next_steps/deep_topic_event_engine/02_topic_continuity_detection.md
Offline: heuristic backend or a deterministic fake embedder; no Bedrock calls.
"""

from datetime import datetime
from typing import List

import pytest

from src.core.schemas import BriefingReport, UtteranceChunk
from src.core.storage.sqlite_store import SQLiteContextStore
from src.ingestion.event_engine import EngineConfig, EventEngine, detect_cue_flags, to_iso
from src.ingestion.scenario_replay import load_event_scenarios, replay_scenario
from src.ingestion.topic_continuity import (
    ContinuityConfig,
    SimilarityScore,
    TopicSimilarity,
    content_terms,
)

T0 = datetime(2026, 10, 13, 10, 0, 0).timestamp()

CALCULUS = [
    "Il limite di una funzione in un punto si definisce con epsilon e delta per ogni intorno del punto",
    "Il teorema del confronto permette di calcolare il limite di una funzione compresa tra due funzioni",
    "La continuità di una funzione in un punto richiede che il limite coincida con il valore della funzione",
    "Il teorema di Weierstrass garantisce massimo e minimo per una funzione continua su un intervallo chiuso",
    "Il teorema degli zeri afferma che una funzione continua che cambia segno si annulla in un punto",
    "La derivata di una funzione è il limite del rapporto incrementale e misura la pendenza della tangente",
]
CHEMISTRY = [
    "Gli alcani sono idrocarburi saturi con atomi di carbonio ibridati sp3 e geometria tetraedrica",
    "La nomenclatura IUPAC degli alcani individua la catena carboniosa più lunga e numera gli atomi di carbonio",
    "Gli alcheni contengono un doppio legame carbonio carbonio e danno addizione elettrofila",
    "La regola di Markovnikov descrive l'addizione di acido bromidrico al doppio legame degli alcheni",
    "La stabilità dei carbocationi cresce da primario a secondario a terziario negli alcheni",
    "I gruppi funzionali come alcoli chetoni ed esteri determinano la reattività dei composti organici",
]
CHATTER = ["Prendi un caffè al bar?", "Sì andiamo che c'è poca fila", "Hai visto la partita ieri sera?"]

HEURISTIC = ContinuityConfig(backend="heuristic", window_min_chunks=3, window_min_words=40, llm_judge=False)
ENGINE_CFG = EngineConfig(t_soft=300, t_hard=1800, min_segment_words=10)


class StaticSynth:
    def segment(self, text, session_id, outline=None, kind="segment"):
        return BriefingReport(topic_title="Segment", context_type="academic_lecture")

    def final(self, parts, extra_text, session_id, outline=None, micro_events=None):
        return BriefingReport(topic_title="Final", context_type="academic_lecture")


@pytest.fixture
def store(tmp_path):
    return SQLiteContextStore(str(tmp_path / "continuity.db"))


def make_engine(store, continuity=None):
    return EventEngine(store=store, config=ENGINE_CFG, clock=lambda: T0, synthesizer=StaticSynth(),
                       continuity=continuity or TopicSimilarity(HEURISTIC))


def say(engine, text, offset, cats=("deep_topic",), conv="bee-1"):
    return engine.record_chunk(UtteranceChunk(
        conversation_uuid=conv, text=text, timestamp=to_iso(T0 + offset), categories=list(cats)
    ))


def feed(engine, sentences, start, step=30, cats=("deep_topic",), conv="bee-1"):
    out = []
    for i, text in enumerate(sentences):
        out.append(say(engine, text, start + i * step, cats=cats, conv=conv))
    return out


# ---------------------------------------------------------------------------
# Similarity primitives
# ---------------------------------------------------------------------------

class TestSimilarityPrimitives:
    def test_content_terms_strip_stopwords_and_stem(self):
        terms = content_terms("Quindi la derivata e le derivate della funzione")
        assert "quindi" not in terms and "della" not in terms
        assert terms.count("deriva") == 2 and "funzio" in terms

    def test_verdict_and_biases(self):
        score = SimilarityScore(0.40, same=0.42, different=0.37, backend="embedding")
        assert score.verdict() == "undecided"
        assert score.verdict(resume_bias=0.05) == "same"
        score_low = SimilarityScore(0.39, same=0.42, different=0.37, backend="embedding")
        assert score_low.verdict(split_bias=0.03) == "different"

    def test_heuristic_profile_scores_same_vs_different(self):
        sim = TopicSimilarity(HEURISTIC)
        profile = None
        for text in CALCULUS[:3]:
            profile = sim.update(profile, text)
        same, _ = sim.score(" ".join(CALCULUS[3:]), profile)
        diff, _ = sim.score(" ".join(CHEMISTRY), profile)
        assert same.value > diff.value
        assert diff.verdict() == "different"
        assert sim.is_mature(profile)

    def test_embedding_backend_with_fake_embedder(self):
        def fake_embed(text: str) -> List[float]:
            t = text.lower()
            return [float("funzion" in t or "limite" in t), float("alcan" in t or "carbonio" in t), 0.1]

        sim = TopicSimilarity(ContinuityConfig(backend="embedding"), embedder=fake_embed)
        profile = sim.update(None, CALCULUS[0])
        same, vec = sim.score(CALCULUS[1], profile)
        diff, _ = sim.score(CHEMISTRY[0], profile)
        assert same.backend == "embedding" and vec is not None
        assert same.value > 0.9 and diff.value < 0.2

    def test_embedding_failure_falls_back_to_heuristic(self):
        def broken(text):
            raise RuntimeError("throttled")

        sim = TopicSimilarity(ContinuityConfig(backend="embedding"), embedder=broken)
        profile = sim.update(None, CALCULUS[0])
        score, vec = sim.score(CALCULUS[1], profile)
        assert vec is None and score.backend == "heuristic"

    def test_blend_title_adds_anchor(self):
        sim = TopicSimilarity(HEURISTIC)
        profile = sim.update(None, CALCULUS[0])
        sim.blend_title(profile, "Limiti e continuità")
        sim.blend_title(profile, "Limiti e continuità")
        assert profile.segment_titles == ["Limiti e continuità"]
        assert "contin" in profile.keywords

    def test_resume_and_opening_cues(self):
        assert detect_cue_flags("Riprendiamo da dove eravamo rimasti").resume
        assert detect_cue_flags("Grazie, il prossimo intervento è sul GDPR").opening
        assert not detect_cue_flags("La derivata seconda descrive la concavità").opening


# ---------------------------------------------------------------------------
# Engine behaviour with continuity
# ---------------------------------------------------------------------------

class TestOnTopicWindows:
    def test_noop_lecture_sentences_keep_event_alive(self, store):
        eng = make_engine(store)
        feed(eng, CALCULUS[:3], 0)                                   # seeds the profile
        # The gatekeeper labels the next lecture sentences noop: windows still match the profile
        feed(eng, CALCULUS[3:] + CALCULUS[:3], 120, step=50, cats=("noop",))
        last_offset = 120 + 5 * 50
        assert eng.tick(now=T0 + last_offset + 299) == []
        assert eng.current_event().status == "active"
        # Phase A would have paused 300 s after the last deep_topic chunk (t=60)
        assert eng.current_event().last_on_topic_at >= to_iso(T0 + 120)

    def test_chatter_windows_do_not_keep_event_alive(self, store):
        eng = make_engine(store)
        feed(eng, CALCULUS[:3], 0)
        feed(eng, CHATTER * 2, 100, step=20, cats=("noop",))
        assert [t.rule for t in eng.tick(now=T0 + 60 + 300)] == ["R1"]


class TestPendingWindow:
    def _lecture_then_pause(self, eng):
        feed(eng, CALCULUS[:3], 0)
        eng.tick(now=T0 + 400)
        assert eng.current_event().status == "paused"
        return eng.current_event_id()

    def test_same_topic_resumes_with_pending_chunks(self, store):
        eng = make_engine(store)
        event_id = self._lecture_then_pause(eng)
        outs = feed(eng, CALCULUS[3:], 900)
        assert outs[0].transitions == []                    # first chunk only starts the pending window
        rules = [t.rule for o in outs for t in o.transitions]
        assert rules == ["R4"]
        ev = eng.current_event()
        assert ev.session_id == event_id and ev.status == "active" and len(ev.segments) == 2
        seg2 = ev.segments[1]
        assert len(store.list_session_chunks(event_id, segment_id=seg2.segment_id)) == 3
        assert seg2.start_time == to_iso(T0 + 900)          # segment starts at the first pending chunk
        assert ev.pending_chunk_ids == []

    def test_different_topic_after_pause_opens_new_event(self, store):
        eng = make_engine(store)
        first_id = self._lecture_then_pause(eng)
        outs = feed(eng, CHEMISTRY[:3], 900)
        rules = [(t.rule, t.reason) for o in outs for t in o.transitions]
        assert rules == [("R7", "new_topic_after_pause"), ("R0", "open_from_pending")]
        new_id = eng.current_event_id()
        assert new_id != first_id
        assert len(store.list_session_chunks(new_id)) == 3              # pending chunks moved
        assert store.get_session_dossier(first_id).status == "concluded"

    def test_undecided_window_extends_then_defaults_to_resume(self, store):
        eng = make_engine(store)
        self._lecture_then_pause(eng)
        eng.continuity.score = lambda text, profile: (SimilarityScore(0.15, 0.20, 0.10, "heuristic"), None)
        outs = feed(eng, CALCULUS[3:] * 4, 900, step=5)
        rules = [t.rule for o in outs for t in o.transitions]
        assert rules == ["R4"]                                  # judge unavailable -> resume
        assert len(eng.current_event().segments) == 2

    def test_judge_can_split_an_undecided_window(self, store):
        eng = make_engine(store)
        self._lecture_then_pause(eng)
        eng.continuity.score = lambda text, profile: (SimilarityScore(0.15, 0.20, 0.10, "heuristic"), None)
        eng.continuity.judge = lambda *a, **k: "different"
        outs = feed(eng, CHEMISTRY * 2, 900, step=5)
        assert [t.rule for o in outs for t in o.transitions][:2] == ["R7", "R0"]

    def test_pending_window_decides_on_age_via_tick(self, store):
        eng = make_engine(store)
        self._lecture_then_pause(eng)
        say(eng, CALCULUS[4], 900)                              # a single chunk: window never "ready"
        assert [t.rule for t in eng.tick(now=T0 + 900 + 90)] == ["R4"]

    # Last on-topic chunk at t=60 -> paused at 360 (T_soft) -> hard-close deadline at 360 + 1800 = 2160
    def test_on_topic_speech_after_hard_deadline_opens_new_event(self, store):
        eng = make_engine(store)
        first_id = self._lecture_then_pause(eng)
        out = say(eng, CHEMISTRY[0], 2200)
        assert [(t.rule, t.reason) for t in out.transitions] == [("R5", "hard_timeout"), ("R0", "open")]
        assert eng.current_event_id() != first_id

    def test_hard_timeout_with_pending_on_tick(self, store):
        eng = make_engine(store)
        first_id = self._lecture_then_pause(eng)
        say(eng, CALCULUS[4], 2100)                             # pending, decision not ready yet
        rules = [(t.rule, t.reason) for t in eng.tick(now=T0 + 2160)]
        assert rules == [("R5", "hard_timeout"), ("R0", "open_from_pending")]
        new_id = eng.current_event_id()
        assert new_id != first_id and len(store.list_session_chunks(new_id)) == 1

    def test_pending_chunks_survive_restart(self, store):
        eng = make_engine(store)
        event_id = self._lecture_then_pause(eng)
        say(eng, CALCULUS[3], 900)
        eng2 = make_engine(store)
        assert eng2.current_event_id() == event_id
        assert [c.text for c in eng2._pending] == [CALCULUS[3]]
        feed(eng2, CALCULUS[4:], 930)
        assert eng2.current_event().status == "active"


class TestDrift:
    def test_sustained_new_subject_splits_without_pause(self, store):
        eng = make_engine(store)
        feed(eng, CALCULUS * 2, 0, step=20)
        outs = feed(eng, CHEMISTRY * 2, 240, step=20)
        rules = [(t.rule, t.reason) for o in outs for t in o.transitions]
        assert ("R9", "topic_drift") in rules and ("R0", "open_from_drift") in rules
        events = [d for d in store.list_session_dossiers() if d.segments]
        assert len(events) == 2
        new_event = eng.current_event()
        texts = [c.text for c in store.list_session_chunks(new_event.session_id)]
        assert all(t in CHEMISTRY for t in texts)              # no calculus chunk moved
        assert texts[0] == CHEMISTRY[0]                        # split exactly at the subject change

    def test_immature_profile_never_drifts(self, store):
        eng = make_engine(store)
        say(eng, CALCULUS[0], 0)
        outs = feed(eng, CHEMISTRY * 2, 20, step=20)
        assert not any(t.rule == "R9" for o in outs for t in o.transitions)

    def test_natural_progression_does_not_split(self, store):
        eng = make_engine(store)
        outs = feed(eng, CALCULUS * 3, 0, step=20)
        assert not any(t.rule == "R9" for o in outs for t in o.transitions)


class TestBeeConversationAndHints:
    def test_new_bee_conversation_during_pause_biases_split(self, store):
        eng = make_engine(store)
        feed(eng, CALCULUS[:3], 0)
        eng.tick(now=T0 + 400)
        eng.on_bee_conversation("new-conversation", {"conversation": {"id": 7, "uuid": "bee-2"}})
        assert eng._bee_boundary_since_pause is True

    def test_update_conversation_title_enriches_profile_of_owning_event(self, store):
        eng = make_engine(store)
        feed(eng, CALCULUS[:3], 0, conv="bee-1")
        eng.on_bee_conversation("new-conversation", {"conversation": {"id": 1, "uuid": "bee-1"}})
        eng.on_bee_conversation("update-conversation", {"conversation": {"id": 1, "title": "Lezione di Analisi"}})
        eng.on_bee_conversation("update-conversation", {"conversation": {"id": 99, "title": "Unrelated chat"}})
        profile = store.get_session_dossier(eng.current_event_id()).topic_profile
        assert profile.bee_titles == ["Lezione di Analisi"]

    def test_active_event_hint(self, store):
        eng = make_engine(store)
        assert eng.active_event_hint() == ""
        feed(eng, CALCULUS[:3], 0)
        hint = eng.active_event_hint()
        assert hint.startswith("ONGOING EVENT") and "deep_topic" in hint and "limite" in hint


# ---------------------------------------------------------------------------
# Scenario replays (heuristic backend, offline)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", load_event_scenarios(), ids=lambda s: s["id"])
def test_scenario_replay_heuristic(scenario, tmp_path):
    store = SQLiteContextStore(str(tmp_path / f"{scenario['id']}.db"))
    engine = EventEngine(
        store=store, config=EngineConfig(), synthesizer=StaticSynth(),
        continuity=TopicSimilarity(ContinuityConfig(backend="heuristic", llm_judge=False)),
    )
    result = replay_scenario(engine, scenario)
    assert result.ok, result.errors
