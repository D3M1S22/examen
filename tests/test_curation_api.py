"""Manual curation over REST and MCP (docs/next_steps/manual_curation/03)."""

import asyncio
import os
import tempfile

import pytest
from starlette.testclient import TestClient

from src.core.config import settings
from src.core.schemas import (
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    VerifiedAction,
)
from src.core.tenancy import tenant_scope
from src.serving.tools import curation_tools
from tests.store_backend import new_store


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = new_store(db_path)
    import src.core.storage as storage_mod

    old = storage_mod._store_instance
    storage_mod._store_instance = s
    yield s
    s.close()
    storage_mod._store_instance = old
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def events(monkeypatch):
    """Records the SSE events of the curation layer instead of broadcasting them."""
    seen = []
    monkeypatch.setattr(curation_tools, "_notify", lambda event_type, data=None, **kw: seen.append((event_type, data)))
    return seen


@pytest.fixture
def enrichments(monkeypatch):
    calls = []
    monkeypatch.setattr(curation_tools, "schedule_enrichment", lambda contact, store: calls.append(contact.id))
    return calls


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(settings, "event_engine_enabled", False)
    monkeypatch.setattr(settings, "backfill_enabled", False)
    from src.serving.mcp_server import create_app

    return TestClient(create_app())


def _routine_and_action(store):
    task = PlannedTask(title="check stove", domain="safety")
    task.id = store.save_planned_task(task)
    action = VerifiedAction(action_type="stove_checked", domain="safety", raw_statement="I checked the stove",
                            confidence=0.95)
    store.save_action(action)
    return task, action


def _contact(store):
    contact = SocialEntity(person_name="Marco Rosi", company_or_role="Engineer at Acme", commitments=[
        SocialCommitment(contact_name="Marco Rosi", debtor="user", description="Send the deck", status="open")])
    contact.id = store.save_social_contact(contact)
    return contact


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

def test_action_edit_and_delete(client, store, events):
    task, action = _routine_and_action(store)
    res = client.put(f"/api/actions/{action.id}", json={"action_type": "Gas stove checked", "domain": "routine"})
    assert res.status_code == 200 and res.json()["action"]["action_type"] == "gas_stove_checked"
    assert client.put(f"/api/actions/{action.id}", json={"domain": "kitchen"}).status_code == 400
    assert client.put(f"/api/actions/{action.id}", json={"raw_statement": "x"}).status_code == 400
    assert client.put(f"/api/actions/{action.id}", content=b"not json").status_code == 400
    assert client.put("/api/actions/missing", json={"domain": "routine"}).status_code == 404

    res = client.delete(f"/api/actions/{action.id}")
    assert res.status_code == 200 and res.json()["reopened_task_id"] == task.id
    assert client.get("/api/actions").json()["count"] == 0
    assert client.delete(f"/api/actions/{action.id}").status_code == 404
    routines = client.get("/api/routines").json()["tasks"]
    assert routines[0]["status"] == "pending" and routines[0]["completion_statement"] is None
    assert [e for e, _ in events] == ["action_updated", "action_deleted", "routine_updated"]


def test_routines_expose_the_completion_statement(client, store):
    task, action = _routine_and_action(store)
    [row] = client.get("/api/routines").json()["tasks"]
    assert row["status"] == "completed" and row["completion_statement"] == "I checked the stove"
    assert row["origin"] == "manual" and row["raw_statement"] is None


def test_routine_edit_is_validated(client, store, events):
    task, _ = _routine_and_action(store)
    res = client.put(f"/api/routines/{task.id}", json={"title": "Check the gas stove", "scheduled_time": "21:30",
                                                        "recurrence": "daily"})
    assert res.status_code == 200
    body = res.json()["task"]
    assert (body["title"], body["scheduled_time"], body["recurrence"]) == ("Check the gas stove", "21:30", "daily")
    assert body["status"] == "completed"  # an edit does not touch the completion
    assert client.put(f"/api/routines/{task.id}", json={"recurrence": "hourly"}).status_code == 400
    assert client.put(f"/api/routines/{task.id}", json={"scheduled_time": "25:99"}).status_code == 400
    assert client.put(f"/api/routines/{task.id}", json={"title": "  "}).status_code == 400
    assert ("routine_updated", body) in events


