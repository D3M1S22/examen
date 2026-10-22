"""Speaker identity: Bee `tagged-utterance` bound to the account's wearer (docs/next_steps/08_speaker_identity.md)."""

import asyncio
import importlib
import sys
from datetime import datetime

import pytest

from src.core.schemas import ChunkClassification, PlannedTask, SpeakerAttribution, VerifiedAction
from src.ingestion.bee_identity import UNTAGGED, WearerIdentity
from src.ingestion.coverage import live_source_key
from src.ingestion.event_engine import EngineConfig, EventEngine
from src.ingestion.orchestrator import BeeStreamOrchestrator
from src.pipeline.nodes.action_state import node_extract_action
from src.pipeline.nodes.persist import derived_entity_id, node_persist, speaker_from_state
from src.pipeline.nodes.scheduler import node_extract_scheduled_task
from src.serving.tools.action_tools import execute_verify_action_status, speaker_label
from tests.store_backend import new_store


# ---------------------------------------------------------------------------
# Wearer matching
# ---------------------------------------------------------------------------

def test_first_name_match_binds_the_person_id():
    who = WearerIdentity("Ada")
    first = who.match_tag(person_id=42, name="Ada", score=0.79)
    assert (first.role, first.source, first.person_id) == ("user", "bee_name", "42")
    assert who.person_ids == {"42"}
    # Later tags are matched by id, even without (or with a changed) first name
    again = who.match_tag(person_id="42", name="", score=0.6)
    assert (again.role, again.source) == ("user", "bee_voice_id")
    assert who.wearer_tags == 2 and who.tags_seen == 2


def test_namesake_with_another_person_id_is_a_contact():
    who = WearerIdentity("Ada")
    who.match_tag(person_id=42, name="Ada")
    other = who.match_tag(person_id=77, name="Ada", score=0.7)
    assert (other.role, other.source) == ("contact", "bee_voice_id")
    assert who.person_ids == {"42"}


def test_account_id_is_not_a_person_id():
    # Observed on a device (2026-10-22): the wearer's person_id differs from the `bee me` id
    who = WearerIdentity("")
    who.apply_profile({"id": 50000, "first_name": "Ada", "last_name": "L"})
    assert who.first_name == "Ada" and who.account_id == "50000"
    contact = who.match_tag(person_id=50000, name="Marco")
    assert contact.role == "contact"
    match = who.match_tag(person_id=42, name="Ada")
    assert (match.role, match.source) == ("user", "bee_name") and who.person_ids == {"42"}


def test_other_name_is_contact_and_never_bound():
    who = WearerIdentity("Ada")
    other = who.match_tag(person_id=77, name="Marco")
    assert other.role == "contact" and who.person_ids == set()
    # A later "Ada" tag on Marco's person id does not turn Marco into the wearer
    assert who.match_tag(person_id=77, name="Ada").role == "user"
    assert who.person_ids == set()


def test_unknown_wearer_keeps_named_tags_unknown():
    who = WearerIdentity("")
    assert who.match_tag(person_id=1, name="Ada").role == "unknown"
    assert who.match_name("Unknown") is UNTAGGED
    assert who.match_name("user").role == "user"


def test_status_reports_binding():
    who = WearerIdentity("Ada")
    assert who.status()["wearer_voice_id_bound"] is False
    who.match_tag(person_id=42, name="Ada")
    status = who.status()
    assert status["wearer_voice_id_bound"] and status["wearer_tags"] == 1 and status["wearer_identity_known"]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return new_store(str(tmp_path / "speaker.db"))


@pytest.fixture
def orchestrator(store, monkeypatch):
    engine = EventEngine(store=store, config=EngineConfig(min_segment_words=5))
    orch = BeeStreamOrchestrator(store=store, engine=engine, identity=WearerIdentity("Ada"))
    orch.engine_enabled = False
    sent = []
    importlib.import_module("src.pipeline.app")
    monkeypatch.setattr(sys.modules["src.pipeline.app"], "agent_invocation",
                        lambda payload: sent.append(payload) or {"ok": True})
    orch.sent = sent  # type: ignore[attr-defined]

    async def _classify(transcript, active_tasks=None, prior_context=None):
        return ChunkClassification(categories=["action"], confidence=0.9, summary_hint="test")
    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", _classify)
    return orch


