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
from src.core.storage.sqlite_store import SQLiteContextStore
from src.pipeline.nodes.action_state import node_extract_action
from src.pipeline.nodes.persist import node_persist
from src.pipeline.nodes.scheduler import (
    node_extract_scheduled_task,
    parse_relative_time_expression,
)
from src.pipeline.nodes.social import node_extract_social
from src.pipeline.nodes.topic_research import node_topic_research


@pytest.fixture(autouse=True)
def temp_store(monkeypatch):
    """Fixture providing an isolated SQLite storage instance for node testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = SQLiteContextStore(db_path=db_path)
    monkeypatch.setattr("src.core.storage.get_storage_store", lambda: store)
    monkeypatch.setattr("src.pipeline.nodes.action_state.get_storage_store", lambda: store)
    monkeypatch.setattr("src.pipeline.nodes.social.get_storage_store", lambda: store)
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
