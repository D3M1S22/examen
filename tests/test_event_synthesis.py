"""Tests for the Deep Topic Event Engine — Phase B (progressive & consolidated synthesis).

Spec: docs/next_steps/deep_topic_event_engine/03_synthesis_scheduling.md
Covers: search cache, query ledger, event outline, transcript condensation, segment/final
synthesis (map-reduce, research reuse, micro-events section) and the engine wiring.
Runs offline: heuristic models (mock_ai) and a fake search provider.
"""

from datetime import datetime, timedelta
from typing import List

import pytest

from src.core.config import settings
from src.core.schemas import BriefingReport, MicroEventRef, UtteranceChunk
from src.ingestion.event_engine import EngineConfig, EventEngine, to_iso
from src.pipeline.nodes.topic_research import (
    EventOutline,
    PipelineEventSynthesizer,
    append_micro_events_section,
    condense_transcript,
    extract_topics,
    research,
)
from src.pipeline.tools.web_search import SearchCache, SearchResultItem, cache_key, execute_search_batch
from tests.store_backend import new_store, sqlite_only

T0 = datetime(2026, 10, 13, 10, 0, 0).timestamp()
LECTURE = "Raft consensus elects a leader with randomized election timeouts and replicates the log to followers"


@pytest.fixture
def store(tmp_path):
    return new_store(str(tmp_path / "synthesis.db"))


@pytest.fixture
def network(monkeypatch):
    """Fake search provider counting real (network) searches."""
    calls: List[str] = []

    def _fake_search(query, count=3):
        calls.append(query)
        slug = "-".join(query.lower().split())
        return [SearchResultItem(title=f"{query} guide", url=f"https://docs.example.com/{slug}",
                                 snippet=f"Reference documentation about {query}.")], "fake"

    monkeypatch.setattr("src.pipeline.tools.web_search.search_with_fallback", _fake_search)
    monkeypatch.setattr(settings, "mock_ai", True)
    return calls


# ---------------------------------------------------------------------------
# Search cache & ledger
# ---------------------------------------------------------------------------

class TestSearchCache:
    def test_cache_hit_avoids_network(self, store, network):
        cache = SearchCache(store, ttl_seconds=3600)
        first = execute_search_batch(["Raft leader election"], cache=cache)
        second = execute_search_batch(["Raft leader election"], cache=cache)
        assert network == ["Raft leader election"]
        assert second.source_urls == first.source_urls
        assert second.evaluations[0].provider_used.endswith("(cached)")

    def test_empty_results_are_not_cached(self, store, monkeypatch):
        monkeypatch.setattr("src.pipeline.tools.web_search.search_with_fallback", lambda q, count=3: ([], "none"))
        cache = SearchCache(store, ttl_seconds=3600)
        execute_search_batch(["obscure query"], cache=cache)
        assert store.get_cached_search(cache_key("obscure query"), 3600) is None

    @sqlite_only
    def test_ttl_expiry(self, store):
        store.put_cached_search("raft", "fake", [{"title": "t", "url": "https://x.org", "snippet": "s"}])
        assert store.get_cached_search("raft", 3600) is not None
        old = (datetime.now() - timedelta(hours=2)).isoformat()
        with store._get_connection() as conn:
            conn.execute("UPDATE web_search_cache SET fetched_at = ?", (old,))
            conn.commit()
        assert store.get_cached_search("raft", 3600) is None

    def test_cache_only_queries_never_hit_network(self, store, network):
        batch = execute_search_batch(["Paxos basics"], cache=SearchCache(store), cache_only={cache_key("Paxos basics")})
        assert network == [] and batch.evaluations == []

    def test_cache_key_normalizes(self):
        assert cache_key("  What is   Raft Consensus? ") == cache_key("raft consensus")


class TestResearchStep:
    def test_already_researched_queries_are_served_from_cache(self, store, network):
        cache = SearchCache(store)
        topic = extract_topics(LECTURE)
        research(topic, LECTURE, cache=cache)
        calls_after_first = len(network)
        outline = EventOutline(researched_queries=[cache_key(q) for q in topic.search_queries])
        batch = research(topic, LECTURE, outline=outline, cache=cache)
        assert len(network) == calls_after_first          # no new network searches
        assert batch.source_urls                           # but the context is still provided

    def test_allow_empty_runs_no_search(self, network):
        topic = extract_topics(LECTURE)
        topic.search_queries = []
        batch = research(topic, LECTURE, allow_empty=True)
        assert network == [] and batch.source_urls == []