def _utterance(uid, conv="uuid-1", text="I just locked the front door."):
    return {"id": uid, "text": text, "conversation_uuid": conv, "received_at": datetime.now().isoformat()}


def _tag(uid, name="Ada", person_id=42, score=0.81, conv="uuid-1"):
    return {"utterance_id": uid, "person_id": person_id, "person_first_name": name, "speaker_score": score,
            "conversation_uuid": conv}


@pytest.mark.asyncio
async def test_tag_during_wait_reaches_the_pipeline_with_score_and_source(orchestrator):
    orchestrator._concurrent_reader = True
    task = asyncio.create_task(orchestrator.process_incoming_utterance(_utterance("u1")))
    await asyncio.sleep(0.05)
    orchestrator.on_tagged_utterance(_tag("u1"))
    await task
    payload = orchestrator.sent[-1]
    assert payload["speaker_role"] == "user" and payload["speaker"] == "Ada"
    assert payload["speaker_score"] == 0.81 and payload["speaker_source"] == "bee_name"
    assert orchestrator.get_status_dict()["wearer_voice_id_bound"] is True
    assert orchestrator.get_status_dict()["speaker_tag_lag_seconds"] is not None


@pytest.mark.asyncio
async def test_tag_received_before_the_utterance_is_applied(orchestrator):
    orchestrator.on_tagged_utterance(_tag("u2"))
    await orchestrator.process_incoming_utterance(_utterance("u2"))
    assert orchestrator.sent[-1]["speaker_source"] == "bee_name"


@pytest.mark.asyncio
async def test_untagged_payload_says_untagged(orchestrator):
    await orchestrator.process_incoming_utterance(_utterance("u3"))
    payload = orchestrator.sent[-1]
    assert payload["speaker_role"] == "unknown" and payload["speaker_source"] == "untagged"


@pytest.mark.asyncio
async def test_simulator_speaker_role_is_internal(orchestrator):
    data = _utterance("u4") | {"speaker_role": "user"}
    await orchestrator.process_incoming_utterance(data)
    assert orchestrator.sent[-1]["speaker_source"] == "internal"


def _seed_action_and_task(store, uid, conv="uuid-1"):
    key = live_source_key(conv, uid)
    task = PlannedTask(id="task-door", title="lock the front door", domain="safety")
    store.save_planned_task(task)
    action_id = derived_entity_id(key, "action")
    store.save_action(VerifiedAction(id=action_id, action_type="door_locked", domain="safety",
                                     raw_statement="I just locked the front door.", confidence=0.95,
                                     matched_task_id="task-door", source_key=key))
    return key, action_id


@pytest.mark.asyncio
async def test_late_contact_tag_revokes_the_action_and_reopens_the_task(orchestrator, store):
    await orchestrator.process_incoming_utterance(_utterance("u5"))
    key, action_id = _seed_action_and_task(store, "u5")  # what the pipeline persisted
    assert store.get_planned_task("task-door").status == "completed"
    orchestrator.identity.match_tag(person_id=42, name="Ada")  # wearer's voice id known
    orchestrator.on_tagged_utterance(_tag("u5", name="Marco", person_id=77, score=0.7))
    await asyncio.gather(*orchestrator._side_tasks)
    action = store.get_verified_action(action_id)
    assert action.is_revoked and action.speaker.role == "contact" and action.speaker.name == "Marco"
    task = store.get_planned_task("task-door")
    assert task.status == "pending" and task.verified_action_id is None
    assert store.get_action_status("door") is None


