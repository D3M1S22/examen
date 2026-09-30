import asyncio
import json
from debug import Debug

class BeeClient(Debug):
    def __init__(self, cli_path='resources/bee-cli/bin/bee.js', debug_mode="none"):
        super().__init__(debug_mode=debug_mode, sector_name="BEE")
        self.cli_path = cli_path
        self.process = None

    async def stream_utterances(self):
        """Spawns the stream and yields only single live utterances."""
        cmd = ['bun', 'run', self.cli_path, 'stream', '--json']
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                limit=1024 * 1024 * 10,
                text=False
            )
            
            print("Listening for Bee device data... (Press Ctrl+C to stop)")
            
            while True:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break
                    
                line = line_bytes.decode('utf-8').strip()
                if not line:
                    continue
                    
                try:
                    data = json.loads(line)
                    
                    # Strictly filter for only new-utterance events
                    if data.get("type") == "new-utterance":
                        text = data.get("utterance", {}).get("text", "")
                        
                        if text:
                            self.debug(f"Extracted text: '{text}'")
                            yield text
                                
                except json.JSONDecodeError:
                    continue
                    
        except asyncio.CancelledError:
            self.stop()
        except Exception as e:
            print(f"Stream error: {e}")
            self.stop()

    def stop(self):
        """Cleanly terminates the underlying subprocess."""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            self.debug("Subprocess terminated.")