# ---------------------------------------------------------------------------
# Outline, condensation, micro-events section
# ---------------------------------------------------------------------------

class TestSynthesisHelpers:
    def test_outline_prompt(self):
        outline = EventOutline(
            event_title="Distributed Systems", context_type="academic_lecture", part_index=2,
            previous_parts=["Raft basics"], researched_queries=["raft leader election"],
        )
        text = outline.as_prompt()
        assert "part 2 of an ongoing academic lecture titled 'Distributed Systems'" in text
        assert "Raft basics" in text and "do NOT repeat" in text and "raft leader election" in text

    def test_short_transcript_is_unchanged(self):
        assert condense_transcript("short text", max_words=100) == "short text"

    def test_long_transcript_is_condensed(self, network):
        words = [f"w{i}" for i in range(4000)]
        out = condense_transcript(" ".join(words), max_words=3000, block_words=1500)
        assert out.count("[Notes block") == 2
        assert "[Latest block, verbatim]" in out and "w3999" in out
        assert len(out.split()) < 3000

    def test_micro_events_section(self):
        report = BriefingReport(topic_title="X", context_type="bug", deep_dive_markdown="# X")
        append_micro_events_section(report, [
            MicroEventRef(event_type="action", record_id="a1", headline="Pushed the migration"),
            MicroEventRef(event_type="social_contact", record_id="c1", headline="Met Sarah Lin"),
        ])
        assert "## During this event" in report.deep_dive_markdown
        assert "### Verified actions" in report.deep_dive_markdown and "- Met Sarah Lin" in report.deep_dive_markdown


# ---------------------------------------------------------------------------
# PipelineEventSynthesizer (heuristic models, fake network)
# ---------------------------------------------------------------------------

class TestPipelineEventSynthesizer:
    def test_segment_returns_kind_and_ledger_entries(self, store, network):
        synth = PipelineEventSynthesizer(store_getter=lambda: store)
        outcome = synth.segment(LECTURE, "ev-1", outline=EventOutline(part_index=1), kind="checkpoint")
        assert outcome.briefing.kind == "checkpoint"
        assert outcome.research and all(e["sources"] for e in outcome.research)
        assert outcome.briefing.web_sources

    def test_final_merges_parts_and_reuses_research(self, store, network):
        synth = PipelineEventSynthesizer(store_getter=lambda: store)
        part1 = synth.segment(LECTURE, "ev-1", outline=EventOutline(part_index=1))
        ledger = [e["query"] for e in part1.research]
        searches_before = len(network)

        part2 = BriefingReport(topic_title="Log replication", context_type="academic_lecture",
                               web_sources=["https://raft.github.io"])
        final = synth.final(
            [part1.briefing, part2], "", "ev-1",
            outline=EventOutline(researched_queries=ledger),
            micro_events=[MicroEventRef(event_type="task_scheduled", record_id="t1", headline="Send notes to Marco")],
        )
        report = final.briefing
        assert report.kind == "final"
        assert "https://raft.github.io" in report.web_sources
        assert set(part1.briefing.web_sources) <= set(report.web_sources)
        assert "Send notes to Marco" in report.deep_dive_markdown
        # Heuristic gap queries equal the already-researched ones -> served from cache, no new network
        assert len(network) == searches_before

    def test_final_without_parts_uses_raw_text(self, store, network):
        synth = PipelineEventSynthesizer(store_getter=lambda: store)
        outcome = synth.final([], "Cos'è una derivata parziale in analisi due", "ev-2")
        assert outcome.briefing.kind == "final" and outcome.research


# ---------------------------------------------------------------------------
# Engine wiring: outline, ledger persistence, micro-events in the final
# ---------------------------------------------------------------------------

