import subprocess
import sys

try:
    result = subprocess.run(
        [sys.executable, "-m", "src.serving.mcp_server"],
        cwd="/Users/demis/github-repos/amazon_challenge",
        capture_output=True,
        text=True,
        timeout=5
    )
    with open("/Users/demis/github-repos/amazon_challenge/server_error.log", "w") as f:
        f.write("STDOUT:\n")
        f.write(result.stdout)
        f.write("\nSTDERR:\n")
        f.write(result.stderr)
        f.write(f"\nRETURN CODE: {result.returncode}\n")
except Exception as e:
    with open("/Users/demis/github-repos/amazon_challenge/server_error.log", "w") as f:
        f.write(str(e))
