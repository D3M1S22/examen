import asyncio
import time
import argparse

# Import the new BeeClient class
from stream_convo import BeeClient
from debug import Debug

# Placeholder for your async analysis model function
async def analyze_text_model(text: str, chunk_id: int):
    print(f"  -> [Task {chunk_id} Started] Analyzing {len(text)} characters...")
    # await your_actual_model_call(text) here
    await asyncio.sleep(2) # Simulated processing time
    return f"Processed output for chunk {chunk_id}"


class BeeStreamOrchestrator(Debug):
    def __init__(self, debug_mode="none", max_chars=5000, max_duration=300):
        super().__init__(debug_mode=debug_mode, sector_name="ORCHESTRATOR")
        self.debug_mode = debug_mode.lower()
        self.max_chars = max_chars
        self.max_duration = max_duration # 300 seconds = 5 minutes
        
        self.text_buffer = ""
        self.last_input_time = time.time()
        self.lock = asyncio.Lock()  # Mutex to safely handle the buffer
        
        # Queue to maintain ordered model responses
        self.response_queue = asyncio.Queue()
        self.chunk_counter = 0

    async def flush_to_model(self, reason: str):
        """Extracts the buffer, clears it, and queues the model task."""
        async with self.lock:
            if not self.text_buffer.strip():
                return
            
            # Save current text and reset state
            text_to_process = self.text_buffer
            self.text_buffer = ""
            self.last_input_time = time.time()
            
            self.chunk_counter += 1
            current_id = self.chunk_counter
            
        print(f"\n--- Trigger: {reason} (Chunk {current_id}) ---")
        
        # 1. Start the model task immediately (concurrent execution)
        task = asyncio.create_task(analyze_text_model(text_to_process, current_id))
        
        # 2. Put the TASK into the queue to maintain the exact order
        await self.response_queue.put(task)

    async def response_worker(self):
        """Background worker that awaits and prints tasks sequentially."""
        while True:
            task = await self.response_queue.get()
            try:
                result = await task
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
        monitor_task = asyncio.create_task(self.timeout_monitor())
        worker_task = asyncio.create_task(self.response_worker())
        
        self.debug("[ORCHESTRATOR DEBUG] Starting background tasks...")
        
        # Initialize the Bee stream client
        bee = BeeClient(debug_mode=self.debug_mode)
        
        try:
            # Asynchronously consume the yielded text from the client
            async for new_text in bee.stream_utterances():
                self.debug(f"[ORCHESTRATOR DEBUG] ⚡ Received handoff: '{new_text}'")
                
                async with self.lock:
                    if self.text_buffer:
                        self.text_buffer += " "
                    self.text_buffer += new_text
                    
                    self.last_input_time = time.time()
                    current_length = len(self.text_buffer)
                    
                    self.debug(f"[ORCHESTRATOR DEBUG] Buffer updated: {current_length}/{self.max_chars} chars")
                
                # Check character limit
                if current_length >= self.max_chars:
                    await self.flush_to_model("5000 Character Limit Reached")
                    
        except asyncio.CancelledError:
            pass
        finally:
            # Safely kill the CLI process and clean up tasks
            bee.stop()
            monitor_task.cancel()
            await self.flush_to_model("Shutdown Flush")
            
            # Wait for any active model analyses to finish and print sequentially
            if not self.response_queue.empty():
                print("\nWaiting for remaining model responses to finish...")
                await self.response_queue.join()
            worker_task.cancel()


if __name__ == "__main__":
    # Setup command line arguments
    parser = argparse.ArgumentParser(description="Bee Stream Ingestion Orchestrator")
    parser.add_argument(
        '--debug', 
        type=str, 
        default="none", 
        help="Specify debug sector: 'all', 'bee', 'orchestrator', or 'none'"
    )
    args = parser.parse_args()

    # Pass the parsed argument into the orchestrator
    orchestrator = BeeStreamOrchestrator(debug_mode=args.debug, max_chars=5000, max_duration=300)
    
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        print("\nOrchestrator stopped gracefully.")