def test_contact_edit_rename_conflict_and_enrichment(client, store, events, enrichments):
    contact = _contact(store)
    store.save_social_contact(SocialEntity(person_name="Giulia Verdi"))
    store.update_contact_web_profile(contact.id, SocialWebProfile(website_url="https://wrong.example"))

    res = client.put(f"/api/contacts/{contact.id}", json={"contact_info": "marco@acme.example"})
    assert res.json()["enrichment"] == "unchanged" and enrichments == []

    res = client.put(f"/api/contacts/{contact.id}", json={"person_name": "Marco Rossi"})
    assert res.status_code == 200 and res.json()["enrichment"] == "scheduled"
    assert res.json()["contact"]["web_profile"] is None and enrichments == [contact.id]
    assert ("contact_updated", {"contact_id": contact.id, "enrichment": "scheduled"}) in events

    res = client.put(f"/api/contacts/{contact.id}", json={"person_name": "Giulia Verdi"})
    assert res.status_code == 409 and res.json()["code"] == "name_taken"
    assert client.put(f"/api/contacts/{contact.id}", json={"website_url": "ftp://x"}).status_code == 400
    assert client.put("/api/contacts/missing", json={"contact_info": "x"}).status_code == 404
    # A name is not an id: the curation routes never resolve contacts by name
    assert client.put("/api/contacts/Marco Rossi", json={"contact_info": "x"}).status_code == 404


def test_contact_cascade_preview_and_delete(client, store, events):
    contact = _contact(store)
    cascade = client.get(f"/api/contacts/{contact.id}/cascade").json()
    assert [c["description"] for c in cascade["commitments"]] == ["Send the deck"] and len(cascade["tasks"]) == 1

    res = client.delete(f"/api/contacts/{contact.id}")
    assert res.status_code == 200
    assert (res.json()["commitments_deleted"], res.json()["tasks_deleted"]) == (1, 1)
    assert client.get("/api/contacts").json()["count"] == 0
    assert client.get("/api/routines").json()["count"] == 0
    assert client.get(f"/api/contacts/{contact.id}/cascade").status_code == 404
    assert events[-1][0] == "contact_deleted"


def test_event_delete(client, store, events):
    from datetime import datetime

    now = datetime.now().isoformat()
    store.save_session_dossier(SessionDossier(session_id="ev-1", title="Raft", start_time=now,
                                              last_updated_at=now, status="concluded"))
    res = client.delete("/api/sessions/ev-1")
    assert res.status_code == 200 and res.json()["deleted_id"] == "ev-1"
    assert client.get("/api/sessions/ev-1").status_code == 404
    assert client.delete("/api/sessions/ev-1").status_code == 404
    assert ("event_deleted", {"session_id": "ev-1"}) in events


def test_deleting_an_action_unlinks_it_from_its_event(client, store):
    from datetime import datetime

    now = datetime.now().isoformat()
    store.save_session_dossier(SessionDossier(session_id="ev-2", start_time=now, last_updated_at=now))
    action = VerifiedAction(action_type="door_locked", domain="safety", raw_statement="I locked the door",
                            confidence=0.9, session_id="ev-2")
    store.save_action(action)
    store.link_micro_event_to_session("ev-2", MicroEventRef(event_type="action", record_id=action.id,
                                                            timestamp=now, headline="door"))
    assert client.delete(f"/api/actions/{action.id}").status_code == 200
    assert store.get_session_dossier("ev-2").linked_micro_events == []


# ---------------------------------------------------------------------------
# Background re-enrichment (D3)
# ---------------------------------------------------------------------------

def test_enrichment_outcomes(store, events, monkeypatch):
    import src.pipeline.nodes.social_profiler as profiler

    contact = _contact(store)
    profile = SocialWebProfile(website_url="https://acme.example")

    def fake(entity, store=None, force=False):
        store.update_contact_web_profile(entity.id, profile)
        return profile

    monkeypatch.setattr(profiler, "enrich_social_contact_sync", fake)
    curation_tools._enrich(store.get_social_contact(contact.id), store, None)
    assert events[-1][0] == "contact_enriched"
    assert store.get_social_contact(contact.id).web_profile.website_url == "https://acme.example"

    monkeypatch.setattr(profiler, "enrich_social_contact_sync", lambda entity, store=None, force=False: None)
    curation_tools._enrich(store.get_social_contact(contact.id), store, None)
    assert events[-1] == ("contact_enrich_failed", {"contact_id": contact.id, "reason": "insufficient_anchors"})


