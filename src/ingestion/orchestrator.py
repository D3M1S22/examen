import asyncio
import time
import argparse
import signal
from typing import Any, List, Optional

import sys
from pathlib import Path

# Add project root (two levels up from src/ingestion/) to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.ingestion.stream_convo import BeeClient
from src.ingestion.debug import Debug
from src.ingestion.gatekeeper import aclassify_chunk, is_noop
from src.ingestion.ring_buffer import ContextRingBuffer
from src.ingestion.session_manager import SessionManager
from src.core.storage import get_storage_store
from src.core.schemas import ChunkClassification, LocationTelemetry, UtteranceChunk


async def analyze_text_model(
    text: str, chunk_id: int, prior_context: Optional[str] = None
) -> Optional[ChunkClassification]:
    """Evaluates an audio chunk with the Semantic Gatekeeper, filtering out noops and qualifying actionable context."""
    clean_text = text.strip()
    if not clean_text:
        return None

    # Retrieve any active pending tasks from context store to prioritize expected routines
    active_task_titles: List[str] = []
    try:
        store = get_storage_store()
        pending_tasks = store.list_planned_tasks(status="pending")
        active_task_titles = [t.title for t in pending_tasks if t.title]
    except Exception:
        # Storage lookup failure should not block screening
        pass

    classification: ChunkClassification = await aclassify_chunk(
        transcript=clean_text,
        active_tasks=active_task_titles if active_task_titles else None,
        prior_context=prior_context,
    )

    if is_noop(classification):
        print(f"  -> [Task {chunk_id} Screened] DROPPED (noop: {classification.summary_hint})")
    else:
        print(
            f"  -> [Task {chunk_id} Screened] QUALIFIED for downstream pipeline: "
            f"{classification.categories} (confidence={classification.confidence:.2f}, "
            f"hint='{classification.summary_hint}')"
        )
    return classification


