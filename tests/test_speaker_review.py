"""Speaker review: results of untagged speech wait for the owner (docs/next_steps/speaker_review/).

Runs on SQLite and, with EXAMEN_TEST_STORAGE=dynamo, on DynamoDB (tests/store_backend.py).
"""

import asyncio
import os
import tempfile

import pytest
from starlette.testclient import TestClient

from src.core.config import settings
from src.core.schemas import PlannedTask, SpeakerAttribution, VerifiedAction
from src.core.tenancy import tenant_scope
from src.ingestion.bee_identity import WearerIdentity
from src.ingestion.coverage import live_source_key
from src.ingestion.event_engine import EventEngine
from src.ingestion.orchestrator import BeeStreamOrchestrator
from src.pipeline.nodes.persist import derived_entity_id, needs_review, node_persist
from src.serving.tools import curation_tools
from src.serving.tools.action_tools import execute_get_daily_actions_recap, execute_get_upcoming_tasks
from tests.store_backend import new_store

UNTAGGED = {"speaker_role": "unknown", "speaker_source": "untagged"}
OWNER = {"speaker_role": "user", "speaker_source": "bee_voice_id", "speaker": "Ada", "speaker_score": 0.8}


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = new_store(str(tmp_path / "review.db"))
    monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: s)
    import src.core.storage as storage_mod

    monkeypatch.setattr(storage_mod, "_store_instance", s)
    return s


@pytest.fixture
def events(monkeypatch):
    seen = []
    monkeypatch.setattr(curation_tools, "_notify", lambda event_type, data=None, **kw: seen.append((event_type, data)))
    return seen


def _persist(store, key, speaker, action=True, task=True, auto_accept=False, statement="I locked the front door"):
    state = {"source_key": key, "auto_accept_untagged": auto_accept, **speaker}
    if action:
        state["action_data"] = VerifiedAction(action_type="door_locked", domain="safety", raw_statement=statement,
                                              confidence=0.9)
    if task:
        state["scheduled_task"] = PlannedTask(title="Push the branch", origin="ambient_voice",
                                              raw_statement="I need to push the branch tonight")
    node_persist(state)
    return derived_entity_id(key, "action"), derived_entity_id(key, "task")


def _routine(store, title="lock the front door"):
    task = PlannedTask(title=title, domain="safety")
    task.id = store.save_planned_task(task)
    return task


# ---------------------------------------------------------------------------
# T-SR-1: the rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("speaker, auto, expected", [
    (None, False, False),                                                             # dashboard / MCP entry
    (SpeakerAttribution(role="user", source="bee_voice_id"), False, False),
    (SpeakerAttribution(role="contact", name="Marco", source="bee_voice_id"), False, False),
    (SpeakerAttribution(role="unknown", source="untagged"), False, True),
    (SpeakerAttribution(role="unknown", source="untagged"), True, False),             # the owner opted in
    (SpeakerAttribution(role="unknown", source="untagged", addressed_to_user=True), False, False),  # R2
    (SpeakerAttribution(role="unknown", source="internal"), False, False),             # simulator
    (SpeakerAttribution(role="user", source="history_name"), False, False),
])
def test_needs_review_rule(speaker, auto, expected):
    assert needs_review(speaker, auto) is expected


# ---------------------------------------------------------------------------
# T-SR-2/3: persist
# ---------------------------------------------------------------------------

def test_untagged_action_waits_and_completes_nothing(store):
    routine = _routine(store)
    action_id, task_id = _persist(store, "live:c:u1", UNTAGGED)
    assert store.list_recent_actions(limit=10) == []
    assert store.get_action_status("door") is None
    assert [a.id for a in store.list_review_actions()] == [action_id]
    assert store.get_planned_task(routine.id).status == "pending"
    assert store.get_planned_task(task_id).status == "review"
    assert task_id not in {t["id"] for t in execute_get_upcoming_tasks(store=store)["tasks"]}
    assert routine.id in {t["id"] for t in execute_get_upcoming_tasks(store=store)["tasks"]}


def test_owner_and_opt_in_skip_review(store):
    _routine(store)
    action_id, task_id = _persist(store, "live:c:u2", OWNER)
    assert store.list_review_actions() == [] and store.get_planned_task(task_id).status == "pending"
    a2, t2 = _persist(store, "live:c:u3", UNTAGGED, auto_accept=True, statement="I locked the back door")
    assert store.get_planned_task(t2).status == "pending" and store.list_review_actions() == []
    assert store.get_verified_action(a2).speaker.source == "untagged"


def test_request_naming_the_owner_skips_review(store):
    state = {"source_key": "live:c:u4", **UNTAGGED,
             "scheduled_task": PlannedTask(title="Push the branch", origin="ambient_voice",
                                           speaker=SpeakerAttribution(role="unknown", source="untagged",
                                                                      addressed_to_user=True))}
    node_persist(state)
    assert store.get_planned_task(derived_entity_id("live:c:u4", "task")).status == "pending"