@pytest.mark.asyncio
async def test_late_wearer_tag_marks_the_action_as_voice_verified(orchestrator, store):
    await orchestrator.process_incoming_utterance(_utterance("u6"))
    _, action_id = _seed_action_and_task(store, "u6")
    orchestrator.on_tagged_utterance(_tag("u6"))
    await asyncio.gather(*orchestrator._side_tasks)
    action = store.get_verified_action(action_id)
    assert not action.is_revoked and action.speaker.role == "user" and action.speaker.score == 0.81
    assert store.get_planned_task("task-door").status == "completed"
    card = execute_verify_action_status("door", store=store)
    assert card["spoken_by"] == "you (voice match)" and card["voice_verified"] is True


def test_reconcile_cancels_a_task_voiced_by_a_contact(orchestrator, store):
    key = live_source_key("uuid-1", "u7")
    store.save_planned_task(PlannedTask(id=derived_entity_id(key, "task"), title="call the dentist",
                                        origin="ambient_voice", source_key=key))
    match = orchestrator.identity.match_tag(person_id=77, name="Marco")
    assert orchestrator.reconcile_speaker(key, match) == {"actions": 0, "tasks": 1}
    task = store.get_planned_task(derived_entity_id(key, "task"))
    assert task.status == "cancelled" and task.speaker.name == "Marco"


@pytest.mark.asyncio
async def test_tag_for_a_noop_utterance_touches_nothing(orchestrator, store, monkeypatch):
    async def _noop(transcript, active_tasks=None, prior_context=None):
        return ChunkClassification(categories=["noop"], confidence=0.9, summary_hint="")
    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", _noop)
    await orchestrator.process_incoming_utterance(_utterance("u8"))
    orchestrator.on_tagged_utterance(_tag("u8"))
    assert orchestrator.sent == []
    assert orchestrator.ring_buffer.get_last_chunk("uuid-1").speaker_role == "user"


# ---------------------------------------------------------------------------
# Pipeline and storage
# ---------------------------------------------------------------------------

def test_contact_speech_does_not_verify_actions_or_schedule_tasks(monkeypatch):
    state = {"raw_transcript": "I just locked the front door.", "speaker_role": "contact", "speaker": "Marco"}
    assert node_extract_action(state) == {"action_data": None}
    state = {"raw_transcript": "Remind me to call the dentist tomorrow at ten.", "speaker_role": "contact"}
    assert node_extract_scheduled_task(state) == {"scheduled_task": None}


def test_speaker_from_state():
    assert speaker_from_state({}) is None
    s = speaker_from_state({"speaker_role": "user", "speaker": "Ada", "speaker_score": 0.8,
                            "speaker_source": "bee_voice_id"})
    assert s == SpeakerAttribution(role="user", name="Ada", score=0.8, source="bee_voice_id")
    unknown = speaker_from_state({"speaker_role": "unknown", "speaker_source": "untagged", "speaker": "x"})
    assert unknown.name is None and unknown.source == "untagged"
    assert speaker_from_state({"speaker_role": "user"}).source == "internal"


def test_persist_records_the_speaker(store, monkeypatch):
    monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: store)
    key = live_source_key("uuid-9", "u9")
    action = VerifiedAction(action_type="medication_taken", domain="routine",
                            raw_statement="I took my medication this morning.", confidence=0.95)
    task = PlannedTask(title="call Marco", origin="ambient_voice", scheduled_time="10:00")
    node_persist({"action_data": action, "scheduled_task": task, "source_key": key, "speaker": "Ada",
                  "speaker_role": "user", "speaker_score": 0.74, "speaker_source": "bee_voice_id",
                  "timestamp": datetime.now().isoformat()})
    saved = store.get_verified_action(derived_entity_id(key, "action"))
    assert saved.speaker.role == "user" and saved.speaker.score == 0.74
    saved_task = store.get_planned_task(derived_entity_id(key, "task"))
    assert saved_task.speaker.source == "bee_voice_id"
    listed = store.list_recent_actions(limit=5)
    assert listed[0].speaker is not None


