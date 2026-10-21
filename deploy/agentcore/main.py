"""AgentCore Runtime entry point (direct code deployment, docs/17_aws_deployment_runbook.md §5.4).

Serves ``src.pipeline.app.agent_invocation`` on port 8080 (``/invocations``, ``/ping``). The runtime
reaches the user's data in DynamoDB with tenant-scoped credentials (EXAMEN_REMOTE_RUNTIME=1).
"""

import os

# The platform sets AWS_REGION to the runtime's region; Bedrock may live elsewhere (BEDROCK_REGION).
# Settings read AWS_REGION at import, so this must run before any src import. DynamoDB uses DYNAMO_REGION.
if os.environ.get("BEDROCK_REGION"):
    os.environ["AWS_REGION"] = os.environ["BEDROCK_REGION"]

from src.pipeline.app import app  # noqa: E402

if __name__ == "__main__":
    app.run()
