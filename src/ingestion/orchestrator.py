import asyncio
import time
import argparse
import signal
from datetime import datetime
from typing import Any, Optional

import sys
from pathlib import Path

# Add project root (two levels up from src/ingestion/) to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ingestion.stream_convo import BeeClient
from src.ingestion.debug import Debug
from src.ingestion.event_engine import EventEngine, EventEngineRuntime, get_event_engine
from src.ingestion.gatekeeper import aclassify_chunk, is_noop
from src.ingestion.ring_buffer import ContextRingBuffer
from src.core.config import settings
from src.core.storage import get_storage_store
from src.core.schemas import LocationTelemetry, UtteranceChunk


class BeeStreamOrchestrator(Debug):
    """Consumes the Bee event stream: screens each utterance, feeds the Deep Topic Event Engine
    and dispatches qualified chunks to the LangGraph pipeline."""

    def __init__(
        self,
        debug_mode="none",
        ring_buffer_capacity=4,
        store=None,
        engine: Optional[EventEngine] = None,
    ):
        super().__init__(debug_mode=debug_mode, sector_name="ORCHESTRATOR")
        self.store = store

        self.last_input_time = time.time()
        self.chunk_counter = 0
        self.main_task = None  # Track the main loop

        # Milestone 3.1: Context Ring Buffer & Multimodal Telemetry
        self.ring_buffer = ContextRingBuffer(capacity=ring_buffer_capacity)
        self.latest_telemetry: Optional[LocationTelemetry] = None
        self.debounce_window: float = 0.75  # 750ms debounce window for diarization

        # Deep Topic Event Engine (macro events, segments, synthesis scheduling)
        self.engine_enabled = settings.event_engine_enabled
        if engine is not None:
            self.engine = engine
        elif store is not None:
            self.engine = EventEngine(store=store)
        else:
            self.engine = get_event_engine()

        # Real-time state & telemetry tracking
        self.is_running = False
        self.last_heartbeat_time: Optional[float] = None
        self.total_utterances_received: int = 0
        self.status = "IDLE"

    def get_status_dict(self) -> dict:
        """Returns a snapshot of the orchestrator liveness, event engine state, and telemetry."""
        now = time.time()
        is_streaming = (
            self.total_utterances_received > 0
            and (now - self.last_input_time < 120.0)
        )
        is_listening = self.is_running and (
            self.last_heartbeat_time is not None or (now - self.last_input_time < 300.0)
        )

        status_label = "STREAMING" if is_streaming else ("LISTENING" if is_listening else ("STANDBY" if self.is_running else "STOPPED"))
        return {
            "running": self.is_running,
            "status": status_label,
            "mode": "ambient_sse",
            "chunks_screened": self.chunk_counter,
            "utterances_received": self.total_utterances_received,
            "last_heartbeat": self.last_heartbeat_time,
            "last_input_time": self.last_input_time,
            "has_location": self.latest_telemetry is not None,
            "event_engine": self.engine.status_summary() if self.engine_enabled else None,
            "detail": f"Orchestrator {status_label.lower()}; {self.chunk_counter} chunks screened",
        }

    def update_location(self, location_data: dict) -> LocationTelemetry:
        """Parses and updates the latest spatial telemetry from an update-location event."""
        lat = float(location_data.get("latitude", 0.0))
        lon = float(location_data.get("longitude", 0.0))
        place = location_data.get("name") or location_data.get("address") or location_data.get("place_name")
        accuracy = location_data.get("horizontal_accuracy") or location_data.get("accuracy_meters")

        telemetry = LocationTelemetry(
            latitude=lat,
            longitude=lon,
            place_name=place,
            accuracy_meters=float(accuracy) if accuracy is not None else None,
        )
        self.latest_telemetry = telemetry
        self.debug(
            f"📍 Telemetry updated: ({lat:.4f}, {lon:.4f}) | Zone: '{telemetry.semantic_zone}' | Place: '{place}'"
        )
        if self.engine_enabled:
            try:
                self.engine.on_location(telemetry.model_dump())
            except Exception as e:
                self.debug(f"Event engine location error: {e}")
        return telemetry

    def patch_diarization(
        self,
        utterance_id: str,
        speaker_id: str,
        speaker_role: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Retrospectively patches diarization speaker info in ring buffer and persistent store."""
        role = speaker_role or ("user" if speaker_id in ("speaker_0", "user") else "contact")
        patched_buffer = self.ring_buffer.patch_speaker(
            chunk_id=utterance_id, speaker_id=speaker_id, speaker_role=role, conv_id=session_id
        )
        try:
            store = self.store or get_storage_store()
            store.patch_utterance_speaker(chunk_id=utterance_id, speaker_id=speaker_id, speaker_role=role)
        except Exception as e:
            self.debug(f"Store speaker patch error: {e}")
        self.debug(f"🎙️ Diarization patched: Chunk '{utterance_id}' -> '{speaker_id}' ({role})")
        return patched_buffer

    def buffer_incoming_utterance(self, utterance_data: dict) -> Optional[UtteranceChunk]:
        """Synchronously parses, attaches current telemetry, and pushes utterance to the ring buffer."""
        chunk_id = str(utterance_data.get("id") or utterance_data.get("chunk_id") or time.time())
        conv_uuid = utterance_data.get("conversation_uuid") or utterance_data.get("session_id") or "default_session"
        text = (utterance_data.get("text") or "").strip()
        if not text:
            return None

        speaker = utterance_data.get("speaker") or utterance_data.get("speaker_id")
        speaker_role = utterance_data.get("speaker_role")
        if not speaker_role or speaker_role == "unknown":
            speaker_role = "user" if speaker in ("speaker_0", "user") else ("contact" if speaker else "unknown")

        # Best-known utterance time: spoken_at (Bee) > received_at (BeeClient) > now
        spoken_at = utterance_data.get("spoken_at")
        received_at = utterance_data.get("received_at")
        timestamp = spoken_at or received_at or datetime.now().isoformat()

        chunk = UtteranceChunk(
            chunk_id=chunk_id,
            conversation_uuid=conv_uuid,
            text=text,
            speaker_id=speaker,
            speaker_role=speaker_role,
            timestamp=timestamp,
            received_at=received_at,
            spoken_at=spoken_at,
            location=self.latest_telemetry.model_dump() if self.latest_telemetry else None,
        )
        self.ring_buffer.push(chunk)
        return chunk

    async def process_incoming_utterance(self, utterance_data: dict) -> Optional[dict]:
        """Processes an incoming utterance: buffers context, screens, feeds the event engine, and routes."""
        chunk = self.buffer_incoming_utterance(utterance_data)
        if not chunk:
            return None

        self.chunk_counter += 1
        conv_uuid = chunk.conversation_uuid
        chunk_id = chunk.chunk_id

        # Retrieve lightweight context for gatekeeper
        historical_context = self.ring_buffer.get_concatenated_context_text(conv_uuid, exclude_current=True)
        rolling_hint = self.ring_buffer.get_rolling_summary_hint(conv_uuid)

        # Gatekeeper evaluation
        active_task_titles = []
        try:
            store = self.store or get_storage_store()
            active_task_titles = [t.title for t in store.list_planned_tasks(status="pending") if t.title]
        except Exception:
            pass

        classification = await aclassify_chunk(
            transcript=chunk.text,
            active_tasks=active_task_titles if active_task_titles else None,
            prior_context=rolling_hint,
        )
        chunk.categories = list(classification.categories)

        # Feed the event engine BEFORE the pipeline, so a chunk that opens an event is already
        # event-managed when its micro-events are persisted.
        event_id: Optional[str] = None
        if self.engine_enabled:
            try:
                outcome = self.engine.record_chunk(chunk)
                event_id = outcome.event_id
                for t in outcome.transitions:
                    self.debug(f"Event {t.rule}: -> {t.to_status} ({t.reason})")
            except Exception as e:
                self.debug(f"Event engine record_chunk error: {e}")

        if is_noop(classification):
            self.debug(f"Chunk '{chunk_id}' screened -> DROPPED (noop)")
            return None

        self.debug(f"Chunk '{chunk_id}' screened -> QUALIFIED {classification.categories}")

        # Dispatch with full context to pipeline
        payload = {
            "raw_transcript": chunk.text,
            "historical_context": historical_context,
            "categories": classification.categories,
            "confidence": classification.confidence,
            "summary_hint": classification.summary_hint,
            "location": chunk.location,
            "speaker": chunk.speaker_id,
            "speaker_role": chunk.speaker_role,
            "utterance_id": chunk.chunk_id,
            "session_id": event_id or chunk.conversation_uuid,
            "timestamp": chunk.timestamp,
            "event_managed": event_id is not None,
        }

        try:
            from src.pipeline.app import agent_invocation
            # agent_invocation is synchronous: keep it off the event loop (SSE/REST stay responsive)
            return await asyncio.to_thread(agent_invocation, payload)
        except Exception as e:
            self.debug(f"Pipeline dispatch error: {e}")
            return None

    async def handle_event(self, event: dict) -> Optional[Any]:
        """Dispatches an incoming SSE event to the appropriate handler."""
        evt_type = event.get("event")
        data = event.get("data", {})

        if evt_type == "update-location":
            return self.update_location(data)
        elif evt_type == "update-utterance":
            uid = str(data.get("utterance_id", ""))
            spk = data.get("speaker", "")
            return self.patch_diarization(uid, spk)
        elif evt_type == "new-utterance":
            self.total_utterances_received += 1
            self.last_input_time = time.time()
            self.status = "STREAMING"
            return await self.process_incoming_utterance(data)
        return None

    async def run(self):
        """Main loop that ingests the stream and drives the event engine runtime."""
        self.main_task = asyncio.current_task()
        self.is_running = True
        self.status = "LISTENING"

        runtime: Optional[EventEngineRuntime] = None
        if self.engine_enabled:
            if self.engine is get_event_engine():
                from src.ingestion.event_engine import get_event_engine_runtime
                runtime = get_event_engine_runtime()
            else:
                runtime = EventEngineRuntime(self.engine)
            runtime.ensure_started()

        self.debug("Starting Bee stream ingestion...")
        bee = BeeClient(debug_mode=self.debug_mode)

        try:
            async for event in bee.stream_events():
                evt_name = event.get('event')
                self.debug(f"⚡ Received event: {evt_name}")
                if evt_name == "stream-heartbeat":
                    self.last_heartbeat_time = time.time()
                await self.handle_event(event)
        except asyncio.CancelledError:
            pass
        finally:
            self.is_running = False
            self.status = "STOPPED"
            bee.stop()

    async def shutdown(self):
        """Safely triggers cancellation of the main run loop only."""
        if self.main_task and not self.main_task.done():
            self.main_task.cancel()


async def main(orchestrator_instance):
    """Bootstraps the event loop and attaches OS signal handlers."""
    loop = asyncio.get_running_loop()

    # Catch OS signals (e.g. from Docker/Colima) to trigger graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(orchestrator_instance.shutdown())
        )

    await orchestrator_instance.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bee Stream Ingestion Orchestrator")
    parser.add_argument(
        '--debug',
        type=str,
        default="none",
        help="Specify debug sector: 'all', 'bee', 'orchestrator', or 'none'"
    )
    args = parser.parse_args()

    orchestrator = BeeStreamOrchestrator(debug_mode=args.debug)

    try:
        asyncio.run(main(orchestrator))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nOrchestrator stopped gracefully.")
