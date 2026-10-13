import asyncio
import json
import os
import platform
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.ingestion.debug import Debug


def normalize_bee_time(value) -> Optional[str]:
    """Converts a Bee time value (epoch seconds/milliseconds or ISO string) to a local ISO string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return datetime.fromtimestamp(seconds).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat()


def get_bee_binary_path() -> Optional[str]:
    """Resolves the best available Bee CLI executable path.

    Checks:
    1. System PATH ('bee')
    2. Local precompiled platform binary in resources/bee-cli/dist/platforms/
    3. resources/bee-cli/bin/bee.js (if bun/node is available)
    """
    which_bee = shutil.which("bee")
    if which_bee:
        return which_bee

    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    base_dir = Path(__file__).resolve().parent.parent.parent

    candidate = None
    if sys_name == "darwin":
        if machine in ("arm64", "aarch64"):
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "mac-arm64" / "bee"
        else:
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "mac-x64" / "bee"
    elif sys_name == "linux":
        if machine in ("arm64", "aarch64"):
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "linux-arm64" / "bee"
        else:
            candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "linux-x64" / "bee"
    elif sys_name == "windows":
        candidate = base_dir / "resources" / "bee-cli" / "dist" / "platforms" / "windows-x64" / "bee.exe"

    if candidate and candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)

    js_candidate = base_dir / "resources" / "bee-cli" / "bin" / "bee.js"
    if js_candidate.exists():
        return str(js_candidate)

    return None


class BeeClient(Debug):
    def __init__(self, cli_path='resources/bee-cli/bin/bee.js', debug_mode="none"):
        super().__init__(debug_mode=debug_mode, sector_name="BEE")
        self.cli_path = cli_path
        self.process = None

    def _build_cmd(self, subcmd_args: List[str]) -> List[str]:
        bin_path = get_bee_binary_path() or self.cli_path
        if bin_path.endswith(".js"):
            runner = "bun" if shutil.which("bun") else ("node" if shutil.which("node") else "bun")
            return [runner, "run", bin_path] + subcmd_args
        return [bin_path] + subcmd_args

    async def get_location(self):
        """Fetches the current location from the Bee CLI."""
        cmd = self._build_cmd(['location', 'current', '--json'])
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
            return data["location"].get("address", "Unknown")
        except json.JSONDecodeError:
            self.debug("Failed to parse JSON from Bee CLI output.")
            return None

    async def stream_events(self):
        """Spawns the stream, yields parsed SSE events (utterances, location, diarization updates)."""
        retry_delay = 1

        while True:
            try:
                cmd = self._build_cmd(['stream', '--json'])
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
                    
                    received_at = datetime.now().isoformat()
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
                                    # Utterance timing: the documented stream payload has no time fields,
                                    # so capture the receive time here (before screening/queueing).
                                    "received_at": received_at,
                                    "spoken_at": normalize_bee_time(utt.get("spoken_at") or data.get("spoken_at")),
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
                        elif "timestamp" in data and not msg_type:
                            yield {
                                "event": "stream-heartbeat",
                                "data": data
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