def test_action_speaker_round_trip_and_update(store):
    store.save_action(VerifiedAction(id="a1", action_type="stove_off", domain="safety", raw_statement="stove off",
                                     confidence=0.9))
    assert store.get_verified_action("a1").speaker is None
    assert store.set_action_speaker("a1", SpeakerAttribution(role="user", source="bee_name", score=0.6)) is True
    assert store.get_verified_action("a1").speaker.score == 0.6
    assert store.set_action_speaker("missing", SpeakerAttribution()) is False
    task = PlannedTask(id="t1", title="unplug iron", speaker=SpeakerAttribution(role="user", source="bee_name"))
    store.save_planned_task(task)
    task.speaker = SpeakerAttribution(role="contact", name="Marco", source="bee_voice_id")
    store.update_planned_task(task)
    assert store.get_planned_task("t1").speaker.name == "Marco"


def test_verified_action_schema_hides_speaker_from_the_model():
    assert "speaker" not in VerifiedAction.model_json_schema().get("properties", {})


@pytest.mark.parametrize("speaker,label", [
    (None, None),
    (SpeakerAttribution(role="user", source="bee_voice_id"), "you (voice match)"),
    (SpeakerAttribution(role="user", source="internal"), "you"),
    (SpeakerAttribution(role="contact", name="Marco", source="bee_name"), "Marco"),
    (SpeakerAttribution(role="unknown"), "unidentified speaker"),
])
def test_speaker_label(speaker, label):
    assert speaker_label(speaker) == label


@pytest.mark.asyncio
async def test_tag_arriving_while_the_pipeline_runs_is_applied_after_it(orchestrator, store, monkeypatch):
    import time as _time

    def slow_pipeline(payload):
        _seed_action_and_task(store, "u10")  # the pipeline persists the action with an unknown speaker
        _time.sleep(0.3)
        return {"ok": True}
    monkeypatch.setattr(sys.modules["src.pipeline.app"], "agent_invocation", slow_pipeline)
    task = asyncio.create_task(orchestrator.process_incoming_utterance(_utterance("u10")))
    await asyncio.sleep(0.1)
    orchestrator.on_tagged_utterance(_tag("u10"))
    await task
    action = store.get_verified_action(derived_entity_id(live_source_key("uuid-1", "u10"), "action"))
    assert action.speaker is not None and action.speaker.role == "user"


# ---------------------------------------------------------------------------
# Requests addressed to the owner ("Damiano, remember to ...")
# ---------------------------------------------------------------------------

@pytest.fixture
def heuristic(monkeypatch):
    from src.core.config import settings
    monkeypatch.setattr(settings, "mock_ai", True)


def _task(state):
    return node_extract_scheduled_task(state)["scheduled_task"]


def test_untagged_request_naming_the_owner_is_an_asked_task(heuristic):
    task = _task({"raw_transcript": "Damiano pls remember to launch the washing machine tonight",
                  "speaker_role": "unknown", "speaker_source": "untagged", "wearer_name": "Damiano"})
    assert task.title.lower().startswith("launch the washing machine")
    assert task.speaker.addressed_to_user and task.speaker.role == "unknown" and task.speaker.name is None


def test_contact_request_is_the_owners_task_asked_by_them(heuristic):
    task = _task({"raw_transcript": "Can you call me tomorrow at 10 am", "speaker_role": "contact",
                  "speaker": "Marco", "speaker_score": 0.7, "speaker_source": "bee_voice_id", "wearer_name": "Damiano"})
    assert "Marco" in task.title
    assert task.speaker == SpeakerAttribution(role="contact", name="Marco", score=0.7, source="bee_voice_id",
                                              addressed_to_user=True)


def test_contact_own_plan_is_not_the_owners_task(heuristic):
    assert _task({"raw_transcript": "Please remind me to call my mum tomorrow", "speaker_role": "contact",
                  "speaker": "Marco", "wearer_name": "Damiano"}) is None


