"""PIPELINE_MODE=agentcore dispatch with in-process fallback (src/pipeline/remote.py)."""

import io
import json

import pytest

from src.core.config import settings
from src.core.tenancy import tenant_scope
from src.pipeline import remote

ARN = "arn:aws:bedrock-agentcore:eu-central-1:123456789012:runtime/examen_pipeline-abc"
UID = "usr_" + "a" * 32


class _FakeClient:
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"response": io.BytesIO(json.dumps(self.result).encode())}


@pytest.fixture
def agentcore(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "agentcore")
    monkeypatch.setattr(settings, "agentcore_runtime_arn", ARN)

    def install(client):
        monkeypatch.setattr(remote, "_client", lambda region: client)
        return client
    return install


def _local(calls):
    return lambda payload: calls.append(payload) or {"status": "success", "where": "local"}


def test_local_mode_never_calls_the_runtime(monkeypatch):
    monkeypatch.setattr(settings, "pipeline_mode", "local")
    monkeypatch.setattr(remote, "_client", lambda region: pytest.fail("remote called"))
    calls = []
    assert remote.invoke_pipeline({"text": "x"}, _local(calls))["where"] == "local"


def test_remote_call_carries_the_tenant_and_a_long_session_id(agentcore):
    client = agentcore(_FakeClient(result={"status": "success", "where": "remote"}))
    with tenant_scope(UID):
        result = remote.invoke_pipeline({"text": "x", "session_id": "ev-1"}, _local([]))
    assert result["where"] == "remote"
    sent = client.calls[0]
    assert sent["agentRuntimeArn"] == ARN
    assert json.loads(sent["payload"])["user_id"] == UID
    assert len(sent["runtimeSessionId"]) >= 33 and sent["runtimeSessionId"].startswith(UID)


def test_session_ids_differ_per_user():
    assert remote.runtime_session_id(UID, "ev-1") != remote.runtime_session_id("usr_" + "b" * 32, "ev-1")
    assert len(remote.runtime_session_id("u", "")) >= 33


def test_remote_failure_falls_back_in_process(agentcore):
    agentcore(_FakeClient(error=RuntimeError("throttled")))
    calls = []
    with tenant_scope(UID):
        result = remote.invoke_pipeline({"text": "x"}, _local(calls))
    assert result["where"] == "local" and calls[0]["user_id"] == UID


def test_tenant_rejection_is_not_retried_locally(agentcore):
    agentcore(_FakeClient(result={"status": "error", "error": "user_id does not match the caller's tenant"}))
    calls = []
    with tenant_scope(UID):
        result = remote.invoke_pipeline({"text": "x"}, _local(calls))
    assert result["status"] == "error" and calls == []


def test_without_a_tenant_the_pipeline_stays_local(agentcore):
    agentcore(_FakeClient(result={"status": "success", "where": "remote"}))
    calls = []
    assert remote.invoke_pipeline({"text": "x"}, _local(calls))["where"] == "local"
