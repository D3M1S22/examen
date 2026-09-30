import asyncio
import json
from debug import Debug

class BeeClient(Debug):
    def __init__(self, cli_path='resources/bee-cli/bin/bee.js', debug_mode="none"):
        super().__init__(debug_mode=debug_mode, sector_name="BEE")
        self.cli_path = cli_path
        self.process = None
    
    async def get_location(self):
        """Fetches the current location from the Bee CLI."""
        cmd = ['bun', 'run', self.cli_path, 'location current', '--json']
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            self.debug(f"Error fetching location: {stderr.strip()}")
            return None
        
        try:
            data = json.loads(stdout)
            return data["location"].get("address", "Unknown");
        except json.JSONDecodeError:
            self.debug("Failed to parse JSON from Bee CLI output.")
            return None

    async def stream_utterances(self):
        """Spawns the stream, yields utterances, and handles aggressive auto-reconnection."""
        retry_delay = 1
        
        while True:
            try:
                cmd = ['bun', 'run', self.cli_path, 'stream', '--json']
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    limit=1024 * 1024 * 10,
                    text=False
                )
                
                self.debug("Connected to Bee stream.")
                retry_delay = 1  # Reset delay on successful connection
                
                while True:
                    try:
                        # Wait maximum 60 seconds for ANY data (utterance or keep-alive)
                        # If the network dies silently, this raises a TimeoutError
                        line_bytes = await asyncio.wait_for(
                            self.process.stdout.readline(), 
                            timeout=330.0
                        )
                    except asyncio.TimeoutError:
                        self.debug("Stream timed out (no data for 330s). Assuming dead connection.")
                        break  # Break inner loop to kill process and retry

                    if not line_bytes:
                        # EOF reached: The bun process crashed or exited
                        self.debug("Stream process ended unexpectedly. Reconnecting...")
                        break 
                    
                    line = line_bytes.decode('utf-8').strip()
                    if not line:
                        # Safely ignore empty lines (SSE keep-alives)
                        continue 
                    
                    try:
                        data = json.loads(line)
                        if data.get("type") == "new-utterance":
                            text = data.get("utterance", {}).get("text", "")
                            if text:
                                self.debug(f"Extracted text: '{text}'")
                                yield text
                    except json.JSONDecodeError:
                        continue
                        
            except asyncio.CancelledError:
                self.stop()
                raise  # Re-raise to gracefully exit the generator during script shutdown
            except Exception as e:
                self.debug(f"Connection error: {e}")
                
            # If we break out of the inner loop, the connection is dead.
            # Clean up the dead process before attempting a retry.
            self.stop() 
            
            self.debug(f"Retrying connection in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            # Exponential backoff up to a maximum 1-minute wait
            retry_delay = min(retry_delay * 2, 60)

    def stop(self):
        """Cleanly terminates the underlying subprocess."""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            self.debug("Subprocess terminated.")