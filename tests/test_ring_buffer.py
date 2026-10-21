"""Tests for Milestone 3.1: Context Ring Buffer, Multimodal Telemetry, and Asynchronous Diarization."""

import pytest
from datetime import datetime, timezone

from src.core.schemas import (
    LocationTelemetry,
    UtteranceChunk,
    VerifiedAction,
    PlannedTask,
    SocialEntity,
    ExamenState,
)
from src.ingestion.ring_buffer import ContextRingBuffer
from src.pipeline.nodes.action_state import node_extract_action
from src.pipeline.nodes.social import node_extract_social
from src.ingestion.orchestrator import BeeStreamOrchestrator
from tests.store_backend import new_store


class TestContextRingBuffer:
    """Tests for ContextRingBuffer FIFO rolling queue and context assembly."""

    def test_buffer_capacity_rolling(self):
        buffer = ContextRingBuffer(capacity=4)
        for i in range(6):
            buffer.push("session_1", UtteranceChunk(
                utterance_id=f"u_{i}",
                text=f"Chunk message {i}",
                speaker_id="speaker_0",
                speaker_role="user"
            ))

        history = buffer.get_historical_context("session_1", exclude_current=False)
        assert len(history) == 4
        # Oldest chunks 0 and 1 should have been evicted
        assert [h.utterance_id for h in history] == ["u_2", "u_3", "u_4", "u_5"]

    def test_concatenated_context_text(self):
        buffer = ContextRingBuffer(capacity=4)
        buffer.push("session_1", UtteranceChunk(
            utterance_id="u_1",
            text="Did you remember the keys?",
            speaker_id="speaker_alice",
            speaker_role="contact"
        ))
        buffer.push("session_1", UtteranceChunk(
            utterance_id="u_2",
            text="Yes, locked the door and took them.",
            speaker_id="speaker_user",
            speaker_role="user"
        ))

        concat = buffer.get_concatenated_context_text("session_1", exclude_current=False)
        assert "[speaker_alice (contact)]: Did you remember the keys?" in concat
        assert "[speaker_user (user)]: Yes, locked the door and took them." in concat

    def test_rolling_summary_hint(self):
        buffer = ContextRingBuffer(capacity=4)
        assert buffer.get_rolling_summary_hint("empty_session") == ""

        buffer.push("session_1", UtteranceChunk(
            utterance_id="u_1",
            text="We need to finalize the quarterly review.",
            speaker_id="speaker_boss"
        ))
        buffer.push("session_1", UtteranceChunk(
            utterance_id="u_2",
            text="Let's schedule a deep dive tomorrow morning.",
            speaker_id="speaker_user"
        ))
        hint = buffer.get_rolling_summary_hint("session_1")
        assert "quarterly review" in hint

    def test_patch_speaker(self):
        buffer = ContextRingBuffer(capacity=4)
        buffer.push("session_1", UtteranceChunk(
            utterance_id="u_target",
            text="I will handle the contract negotiation.",
            speaker_id="unknown_speaker",
            speaker_role="unknown"
        ))

        # Retrospective diarization patch arrives
        patched = buffer.patch_speaker("session_1", "u_target", "spk_elena", "contact")
        assert patched is True

        last = buffer.get_last_chunk("session_1")
        assert last is not None
        assert last.speaker_id == "spk_elena"
        assert last.speaker_role == "contact"

    def test_clear_buffer(self):
        buffer = ContextRingBuffer(capacity=4)
        buffer.push("session_1", UtteranceChunk(utterance_id="u_1", text="Test"))
        assert len(buffer.get_historical_context("session_1", exclude_current=False)) == 1
        buffer.clear("session_1")
        assert len(buffer.get_historical_context("session_1", exclude_current=False)) == 0


class TestLocationTelemetry:
    """Tests for LocationTelemetry schema and semantic zone inference."""

    def test_semantic_zone_home_inference(self):
        telemetry = LocationTelemetry(
            latitude=37.7749,
            longitude=-122.4194,
            place_name="Sweet Home Apartment #4B"
        )
        assert telemetry.semantic_zone == "home"

    def test_semantic_zone_work_office_inference(self):
        telemetry = LocationTelemetry(
            latitude=47.6062,
            longitude=-122.3321,
            place_name="AWS HQ Office Campus"
        )
        assert telemetry.semantic_zone == "work_office"

    def test_semantic_zone_transit_inference(self):
        telemetry = LocationTelemetry(
            latitude=40.7128,
            longitude=-74.0060,
            place_name="Grand Central Station Metro"
        )
        assert telemetry.semantic_zone == "transit"

    def test_semantic_zone_public_venue_inference(self):
        telemetry = LocationTelemetry(
            latitude=41.8781,
            longitude=-87.6298,
            place_name="Blue Bottle Cafe & Coffee Bar"
        )
        assert telemetry.semantic_zone == "public_venue"

    def test_semantic_zone_unspecified_fallback(self):
        telemetry = LocationTelemetry(
            latitude=0.0,
            longitude=0.0,
            place_name="Open Field Sector 9"
        )
        assert telemetry.semantic_zone == "unknown"


