import asyncio
import json

from src.ingestion.debug import Debug


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

    async def stream_events(self):
        """Spawns the stream, yields parsed SSE events (utterances, location, diarization updates)."""
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
                retry_delay = 1
                
                while True:
                    try:
                        line_bytes = await asyncio.wait_for(
                            self.process.stdout.readline(), 
                            timeout=330.0
                        )
                    except asyncio.TimeoutError:
                        self.debug("Stream timed out (no data for 330s). Assuming dead connection.")
                        break

                    if not line_bytes:
                        self.debug("Stream process ended unexpectedly. Reconnecting...")
                        break 
                    
                    line = line_bytes.decode('utf-8').strip()
                    if not line:
                        continue 
                    
                    try:
                        data = json.loads(line)
                        self.debug(f"Received data: {data}")
                        msg_type = data.get("type") or data.get("event")

                        if msg_type == "new-utterance":
                            utt = data.get("utterance", {})
                            yield {
                                "event": "new-utterance",
                                "data": {
                                    "id": str(utt.get("id") or data.get("id") or ""),
                                    "text": utt.get("text") or data.get("text") or "",
                                    "speaker": utt.get("speaker") or data.get("speaker"),
                                    "conversation_uuid": data.get("conversation_id") or data.get("conversation_uuid") or "default_session",
                                }
                            }
                        elif msg_type == "update-location":
                            loc = data.get("location") or data.get("data", {}).get("location", {})
                            yield {
                                "event": "update-location",
                                "data": loc
                            }
                        elif msg_type == "update-utterance":
                            yield {
                                "event": "update-utterance",
                                "data": {
                                    "utterance_id": str(data.get("utterance_id") or data.get("id") or data.get("data", {}).get("utterance_id") or ""),
                                    "speaker": data.get("speaker") or data.get("data", {}).get("speaker"),
                                    "conversation_uuid": data.get("conversation_id") or data.get("data", {}).get("conversation_id") or "default_session",
                                }
                            }
                    except json.JSONDecodeError:
                        continue
                        
            except asyncio.CancelledError:
                self.stop()
                raise
            except Exception as e:
                self.debug(f"Connection error: {e}")
                
            self.stop() 
            self.debug(f"Retrying connection in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)

    async def stream_utterances(self):
        """Spawns the stream, yields raw utterance text strings for backward compatibility."""
        async for event in self.stream_events():
            if event.get("event") == "new-utterance":
                text = event.get("data", {}).get("text", "")
                if text:
                    self.debug(f"Extracted text: '{text}'")
                    yield text

    def stop(self):
        """Cleanly terminates the underlying subprocess."""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            self.debug("Subprocess terminated.")