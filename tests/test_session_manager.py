"""Unit & Integration Tests for Milestone 3.2: Session Merging & Micro-Event Decoupling.

Validates:
1. SessionDossier & MicroEventRef schema models and foreign-key linking.
2. SQLiteContextStore session persistence, chunk appending, and micro-event linking.
3. SessionManager lifecycle state machine, inactivity timeouts, closing phrase detection,
   and GPS location shift boundary triggers.
4. Micro-event decoupling in LangGraph node_persist with automatic foreign-key linking.
5. FastMCP serving tools (execute_get_session_dossier, execute_list_session_dossiers)
   and Echo Show SESSION_DOSSIER_VIEWER card template payloads.
"""

import os
import tempfile
import time
from datetime import datetime, timezone
import pytest

from src.core.schemas import (
    BriefingReport,
    MicroEventRef,
    PlannedTask,
    SessionDossier,
    SocialEntity,
    VerifiedAction,
)
from src.ingestion.session_manager import (
    SessionManager,
    calculate_haversine_distance,
)
from src.pipeline.nodes.persist import node_persist
from src.serving.tools.session_tools import (
    execute_get_session_dossier,
    execute_list_session_dossiers,
    get_session_dossier,
    list_session_dossiers,
)
from tests.store_backend import new_store


@pytest.fixture
def temp_store():
    """Provides an isolated SQLiteContextStore instance for session tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = new_store(db_path)
    yield store
    if os.path.exists(db_path):
        os.remove(db_path)


class TestSessionDossierSchemas:
    """Validates schemas and serialization for Macro Sessions and Micro Events."""

    def test_micro_event_ref_creation(self):
        ref = MicroEventRef(
            event_type="action",
            record_id="act-123",
            headline="Turned off the stove",
        )
        assert ref.event_type == "action"
        assert ref.record_id == "act-123"
        assert ref.headline == "Turned off the stove"
        assert ref.timestamp is not None

    def test_session_dossier_defaults(self):
        dossier = SessionDossier(
            session_id="sess-alpha-001",
            title="Sprint Planning Meeting",
            domain="meeting",
        )
        assert dossier.session_id == "sess-alpha-001"
        assert dossier.status == "active"
        assert dossier.transcript_chunks == []
        assert dossier.linked_micro_events == []
        assert dossier.final_briefing_id is None
        assert dossier.briefing_report is None


class TestSQLiteStoreSessionMethods:
    """Validates SQLiteContextStore session CRUD, chunk appending, and event linking."""

    def test_save_and_get_session_dossier(self, temp_store):
        dossier = SessionDossier(
            session_id="sess-db-001",
            title="Q3 Strategy Sync",
            domain="meeting",
            status="active",
            location={"place_name": "Room 402", "latitude": 45.4642, "longitude": 9.1900},
            transcript_chunks=["Let us discuss Q3 goals.", "First priority is cloud migration."],
            key_discussion_points=["Cloud migration", "Latency reduction"],
        )
        saved_id = temp_store.save_session_dossier(dossier)
        assert saved_id == "sess-db-001"

        fetched = temp_store.get_session_dossier("sess-db-001")
        assert fetched is not None
        assert fetched.session_id == "sess-db-001"
        assert fetched.title == "Q3 Strategy Sync"
        assert len(fetched.transcript_chunks) == 2
        assert len(fetched.key_discussion_points) == 2
        assert fetched.location["place_name"] == "Room 402"

    def test_append_chunk_to_session(self, temp_store):
        sess_id = "sess-append-001"
        d1 = temp_store.append_chunk_to_session(sess_id, "Hello everyone, starting the sync.")
        assert d1.session_id == sess_id
        assert len(d1.transcript_chunks) == 1

        d2 = temp_store.append_chunk_to_session(sess_id, "We have agreed on DynamoDB.")
        assert len(d2.transcript_chunks) == 2
        assert d2.transcript_chunks[1] == "We have agreed on DynamoDB."

    def test_link_micro_event_and_deduplication(self, temp_store):
        sess_id = "sess-events-001"
        event1 = MicroEventRef(
            event_type="action",
            record_id="act-001",
            headline="Iron unplugged",
        )
        temp_store.link_micro_event_to_session(sess_id, event1)

        dossier = temp_store.get_session_dossier(sess_id)
        assert len(dossier.linked_micro_events) == 1
        assert dossier.linked_micro_events[0].record_id == "act-001"

        # Attempt linking same event again (deduplication check)
        temp_store.link_micro_event_to_session(sess_id, event1)
        dossier_dedup = temp_store.get_session_dossier(sess_id)
        assert len(dossier_dedup.linked_micro_events) == 1

        # Link a distinct second event
        event2 = MicroEventRef(
            event_type="social_contact",
            record_id="soc-002",
            headline="Met Dr. Sarah Lin",
        )
        temp_store.link_micro_event_to_session(sess_id, event2)
        dossier_two = temp_store.get_session_dossier(sess_id)
        assert len(dossier_two.linked_micro_events) == 2

    def test_conclude_session_dossier_with_briefing(self, temp_store):
        sess_id = "sess-conclude-001"
        temp_store.append_chunk_to_session(sess_id, "Discussing distributed consensus.")

        briefing = BriefingReport(
            id="rep-raft-001",
            topic_title="Distributed Consensus via Raft",
            context_type="tech_stack",
            executive_summary=["Raft consensus enables leader election.", "Log replication is guaranteed."],
            explanatory_synthesis="Raft decomposes consensus into leader election, log replication, and safety.",
        )
        temp_store.save_topic_briefing(briefing)

        concluded = temp_store.conclude_session_dossier(sess_id, briefing_report_id="rep-raft-001")
        assert concluded is not None
        assert concluded.status == "concluded"
        assert concluded.final_briefing_id == "rep-raft-001"
        assert concluded.briefing_report is not None
        assert concluded.briefing_report.topic_title == "Distributed Consensus via Raft"

    def test_micro_records_foreign_key_persistence(self, temp_store):
        # 1. Action with session_id
        action = VerifiedAction(
            action_type="door_locked",
            domain="safety",
            raw_statement="I locked the front door.",
            confidence=0.98,
            session_id="sess-fk-001",
        )
        act_id = temp_store.save_action(action)
        loaded_act = temp_store.get_action_status("door")
        assert loaded_act is not None
        assert loaded_act.session_id == "sess-fk-001"

        # 2. Social contact with session_id
        contact = SocialEntity(
            person_name="Giulia Rossi",
            company_or_role="VP Engineering",
            session_id="sess-fk-001",
        )
        soc_id = temp_store.save_social_contact(contact)
        loaded_soc = temp_store.get_social_contact("Giulia Rossi")
        assert loaded_soc is not None
        assert loaded_soc.session_id == "sess-fk-001"

        # 3. Planned task with session_id
        task = PlannedTask(
            title="Deploy release v2",
            domain="work_task",
            session_id="sess-fk-001",
        )
        tsk_id = temp_store.save_planned_task(task)
        loaded_tsk = temp_store.get_planned_task(tsk_id)
        assert loaded_tsk is not None
        assert loaded_tsk.session_id == "sess-fk-001"


class TestSessionManagerBoundaryDetection:
    """Validates boundary triggers: closing phrases, inactivity timeout, and GPS location shifts."""

    def test_haversine_distance_calculation(self):
        # Duomo di Milano (45.4642, 9.1900) to Stazione Centrale (45.4870, 9.2045) ~2.7km
        dist = calculate_haversine_distance(45.4642, 9.1900, 45.4870, 9.2045)
        assert 2500 < dist < 3000

        # Identical location should be 0
        assert calculate_haversine_distance(45.4642, 9.1900, 45.4642, 9.1900) == 0.0

    def test_closing_phrases_detection(self, temp_store):
        mgr = SessionManager(store=temp_store)

        # English phrases
        assert mgr.is_closing_phrase("That concludes today's meeting, thank you everyone.") is True
        assert mgr.is_closing_phrase("Let's wrap up the meeting now.") is True
        assert mgr.is_closing_phrase("The meeting is adjourned.") is True
        assert mgr.is_closing_phrase("Let's call it a day.") is True

        # Italian phrases
        assert mgr.is_closing_phrase("Fine riunione, ci vediamo domani.") is True
        assert mgr.is_closing_phrase("Concludiamo la riunione qui.") is True
        assert mgr.is_closing_phrase("Chiudiamo la riunione.") is True

        # Non-closing phrases
        assert mgr.is_closing_phrase("Let's discuss the next topic on the agenda.") is False
        assert mgr.is_closing_phrase("We will deploy to production tomorrow.") is False

    def test_record_chunk_closing_phrase_triggers_boundary(self, temp_store):
        mgr = SessionManager(store=temp_store)
        sess_id = "sess-close-001"

        dossier, triggered = mgr.record_chunk(sess_id, "First point of agenda.")
        assert triggered is False
        assert dossier.status == "active"

        dossier2, triggered2 = mgr.record_chunk(sess_id, "That concludes our meeting today.")
        assert triggered2 is True
        assert dossier2.status == "paused"

    def test_inactivity_timeout_triggers_boundary(self, temp_store):
        mgr = SessionManager(inactivity_timeout_seconds=60.0, store=temp_store)
        sess_id = "sess-timeout-001"

        t0 = 1000.0
        mgr.record_chunk(sess_id, "Chunk at t0", timestamp=t0)

        # 30 seconds later (no boundary)
        _, triggered = mgr.record_chunk(sess_id, "Chunk at t0+30", timestamp=t0 + 30.0)
        assert triggered is False

        # 120 seconds later (> 60s timeout threshold)
        _, triggered_timeout = mgr.record_chunk(sess_id, "Chunk after silence", timestamp=t0 + 150.0)
        assert triggered_timeout is True

    def test_check_inactivity_timeouts_method(self, temp_store):
        mgr = SessionManager(inactivity_timeout_seconds=60.0, store=temp_store)
        sess_id = "sess-scan-001"
        mgr.record_chunk(sess_id, "Initial discussion.", timestamp=1000.0)

        # At timestamp 1030 (30s later) -> no timeout
        assert mgr.check_inactivity_timeouts(current_time=1030.0) == []

        # At timestamp 1070 (70s later) -> timed out!
        timed_out = mgr.check_inactivity_timeouts(current_time=1070.0)
        assert timed_out == [sess_id]
        dossier = mgr.get_session(sess_id)
        assert dossier.status == "paused"

    def test_location_shift_triggers_boundary(self, temp_store):
        mgr = SessionManager(location_distance_threshold_meters=500.0, store=temp_store)
        sess_id = "sess-gps-001"

        loc1 = {"latitude": 45.4642, "longitude": 9.1900, "place_name": "Conference Room"}
        mgr.record_chunk(sess_id, "Chunk inside conference room.", location=loc1)

        # Move 50 meters (same building) -> no boundary
        loc2 = {"latitude": 45.4646, "longitude": 9.1902, "place_name": "Hallway"}
        _, triggered_small = mgr.record_chunk(sess_id, "Walking to hallway.", location=loc2)
        assert triggered_small is False

        # Move 2.7 km away (Stazione Centrale) -> boundary triggered!
        loc3 = {"latitude": 45.4870, "longitude": 9.2045, "place_name": "Central Station"}
        _, triggered_far = mgr.record_chunk(sess_id, "Now at station.", location=loc3)
        assert triggered_far is True


class TestMicroEventDecouplingInPipeline:
    """Validates that LangGraph node_persist links micro-events to active SessionDossier."""

    def test_node_persist_links_actions_tasks_contacts(self, monkeypatch, temp_store):
        monkeypatch.setattr("src.pipeline.nodes.persist.get_storage_store", lambda: temp_store)

        sess_id = "sess-pipeline-link-001"
        # Seed an active session
        temp_store.append_chunk_to_session(sess_id, "Team planning session started.")

        # Simulate state with multiple micro-events and session_id
        action = VerifiedAction(
            action_type="server_rebooted",
            domain="work_task",
            raw_statement="I just rebooted the production staging server.",
            confidence=0.96,
        )
        contact = SocialEntity(
            person_name="Alex Turner",
            company_or_role="Security Lead",
        )
        task = PlannedTask(
            title="Rotate API keys",
            domain="work_task",
            origin="ambient_voice",
        )

        state = {
            "session_id": sess_id,
            "action_data": action,
            "social_data": contact,
            "scheduled_task": task,
        }

        node_persist(state)

        # Verify SessionDossier received all 3 linked micro-events
        dossier = temp_store.get_session_dossier(sess_id)
        assert len(dossier.linked_micro_events) == 3

        event_types = {e.event_type for e in dossier.linked_micro_events}
        assert event_types == {"action", "social_contact", "task_scheduled"}

        # Verify individual entities also carry session_id foreign key
        saved_action = temp_store.get_action_status("server")
        assert saved_action is not None
        assert saved_action.session_id == sess_id

        saved_contact = temp_store.get_social_contact("Alex Turner")
        assert saved_contact is not None
        assert saved_contact.session_id == sess_id

        saved_tasks = temp_store.list_planned_tasks(origin="ambient_voice")
        assert any(t.session_id == sess_id for t in saved_tasks)


class TestServingSessionTools:
    """Validates execute_get_session_dossier, execute_list_session_dossiers, and FastMCP tools."""

    def test_execute_get_session_dossier_found(self, temp_store):
        sess_id = "sess-serving-001"
        temp_store.append_chunk_to_session(sess_id, "Discussing DynamoDB migration.")
        temp_store.link_micro_event_to_session(
            sess_id,
            MicroEventRef(
                event_type="action",
                record_id="act-tf",
                headline="Terraform apply executed",
            ),
        )
        temp_store.link_micro_event_to_session(
            sess_id,
            MicroEventRef(
                event_type="task_scheduled",
                record_id="tsk-bench",
                headline="Deliver latency benchmarks to Marco",
            ),
        )

        res = execute_get_session_dossier(session_id=sess_id, store=temp_store)
        assert res["found"] is True
        assert res["session_id"] == sess_id
        assert res["display_template"] == "SESSION_DOSSIER_VIEWER"
        assert res["ui_card_type"] == "SESSION_DOSSIER_VIEWER"
        assert res["actions_count"] == 1
        assert res["tasks_count"] == 1
        assert "spoken_summary" in res
        assert "recap" in res["spoken_summary"].lower()

        card_payload = res["card_payload"]
        assert card_payload["template"] == "SESSION_DOSSIER_VIEWER"
        assert len(card_payload["actions"]) == 1
        assert len(card_payload["tasks"]) == 1

    def test_execute_get_session_dossier_not_found(self, temp_store):
        res = execute_get_session_dossier(session_id="non-existent", store=temp_store)
        assert res["found"] is False
        assert res["display_template"] == "SESSION_NOT_FOUND"
        assert res["ui_card_type"] == "SESSION_NOT_FOUND"

    def test_execute_list_session_dossiers(self, temp_store):
        temp_store.save_session_dossier(
            SessionDossier(session_id="sess-list-1", title="Meeting 1", status="active")
        )
        temp_store.save_session_dossier(
            SessionDossier(session_id="sess-list-2", title="Meeting 2", status="concluded")
        )

        all_res = execute_list_session_dossiers(store=temp_store)
        assert all_res["found"] is True
        assert all_res["total"] == 2

        active_res = execute_list_session_dossiers(status="active", store=temp_store)
        assert active_res["total"] == 1
        assert active_res["sessions"][0]["session_id"] == "sess-list-1"

    def test_mcp_wrapper_functions(self, monkeypatch, temp_store):
        monkeypatch.setattr("src.serving.tools.session_tools.get_storage_store", lambda: temp_store)
        sess_id = "sess-wrap-001"
        temp_store.append_chunk_to_session(sess_id, "Wrapper function verification.")

        res = get_session_dossier(session_id=sess_id)
        assert res["found"] is True
        assert res["session_id"] == sess_id

        list_res = list_session_dossiers()
        assert list_res["found"] is True
        assert list_res["total"] >= 1
