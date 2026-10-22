"""Unit and integration tests for the specialized pipeline nodes in src/pipeline/nodes/."""

import os
import tempfile
import pytest

from src.core.config import settings
from src.core.schemas import (
    BriefingReport,
    ExamenState,
    PlannedTask,
    SocialEntity,
    TopicExtraction,
    VerifiedAction,
)
from src.pipeline.nodes.action_state import node_extract_action
from src.pipeline.nodes.persist import node_persist
from src.pipeline.nodes.scheduler import (
    node_extract_scheduled_task,
    parse_relative_time_expression,
)
from src.pipeline.nodes.social import node_extract_social
from src.pipeline.nodes.topic_research import node_topic_research
from tests.store_backend import new_store


@pytest.fixture(autouse=True)
def temp_store(monkeypatch):
    """Fixture providing an isolated SQLite storage instance for node testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = new_store(db_path)
    monkeypatch.setattr("src.core.storage.get_storage_store", lambda: store)
    monkeypatch.setattr("src.pipeline.nodes.action_state.get_storage_store", lambda: store)
    monkeypatch.setattr("src.pipeline.nodes.social.get_storage_store", lambda: store)
    monkeypatch.setattr("src.pipeline.nodes.social_profiler.get_storage_store", lambda: store)
    monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: store)

    yield store

    if os.path.exists(db_path):
        os.remove(db_path)



class TestActionStateNode:
    """Tests for Stage 3B Action-State Verifier."""

    def test_extract_confirmed_safety_action(self):
        state: ExamenState = {
            "raw_transcript": "I just unplugged the clothes iron before leaving the house.",
            "session_id": "test_session",
            "categories": ["action"],
        }
        res = node_extract_action(state)
        action: VerifiedAction = res.get("action_data")
        assert action is not None
        assert action.action_type == "iron_unplugged"
        assert action.domain == "safety"
        assert action.confidence >= 0.75
        assert "iron" in action.raw_statement.lower()

    def test_extract_work_task_action(self):
        state: ExamenState = {
            "raw_transcript": "I deployed the staging build and merged the pull request.",
            "session_id": "test_session",
            "categories": ["action"],
        }
        res = node_extract_action(state)
        action: VerifiedAction = res.get("action_data")
        assert action is not None
        assert action.domain == "work_task"
        assert action.action_type in ("pr_merged", "service_deployed", "build_deployed")

    def test_rejects_doubts_and_future_intentions(self):
        doubt_transcripts = [
            "I should remember to turn off the stove later today.",
            "Did I remember to lock the front door?",
            "I need to take my blood pressure medication tonight.",
            "I'm planning to deploy to production tomorrow morning."
        ]
        for t in doubt_transcripts:
            state: ExamenState = {
                "raw_transcript": t,
                "session_id": "test_session",
                "categories": ["action"],
            }
            res = node_extract_action(state)
            assert res.get("action_data") is None, f"Expected rejection for doubt: '{t}'"

    def test_extract_action_matching_scheduled_task(self, temp_store):
        # Pre-seed a scheduled task
        task = PlannedTask(
            id="task-window-99",
            title="close bedroom window",
            domain="safety",
            status="pending"
        )
        temp_store.save_planned_task(task)

        state: ExamenState = {
            "raw_transcript": "I just closed the bedroom window before leaving.",
            "session_id": "test_session",
            "categories": ["action"],
        }
        res = node_extract_action(state)
        action: VerifiedAction = res.get("action_data")
        assert action is not None
        assert action.matched_task_id == "task-window-99"
        assert action.domain == "safety"
        assert action.confidence >= 0.75

    def test_extract_action_unplanned_leaves_matched_task_none(self, temp_store):
        # Pre-seed unrelated scheduled task
        task = PlannedTask(
            id="task-iron-1",
            title="unplug clothes iron",
            domain="safety",
            status="pending"
        )
        temp_store.save_planned_task(task)

        state: ExamenState = {
            "raw_transcript": "I deployed the staging build",
            "session_id": "test_session",
            "categories": ["action"],
        }
        res = node_extract_action(state)
        action: VerifiedAction = res.get("action_data")
        assert action is not None
        assert action.domain == "work_task"
        assert action.matched_task_id is None

    def test_doubt_rejection_even_with_scheduled_task(self, temp_store):
        # Pre-seed a scheduled task
        task = PlannedTask(
            id="task-window-99",
            title="close bedroom window",
            domain="safety",
            status="pending"
        )
        temp_store.save_planned_task(task)

        # Spoken doubt should still be rejected by veracity filter
        state: ExamenState = {
            "raw_transcript": "I should remember to close the bedroom window later.",
            "session_id": "test_session",
            "categories": ["action"],
        }
        res = node_extract_action(state)
        assert res.get("action_data") is None

    def test_empty_transcript(self):
        res = node_extract_action({"raw_transcript": ""})
        assert res.get("action_data") is None



class TestSocialNode:
    """Tests for Stage 3A Social Recall Extractor."""

    def test_extract_encounter_with_commitment(self, temp_store):
        state: ExamenState = {
            "raw_transcript": "Hi, I'm Luca Rossi, Cloud Architect at AWS. I will send you the whitepaper tomorrow.",
            "session_id": "test_session",
            "categories": ["social"],
        }
        res = node_extract_social(state)
        social: SocialEntity = res.get("social_data")
        assert social is not None
        assert "Luca Rossi" in social.person_name
        assert social.company_or_role is not None
        assert any("send" in c.lower() for c in social.commitments)

    def test_deduplicates_and_merges_commitments(self, temp_store):
        # 1. Pre-seed contact
        initial = SocialEntity(
            person_name="Marco Bianchi",
            company_or_role="CTO at Acme",
            commitments=["Initial lunch scheduled"],
            key_topics=["Cloud"]
        )
        temp_store.save_social_contact(initial)

        # 2. Extract new encounter with additional commitment
        state: ExamenState = {
            "raw_transcript": "Pleased to meet you again, I'm Marco Bianchi from Acme. I will review the pull request.",
            "session_id": "test_session",
            "categories": ["social"],
        }
        res = node_extract_social(state)
        social: SocialEntity = res.get("social_data")
        assert social is not None
        assert social.person_name == "Marco Bianchi"
        # Verify both commitments exist
        assert len(social.commitments) >= 2
        assert any("Initial lunch" in c for c in social.commitments)
        assert any("pull request" in c.lower() or "review" in c.lower() for c in social.commitments)

    def test_non_social_returns_none(self, temp_store):
        state: ExamenState = {
            "raw_transcript": "The weather is very nice outside today, let's grab coffee.",
            "session_id": "test_session",
            "categories": ["noop"],
        }
        res = node_extract_social(state)
        assert res.get("social_data") is None

    def test_extract_bilateral_commitments_debtor_and_timing(self, temp_store):
        # 1. Contact promises user
        state_contact: ExamenState = {
            "raw_transcript": "Hi, I'm Luca Rossi from AWS. I will send you the whitepaper tomorrow at 10 AM.",
            "session_id": "test_session",
            "categories": ["social"],
        }
        res_contact = node_extract_social(state_contact)
        social_contact: SocialEntity = res_contact.get("social_data")
        assert social_contact is not None
        comms = social_contact.get_commitments_as_objects()
        assert len(comms) >= 1
        c = comms[0]
        assert c.debtor in ("contact", "user")
        assert "tomorrow at 10 am" in (c.due_date_raw or "").lower()
        assert c.normalized_deadline is not None

        # 2. User explicitly promises contact
        state_user: ExamenState = {
            "raw_transcript": "Nice to meet you Giulia Verdi from Datadog. I will send you our pitch deck tomorrow at 10 AM.",
            "session_id": "test_session",
            "categories": ["social"],
        }
        res_user = node_extract_social(state_user)
        social_user: SocialEntity = res_user.get("social_data")
        assert social_user is not None
        user_comms = social_user.get_commitments_as_objects()
        assert len(user_comms) >= 1
        user_c = user_comms[0]
        assert user_c.debtor == "user"
        assert "pitch deck" in user_c.description.lower() or "send" in user_c.description.lower()


class TestTopicResearchNode:
    """Tests for Stage 3C Deep Research & Briefing Synthesizer."""

    def test_extract_and_research_tech_topic(self):
        state: ExamenState = {
            "raw_transcript": "We are evaluating LangGraph with AWS Bedrock AgentCore for multi-agent workflows.",
            "session_id": "test_session",
            "categories": ["deep_topic"],
        }
        res = node_topic_research(state)
        topic: TopicExtraction = res.get("topic_extracted")
        report: BriefingReport = res.get("briefing_report")

        assert topic is not None
        assert len(topic.topic_title) > 0
        assert len(topic.search_queries) >= 1

        assert report is not None
        assert report.topic_title.lower() == topic.topic_title.lower()
        assert len(report.executive_summary) >= 2
        assert len(report.deep_dive_markdown) > 50
        assert len(report.action_items) >= 1
        assert len(report.explanatory_synthesis) > 40
        # Real web search should have populated sources
        assert isinstance(report.web_sources, list)
        assert len(report.web_sources) >= 1

    def test_contextual_synthesis_depth_academic_and_bug(self):
        # 1. Academic lecture test
        academic_state: ExamenState = {
            "raw_transcript": "In today's lecture we study distributed consensus algorithms and the Raft leader election theorem.",
            "session_id": "academic_session",
            "categories": ["deep_topic"],
        }
        res_acad = node_topic_research(academic_state)
        report_acad = res_acad.get("briefing_report")
        assert report_acad is not None
        assert report_acad.context_type == "academic_lecture"
        assert len(report_acad.explanatory_synthesis) > 30

        # 2. Bug / incident test
        bug_state: ExamenState = {
            "raw_transcript": "We hit a critical bug with Bedrock AgentCore socket timeouts causing 504 Gateway errors in production.",
            "session_id": "incident_session",
            "categories": ["deep_topic"],
        }
        res_bug = node_topic_research(bug_state)
        report_bug = res_bug.get("briefing_report")
        assert report_bug is not None
        assert report_bug.context_type in ("bug", "system_incident")
        assert len(report_bug.explanatory_synthesis) > 30

    def test_empty_transcript_topic(self):
        res = node_topic_research({"raw_transcript": ""})
        assert res.get("topic_extracted") is None
        assert res.get("briefing_report") is None


class TestPersistNode:
    """Tests for the atomic context store persistence node."""

    def test_persist_action_and_auto_resolve_task(self, temp_store):
        # 1. Schedule a pending task
        task = PlannedTask(
            title="unplug clothes iron",
            domain="safety",
            status="pending"
        )
        task_id = temp_store.save_planned_task(task)

        # 2. Prepare state with matching completed action
        action = VerifiedAction(
            action_type="iron_unplugged",
            domain="safety",
            raw_statement="I just unplugged the clothes iron",
            confidence=0.95
        )
        state: ExamenState = {
            "action_data": action,
            "session_id": "test_session"
        }

        # 3. Persist
        node_persist(state)

        # 4. Verify action was saved and task was auto-resolved
        saved_action = temp_store.get_action_status("iron")
        assert saved_action is not None
        assert saved_action.action_type == "iron_unplugged"

        resolved_task = temp_store.get_planned_task(task_id)
        assert resolved_task.status == "completed"
        assert resolved_task.completed_at is not None
        assert resolved_task.verified_action_id == saved_action.id

    def test_persist_action_with_prematched_task_id(self, temp_store):
        # 1. Pre-seed scheduled task
        task = PlannedTask(
            id="task-heater-101",
            title="turn off garage heater",
            domain="safety",
            status="pending"
        )
        temp_store.save_planned_task(task)

        # 2. Action with pre-matched task id (e.g. set by action_state node)
        action = VerifiedAction(
            action_type="garage_heater_off",
            domain="safety",
            raw_statement="I turned off the garage heater",
            confidence=0.95,
            matched_task_id="task-heater-101"
        )
        state: ExamenState = {
            "action_data": action,
            "session_id": "test_session"
        }

        # 3. Persist
        node_persist(state)

        # 4. Verify task is completed
        completed = temp_store.get_planned_task("task-heater-101")
        assert completed.status == "completed"
        assert completed.verified_action_id == action.id
        assert completed.completed_at is not None


    def test_rerun_of_a_chunk_keeps_one_briefing(self, temp_store):
        # A backfill retry of a chunk the AgentCore runtime may already have processed
        for _ in range(2):
            report = BriefingReport(topic_title="Raft consensus", context_type="lecture",
                                    executive_summary=["Leader election"])
            node_persist({"briefing_report": report, "session_id": "test_session", "source_key": "live:c1:u1"})
        briefings = temp_store.list_topic_briefings(limit=10)
        assert [b.topic_title for b in briefings] == ["Raft consensus"]

    def test_persist_social_and_topic_briefing(self, temp_store):
        social = SocialEntity(
            person_name="Sara Jenkins",
            company_or_role="Staff Engineer",
            commitments=["Send demo repository link"]
        )
        report = BriefingReport(
            topic_title="Docker Container Security",
            context_type="tech_stack",
            executive_summary=["Point 1", "Point 2"],
            deep_dive_markdown="# Docker Security\nDetails...",
            web_sources=["https://docs.docker.com"],
            action_items=["Enable rootless mode"]
        )
        state: ExamenState = {
            "social_data": social,
            "briefing_report": report
        }

        node_persist(state)

        # Verify social contact is queryable
        contacts = temp_store.search_social_contact("Sara Jenkins")
        assert len(contacts) >= 1
        assert contacts[0].person_name == "Sara Jenkins"

        # Verify briefing report is queryable
        briefing = temp_store.get_topic_briefing("Docker")
        assert briefing is not None
        assert briefing.topic_title == "Docker Container Security"

    def test_persist_scheduled_task(self, temp_store):
        task = PlannedTask(
            title="Call Dr. Smith",
            domain="personal",
            scheduled_time="2026-10-09T15:00:00",
            origin="ambient_voice",
            raw_statement="I need to call Dr. Smith at 3 PM tomorrow.",
            confidence=0.92,
            relative_time_anchor="at 3 PM tomorrow",
            status="pending",
        )
        state: ExamenState = {
            "scheduled_task": task,
        }

        node_persist(state)

        # Verify task is persisted
        tasks = temp_store.list_planned_tasks(origin="ambient_voice")
        assert len(tasks) == 1
        assert tasks[0].title == "Call Dr. Smith"
        assert tasks[0].origin == "ambient_voice"
        assert tasks[0].relative_time_anchor == "at 3 PM tomorrow"
        assert tasks[0].raw_statement == "I need to call Dr. Smith at 3 PM tomorrow."


class TestAmbientSchedulerNode:
    """Tests for Stage 3D Ambient Scheduled Task Extraction."""

    def test_parse_relative_time_expressions(self):
        from datetime import datetime
        base = datetime(2026, 10, 8, 10, 0, 0)

        # 1. in 30 minutes
        iso_min, anchor_min = parse_relative_time_expression("in 30 minutes", ref_dt=base)
        assert iso_min == "2026-10-08T10:30:00"
        assert anchor_min == "in 30 minutes"

        # 2. in an hour
        iso_hr, anchor_hr = parse_relative_time_expression("in an hour", ref_dt=base)
        assert iso_hr == "2026-10-08T11:00:00"
        assert anchor_hr == "in an hour"

        # 3. tomorrow at 3 pm
        iso_tom, anchor_tom = parse_relative_time_expression("tomorrow at 3 pm", ref_dt=base)
        assert iso_tom == "2026-10-09T15:00:00"
        assert "tomorrow at 3 pm" in anchor_tom

        # 4. tonight at 9 pm
        iso_ton, anchor_ton = parse_relative_time_expression("tonight at 9 pm", ref_dt=base)
        assert iso_ton == "2026-10-08T21:00:00"
        assert "tonight at 9 pm" in anchor_ton

    def test_extract_scheduled_task_ambient_voice(self):
        state: ExamenState = {
            "raw_transcript": "I need to call Dr. Smith at 3 PM tomorrow.",
            "session_id": "session_sched_1",
            "categories": ["scheduled_task"],
        }
        res = node_extract_scheduled_task(state)
        task: PlannedTask = res.get("scheduled_task")
        assert task is not None
        assert "call dr. smith" in task.title.lower() or "dr. smith" in task.title.lower()
        assert task.origin == "ambient_voice"
        assert task.raw_statement == "I need to call Dr. Smith at 3 PM tomorrow."
        assert task.confidence >= 0.8
        assert task.status == "pending"

    def test_extract_safety_scheduled_task(self):
        state: ExamenState = {
            "raw_transcript": "Remind me to turn off the irrigation valve in an hour.",
            "session_id": "session_sched_2",
            "categories": ["scheduled_task"],
        }
        res = node_extract_scheduled_task(state)
        task: PlannedTask = res.get("scheduled_task")
        assert task is not None
        assert task.domain == "safety"
        assert task.origin == "ambient_voice"
        assert "turn off" in task.title.lower() or "irrigation" in task.title.lower()
        assert task.scheduled_time is not None

    def test_empty_transcript_scheduler(self):
        res = node_extract_scheduled_task({"raw_transcript": ""})
        assert res.get("scheduled_task") is None


class TestSocialProfilerNode:
    """Tests for Milestone 2.1: Autonomous Social Web Profiler."""

    def test_disambiguation_guardrails(self):
        from src.pipeline.nodes.social_profiler import verify_disambiguation_anchors

        # 1. Standalone single-word names without company/role/topics must be rejected
        assert verify_disambiguation_anchors("Dave") is False
        assert verify_disambiguation_anchors("Marco") is False
        assert verify_disambiguation_anchors("Elena") is False
        assert verify_disambiguation_anchors("") is False
        assert verify_disambiguation_anchors("   ") is False

        # 2. Single-word name with strong company/role anchor passes
        assert verify_disambiguation_anchors("Luca", company_or_role="VP at CloudScale") is True
        assert verify_disambiguation_anchors("Elena", company_or_role="Lab Head at ETH Zurich") is True
        assert verify_disambiguation_anchors("Marco", topics=["AgentCore", "AWS"]) is True

        # 3. Full multi-word names pass with or without additional context
        assert verify_disambiguation_anchors("Luca Bianchi", company_or_role="VP of Infrastructure") is True
        assert verify_disambiguation_anchors("Dr. Elena Rostova", topics=["Computer Vision"]) is True
        assert verify_disambiguation_anchors("Sarah Connor", notes="sarah@cyberdyne.com") is True
        assert verify_disambiguation_anchors("Luca Bianchi") is True

    def test_query_formulation(self):
        from src.pipeline.nodes.social_profiler import build_profiling_queries

        queries = build_profiling_queries(
            name="Luca Bianchi",
            company_or_role="VP of Infrastructure at CloudScale",
            topics=["Distributed Systems", "Raft"]
        )
        assert len(queries) >= 2
        assert any("Luca Bianchi" in q for q in queries)
        assert any("CloudScale" in q or "VP" in q for q in queries)
        # Should NOT contain personal social networks
        for q in queries:
            assert "instagram" not in q.lower()
            assert "tiktok" not in q.lower()

    def test_enrich_social_contact_heuristic(self, temp_store, monkeypatch):
        from src.pipeline.nodes.social_profiler import enrich_social_contact_sync, heuristic_profile_synthesis
        from src.core.schemas import SocialEntity

        # Test deterministic heuristic synthesizer directly
        contact = SocialEntity(
            person_name="Luca Bianchi",
            company_or_role="VP of Infrastructure at CloudScale",
            key_topics=["Distributed Systems", "AWS"],
        )
        h_profile = heuristic_profile_synthesis(contact)
        assert h_profile is not None
        assert "CloudScale" in (h_profile.organization or h_profile.headline)
        assert "Distributed Systems" in h_profile.areas_of_expertise
        assert h_profile.linkedin_url is not None

        # Test enrich_social_contact_sync with mock_ai
        monkeypatch.setattr(settings, "mock_ai", True)
        temp_store.save_social_contact(contact)
        profile = enrich_social_contact_sync(contact, store=temp_store)
        assert profile is not None
        assert profile.headline is not None
        assert "CloudScale" in (profile.organization or profile.headline)
        assert profile.bio_summary is not None
        assert len(profile.areas_of_expertise) > 0
        assert profile.linkedin_url is not None
        assert "linkedin.com/in/" in profile.linkedin_url

        # Verify persisted in store
        persisted = temp_store.get_social_contact("Luca Bianchi")
        assert persisted.web_profile is not None
        assert persisted.web_profile.headline == profile.headline

    def test_enrich_social_contact_guardrail_rejection(self, temp_store):
        from src.pipeline.nodes.social_profiler import enrich_social_contact_sync
        from src.core.schemas import SocialEntity

        # Ambiguous contact with only first name and no role/topics
        contact = SocialEntity(
            person_name="Dave",
            company_or_role=None,
            key_topics=[],
        )
        profile = enrich_social_contact_sync(contact, store=temp_store)
        assert profile is None

    def test_profiler_prompt_placeholders_match_format_kwargs(self):
        import string
        from src.pipeline.nodes.social_profiler import (
            PROFILER_SYSTEM_PROMPT,
            SOURCE_EVALUATION_SYSTEM_PROMPT,
        )

        def fields(template):
            return {f for _, f, _, _ in string.Formatter().parse(template) if f is not None}

        base = {"person_name", "company_or_role", "website_url", "key_topics", "transcript"}
        assert fields(PROFILER_SYSTEM_PROMPT) <= base | {"search_snippets"}
        assert fields(SOURCE_EVALUATION_SYSTEM_PROMPT) <= base | {"numbered_candidates"}

    def test_disambiguation_result_coerces_malformed_llm_output(self):
        from src.core.schemas import DisambiguationResult

        res = DisambiguationResult.model_validate({
            "canonical_linkedin_url": ["https://www.linkedin.com/in/ada"],
            "canonical_github_url": [],
            "verified_source_indices": "0, 2",
            "rejected_source_indices": None,
            "clean_combined_facts": "Ada has a LinkedIn profile",
        })
        assert res.canonical_linkedin_url == "https://www.linkedin.com/in/ada"
        assert res.canonical_github_url is None
        assert res.verified_source_indices == [0, 2]
        assert res.rejected_source_indices == []
        assert res.clean_combined_facts == ["Ada has a LinkedIn profile"]

    def test_synthesized_profile_schema_ignores_disambiguation_report(self):
        from src.pipeline.nodes.social_profiler import SynthesizedWebProfile

        assert "disambiguation_report" not in SynthesizedWebProfile.model_fields
        res = SynthesizedWebProfile.model_validate({
            "headline": "Ada | Analytical Engines",
            "linkedin_url": "https://www.linkedin.com/in/ada",
            "disambiguation_report": {"canonical_github_url": [[]], "confidence_score": "high"},
        })
        assert res.headline == "Ada | Analytical Engines"
        assert res.linkedin_url == "https://www.linkedin.com/in/ada"

    def test_enrich_live_keeps_verified_linkedin_when_synthesis_fails(self, temp_store, monkeypatch):
        from src.pipeline.nodes import social_profiler
        from src.pipeline.tools.web_search import QueryEvaluation, SearchResultItem, WebSearchBatchResult
        from src.core.schemas import SocialEntity

        linkedin = "https://www.linkedin.com/in/luca-bianchi-cloud"
        batch = WebSearchBatchResult(evaluations=[
            QueryEvaluation(
                query="q",
                normalized_query="q",
                is_empty=False,
                results=[SearchResultItem(
                    title="Luca Bianchi - VP of Infrastructure - CloudScale | LinkedIn",
                    url=linkedin,
                    snippet="Luca Bianchi, VP of Infrastructure at CloudScale.",
                )],
            )
        ])

        def failing_model():
            raise RuntimeError("model unavailable")

        monkeypatch.setattr(settings, "mock_ai", False)
        monkeypatch.setattr(social_profiler, "has_active_model_credentials", lambda *a, **k: True)
        monkeypatch.setattr(social_profiler, "execute_search_batch", lambda *a, **k: batch)
        monkeypatch.setattr(social_profiler, "get_fast_model", failing_model)

        contact = SocialEntity(
            person_name="Luca Bianchi",
            company_or_role="VP of Infrastructure at CloudScale",
            key_topics=["Distributed Systems", "AWS"],
        )
        temp_store.save_social_contact(contact)
        profile = social_profiler.enrich_social_contact_sync(contact, store=temp_store, force=True)

        assert profile is not None
        assert profile.linkedin_url and "linkedin.com/in/luca-bianchi-cloud" in profile.linkedin_url
        assert profile.disambiguation_report is not None

        persisted = temp_store.get_social_contact("Luca Bianchi")
        assert persisted.web_profile.linkedin_url == profile.linkedin_url

    def test_node_extract_social_with_profiler(self, temp_store):
        from src.pipeline.nodes.social import node_extract_social
        from src.core.schemas import ExamenState

        state: ExamenState = {
            "raw_transcript": "Hi, I'm Luca Bianchi, VP of Infrastructure at CloudScale. Let's discuss Raft consensus.",
            "session_id": "test_social_profiler_sess",
            "categories": ["social"],
        }
        res = node_extract_social(state)
        social = res.get("social_data")
        assert social is not None
        assert social.person_name == "Luca Bianchi"
        # Autonomous profiler should have enriched this qualified contact
        assert social.web_profile is not None
        assert social.web_profile.headline is not None
        assert len(social.web_profile.bio_summary) > 0
        assert social.web_profile.confidence_score > 0

