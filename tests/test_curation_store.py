"""Manual curation in the store: edit, revoke, rename, cascades (docs/next_steps/manual_curation/02).

Runs on SQLite and, with EXAMEN_TEST_STORAGE=dynamo, on DynamoDB (tests/store_backend.py).
"""

from datetime import datetime

import pytest

from src.core.schemas import (
    ActionChanges,
    BriefingReport,
    ContactChanges,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialCommitment,
    SocialEntity,
    SocialWebProfile,
    UtteranceChunk,
    VerifiedAction,
)
from src.core.storage.errors import UniqueConflict
from src.pipeline.nodes.persist import derived_entity_id, node_persist
from tests.store_backend import new_store


@pytest.fixture
def store(tmp_path):
    return new_store(str(tmp_path / "curation.db"))


def _action(store, title="stove off", statement="I turned off the stove", **kw):
    action = VerifiedAction(action_type=title, domain="safety", raw_statement=statement, confidence=0.95, **kw)
    store.save_action(action)
    return action


def _contact(store, name="Marco Rosi", role="Engineer at Acme", commitments=()):
    contact = SocialEntity(person_name=name, company_or_role=role, commitments=list(commitments))
    contact.id = store.save_social_contact(contact)
    return contact


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def test_update_action_normalises_title_and_keeps_evidence(store):
    action = _action(store)
    updated = store.update_action(action.id, ActionChanges(action_type="  Gas Stove   OFF ", domain="routine"))
    assert updated.action_type == "gas_stove_off" and updated.domain == "routine"
    assert updated.raw_statement == "I turned off the stove"


def test_update_action_rejects_blank_title_and_unknown_ids(store):
    action = _action(store)
    with pytest.raises(ValueError):
        store.update_action(action.id, ActionChanges(action_type="   "))
    assert store.update_action("missing", ActionChanges(domain="routine")) is None


def test_revoke_hides_the_action_and_reopens_its_routine(store):
    task = PlannedTask(title="check stove", domain="safety", status="pending")
    task.id = store.save_planned_task(task)
    other = PlannedTask(title="lock door", domain="safety", status="pending")
    other.id = store.save_planned_task(other)
    action = _action(store, title="stove_checked", statement="I checked the stove")
    _action(store, title="door_locked", statement="I locked the door")
    assert store.get_planned_task(task.id).status == "completed"

    result = store.revoke_action(action.id)
    assert result.reopened_task_id == task.id
    assert [a.action_type for a in store.list_recent_actions(limit=10)] == ["door_locked"]
    assert store.get_action_status("stove") is None
    reopened = store.get_planned_task(task.id)
    assert reopened.status == "pending" and reopened.completed_at is None and reopened.verified_action_id is None
    assert store.get_planned_task(other.id).status == "completed"  # completed by another action
    assert store.revoke_action(action.id) is None                 # already revoked
    assert store.update_action(action.id, ActionChanges(domain="routine")) is None


def test_revoked_action_is_not_recreated_by_a_rerun_of_its_chunk(store, monkeypatch):
    monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: store)
    source_key = "live:conv-1:utt-7"

    def run():
        node_persist({"action_data": VerifiedAction(action_type="stove_off", domain="safety",
                                                    raw_statement="I turned off the stove", confidence=0.9),
                      "source_key": source_key})

    run()
    action_id = derived_entity_id(source_key, "action")
    assert store.revoke_action(action_id) is not None
    run()  # backfill retry of the same chunk
    assert store.get_verified_action(action_id).is_revoked
    assert store.list_recent_actions(limit=10) == []


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def test_rename_moves_commitments_and_clears_the_web_profile(store):
    contact = _contact(store, commitments=[SocialCommitment(contact_name="Marco Rosi", debtor="user",
                                                            description="Send the deck", status="open")])
    store.update_contact_web_profile(contact.id, SocialWebProfile(website_url="https://wrong.example"))
    assert store.get_social_contact(contact.id).web_profile is not None

    update = store.update_social_contact(contact.id, ContactChanges(person_name="Marco Rossi"))
    assert update.anchors_changed and update.renamed_from == "Marco Rosi"
    renamed = store.get_social_contact(contact.id)
    assert renamed.person_name == "Marco Rossi"
    assert renamed.web_profile is None and renamed.website_url is None
    assert store.get_social_contact("Marco Rossi").id == contact.id
    assert store.get_social_contact("Marco Rosi") is None
    assert [c.description for c in store.list_social_commitments(contact_name="Marco Rossi")] == ["Send the deck"]
    assert store.list_social_commitments(contact_name="Marco Rosi") == []
    assert [c.description for c in renamed.commitments] == ["Send the deck"]
    # A later extraction of the same commitment under the new name is not a duplicate
    store.save_social_commitment(SocialCommitment(contact_name="Marco Rossi", debtor="user",
                                                  description="Send the deck", status="open"))
    assert len(store.list_social_commitments(contact_name="Marco Rossi")) == 1