class TestStorageMultimodalGrounding:
    """Tests for SQLite persistence of spatial metadata and diarization patching."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        db_file = tmp_path / "test_multimodal.db"
        return new_store(str(db_file))

    def test_action_location_persistence(self, temp_store):
        action = VerifiedAction(
            action_type="door_locked",
            domain="safety",
            raw_statement="I just locked the front door.",
            confidence=0.98,
            location={"place_name": "Home Apartment", "semantic_zone": "home"}
        )
        action_id = temp_store.save_action(action)
        retrieved = temp_store.get_action_status(action_id)
        assert retrieved is not None
        assert retrieved.location is not None
        assert retrieved.location["place_name"] == "Home Apartment"
        assert retrieved.location["semantic_zone"] == "home"

    def test_planned_task_location_persistence(self, temp_store):
        task = PlannedTask(
            title="Buy fresh espresso beans",
            domain="routine",
            status="pending",
            location={"place_name": "Artisan Coffee Roasters", "semantic_zone": "public_venue"}
        )
        task_id = temp_store.save_planned_task(task)
        retrieved = temp_store.get_planned_task(task_id)
        assert retrieved is not None
        assert retrieved.location is not None
        assert retrieved.location["semantic_zone"] == "public_venue"

    def test_social_contact_location_encountered(self, temp_store):
        contact = SocialEntity(
            person_name="Sophia Martinez",
            company_or_role="VP of AI at Anthropic",
            key_topics=["Model alignment", "Safety"],
            location_encountered="NeurIPS Conference Hall C"
        )
        temp_store.save_social_contact(contact)
        retrieved = temp_store.get_social_contact("Sophia Martinez")
        assert retrieved is not None
        assert retrieved.location_encountered == "NeurIPS Conference Hall C"

    def test_patch_utterance_speaker_in_store(self, temp_store):
        success = temp_store.patch_utterance_speaker(
            chunk_id="chunk_99",
            speaker_id="speaker_dr_stone",
            speaker_role="contact"
        )
        assert success is True


class TestPipelineAnaphoraAndTelemetryGrounding:
    """Tests for LangGraph pipeline nodes with historical context & telemetry grounding."""

    def test_action_anaphora_resolution_with_history(self):
        # Spoken dialogue split across turns:
        # Prior: "Did you lock the main front entrance?"
        # Current: "Yes, I just did."
        state: ExamenState = {
            "raw_transcript": "Yes, I just did.",
            "session_id": "anaphora_action_session",
            "categories": ["action_state"],
            "historical_context": [
                {
                    "utterance_id": "u_prev",
                    "text": "Did you lock the main front entrance?",
                    "speaker_id": "speaker_partner",
                    "speaker_role": "contact",
                }
            ],
            "location": {
                "place_name": "Downtown Condo",
                "semantic_zone": "home"
            }
        }
        res = node_extract_action(state)
        action: VerifiedAction = res.get("action_data")
        assert action is not None
        assert action.action_type in ("door_locked", "entrance_locked")
        assert action.domain in ("security", "safety")
        # Ensure location metadata was grounded from telemetry
        assert action.location is not None
        assert action.location["semantic_zone"] == "home"

    def test_social_anaphora_and_debtor_alignment(self, tmp_path):
        db_file = tmp_path / "social_anaphora.db"
        store = new_store(str(db_file))

        # Prior chunk: Contact introduces themselves
        # Current chunk: Contact speaks a commitment
        state: ExamenState = {
            "raw_transcript": "I will send you the revised project proposal tomorrow morning.",
            "session_id": "anaphora_social_session",
            "categories": ["social"],
            "historical_context": [
                {
                    "utterance_id": "u_intro",
                    "text": "Hi, I'm Dr. Evelyn Stone, Lead Scientist at BioGen.",
                    "speaker_id": "spk_evelyn",
                    "speaker_role": "contact"
                }
            ],
            "speaker_role": "contact",
            "speaker": "spk_evelyn",
            "location": {
                "place_name": "BioTech Summit Exhibition Center",
                "semantic_zone": "public_venue"
            }
        }
        res = node_extract_social(state)
        social: SocialEntity = res.get("social_data")
        assert social is not None
        assert "Evelyn Stone" in social.person_name
        # Location encountered captured
        assert social.location_encountered == "BioTech Summit Exhibition Center"
        # Commitment debtor correctly aligned to contact
        comms = social.get_commitments_as_objects()
        assert len(comms) >= 1
        assert comms[0].debtor == "contact"
        assert "proposal" in comms[0].description.lower() or "send" in comms[0].description.lower()


class TestBeeStreamOrchestratorMultimodal:
    """Tests for BeeStreamOrchestrator multimodal SSE routing."""

    def test_orchestrator_handles_location_and_diarization(self, tmp_path):
        db_file = tmp_path / "orchestrator_test.db"
        store = new_store(str(db_file))
        orch = BeeStreamOrchestrator(store=store)

        # 1. Dispatch update-location event
        orch.update_location({
            "latitude": 37.7749,
            "longitude": -122.4194,
            "place_name": "Coworking Space Lounge"
        })
        assert orch.latest_telemetry is not None
        assert orch.latest_telemetry.semantic_zone == "work_office"

        # 2. Feed an utterance into the ring buffer
        chunk = orch.buffer_incoming_utterance({
            "id": "utt_101",
            "text": "I will review the pull request by Friday.",
            "speaker_id": "unknown",
            "speaker_role": "unknown",
            "session_id": "sess_stream"
        })
        assert chunk.utterance_id == "utt_101"
        assert len(orch.ring_buffer.get_historical_context("sess_stream", exclude_current=False)) == 1

        # 3. Dispatch update-utterance event for retrospective diarization
        orch.patch_diarization("utt_101", "spk_alex", "contact", session_id="sess_stream")
        patched_chunk = orch.ring_buffer.get_last_chunk("sess_stream")
        assert patched_chunk.speaker_id == "spk_alex"
        assert patched_chunk.speaker_role == "contact"
