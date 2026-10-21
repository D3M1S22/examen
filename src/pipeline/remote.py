"""Pipeline dispatch: in-process or on AgentCore Runtime (docs/17_aws_deployment_runbook.md §5.4).

``PIPELINE_MODE=agentcore`` with ``AGENTCORE_RUNTIME_ARN`` sends each qualified chunk to the deployed
runtime (``deploy/agentcore/``), which runs the same ``agent_invocation`` and writes the user's data
straight to DynamoDB with tenant-scoped credentials. Any remote failure falls back to the in-process
pipeline, so ingestion never stops because of the runtime. The payload always carries ``user_id``.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Callable, Dict, Optional

from src.core.config import settings
from src.core.tenancy import get_tenant_id

logger = logging.getLogger("examen.pipeline.remote")

_client_lock = threading.Lock()
_clients: Dict[str, Any] = {}


def remote_enabled() -> bool:
    return settings.pipeline_mode == "agentcore" and bool(settings.agentcore_runtime_arn)


def _client(region: str) -> Any:
    with _client_lock:
        client = _clients.get(region)
        if client is None:
            from botocore.config import Config

            from src.core.storage.dynamo_client import _session

            client = _session().client("bedrock-agentcore", region_name=region, config=Config(
                read_timeout=settings.agentcore_timeout_seconds, connect_timeout=10,
                retries={"mode": "standard", "max_attempts": 2}))
            _clients[region] = client
        return client


def runtime_session_id(user_id: str, session_id: str) -> str:
    """AgentCore session ids are at least 33 characters; one per user and event, never shared by users."""
    base = f"{user_id}-{session_id or 'nosession'}"
    return base if len(base) >= 33 else base + "-" + uuid.uuid5(uuid.NAMESPACE_URL, base).hex[: 33 - len(base)]


def invoke_remote(payload: Dict[str, Any]) -> Dict[str, Any]:
    arn = settings.agentcore_runtime_arn
    region = arn.split(":")[3]
    response = _client(region).invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=runtime_session_id(payload["user_id"], str(payload.get("session_id") or "")),
        contentType="application/json",
        accept="application/json",
        payload=json.dumps(payload, default=str).encode("utf-8"),
    )
    body = response["response"].read()
    result = json.loads(body.decode("utf-8")) if body else {}
    if not isinstance(result, dict):
        raise ValueError("AgentCore runtime returned a non-object result")
    return result


def invoke_pipeline(payload: Dict[str, Any], local: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
                    ) -> Dict[str, Any]:
    """Same contract as ``agent_invocation``: payload in, result dict out. ``local`` is the in-process
    pipeline (default ``src.pipeline.app.agent_invocation``)."""
    if local is None:
        from src.pipeline.app import agent_invocation as local

    agent_invocation = local
    payload = dict(payload)
    payload.setdefault("user_id", get_tenant_id())
    if payload.get("user_id") is None:
        payload.pop("user_id")
    if not remote_enabled() or "user_id" not in payload:
        return agent_invocation(payload)
    try:
        result = invoke_remote(payload)
        if result.get("status") == "error" and "user_id" in str(result.get("error", "")):
            return result  # a tenant rejection must not be retried locally under another identity
        try:
            from src.core.metrics import metrics

            metrics.incr("pipeline.remote", payload.get("user_id"))
        except Exception:
            pass
        return result
    except Exception as e:
        from src.core.service_log import report_event

        report_event("pipeline.remote_fallback", "warning",
                     f"AgentCore runtime unavailable, pipeline ran in-process: {type(e).__name__}",
                     component="pipeline", error=e)
        return agent_invocation(payload)
