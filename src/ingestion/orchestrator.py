import asyncio
import time
import argparse
import signal
from typing import Optional, List

from src.ingestion.stream_convo import BeeClient
from src.ingestion.debug import Debug
from src.ingestion.gatekeeper import aclassify_chunk, is_noop
from src.core.storage import get_storage_store
from src.core.schemas import ChunkClassification


async def analyze_text_model(text: str, chunk_id: int) -> Optional[ChunkClassification]:
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
        active_tasks=active_task_titles if active_task_titles else None
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
    __slots__ = [
        'max_chars', 'max_duration', 'text_buffer', 'last_input_time', 
        'lock', 'response_queue', 'chunk_counter', 'main_task'
    ]
    
    def __init__(self, debug_mode="none", max_chars=5000, max_duration=300):
        super().__init__(debug_mode=debug_mode, sector_name="ORCHESTRATOR")
        self.max_chars = max_chars
        self.max_duration = max_duration 
        
        self.text_buffer = ""
        self.last_input_time = time.time()
        self.lock = asyncio.Lock()  
        
        self.response_queue = asyncio.Queue()
        self.chunk_counter = 0
        self.main_task = None  # Track the main loop

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
        
        task = asyncio.create_task(analyze_text_model(text_to_process, current_id))
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
            async for new_text in bee.stream_utterances():
                self.debug(f"⚡ Received handoff: '{new_text}'")
                
                async with self.lock:
                    if self.text_buffer:
                        self.text_buffer += " "
                    self.text_buffer += new_text
                    
                    self.last_input_time = time.time()
                    current_length = len(self.text_buffer)
                    
                    self.debug(f"Buffer updated: {current_length}/{self.max_chars} chars")
                
                # Check character limit using the extracted method
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