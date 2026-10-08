"""End-to-end integration tests for the LangGraph StateGraph & Bedrock AgentCore Runtime.

Validates single-channel execution, multi-label parallel fan-out, persistence convergence,
noop short-circuiting, and AgentCore runtime ingress payloads.
"""

import os
import tempfile
import pytest

from src.core.schemas import ExamenState, PlannedTask
from src.core.storage.sqlite_store import SQLiteContextStore
from src.pipeline.app import agent_invocation
from src.pipeline.graph import pipeline_graph


@pytest.fixture(autouse=True)
def temp_store(monkeypatch):
    """Provides an isolated SQLite storage instance for end-to-end pipeline testing."""
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


class TestLangGraphPipeline:
    """Integration tests for compiled LangGraph StateGraph."""

    def test_pipeline_action_flow(self, temp_store):
        # Pre-seed a scheduled task to verify linking
        task = PlannedTask(
            id="task-iron-01",
            title="unplug clothes iron",
            domain="safety",
            status="pending",
        )
        temp_store.save_planned_task(task)

        state: ExamenState = {
            "raw_transcript": "I just unplugged the clothes iron before leaving the house.",
            "session_id": "test_action_sess",
            "categories": ["action"],
            "confidence": 0.95,
        }

        result = pipeline_graph.invoke(state)

        # 1. Verify state outputs
        action = result.get("action_data")
        assert action is not None
        assert action.action_type in ("iron_unplugged", "unplug_clothes_iron")
        assert action.domain == "safety"
        assert action.matched_task_id == "task-iron-01"

        # 2. Verify persistence in context store
        saved = temp_store.get_action_status("iron")
        assert saved is not None
        assert saved.action_type in ("iron_unplugged", "unplug_clothes_iron")

        # 3. Verify planned task completion
        completed_task = temp_store.get_planned_task("task-iron-01")
        assert completed_task.status == "completed"
        assert completed_task.verified_action_id == action.id

    def test_pipeline_social_flow(self, temp_store):
        state: ExamenState = {
            "raw_transcript": "Pleased to meet you, I'm Luca Rossi, Tech Lead at AWS. I will send you the whitepaper tomorrow.",
            "session_id": "test_social_sess",
            "categories": ["social"],
            "confidence": 0.94,
        }

        result = pipeline_graph.invoke(state)

        # 1. Verify state outputs
        social = result.get("social_data")
        assert social is not None
        assert "Luca Rossi" in social.person_name
        assert any("send" in c.lower() for c in social.commitments)

        # 2. Verify persistence in context store
        contacts = temp_store.search_social_contact("Luca Rossi")
        assert len(contacts) >= 1
        assert contacts[0].person_name == "Luca Rossi"

    def test_pipeline_deep_topic_flow(self, temp_store):
        state: ExamenState = {
            "raw_transcript": "In today's meeting we are evaluating LangGraph with AWS Bedrock AgentCore for multi-agent workflows.",
            "session_id": "test_topic_sess",
            "categories": ["deep_topic"],
            "confidence": 0.92,
        }

        result = pipeline_graph.invoke(state)

        # 1. Verify state outputs
        topic = result.get("topic_extracted")
        report = result.get("briefing_report")
        assert topic is not None
        assert report is not None
        assert len(report.topic_title) > 0
        assert len(report.web_sources) >= 1

        # 2. Verify persistence in context store
        saved_report = temp_store.get_topic_briefing(topic.topic_title[:10])
        assert saved_report is not None

    def test_pipeline_multilabel_fanout(self, temp_store):
        """Validates that a multi-label chunk triggers parallel branches and converges to persist."""
        state: ExamenState = {
            "raw_transcript": "Nice to meet you, I am Marco Bianchi from Acme. I will review the proposal. Also, I just deployed the staging build.",
            "session_id": "test_multi_sess",
            "categories": ["social", "action"],
            "confidence": 0.96,
        }

        result = pipeline_graph.invoke(state)

        # Both channels must have executed
        assert result.get("social_data") is not None
        assert result.get("action_data") is not None

        # Both entities must be stored in DB
        contacts = temp_store.search_social_contact("Marco Bianchi")
        assert len(contacts) >= 1

        action = temp_store.get_action_status("build") or temp_store.get_action_status("service")
        assert action is not None

    def test_pipeline_scheduled_task_flow(self, temp_store):
        """Validates that spoken future tasks fan out to scheduler node and persist in SQLite."""
        state: ExamenState = {
            "raw_transcript": "I need to call Dr. Smith at 3 PM tomorrow.",
            "session_id": "test_sched_flow_sess",
            "categories": ["scheduled_task"],
            "confidence": 0.94,
        }

        result = pipeline_graph.invoke(state)

        # 1. Verify state outputs
        task = result.get("scheduled_task")
        assert task is not None
        assert "dr. smith" in task.title.lower() or "call" in task.title.lower()
        assert task.origin == "ambient_voice"
        assert task.status == "pending"

        # 2. Verify persistence in context store
        stored_tasks = temp_store.list_planned_tasks(origin="ambient_voice")
        assert len(stored_tasks) >= 1
        assert any("smith" in t.title.lower() for t in stored_tasks)

    def test_pipeline_noop_shortcircuit(self, temp_store):
        """Validates that noop categories bypass extraction nodes directly to END."""
        state: ExamenState = {
            "raw_transcript": "What a beautiful sunny day, let's grab coffee.",
            "session_id": "test_noop_sess",
            "categories": ["noop"],
            "confidence": 0.98,
        }

        result = pipeline_graph.invoke(state)

        assert result.get("action_data") is None
        assert result.get("social_data") is None
        assert result.get("briefing_report") is None
        assert result.get("scheduled_task") is None

        # Verify nothing persisted
        actions = temp_store.list_recent_actions(limit=10)
        assert len(actions) == 0