class RecordingSynthesizer:
    def __init__(self):
        self.segment_outlines = []
        self.final_args = None
        self.n = 0

    def _briefing(self, title):
        self.n += 1
        return BriefingReport(topic_title=title, context_type="academic_lecture",
                              executive_summary=[f"{title} point"], web_sources=[f"https://src/{self.n}"])

    def segment(self, text, session_id, outline=None, kind="segment"):
        from src.pipeline.nodes.topic_research import SynthesisOutcome
        self.segment_outlines.append(outline)
        return SynthesisOutcome(
            briefing=self._briefing(f"Part topic {outline.part_index}"),
            research=[{"query": f"q{outline.part_index}", "sources": [f"https://src/{self.n + 1}"]}],
        )

    def final(self, parts, extra_text, session_id, outline=None, micro_events=None):
        self.final_args = {"parts": parts, "extra_text": extra_text, "outline": outline, "micro_events": micro_events}
        return self._briefing("Whole lecture")


def _chunk(text, offset, cats=("deep_topic",)):
    return UtteranceChunk(conversation_uuid="c", text=text, timestamp=to_iso(T0 + offset), categories=list(cats))


class TestEngineWiring:
    @pytest.fixture
    def engine(self, store):
        synth = RecordingSynthesizer()
        eng = EventEngine(store=store, config=EngineConfig(min_segment_words=10), clock=lambda: T0, synthesizer=synth)
        eng._synth = synth  # type: ignore[attr-defined]
        return eng

    def _two_part_lecture(self, engine):
        engine.record_chunk(_chunk(LECTURE, 0))
        engine.tick(now=T0 + 400)                       # pause -> segment 1 closed
        engine.run_pending_jobs_sync()
        engine.record_chunk(_chunk(LECTURE, 1200))      # resume -> segment 2
        engine.tick(now=T0 + 1600)                      # pause -> segment 2 closed
        engine.run_pending_jobs_sync()

    def test_second_segment_receives_event_context(self, engine):
        self._two_part_lecture(engine)
        first, second = engine._synth.segment_outlines
        assert first.part_index == 1 and first.previous_parts == [] and first.researched_queries == []
        assert second.part_index == 2
        assert second.previous_parts == ["Part topic 1"]
        assert second.researched_queries == ["q1"]
        assert second.event_title == "Part topic 1" and second.context_type == "academic_lecture"

    def test_ledger_is_persisted(self, engine, store):
        self._two_part_lecture(engine)
        ev = store.get_session_dossier(engine.current_event_id())
        assert [(e["query"], e["kind"]) for e in ev.research_ledger] == [("q1", "segment"), ("q2", "segment")]
        assert ev.research_ledger[0]["segment_id"] == ev.segments[0].segment_id

    def test_final_gets_parts_ledger_and_micro_events(self, engine, store):
        self._two_part_lecture(engine)
        event_id = engine.current_event_id()
        store.link_micro_event_to_session(
            event_id, MicroEventRef(event_type="action", record_id="a1", headline="Pushed the migration")
        )
        engine.conclude(event_id)
        engine.run_pending_jobs_sync()
        args = engine._synth.final_args
        assert [p.topic_title for p in args["parts"]] == ["Part topic 1", "Part topic 2"]
        assert args["outline"].researched_queries == ["q1", "q2"]
        assert [m.headline for m in args["micro_events"]] == ["Pushed the migration"]
        ev = store.get_session_dossier(event_id)
        assert ev.final_status == "ready" and ev.briefing_report.topic_title == "Whole lecture"

    def test_single_segment_promotion_adds_micro_events(self, engine, store):
        engine.record_chunk(_chunk(LECTURE, 0))
        event_id = engine.current_event_id()
        store.link_micro_event_to_session(
            event_id, MicroEventRef(event_type="social_contact", record_id="c1", headline="Met Sarah Lin")
        )
        engine.conclude(event_id)
        engine.run_pending_jobs_sync()
        ev = store.get_session_dossier(event_id)
        assert engine._synth.final_args is None                      # no consolidated LLM call
        assert ev.briefing_report.kind == "final"
        assert "Met Sarah Lin" in ev.briefing_report.deep_dive_markdown
        segment_briefing = store.get_topic_briefing(ev.segments[0].briefing_id)
        assert "Met Sarah Lin" not in (segment_briefing.deep_dive_markdown or "")  # segment copy untouched


def test_failed_queries_are_not_recorded_in_ledger(monkeypatch):
    from src.pipeline.nodes.topic_research import research_entries

    monkeypatch.setattr("src.pipeline.tools.web_search.search_with_fallback", lambda q, count=3: ([], "none"))
    batch = execute_search_batch(["raft leader election process"])
    assert research_entries(batch) == []