# ---------------------------------------------------------------------------
# T-SR-5/6: accept and dismiss
# ---------------------------------------------------------------------------

def test_accept_runs_the_routine_matching_it_skipped(store, events):
    routine = _routine(store)
    action_id, task_id = _persist(store, "live:c:u5", UNTAGGED)
    out = curation_tools.execute_accept("action", action_id, store=store)
    assert out["action"]["speaker"]["source"] == "user_confirmed"
    assert store.get_planned_task(routine.id).status == "completed"
    assert store.get_verified_action(action_id).matched_task_id == routine.id
    assert [a.id for a in store.list_recent_actions(limit=5)] == [action_id]
    curation_tools.execute_accept("task", task_id, store=store)
    assert store.get_planned_task(task_id).status == "pending"
    with pytest.raises(curation_tools.CurationError) as err:
        curation_tools.execute_accept("task", task_id, store=store)
    assert err.value.status == 409
    assert ("review_resolved", {"kind": "action", "id": action_id, "outcome": "accepted"}) in events


def test_dismissed_items_never_come_back(store, events):
    action_id, task_id = _persist(store, "live:c:u6", UNTAGGED)
    curation_tools.execute_dismiss("action", action_id, store=store)
    curation_tools.execute_dismiss("task", task_id, store=store)
    assert store.list_review_actions() == [] and store.list_planned_tasks(status="review") == []
    assert [t.id for t in store.list_planned_tasks()] == []
    _persist(store, "live:c:u6", UNTAGGED)  # backfill retry of the same sentence
    assert store.list_review_actions() == [] and store.get_planned_task(task_id).status == "dismissed"
    assert store.get_verified_action(action_id).is_revoked


def test_deleting_a_review_routine_dismisses_it(store, events):
    _, task_id = _persist(store, "live:c:u7", UNTAGGED, action=False)
    curation_tools.execute_delete_task(task_id, confirm=True, store=store)
    assert store.get_planned_task(task_id).status == "dismissed"


def test_accept_all_and_counters(store, events):
    _persist(store, "live:c:u8", UNTAGGED)
    _persist(store, "live:c:u9", UNTAGGED, statement="I locked the garage")
    recap = execute_get_daily_actions_recap(store=store)
    assert recap["summary"]["to_confirm"] == 4 and recap["summary"]["planned_pending"] == 0
    assert curation_tools.execute_list_review(store=store)["count"] == 4
    assert curation_tools.execute_accept_all(store=store)["accepted"] == 4
    assert curation_tools.execute_list_review(store=store)["count"] == 0


# ---------------------------------------------------------------------------
# T-SR-7: late tags
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator(store):
    engine = EventEngine(store=store)
    orch = BeeStreamOrchestrator(store=store, engine=engine, identity=WearerIdentity("Ada"))
    orch.engine_enabled = False
    return orch


def test_late_owner_tag_accepts(store, orchestrator, events):
    routine = _routine(store)
    key = live_source_key("uuid-1", "u10")
    action_id, task_id = _persist(store, key, UNTAGGED)
    match = orchestrator.identity.match_tag(person_id=42, name="Ada", score=0.8)
    assert orchestrator.reconcile_speaker(key, match) == {"actions": 1, "tasks": 1}
    action = store.get_verified_action(action_id)
    assert not action.needs_review and action.speaker.source == "bee_name"
    assert store.get_planned_task(routine.id).status == "completed"
    assert store.get_planned_task(task_id).status == "pending"


def test_late_contact_tag_dismisses_but_keeps_requests(store, orchestrator, events):
    key = live_source_key("uuid-1", "u11")
    action_id, task_id = _persist(store, key, UNTAGGED)
    match = orchestrator.identity.match_tag(person_id=77, name="Marco")
    orchestrator.reconcile_speaker(key, match)
    assert store.get_verified_action(action_id).is_revoked
    assert store.get_planned_task(task_id).status == "dismissed"

    key2 = live_source_key("uuid-1", "u12")
    node_persist({"source_key": key2, **UNTAGGED, "scheduled_task": PlannedTask(
        title="Push the branch", origin="ambient_voice", raw_statement="Ada, can you push the branch tonight?")})
    task2 = derived_entity_id(key2, "task")
    assert store.get_planned_task(task2).status == "review"
    orchestrator.reconcile_speaker(key2, orchestrator.identity.match_tag(person_id=77, name="Marco"))
    stored = store.get_planned_task(task2)
    assert stored.status == "pending" and stored.speaker.addressed_to_user and stored.speaker.name == "Marco"


