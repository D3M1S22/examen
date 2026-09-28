"""Unit tests for SQLiteContextStore."""

import os
import tempfile
import pytest
from src.core.schemas import VerifiedAction, SocialEntity, BriefingReport
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
        action_type="ferro_staccato",
        domain="safety",
        raw_statement="Sto staccando la spina del ferro da stiro prima di uscire",
        confidence=0.96,
        timestamp="2026-09-29T08:14:00+02:00"
    )
    rec_id = temp_store.save_action(action)
    assert rec_id is not None

    # Query per parola chiave 'ferro'
    status = temp_store.get_action_status("ferro")
    assert status is not None
    assert status.action_type == "ferro_staccato"
    assert status.confidence == 0.96

    # Elenco azioni recenti
    recent = temp_store.list_recent_actions(limit=5)
    assert len(recent) == 1
    assert recent[0].action_type == "ferro_staccato"


def test_social_contact_lifecycle(temp_store):
    contact = SocialEntity(
        person_name="Marco Rossi",
        company_or_role="Tech Lead @ Acme Corp",
        contact_info="marco@acme.com",
        commitments=["Inviare link documentazione", "Feedback venerdì"],
        key_topics=["AWS Bedrock", "AgentCore", "LangGraph"],
        timestamp="2026-09-29T10:30:00+02:00"
    )
    rec_id = temp_store.save_social_contact(contact)
    assert rec_id is not None

    # Ricerca per nome
    matches = temp_store.search_social_contact("Marco")
    assert len(matches) == 1
    assert matches[0].person_name == "Marco Rossi"
    assert len(matches[0].commitments) == 2

    # Ricerca per topic
    topic_matches = temp_store.search_social_contact("AgentCore")
    assert len(topic_matches) == 1


def test_topic_briefing_lifecycle(temp_store):
    briefing = BriefingReport(
        topic_title="AWS AgentCore Architecture",
        context_type="tech_stack",
        executive_summary=["Framework runtime serverless", "Multi-model tiering"],
        deep_dive_markdown="## AgentCore Overview\nSupporta microVM isolate.",
        web_sources=["https://docs.aws.amazon.com"],
        action_items=["Configurare IAM Role"],
        created_at="2026-09-29T12:00:00+02:00"
    )
    rec_id = temp_store.save_topic_briefing(briefing)
    assert rec_id is not None

    # Recupero ultimo report
    report = temp_store.get_topic_briefing()
    assert report is not None
    assert report.topic_title == "AWS AgentCore Architecture"
    assert len(report.executive_summary) == 2