class TestAgentCoreApp:
    """Integration tests for AWS Bedrock AgentCore Runtime entrypoint."""

    def test_agentcore_ingestion_payload(self, temp_store):
        payload = {
            "raw_transcript": "I just turned off the stove before leaving.",
            "categories": ["action"],
            "confidence": 0.95,
            "summary_hint": "Turned off stove",
            "session_id": "sess-ingest-01",
        }

        res = agent_invocation(payload, None)

        assert res["status"] == "success"
        assert res["session_id"] == "sess-ingest-01"
        assert "stove_off" in str(res["action_data"])
        assert "Verified completed action" in res["summary"]

    def test_agentcore_console_prompt_ingress(self, temp_store):
        """Validates that a direct conversational prompt runs ingress screening and extracts action."""
        payload = {
            "prompt": "I just turned off the stove",
            "session_id": "sess-prompt-01",
        }

        res = agent_invocation(payload, None)

        assert res["status"] == "success"
        assert res["session_id"] == "sess-prompt-01"
        assert res["action_data"] is not None
        assert res["action_data"]["action_type"] == "stove_off"

    def test_agentcore_scheduled_task_ingress(self, temp_store):
        """Validates that a direct conversational prompt with future intention extracts scheduled task."""
        payload = {
            "prompt": "I need to call Dr. Smith at 3 PM tomorrow",
            "session_id": "sess-prompt-sched",
        }

        res = agent_invocation(payload, None)

        assert res["status"] == "success"
        assert res["session_id"] == "sess-prompt-sched"
        assert res["scheduled_task"] is not None
        assert res["scheduled_task"]["origin"] == "ambient_voice"
        assert "scheduled task" in res["summary"].lower()

    def test_agentcore_empty_prompt_returns_noop(self):
        payload = {"prompt": "   "}
        res = agent_invocation(payload, None)

        assert res["status"] == "noop"
        assert res["categories"] == ["noop"]
        assert "Empty transcript" in res["summary"]
