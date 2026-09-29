"""Tests for the semantic screening Gatekeeper (English Standard)."""

import pytest
from src.core.schemas import ChunkClassification
from src.ingestion.gatekeeper import classify_chunk, aclassify_chunk, is_noop


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
    """Doubtful statements or future intentions must NOT be treated as completed actions."""
    doubt_samples = [
        "I should remember to unplug the clothes iron before heading out.",
        "Need to remember to lock the front door tonight.",
        "Did I unplug the stove? I wonder if I turned it off.",
        "Need to deploy the database update tomorrow morning.",
        "I have to check the logs later on.",
    ]
    for sample in doubt_samples:
        res = classify_chunk(sample, force_mock=True)
        assert is_noop(res) is True, f"Doubt sample '{sample}' should be dropped, got: {res.categories}"


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
