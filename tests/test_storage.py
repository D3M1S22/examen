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
        explanatory_synthesis="AWS Bedrock AgentCore provides low-latency runtime microVM isolation specifically engineered for autonomous agents.",
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
    assert "low-latency runtime" in report.explanatory_synthesis

    # Search by keyword matching explanatory_synthesis
    searched = temp_store.get_topic_briefing(query="microVM isolation")
    assert searched is not None
    assert searched.id == rec_id
    assert searched.explanatory_synthesis == briefing.explanatory_synthesis


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


def test_planned_task_update_and_delete(temp_store):
    task = PlannedTask(
        title="Original Title",
        domain="routine",
        scheduled_time="09:00",
        recurrence="none",
        status="pending",
    )
    task_id = temp_store.save_planned_task(task)
    assert task_id is not None

    # Update task
    task.title = "Updated Title"
    task.scheduled_time = "10:30"
    task.domain = "safety"
    updated = temp_store.update_planned_task(task)
    assert updated is True

    fetched = temp_store.get_planned_task(task_id)
    assert fetched.title == "Updated Title"
    assert fetched.scheduled_time == "10:30"
    assert fetched.domain == "safety"

    # Delete task
    deleted = temp_store.delete_planned_task(task_id)
    assert deleted is True
    assert temp_store.get_planned_task(task_id) is None

    # Deleting non-existent task returns False
    assert temp_store.delete_planned_task("non-existent-id") is False


def test_planned_task_ambient_voice_fields(temp_store):
    task = PlannedTask(
        title="Call Dr. Smith",
        domain="personal",
        scheduled_time="2026-10-09T15:00:00",
        recurrence="none",
        status="pending",
        origin="ambient_voice",
        raw_statement="I need to call Dr. Smith at 3 PM tomorrow.",
        confidence=0.95,
        relative_time_anchor="at 3 PM tomorrow",
        session_id="ambient_session_123",
    )
    task_id = temp_store.save_planned_task(task)
    assert task_id is not None

    fetched = temp_store.get_planned_task(task_id)
    assert fetched is not None
    assert fetched.origin == "ambient_voice"
    assert fetched.raw_statement == "I need to call Dr. Smith at 3 PM tomorrow."
    assert fetched.confidence == 0.95
    assert fetched.relative_time_anchor == "at 3 PM tomorrow"
    assert fetched.session_id == "ambient_session_123"

    # List with origin filter
    ambient_tasks = temp_store.list_planned_tasks(origin="ambient_voice")
    assert len(ambient_tasks) == 1
    assert ambient_tasks[0].id == task_id

    manual_tasks = temp_store.list_planned_tasks(origin="manual")
    assert len(manual_tasks) == 0


def test_social_commitments_lifecycle(temp_store):
    from src.core.schemas import SocialCommitment

    # 1. User commitment -> should auto-provision a PlannedTask
    user_com = SocialCommitment(
        contact_name="Sara Bianchi",
        debtor="user",
        description="Send pitch deck",
        due_date_raw="tomorrow at 10 AM",
        normalized_deadline="2026-10-09T10:00:00",
        status="open"
    )
    user_id = temp_store.save_social_commitment(user_com)
    assert user_id is not None
    assert user_com.auto_scheduled_task_id is not None

    # Verify PlannedTask was auto-created with origin="social_commitment"
    task = temp_store.get_planned_task(user_com.auto_scheduled_task_id)
    assert task is not None
    assert task.origin == "social_commitment"
    assert "Send pitch deck" in task.title
    assert "Sara Bianchi" in task.title
    assert task.scheduled_time == "2026-10-09T10:00:00"
    assert task.status == "pending"

    # 2. Contact commitment -> should NOT auto-provision a PlannedTask
    contact_com = SocialCommitment(
        contact_name="Sara Bianchi",
        debtor="contact",
        description="Review security architecture proposal",
        status="open"
    )
    contact_id = temp_store.save_social_commitment(contact_com)
    assert contact_id is not None
    assert contact_com.auto_scheduled_task_id is None

    # 3. Filtering by debtor and contact
    user_list = temp_store.list_social_commitments(debtor="user")
    assert len(user_list) == 1
    assert user_list[0].id == user_id

    contact_list = temp_store.list_social_commitments(debtor="contact")
    assert len(contact_list) == 1
    assert contact_list[0].id == contact_id

    all_sara = temp_store.list_social_commitments(contact_name="Sara Bianchi")
    assert len(all_sara) == 2

    # 4. Update status to fulfilled -> linked PlannedTask should be completed
    updated = temp_store.update_social_commitment_status(user_id, "fulfilled")
    assert updated is True
    com_fetched = temp_store.get_social_commitment(user_id)
    assert com_fetched.status == "fulfilled"

    task_updated = temp_store.get_planned_task(user_com.auto_scheduled_task_id)
    assert task_updated.status == "completed"


def test_social_commitments_closed_loop_fulfillment(temp_store):
    from src.core.schemas import SocialCommitment

    com = SocialCommitment(
        contact_name="Luca Nardi",
        debtor="user",
        description="Deliver API documentation",
        status="open"
    )
    com_id = temp_store.save_social_commitment(com)
    assert com.auto_scheduled_task_id is not None

    # User verifies action matching the commitment
    action = VerifiedAction(
        action_type="documentation_delivered",
        domain="work_task",
        raw_statement="I just finished and delivered API documentation to Luca Nardi",
        confidence=0.97,
        timestamp="2026-10-08T18:00:00"
    )
    temp_store.save_action(action)

    # Commitment should now be automatically marked fulfilled
    com_updated = temp_store.get_social_commitment(com_id)
    assert com_updated.status == "fulfilled"

    # And the planned task is marked completed
    task = temp_store.get_planned_task(com.auto_scheduled_task_id)
    assert task.status == "completed"