class BeeStreamOrchestrator(Debug):
    def __init__(self, debug_mode="none", max_chars=5000, max_duration=300, ring_buffer_capacity=4, store=None):
        super().__init__(debug_mode=debug_mode, sector_name="ORCHESTRATOR")
        self.max_chars = max_chars
        self.max_duration = max_duration 
        self.store = store
        
        self.text_buffer = ""
        self.last_input_time = time.time()
        self.lock = asyncio.Lock()  
        
        self.response_queue = asyncio.Queue()
        self.chunk_counter = 0
        self.main_task = None  # Track the main loop

        # Milestone 3.1: Context Ring Buffer & Multimodal Telemetry
        self.ring_buffer = ContextRingBuffer(capacity=ring_buffer_capacity)
        self.latest_telemetry: Optional[LocationTelemetry] = None
        self.debounce_window: float = 0.75  # 750ms debounce window for diarization

        # Milestone 3.2: Macro Session & Micro-Event Decoupling
        self.session_manager = SessionManager(store=self.store)

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

        chunk = UtteranceChunk(
            chunk_id=chunk_id,
            conversation_uuid=conv_uuid,
            text=text,
            speaker_id=speaker,
            speaker_role=speaker_role,
            location=self.latest_telemetry.model_dump() if self.latest_telemetry else None,
        )
        self.ring_buffer.push(chunk)
        return chunk

    async def process_incoming_utterance(self, utterance_data: dict) -> Optional[dict]:
        """Processes an incoming utterance chunk: attaches telemetry, buffers context, screens, and routes."""
        chunk = self.buffer_incoming_utterance(utterance_data)
        if not chunk:
            return None

        conv_uuid = chunk.conversation_uuid
        chunk_id = chunk.chunk_id

        # Record into macro session buffer & detect boundary events (Milestone 3.2)
        try:
            dossier, boundary_triggered = self.session_manager.record_chunk(
                session_id=conv_uuid,
                text=chunk.text,
                location=chunk.location,
            )
            if boundary_triggered:
                self.debug(f"Boundary event triggered on session '{conv_uuid}'")
        except Exception as e:
            self.debug(f"Session manager record_chunk error: {e}")

        # Retrieve lightweight context for gatekeeper
        historical_context = self.ring_buffer.get_concatenated_context_text(conv_uuid, exclude_current=True)
        rolling_hint = self.ring_buffer.get_rolling_summary_hint(conv_uuid)

        # Gatekeeper evaluation
        active_task_titles = []
        try:
            store = get_storage_store()
            active_task_titles = [t.title for t in store.list_planned_tasks(status="pending") if t.title]
        except Exception:
            pass

        classification = await aclassify_chunk(
            transcript=chunk.text,
            active_tasks=active_task_titles if active_task_titles else None,
            prior_context=rolling_hint,
        )

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
            "session_id": chunk.conversation_uuid,
        }

        try:
            from src.pipeline.app import agent_invocation
            result = agent_invocation(payload)
            return result
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
            return await self.process_incoming_utterance(data)
        return None

    async def flush_to_model(self, reason: str, text_to_process: str = None):
        """Extracts the buffer, clears it, and queues the model task."""
        async with self.lock:
            # If no specific text chunk was passed, take the whole buffer
            if text_to_process is None:
                if not self.text_buffer.strip():
                    return
                text_to_process = self.text_buffer
                self.text_buffer = ""
                
            self.last_input_time = time.time()
            self.chunk_counter += 1
            current_id = self.chunk_counter
            
        print(f"\n--- Trigger: {reason} (Chunk {current_id}) ---")
        
        rolling_hint = self.ring_buffer.get_rolling_summary_hint()
        task = asyncio.create_task(analyze_text_model(text_to_process, current_id, prior_context=rolling_hint))
        await self.response_queue.put(task)

    async def _evaluate_buffer_limit(self, current_length: int):
        """Evaluates the buffer limit and applies semantic chunking if necessary."""
        if current_length < self.max_chars:
            return

        pass_to_model = None
        async with self.lock:
            # Find safe cut point (period or space)
            cut_index = self.text_buffer.rfind('. ', 0, self.max_chars)
            if cut_index == -1:
                cut_index = self.text_buffer.rfind(' ', 0, self.max_chars)
            
            if cut_index != -1:
                # Split the text safely without cutting words in half
                chunk_to_send = self.text_buffer[:cut_index + 1].strip()
                self.text_buffer = self.text_buffer[cut_index + 1:].strip()
                pass_to_model = chunk_to_send
            else:
                # Fallback if there are no spaces at all
                pass_to_model = self.text_buffer
                self.text_buffer = ""
                
        if pass_to_model:
            await self.flush_to_model("5000 Character Limit Reached", pass_to_model)

    async def response_worker(self):
        """Background worker that awaits and prints tasks sequentially."""
        while True:
            task = await self.response_queue.get()
            try:
                result = await task
                if result:
                    if hasattr(result, "categories"):
                        status_str = "DROPPED (noop)" if is_noop(result) else f"QUALIFIED: {result.categories}"
                        print(f"\n[GATEKEEPER CLASSIFICATION] {status_str} | Hint: {result.summary_hint} | Conf: {result.confidence:.2f}\n")
                    else:
                        print(f"\n[MODEL RESPONSE IN ORDER] {result}\n")
            except Exception as e:
                print(f"\n[MODEL ERROR] {e}\n")
            finally:
                self.response_queue.task_done()

    async def timeout_monitor(self):
        """Background loop checking if 5 minutes passed since the last text input."""
        while True:
            await asyncio.sleep(5) 
            
            async with self.lock:
                has_data = len(self.text_buffer.strip()) > 0
                time_passed = time.time() - self.last_input_time
            
            if has_data and time_passed >= self.max_duration:
                await self.flush_to_model("5-Minute Inactivity Timeout")

    async def run(self):
        """Main loop that ingests the stream and manages triggers."""
        self.main_task = asyncio.current_task()
        
        monitor_task = asyncio.create_task(self.timeout_monitor())
        worker_task = asyncio.create_task(self.response_worker())
        
        self.debug("Starting background tasks...")
        
        bee = BeeClient(debug_mode=self.debug_mode)
        
        try:
            async for event in bee.stream_events():
                self.debug(f"⚡ Received event: {event.get('event')}")
                await self.handle_event(event)

                if event.get("event") == "new-utterance":
                    new_text = event.get("data", {}).get("text", "")
                    if new_text:
                        async with self.lock:
                            if self.text_buffer:
                                self.text_buffer += " "
                            self.text_buffer += new_text
                            
                            self.last_input_time = time.time()
                            current_length = len(self.text_buffer)
                            
                            self.debug(f"Buffer updated: {current_length}/{self.max_chars} chars")
                        
                        await self._evaluate_buffer_limit(current_length)
                        
        except asyncio.CancelledError:
            pass
        finally:
            bee.stop()
            monitor_task.cancel()
            await self.flush_to_model("Shutdown Flush")
            
            if not self.response_queue.empty():
                print("\nWaiting for remaining model responses to finish...")
                await self.response_queue.join()
            worker_task.cancel()


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

    orchestrator = BeeStreamOrchestrator(debug_mode=args.debug, max_chars=5000, max_duration=300)
    
    try:
        asyncio.run(main(orchestrator))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nOrchestrator stopped gracefully.")