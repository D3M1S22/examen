"""Unit tests for SQLiteContextStore."""

import os
import tempfile
import pytest
from src.core.schemas import VerifiedAction, SocialEntity, BriefingReport, PlannedTask
from src.core.storage.sqlite_store import SQLiteContextStore


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteContextStore(db_path=path)
    yield store
    store.close()
    if os.path.exists(path):
        os.remove(path)


def test_action_lifecycle(temp_store):
    action = VerifiedAction(
        action_type="iron_unplugged",
        domain="safety",
        raw_statement="I'm unplugging the clothes iron before leaving the house",
        confidence=0.96,
        timestamp="2026-09-29T08:14:00+02:00"
    )
    rec_id = temp_store.save_action(action)
    assert rec_id is not None

    # Query for keyword 'iron'
    status = temp_store.get_action_status("iron")
    assert status is not None
    assert status.action_type == "iron_unplugged"
    assert status.confidence == 0.96

    # List recent actions
    recent = temp_store.list_recent_actions(limit=5)
    assert len(recent) == 1
    assert recent[0].action_type == "iron_unplugged"


def test_social_contact_lifecycle(temp_store):
    contact = SocialEntity(
        person_name="Marco Rossi",
        company_or_role="Tech Lead @ Acme Corp",
        contact_info="marco@acme.com",
        commitments=["Send documentation link", "Feedback on Friday"],
        key_topics=["AWS Bedrock", "AgentCore", "LangGraph"],
        timestamp="2026-09-29T10:30:00+02:00"
    )
    rec_id = temp_store.save_social_contact(contact)
    assert rec_id is not None

    # Search by person name
    matches = temp_store.search_social_contact("Marco")
    assert len(matches) == 1
    assert matches[0].person_name == "Marco Rossi"
    assert len(matches[0].commitments) == 2

    # Search by topic tag
    topic_matches = temp_store.search_social_contact("AgentCore")
    assert len(topic_matches) == 1


def test_topic_briefing_lifecycle(temp_store):
    briefing = BriefingReport(
        topic_title="AWS AgentCore Architecture",
        context_type="tech_stack",
        executive_summary=["Serverless runtime framework", "Multi-model tiering"],
        deep_dive_markdown="## AgentCore Overview\nSupports isolated microVMs.",
        web_sources=["https://docs.aws.amazon.com"],
        action_items=["Configure IAM Execution Role"],
        created_at="2026-09-29T12:00:00+02:00"
    )
    rec_id = temp_store.save_topic_briefing(briefing)
    assert rec_id is not None

    # Retrieve latest briefing
    report = temp_store.get_topic_briefing()
    assert report is not None
    assert report.topic_title == "AWS AgentCore Architecture"
    assert len(report.executive_summary) == 2


def test_planned_task_lifecycle(temp_store):
    # 1. Create a planned task
    task = PlannedTask(
        title="unplug clothes iron",
        domain="safety",
        recurrence="daily",
        scheduled_time="08:30"
    )
    task_id = temp_store.save_planned_task(task)
    assert task_id is not None

    # Verify task is pending
    pending = temp_store.list_planned_tasks(status="pending")
    assert len(pending) == 1
    assert pending[0].id == task_id
    assert pending[0].title == "unplug clothes iron"
    assert pending[0].status == "pending"

    # 2. Save a matching VerifiedAction
    action = VerifiedAction(
        action_type="iron_unplugged",
        domain="safety",
        raw_statement="I just unplugged the clothes iron before leaving the house",
        confidence=0.98,
        timestamp="2026-09-29T08:25:00+02:00"
    )
    action_id = temp_store.save_action(action)
    assert action_id is not None
    assert action.matched_task_id == task_id

    # 3. Verify task auto-resolved to completed
    updated_task = temp_store.get_planned_task(task_id)
    assert updated_task is not None
    assert updated_task.status == "completed"
    assert updated_task.verified_action_id == action_id
    assert updated_task.completed_at == "2026-09-29T08:25:00+02:00"

    # Pending list should now be empty, completed list has 1
    assert len(temp_store.list_planned_tasks(status="pending")) == 0
    completed = temp_store.list_planned_tasks(status="completed")
    assert len(completed) == 1
    assert completed[0].id == task_id