# ---------------------------------------------------------------------------
# T-SR-8/9/10/11: REST, MCP, setting, status
# ---------------------------------------------------------------------------

@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(settings, "event_engine_enabled", False)
    monkeypatch.setattr(settings, "backfill_enabled", False)
    from src.serving.mcp_server import create_app

    return TestClient(create_app())


def test_review_routes_and_status(client, store):
    action_id, task_id = _persist(store, "live:c:u13", UNTAGGED)
    queue = client.get("/api/review").json()
    assert queue["count"] == 2 and queue["tasks"][0]["status"] == "review"
    stats = client.get("/api/status").json()["stats"]
    assert (stats["planned_tasks_pending"], stats["planned_tasks_review"], stats["actions_review"]) == (0, 1, 1)
    assert client.post(f"/api/review/action/{action_id}/accept").status_code == 200
    assert client.post(f"/api/review/action/{action_id}/accept").status_code == 409
    assert client.post(f"/api/review/task/{task_id}/dismiss").status_code == 200
    assert client.post("/api/review/task/missing/accept").status_code == 404
    assert client.post(f"/api/review/note/{task_id}/accept").status_code == 400
    assert client.post(f"/api/review/task/{task_id}/maybe").status_code == 400
    assert client.get("/api/review").json()["count"] == 0
    assert all(t["status"] != "dismissed" for t in client.get("/api/routines").json()["tasks"])


def test_routine_edit_cannot_reach_review_states(client, store):
    _, task_id = _persist(store, "live:c:u14", UNTAGGED, action=False)
    assert client.put(f"/api/routines/{task_id}", json={"status": "pending"}).status_code == 409
    assert client.put(f"/api/routines/{task_id}", json={"title": "Push main"}).status_code == 200
    other = _routine(store)
    assert client.put(f"/api/routines/{other.id}", json={"status": "review"}).status_code == 400


def test_mcp_review_tools(store, events):
    action_id, task_id = _persist(store, "live:c:u15", UNTAGGED)
    listed = curation_tools.list_items_to_review()
    assert listed["count"] == 2 and "2 things to confirm" in listed["spoken_summary"]
    assert curation_tools.accept_item("task", task_id)["status"] == "accepted"
    assert curation_tools.dismiss_item("action", action_id)["status"] == "dismissed"
    assert curation_tools.dismiss_item("action", action_id)["status"] == "not_found"
    from src.serving.mcp_server import mcp

    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert tools["list_items_to_review"].annotations.readOnlyHint is True
    assert tools["dismiss_item"].annotations.destructiveHint is False


def test_setting_single_user_mode(monkeypatch):
    from src.core.speaker_prefs import auto_accept_untagged

    assert auto_accept_untagged() is False
    monkeypatch.setattr(settings, "speaker_auto_accept_untagged", True)
    assert auto_accept_untagged() is True


def test_setting_per_user_reaches_the_payload(monkeypatch, store):
    from src.core.auth import get_auth_store
    from src.core.speaker_prefs import auto_accept_untagged

    monkeypatch.setattr(settings, "auth_enabled", True)
    user = get_auth_store().create_user("ada@example.com", "correct horse battery staple")
    assert auto_accept_untagged(user.id) is False
    get_auth_store().set_auto_accept_untagged(user.id, True)
    assert get_auth_store().get_user(user.id).auto_accept_untagged is True
    with tenant_scope(user.id):
        assert auto_accept_untagged() is True

    import importlib
    import sys

    importlib.import_module("src.pipeline.app")
    seen = {}
    monkeypatch.setattr(sys.modules["src.pipeline.app"], "_run_pipeline",
                        lambda payload, context=None: seen.update(payload) or {"status": "ok"})
    from src.pipeline.remote import invoke_pipeline

    with tenant_scope(user.id):
        invoke_pipeline({"raw_transcript": "x", "auto_accept_untagged": True})
    assert seen["auto_accept_untagged"] is True


def test_account_patch_validates_the_setting(monkeypatch, store):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "event_engine_enabled", False)
    monkeypatch.setattr(settings, "backfill_enabled", False)
    from src.core.auth import passwords

    monkeypatch.setattr(passwords, "_LOG2_N", 10)
    from src.serving.mcp_server import create_app

    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"email": "ada@example.com", "password": "correct horse battery",
                                           "display_name": "Ada", "privacy_consent": True})
    if r.status_code == 403:  # closed registration: create the account directly and sign in
        from src.core.auth import get_auth_store

        get_auth_store().create_user("ada@example.com", "correct horse battery", consent_version="1")
        c.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse battery"})
    assert c.patch("/api/account", json={"auto_accept_untagged": "yes"}).status_code == 400
    assert c.patch("/api/account", json={"auto_accept_untagged": True}).json()["user"]["auto_accept_untagged"] is True