def test_non_anchor_edit_keeps_the_web_profile(store):
    contact = _contact(store)
    store.update_contact_web_profile(contact.id, SocialWebProfile(website_url="https://acme.example"))
    update = store.update_social_contact(contact.id, ContactChanges(contact_info="marco@acme.example",
                                                                    key_topics=["robotics", " "]))
    assert not update.anchors_changed and update.renamed_from is None
    stored = store.get_social_contact(contact.id)
    assert stored.web_profile is not None and stored.contact_info == "marco@acme.example"
    assert stored.key_topics == ["robotics"]


def test_new_website_survives_an_anchor_change(store):
    contact = _contact(store)
    update = store.update_social_contact(contact.id, ContactChanges(company_or_role="CTO at Beta",
                                                                    website_url="https://beta.example"))
    assert update.anchors_changed
    assert store.get_social_contact(contact.id).website_url == "https://beta.example"


def test_rename_onto_another_contact_is_refused(store):
    contact = _contact(store)
    _contact(store, name="Giulia Verdi", role="Designer")
    with pytest.raises(UniqueConflict):
        store.update_social_contact(contact.id, ContactChanges(person_name="giulia verdi"))
    assert store.get_social_contact(contact.id).person_name == "Marco Rosi"
    assert store.get_social_contact("Giulia Verdi").person_name == "Giulia Verdi"
    assert store.update_social_contact("missing", ContactChanges(contact_info="x")) is None


def test_delete_contact_cascades_to_commitments_and_their_tasks(store):
    contact = _contact(store, commitments=[
        SocialCommitment(contact_name="Marco Rosi", debtor="user", description="Send the deck", status="open"),
        SocialCommitment(contact_name="Marco Rosi", debtor="contact", description="Share the API docs",
                         status="open"),
    ])
    manual = PlannedTask(title="Send the deck to the team", domain="work_task")
    manual.id = store.save_planned_task(manual)
    scheduled = [t for t in store.list_planned_tasks() if t.origin == "social_commitment"]
    assert len(scheduled) == 1

    deleted = store.delete_social_contact(contact.id)
    assert (deleted.commitments_deleted, deleted.tasks_deleted) == (2, 1)
    assert store.get_social_contact(contact.id) is None
    assert store.list_social_commitments(contact_name="Marco Rosi") == []
    assert [t.id for t in store.list_planned_tasks()] == [manual.id]
    assert store.delete_social_contact(contact.id) is None
    # The name is free again
    assert store.get_social_contact(_contact(store).id).person_name == "Marco Rosi"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _event(store, session_id="ev-1"):
    now = datetime.now().isoformat()
    store.save_session_dossier(SessionDossier(session_id=session_id, title="Raft lecture", start_time=now,
                                              last_updated_at=now, status="concluded"))
    for i in range(3):
        chunk = UtteranceChunk(chunk_id=f"{session_id}-c{i}", conversation_uuid="conv-1", text=f"Raft part {i}",
                               timestamp=now)
        store.append_session_chunk(chunk, session_id, segment_id="seg-1", on_topic=True)
    store.patch_utterance_speaker(f"{session_id}-c0", "Prof", "other")
    store.save_topic_briefing(BriefingReport(topic_title="Raft", context_type="academic_lecture",
                                             session_id=session_id, kind="segment"))
    final_id = store.save_topic_briefing(BriefingReport(topic_title="Raft final", context_type="academic_lecture",
                                                        session_id=session_id, kind="final"))
    dossier = store.get_session_dossier(session_id)
    dossier.final_briefing_id = final_id
    store.save_session_dossier(dossier)


def test_delete_event_removes_log_and_briefings_but_keeps_results(store):
    _event(store)
    _event(store, "ev-2")
    action = _action(store, session_id="ev-1")
    store.link_micro_event_to_session("ev-1", MicroEventRef(event_type="action", record_id=action.id,
                                                            timestamp=action.timestamp, headline="stove"))

    deleted = store.delete_event("ev-1")
    assert (deleted.briefings_deleted, deleted.chunks_deleted, deleted.title) == (2, 3, "Raft lecture")
    assert store.get_session_dossier("ev-1") is None
    assert store.list_session_chunks("ev-1") == []
    assert store.list_briefings_for_session("ev-1") == []
    assert store.get_verified_action(action.id) is not None
    assert len(store.list_session_chunks("ev-2")) == 3 and len(store.list_briefings_for_session("ev-2")) == 2
    assert store.delete_event("ev-1") is None


def test_unlink_micro_event(store):
    _event(store)
    for rid in ("a1", "a2"):
        store.link_micro_event_to_session("ev-1", MicroEventRef(event_type="action", record_id=rid,
                                                                timestamp=datetime.now().isoformat(), headline=rid))
    assert store.unlink_micro_event("ev-1", "action", "a1")
    assert not store.unlink_micro_event("ev-1", "action", "a1")
    assert not store.unlink_micro_event("missing", "action", "a2")
    assert [r.record_id for r in store.get_session_dossier("ev-1").linked_micro_events] == ["a2"]
    # A save from a stale copy of the dossier does not bring the link back (DynamoDB link versions)
    dossier = store.get_session_dossier("ev-1")
    dossier.title = "Renamed"
    store.save_session_dossier(dossier)
    assert [r.record_id for r in store.get_session_dossier("ev-1").linked_micro_events] == ["a2"]
