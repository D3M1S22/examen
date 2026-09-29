import subprocess
import json

def log_bee_conversations():
    # Spawns the CLI stream command from the local submodule
    cmd = ['bun', 'run', 'resources/bee-cli/bin/bee.js', 'stream']
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        print("Listening for Bee device data... (Press Ctrl+C to stop)")
        print("=" * 60)
        
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue
            
            # FAST STRING PARSING (No Regex)
            # An ISO timestamp always has 'T' at index 10, 'Z' at index 23, and starts with a year.
            # Example: 2026-09-29T18:09:31.044Z
            if len(line) >= 24 and line[10] == 'T' and line[23] == 'Z' and line[:4].isdigit():
                
                # 1. Isolate the timestamp
                timestamp = line[:24]
                
                # 2. Extract the rest of the line (.strip() removes the leading space)
                remainder = line[24:].strip()
                
                # 3. Split exclusively on the FIRST space to separate the event name from its payload
                parts = remainder.split(' ', 1)
                event_type = parts[0]
                payload = parts[1] if len(parts) > 1 else ""
                
                print(f"\n[{event_type.upper()}] - {timestamp}")
                
                # 4. JSON Guard: Only attempt to parse if the payload is clearly a JSON object
                if payload.startswith('{') and payload.endswith('}'):
                    try:
                        data = json.loads(payload)
                        print(json.dumps(data, indent=2))
                    except json.JSONDecodeError:
                        print(f"  {payload}")
                elif payload:
                    # Print standard string payloads (like the "Prova." string)
                    print(f"  {payload}")
                    
            else:
                # Catch non-timestamped lines (startup text, summary strings, or errors)
                print(f"  > {line}")

    except KeyboardInterrupt:
        print("\nStopped listening.")
    except FileNotFoundError:
        print("Error: Command not found. Ensure Bun is installed and you are in the correct directory.")

if __name__ == "__main__":
    log_bee_conversations()