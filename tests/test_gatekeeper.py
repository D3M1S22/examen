"""Tests for the semantic screening Gatekeeper (English Standard)."""

import pytest
from src.core.schemas import ChunkClassification
from src.ingestion.gatekeeper import (
    classify_chunk,
    aclassify_chunk,
    is_noop,
    build_gatekeeper_prompt,
    GATEKEEPER_SYSTEM_PROMPT,
)


def test_gatekeeper_empty_transcript():
    """Empty or whitespace transcripts must immediately return noop."""
    res = classify_chunk("", force_mock=True)
    assert isinstance(res, ChunkClassification)
    assert res.categories == ["noop"]
    assert is_noop(res) is True

    res_spaces = classify_chunk("   \n\t  ", force_mock=True)
    assert res_spaces.categories == ["noop"]
    assert is_noop(res_spaces) is True


def test_gatekeeper_noop_chitchat():
    """Casual banter and pleasantries must be classified as noop."""
    chit_chat_samples = [
        "What a nice sunny day in Seattle, really warm outside.",
        "Let's grab a coffee at the coffee shop on the corner.",
        "Yeah, totally, let's catch up later today, take care.",
        "Did you catch the basketball game yesterday evening?",
        "Sounds good to me, see you in a bit.",
    ]
    for sample in chit_chat_samples:
        res = classify_chunk(sample, force_mock=True)
        assert "noop" in res.categories, f"Sample '{sample}' should be noop, got: {res.categories}"
        assert is_noop(res) is True


def test_gatekeeper_action_completed():
    """Verified completed actions must be identified with high confidence."""
    action_samples = [
        "I just unplugged the clothes iron before leaving the house.",
        "I have locked the front door and switched off the stove.",
        "We just merged the pull request on the staging repository.",
        "I completed the database backup and sent the confirmation email.",
    ]
    for sample in action_samples:
        res = classify_chunk(sample, force_mock=True)
        assert "action" in res.categories, f"Sample '{sample}' should detect action, got: {res.categories}"
        assert is_noop(res) is False
        assert res.confidence >= 0.80


def test_gatekeeper_action_doubt_rejection():
    """Retrospective doubts and uncertain questions must NOT be treated as completed actions."""
    doubt_samples = [
        "Did I unplug the stove? I wonder if I turned it off.",
        "Did I lock the front door when leaving?",
        "I wonder if we turned off the water valve.",
        "Did we shut down the server? Not sure.",
        "Was it locked? Maybe I forgot.",
    ]
    for sample in doubt_samples:
        res = classify_chunk(sample, force_mock=True)
        assert is_noop(res) is True, f"Doubt sample '{sample}' should be dropped as noop, got: {res.categories}"
        assert "action" not in res.categories
        assert "scheduled_task" not in res.categories


def test_gatekeeper_scheduled_tasks():
    """Forward commitments, reminders, and deadlines must be classified as scheduled_task."""
    task_samples = [
        "I need to call Dr. Smith at 3 PM tomorrow.",
        "Remind me to turn off the irrigation valve in an hour.",
        "I have to deploy the database update tomorrow morning.",
        "Don't forget to lock the front door tonight.",
        "Need to finish the quarterly performance review before Friday.",
    ]
    for sample in task_samples:
        res = classify_chunk(sample, force_mock=True)
        assert "scheduled_task" in res.categories, f"Sample '{sample}' should be scheduled_task, got: {res.categories}"
        assert "action" not in res.categories
        assert is_noop(res) is False
        assert res.confidence >= 0.85


def test_gatekeeper_social_recall():
    """Introductions, job titles, and mutual commitments must be detected."""
    social_samples = [
        "Nice to meet you, I'm Marco, Tech Lead at Acme Corp. Let's keep in touch.",
        "Pleased to meet you, my name is Dario, founder at CloudScale. I will follow up with you.",
        "Great to meet you, I work as lead engineer at Stripe.",
    ]
    for sample in social_samples:
        res = classify_chunk(sample, force_mock=True)
        assert "social" in res.categories, f"Social sample '{sample}' failed, got: {res.categories}"
        assert is_noop(res) is False


def test_gatekeeper_deep_topic():
    """Technical architecture, framework debates, and bugs must trigger deep_topic."""
    topic_samples = [
        "In today's meeting we will conduct the architecture review for AWS Bedrock AgentCore.",
        "During this meeting our agenda for today is evaluating the architecture and investigating the memory leak.",
        "In today's lecture we cover distributed systems, distributed consensus, and the CAP theorem.",
    ]
    for sample in topic_samples:
        res = classify_chunk(sample, force_mock=True)
        assert "deep_topic" in res.categories, f"Topic sample '{sample}' failed, got: {res.categories}"
        assert is_noop(res) is False


def test_gatekeeper_multilabel():
    """Utterances containing both social introduction and completed action."""
    sample = "Nice to meet you! I just merged the staging pull request."
    res = classify_chunk(sample, force_mock=True)
    assert "social" in res.categories
    assert "action" in res.categories
    assert is_noop(res) is False


@pytest.mark.asyncio
async def test_gatekeeper_async():
    """Asynchronous classification endpoint must return valid ChunkClassification."""
    sample = "I just turned off the clothes iron."
    res = await aclassify_chunk(sample, force_mock=True)
    assert isinstance(res, ChunkClassification)
    assert "action" in res.categories
    assert is_noop(res) is False


def test_gatekeeper_prompt_builder():
    """System prompt builder should cleanly inject active pending tasks."""
    default_prompt = build_gatekeeper_prompt()
    assert default_prompt == GATEKEEPER_SYSTEM_PROMPT
    assert "ACTIVE PENDING TASKS" not in default_prompt

    empty_prompt = build_gatekeeper_prompt([])
    assert empty_prompt == GATEKEEPER_SYSTEM_PROMPT

    tasks = ["unplug clothes iron", "evening blood pressure medication"]
    injected_prompt = build_gatekeeper_prompt(tasks)
    assert "ACTIVE PENDING TASKS / ROUTINES TO WATCH FOR:" in injected_prompt
    assert "- unplug clothes iron" in injected_prompt
    assert "- evening blood pressure medication" in injected_prompt
    assert "PRIORITY INSTRUCTION FOR ACTIVE TASKS:" in injected_prompt


def test_gatekeeper_active_tasks_detection():
    """Pending tasks passed to Gatekeeper should be detected even if phrased conversationally."""
    active_tasks = ["evening medication", "front door lock"]

    # Utterance referencing the active task with completion phrase
    sample = "The evening medication is done and all taken care of."
    res = classify_chunk(sample, active_tasks=active_tasks, force_mock=True)
    assert "action" in res.categories
    assert is_noop(res) is False
    assert res.confidence >= 0.80

    # Utterance referencing another active task
    sample_door = "The front door is locked and checked."
    res_door = classify_chunk(sample_door, active_tasks=active_tasks, force_mock=True)
    assert "action" in res_door.categories
    assert is_noop(res_door) is False

