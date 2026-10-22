"""Pipeline dispatch: in-process or on AgentCore Runtime (docs/17_aws_deployment_runbook.md §5.4).

``PIPELINE_MODE=agentcore`` with ``AGENTCORE_RUNTIME_ARN`` sends each qualified chunk to the deployed
runtime (``deploy/agentcore/``), which runs the same ``agent_invocation`` and writes the user's data
straight to DynamoDB with tenant-scoped credentials. The payload always carries ``user_id``.

The invocation is not idempotent, so it is never retried. A failure before the runtime received the
payload (connection, credentials, throttling, other 4xx) falls back to the in-process pipeline. A
failure after it may have run (read timeout, dropped connection, 5xx, unreadable answer) is returned
as an error: the chunk is marked ``failed`` in the ledger and the backfill analyses it again, instead
of running it twice now.
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


class RemoteOutcomeUnknown(Exception):
    """The runtime may have run the payload: it must not be run again in-process."""


def remote_enabled() -> bool:
    return settings.pipeline_mode == "agentcore" and bool(settings.agentcore_runtime_arn)


def _client(region: str) -> Any:
    with _client_lock:
        client = _clients.get(region)
        if client is None:
            from botocore.config import Config

            from src.core.storage.dynamo_client import _session

            # One attempt only: botocore would resend the payload after a read timeout
            # (``max_attempts`` counts retries, ``total_max_attempts`` includes the first call)
            client = _session().client("bedrock-agentcore", region_name=region, config=Config(
                read_timeout=settings.agentcore_timeout_seconds, connect_timeout=10,
                retries={"mode": "standard", "total_max_attempts": 1}))
            _clients[region] = client
        return client


def _reached_runtime(error: Exception) -> bool:
    """Whether the runtime may have received (and run) the payload when ``error`` was raised."""
    from botocore.exceptions import BotoCoreError, ClientError, ConnectionError, HTTPClientError

    if isinstance(error, ConnectionError):  # endpoint, connect timeout, proxy, TLS: nothing was sent
        return False
    if isinstance(error, ClientError):
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
        # 4xx: rejected by the service (throttling, access, validation); 424: the runtime itself failed
        return not (400 <= status < 500 and status != 424)
    if isinstance(error, BotoCoreError):
        return isinstance(error, HTTPClientError)  # read timeout, connection closed, broken stream
    return True


def runtime_session_id(user_id: str, session_id: str) -> str:
    """AgentCore session ids are at least 33 characters; one per user and event, never shared by users."""
    base = f"{user_id}-{session_id or 'nosession'}"
    return base if len(base) >= 33 else base + "-" + uuid.uuid5(uuid.NAMESPACE_URL, base).hex[: 33 - len(base)]


def invoke_remote(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Raises ``RemoteOutcomeUnknown`` when the runtime may have run the payload, any other error when not."""
    arn = settings.agentcore_runtime_arn
    region = arn.split(":")[3]
    client = _client(region)
    body = json.dumps(payload, default=str).encode("utf-8")
    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            runtimeSessionId=runtime_session_id(payload["user_id"], str(payload.get("session_id") or "")),
            contentType="application/json",
            accept="application/json",
            payload=body,
        )
    except Exception as e:
        if _reached_runtime(e):
            raise RemoteOutcomeUnknown(type(e).__name__) from e
        raise
    try:
        raw = response["response"].read()
        result = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(result, dict):
            raise ValueError("AgentCore runtime returned a non-object result")
    except Exception as e:
        raise RemoteOutcomeUnknown(type(e).__name__) from e
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
        _metric("pipeline.remote", payload.get("user_id"))
        return result
    except RemoteOutcomeUnknown as e:
        from src.core.service_log import report_event

        cause = e.__cause__ or e
        report_event("pipeline.remote_unknown", "error",
                     f"AgentCore outcome unknown, chunk left to the backfill: {type(cause).__name__}",
                     component="pipeline", error=cause)
        _metric("pipeline.remote_unknown", payload.get("user_id"))
        return {"status": "error", "error": f"AgentCore outcome unknown: {type(cause).__name__}",
                "remote_outcome": "unknown"}
    except Exception as e:
        from src.core.service_log import report_event

        report_event("pipeline.remote_fallback", "warning",
                     f"AgentCore runtime unavailable, pipeline ran in-process: {type(e).__name__}",
                     component="pipeline", error=e)
        return agent_invocation(payload)


def _metric(name: str, user_id: Optional[str]) -> None:
    try:
        from src.core.metrics import metrics

        metrics.incr(name, user_id)
    except Exception:
        pass