def test_owner_talking_to_themselves_is_not_a_request(heuristic):
    task = _task({"raw_transcript": "Damiano, remember to buy milk tomorrow", "speaker_role": "user",
                  "speaker": "Damiano", "speaker_source": "bee_name", "wearer_name": "Damiano"})
    assert task is not None and task.speaker is None


class _FakeExtractor:
    def __init__(self, result):
        self.result, self.messages = result, None

    def invoke(self, messages):
        self.messages = messages
        return self.result


def _llm(monkeypatch, result):
    from src.core.config import settings
    from src.core.schemas import ScheduledTaskExtraction
    import src.pipeline.nodes.scheduler as scheduler

    fake = _FakeExtractor(ScheduledTaskExtraction(**result))
    monkeypatch.setattr(settings, "mock_ai", False)
    monkeypatch.setattr(scheduler, "has_active_model_credentials", lambda provider: True)
    monkeypatch.setattr(scheduler, "_get_scheduled_task_extractor", lambda: fake)
    return fake


def test_llm_sees_the_speaker_and_can_drop_a_contacts_own_plan(monkeypatch):
    fake = _llm(monkeypatch, {"title": "Call mum", "for_owner": False})
    assert _task({"raw_transcript": "Remind me to call my mum", "speaker_role": "contact", "speaker": "Marco",
                  "wearer_name": "Damiano"}) is None
    system = fake.messages[0].content
    assert "NOT the device owner" in system and "Marco" in system and "Damiano" in system


def test_llm_request_from_an_unidentified_speaker(monkeypatch):
    fake = _llm(monkeypatch, {"title": "Start the washing machine", "for_owner": True, "requested_by": "Giulia"})
    task = _task({"raw_transcript": "Damiano, start the washing machine please, Giulia here",
                  "speaker_role": "unknown", "speaker_source": "untagged", "wearer_name": "Damiano"})
    assert task.speaker.addressed_to_user and task.speaker.name == "Giulia"
    assert "not identified" in fake.messages[0].content


def test_late_contact_tag_keeps_a_request_and_names_the_asker(orchestrator, store):
    key = live_source_key("uuid-1", "u11")
    store.save_planned_task(PlannedTask(id=derived_entity_id(key, "task"), title="Launch the washing machine",
                                        origin="ambient_voice", source_key=key,
                                        raw_statement="Damiano pls remember to launch the washing machine",
                                        speaker=SpeakerAttribution(source="untagged", addressed_to_user=True)))
    orchestrator.identity = WearerIdentity("Damiano")
    match = orchestrator.identity.match_tag(person_id=77, name="Giulia", score=0.66)
    orchestrator.reconcile_speaker(key, match)
    task = store.get_planned_task(derived_entity_id(key, "task"))
    assert task.status == "pending"
    assert task.speaker.addressed_to_user and task.speaker.name == "Giulia" and task.speaker.role == "contact"


def test_late_contact_tag_on_an_unflagged_request_keeps_it(orchestrator, store):
    key = live_source_key("uuid-1", "u12")
    store.save_planned_task(PlannedTask(id=derived_entity_id(key, "task"), title="Buy bread", origin="ambient_voice",
                                        source_key=key, raw_statement="Can you buy bread on the way home"))
    orchestrator.reconcile_speaker(key, orchestrator.identity.match_tag(person_id=77, name="Giulia"))
    task = store.get_planned_task(derived_entity_id(key, "task"))
    assert task.status == "pending" and task.speaker.addressed_to_user


def test_asked_and_unverified_labels(store):
    assert speaker_label(SpeakerAttribution(role="contact", name="Giulia", addressed_to_user=True)) == "asked by Giulia"
    store.save_action(VerifiedAction(id="a9", action_type="door_locked", domain="safety",
                                     raw_statement="I locked the door", confidence=0.9,
                                     speaker=SpeakerAttribution(role="unknown", source="untagged")))
    card = execute_verify_action_status("door", store=store)
    assert card["spoken_by"] == "unidentified speaker" and "could not confirm" in card["spoken_summary"]