def test_stale_enrichment_does_not_write(store, events, monkeypatch):
    import src.pipeline.nodes.social_profiler as profiler
    from src.core.schemas import ContactChanges

    contact = _contact(store)
    started_with = store.get_social_contact(contact.id)

    def slow(entity, store=None, force=False):
        # The user renames the contact again while this search runs
        store._store.update_social_contact(contact.id, ContactChanges(person_name="Marco Rossi"))
        store.update_contact_web_profile(entity.id, SocialWebProfile(website_url="https://old-name.example"))
        return SocialWebProfile()

    monkeypatch.setattr(profiler, "enrich_social_contact_sync", slow)
    curation_tools._enrich(started_with, store, None)
    assert store.get_social_contact(contact.id).web_profile is None
    assert events == []


# ---------------------------------------------------------------------------
# MCP tools (D4)
# ---------------------------------------------------------------------------

def test_mcp_delete_needs_confirmation(store, events):
    task, action = _routine_and_action(store)
    preview = curation_tools.delete_action(action.id)
    assert preview["confirm_required"] and preview["would_delete"]["reopens_routine"] == "check stove"
    assert preview["would_delete"]["transcript"] == "I checked the stove"
    assert store.list_recent_actions(limit=5) and events == []

    done = curation_tools.delete_action(action.id, confirm=True)
    assert done["status"] == "deleted" and "reopened" in done["spoken_summary"]
    assert curation_tools.delete_action(action.id, confirm=True)["status"] == "not_found"


def test_mcp_contact_and_event_previews(store, events, enrichments):
    contact = _contact(store)
    preview = curation_tools.delete_contact(contact.id)
    assert len(preview["would_delete"]["commitments"]) == 1 and "1 routine" in preview["spoken_summary"]
    assert store.get_social_contact(contact.id) is not None

    edit = curation_tools.update_contact(contact.id, name="Marco Rossi")
    assert edit["enrichment"] == "scheduled" and "searching the web" in edit["spoken_summary"]
    assert curation_tools.update_contact(contact.id, website_url="not a url")["status"] == "invalid"

    from datetime import datetime

    now = datetime.now().isoformat()
    store.save_session_dossier(SessionDossier(session_id="ev-3", title="Raft", start_time=now, last_updated_at=now))
    from src.ingestion.event_engine import EventEngine

    engine = EventEngine(store=store)
    preview = curation_tools.execute_delete_event("ev-3", engine=engine)
    assert preview["would_delete"]["title"] == "Raft" and store.get_session_dossier("ev-3") is not None
    assert curation_tools.execute_delete_event("ev-3", confirm=True, engine=engine)["status"] == "deleted"


def test_mcp_task_tools(store):
    task, _ = _routine_and_action(store)
    assert curation_tools.update_planned_task(task.id, scheduled_time="07:15")["task"]["scheduled_time"] == "07:15"
    assert curation_tools.delete_planned_task(task.id)["confirm_required"]
    assert curation_tools.delete_planned_task(task.id, confirm=True)["status"] == "deleted"
    assert store.get_planned_task(task.id) is None


def test_mcp_tools_carry_annotations():
    from src.serving.mcp_server import mcp

    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    for name in ("delete_action", "delete_planned_task", "delete_contact", "delete_session_dossier"):
        assert tools[name].annotations.destructiveHint is True
        assert "confirm" in tools[name].inputSchema["properties"]
    for name in ("update_action", "update_planned_task", "update_contact"):
        assert tools[name].annotations.destructiveHint is False and tools[name].annotations.idempotentHint


def test_curation_is_tenant_scoped(monkeypatch, events):
    monkeypatch.setattr(settings, "auth_enabled", True)
    from src.core.storage import get_storage_store

    a, b = "usr_" + "7" * 32, "usr_" + "8" * 32
    with tenant_scope(a):
        contact_id = get_storage_store().save_social_contact(SocialEntity(person_name="Marco Rosi"))
    with tenant_scope(b):
        assert curation_tools.delete_contact(contact_id, confirm=True)["status"] == "not_found"
        assert curation_tools.update_contact(contact_id, name="X")["status"] == "not_found"
    with tenant_scope(a):
        assert get_storage_store().get_social_contact(contact_id).person_name == "Marco Rosi"
