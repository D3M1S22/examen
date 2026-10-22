"""Admin console: service log, incidents, health monitor, runtime settings (docs/next_steps/admin_console/05 §2).

Offline: fake probes, fake readers and counters, temporary data dir (conftest). T-AC ids refer to the
test matrix of doc 05.
"""

import asyncio
import json
import logging
import re
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.core import runtime_settings
from src.core.config import settings
from src.core.metrics import Metrics
from src.core.ops_store import get_ops_store, utcnow
from src.core.service_log import (
    classify_llm_error,
    get_sink,
    report_event,
    resolve_quiet_incidents,
    sanitize,
)
from src.core.tenancy import tenant_scope
from tests import store_backend
from tests.test_accounts import PASSWORD, _register, app, multi_user  # noqa: F401

UID_A = "usr_" + "a1" * 16
UID_B = "usr_" + "b2" * 16


def _events(**filters):
    get_sink().flush()
    return get_ops_store().list_events(**filters)


def _admin(app):
    from src.core.auth import get_auth_store

    c = TestClient(app)
    uid = _register(c, "boss@example.com").json()["user"]["id"]
    get_auth_store().set_admin(uid, True)
    return c, uid


@pytest.fixture
def probes(monkeypatch):
    """Fake model probes: {group: exception or None}."""
    outcome = {"gatekeeper": None, "reasoner": None, "embeddings": None}

    def make(group):
        def _probe(cfg):
            if outcome[group] is not None:
                raise outcome[group]
            return f"{group} ok ({cfg.gatekeeper_model_id})"
        return _probe

    for group in outcome:
        monkeypatch.setitem(runtime_settings.PROBES, group, make(group))
    return outcome


# ---------------------------------------------------------------------------
# T-AC-1..3: capture and sanitising
# ---------------------------------------------------------------------------

def test_warning_records_become_sanitised_events():
    from src.core.logging_setup import setup_logging

    setup_logging()
    with tenant_scope(UID_A):
        logging.getLogger("examen.pipeline.social").warning("Failed for 'Marco Rossi': boom")
    [event] = _events(code="log.warning")
    assert event["message"] == "Failed for '…': boom"
    assert event["user_id"] == UID_A and event["component"] == "pipeline"
    assert event["location"] is None  # only src/ code locations are kept (this record comes from tests/)


def test_sanitizer_masks_personal_data_and_secrets():
    prompt = "ValidationException: " + "please summarise what Marco said about the contract " * 5
    out = sanitize(prompt)
    assert len(out) <= len("ValidationException: ") + 121 and out.endswith("…")
    masked = sanitize("mail ana@example.com from 192.168.1.9 key AKIAABCDEFGHIJKLMNOP api_key=abc123 "
                      "Bearer eyJhbGciOi exm_abcdefghijkl")
    for leaked in ("ana@example.com", "192.168.1.9", "AKIAABCDEFGHIJKLMNOP", "abc123", "eyJhbGciOi", "exm_abcdefghijkl"):
        assert leaked not in masked
    assert sanitize("x" * 1000).endswith("…") and len(sanitize("x" * 1000)) <= 300


def test_context_keeps_whitelisted_keys_only():
    report_event("pipeline.dispatch_failed", "error", "boom", component="pipeline",
                 transcript="I told Marco the code is 1234", session_id="ses_1", model_id="m")
    [event] = _events(code="pipeline.dispatch_failed")
    assert event["context"] == {"session_id": "ses_1", "model_id": "m"}
    assert "Marco" not in json.dumps(event)


def test_debug_lines_with_speech_never_reach_the_logs():
    from src.ingestion.debug import Debug

    seen = []
    handler = logging.Handler()
    handler.emit = lambda record: seen.append(record.getMessage())
    logger = logging.getLogger("examen.ingestion.stream_convo")
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        d = Debug("none", "BEE")
        d.debug("Received data: {'text': 'my PIN is 1234'}", log=False)
        d.debug("Connected to Bee stream (proxy).")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    assert seen == ["Connected to Bee stream (proxy)."]


def test_no_log_line_interpolates_user_content():
    """Phase 1 exit: names, titles and summaries are never interpolated into log messages."""
    # Manual curation added the fields of actions and commitments (docs/next_steps/manual_curation/05 T-MC-16)
    pattern = re.compile(r"logger\.\w+\(f[\"'].*\{[^}]*(person_name|topic_title|\.title|summary|transcript|\.text"
                         r"|raw_statement|action_type|\.description|contact_name)\b")
    offenders = []
    for path in Path("src").rglob("*.py"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path}:{n}")
    assert offenders == []


# ---------------------------------------------------------------------------
# T-AC-4..6: incidents, unhandled errors, erasure
# ---------------------------------------------------------------------------

def test_repeated_errors_group_into_one_incident():
    for _ in range(50):
        report_event("storage.write_failed", "error", "disk I/O error", component="storage", user_id=None)
    get_sink().flush()
    store = get_ops_store()
    [inc] = store.list_incidents(status="active")
    assert inc["count"] == 50 and inc["severity"] == "error"
    resolved = resolve_quiet_incidents(store, now=utcnow() + timedelta(minutes=61))
    assert [r["id"] for r in resolved] == [inc["id"]]
    report_event("storage.write_failed", "error", "disk I/O error", component="storage", user_id=None)
    get_sink().flush()
    again = store.get_incident(inc["id"])
    assert again["status"] == "open" and again["count"] == 51  # re-opened, same id


def test_warnings_open_an_incident_only_when_they_repeat():
    for i in range(4):
        report_event("bee.stream_disconnected", "warning", "Proxy error", component="bee", user_id=UID_A)
    get_sink().flush()
    assert get_ops_store().list_incidents(status="active") == []
    report_event("bee.stream_disconnected", "warning", "Proxy error", component="bee", user_id=UID_A)
    get_sink().flush()
    [inc] = get_ops_store().list_incidents(status="active")
    assert inc["count"] == 5 and inc["user_id"] == UID_A


def test_unhandled_route_error_answers_500_with_event_id(monkeypatch):
    from src.serving.mcp_server import create_app

    app_ = create_app()

    async def boom(request):
        raise RuntimeError("kaput")

    from starlette.routing import Route

    app_.router.routes.insert(0, Route("/api/test-boom", boom))  # before the static "/" mount
    res = TestClient(app_, raise_server_exceptions=False).get("/api/test-boom")
    assert res.status_code == 500 and res.json()["error"] == "internal_error"
    [event] = _events(code="serving.unhandled_exception")
    assert event["ref"] == res.json()["event_id"] and event["error_type"] == "RuntimeError"


def test_task_and_thread_exceptions_are_reported():
    from src.core.logging_setup import setup_logging
    from src.serving.error_capture import install_asyncio_handler

    setup_logging()

    async def main():
        loop = asyncio.get_running_loop()
        install_asyncio_handler(loop)
        loop.set_exception_handler(loop.get_exception_handler())
        loop.call_exception_handler({"message": "Task exception was never retrieved",
                                     "exception": ValueError("lost")})

    asyncio.run(main())
    t = threading.Thread(target=lambda: (_ for _ in ()).throw(KeyError("thread boom")), name="worker-x")
    t.start()
    t.join()
    codes = {e["code"] for e in _events()}
    assert {"system.task_exception", "system.thread_exception"} <= codes


def test_account_erasure_deletes_its_events(app):
    c = TestClient(app)
    uid = _register(c, "gone@example.com").json()["user"]["id"]
    report_event("bee.stream_stalled", "error", "stalled", component="bee", user_id=uid)
    report_event("system.started", "info", "other", component="system", user_id=None)
    get_sink().flush()
    assert _events(user_id=uid)
    assert c.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 200
    assert _events(user_id=uid) == []
    assert get_ops_store().list_incidents(user_id=uid, status="all") == []
    assert _events(code="system.started")


def test_llm_errors_are_classified():
    from botocore.exceptions import ClientError

    def client_error(code, message="x"):
        return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")

    assert classify_llm_error(client_error("ThrottlingException")) == "llm.throttled"
    assert classify_llm_error(client_error("AccessDeniedException")) == "llm.access_denied"
    assert classify_llm_error(client_error("ValidationException", "The provided model identifier is invalid.")) \
        == "llm.invalid_model"
    assert classify_llm_error(ValueError("bad json")) is None


def test_gatekeeper_fallback_is_reported(monkeypatch):
    from src.core.metrics import metrics
    from src.ingestion import gatekeeper

    monkeypatch.setattr(settings, "mock_ai", False)
    monkeypatch.setattr(gatekeeper, "has_active_model_credentials", lambda provider: True)

    class _Broken:
        def invoke(self, messages):
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")

    monkeypatch.setattr(gatekeeper, "_get_bedrock_classifier", lambda: _Broken())
    result = gatekeeper.classify_chunk("I locked the door")
    assert result.categories  # heuristic answer
    codes = [e["code"] for e in _events()]
    assert "gatekeeper.fallback" in codes and "llm.throttled" in codes
    assert metrics.count("gatekeeper.calls", 60) == 1


# ---------------------------------------------------------------------------
# T-AC-7..9: health monitor
# ---------------------------------------------------------------------------

def _monitor(**kwargs):
    from src.serving.health_monitor import HealthMonitor

    defaults = dict(metrics=Metrics(), memory_reader=lambda: (100, 1000), disk_reader=lambda: (10 ** 12, 2 * 10 ** 12))
    defaults.update(kwargs)
    return HealthMonitor(**defaults)


def _active(code):
    return [i for i in get_ops_store().list_incidents(status="active") if i["code"] == code]


def test_gatekeeper_degradation_opens_and_resolves():
    m = Metrics()
    monitor = _monitor(metrics=m)
    m.incr("gatekeeper.calls", value=20)
    m.incr("event:gatekeeper.fallback", value=6)
    monitor.tick()
    [inc] = _active("check.gatekeeper_degraded")
    assert inc["severity"] == "error"
    m.incr("gatekeeper.calls", value=60)
    monitor.tick()
    assert _active("check.gatekeeper_degraded") == []


def test_silent_stream_is_reported_for_that_user_only():
    clock = [10_000.0]
    streams = [{"user_id": UID_A, "linked": True, "running": True, "last_frame": clock[0] - 16 * 60},
               {"user_id": UID_B, "linked": True, "running": True, "last_frame": clock[0] - 30}]
    monitor = _monitor(stream_snapshot=lambda: streams, clock=lambda: clock[0])
    monitor.tick()
    assert [i["user_id"] for i in _active("check.stream_silent")] == [UID_A]
    streams[0]["last_frame"] = clock[0]
    monitor.tick()
    assert _active("check.stream_silent") == []


def test_disk_and_memory_checks():
    monitor = _monitor(disk_reader=lambda: (int(0.5 * 1024 ** 3), 100 * 1024 ** 3),
                       memory_reader=lambda: (800 * 1024 ** 2, 1000 * 1024 ** 2))
    monitor.tick()
    assert _active("check.disk_space")[0]["severity"] == "critical"
    assert _active("check.memory")[0]["severity"] == "warning"


def test_llm_limit_follows_the_setting(monkeypatch):
    from src.core.limits import llm_slot, llm_slots_in_use, notify_llm_limit_changed

    monkeypatch.setattr(settings, "max_concurrent_llm_calls", 1)
    peak = [0]

    async def worker():
        async with llm_slot():
            peak[0] = max(peak[0], llm_slots_in_use())
            await asyncio.sleep(0.02)

    async def main():
        tasks = [asyncio.create_task(worker()) for _ in range(4)]
        await asyncio.sleep(0.005)
        monkeypatch.setattr(settings, "max_concurrent_llm_calls", 4)
        await notify_llm_limit_changed()
        await asyncio.gather(*tasks)

    asyncio.run(main())
    assert peak[0] >= 2  # raised at runtime without a restart


# ---------------------------------------------------------------------------
# T-AC-10..17: runtime settings
# ---------------------------------------------------------------------------

def test_hot_override_applies_and_is_recorded(app, probes):
    from src.core.auth import get_auth_store
    from src.core.models import get_fast_model

    admin, admin_id = _admin(app)
    changes = {"gatekeeper_model_id": "us.anthropic.claude-haiku-4-5-v1:0"}
    test = admin.post("/api/admin/settings/test", json={"changes": changes}).json()
    assert test["ok"] and [r["group"] for r in test["results"]] == ["gatekeeper"]
    res = admin.put("/api/admin/settings", json={"changes": changes})
    assert res.status_code == 200, res.text
    assert settings.gatekeeper_model_id == "us.anthropic.claude-haiku-4-5-v1:0"
    assert getattr(get_fast_model(), "model_id", None) == "us.anthropic.claude-haiku-4-5-v1:0"
    row = next(r for r in admin.get("/api/admin/settings").json()["settings"] if r["key"] == "gatekeeper_model_id")
    assert row["source"] == "override" and row["override_by"] == admin_id
    history = admin.get("/api/admin/settings/history").json()["history"]
    assert history[0]["changes"][0]["new"] == "us.anthropic.claude-haiku-4-5-v1:0"
    assert any(e["event"] == "settings_changed" for e in get_auth_store().list_audit(limit=20))


def test_invalid_changes_are_rejected_whole(app):
    admin, _ = _admin(app)
    before = (settings.max_active_users, settings.web_search_cache_ttl_seconds)
    res = admin.put("/api/admin/settings", json={"changes": {
        "max_active_users": 0, "bee_stream_transport": "carrier-pigeon", "aws_secret_access_key": "x",
        "event_t_soft_seconds": 5000, "web_search_cache_ttl_seconds": 10}})
    assert res.status_code == 400
    errors = res.json()["errors"]
    assert set(errors) >= {"max_active_users", "bee_stream_transport", "aws_secret_access_key"}
    assert (settings.max_active_users, settings.web_search_cache_ttl_seconds) == before  # nothing applied
    cross = admin.put("/api/admin/settings", json={"changes": {"event_t_soft_seconds": 5000,
                                                               "event_t_hard_seconds": 4000}})
    assert cross.status_code == 400 and "event_t_soft_seconds" in cross.json()["errors"]


def test_ai_changes_need_a_passing_test(app, probes):
    admin, _ = _admin(app)
    changes = {"reasoner_model_id": "anthropic.claude-sonnet-4-5"}
    assert admin.put("/api/admin/settings", json={"changes": changes}).json()["error"] == "test_required"
    probes["reasoner"] = RuntimeError("ValidationException: The provided model identifier is invalid.")
    result = admin.post("/api/admin/settings/test", json={"changes": changes}).json()
    assert result["ok"] is False and "invalid" in result["results"][0]["message"]
    assert admin.put("/api/admin/settings", json={"changes": changes}).status_code == 409
    forced = admin.put("/api/admin/settings", json={"changes": changes, "force": True})
    assert forced.status_code == 200 and forced.json()["forced_untested"] == ["reasoner"]
    assert _events(code="settings.forced_untested")


def test_runtime_keys_rebuild_every_users_runtime(multi_user, monkeypatch):
    from src.ingestion import event_engine as ee

    server = multi_user
    monkeypatch.setattr(ee, "_tenant_engines", {})
    monkeypatch.setattr(ee, "_tenant_runtimes", {})
    monkeypatch.setattr(server.OrchestratorManager, "_tenant_instances", {})

    async def main():
        for uid in (UID_A, UID_B):
            with tenant_scope(uid):
                ee.get_event_engine_runtime()
        old = {uid: ee._tenant_engines[uid] for uid in (UID_A, UID_B)}
        monkeypatch.setattr(settings, "event_t_soft_seconds", 400.0)
        rebuilt = await server.rebuild_all_runtimes()
        return old, rebuilt

    old, rebuilt = asyncio.run(main())
    assert rebuilt == 2
    for uid in (UID_A, UID_B):
        assert ee._tenant_engines[uid] is not old[uid]
        assert ee._tenant_engines[uid].config.t_soft == 400.0
    for uid in (UID_A, UID_B):
        ee.drop_tenant_event_engine(uid)


def test_runtime_change_calls_the_rebuild_hook(app):
    from src.core.runtime_settings import get_settings_service

    calls = []

    async def fake_rebuild():
        calls.append(1)
        return 3

    get_settings_service().rebuild_runtimes = fake_rebuild
    admin, _ = _admin(app)
    res = admin.put("/api/admin/settings", json={"changes": {"event_t_soft_seconds": 240}})
    assert res.json()["rebuilt_runtimes"] == 3 and calls == [1]
    hot = admin.put("/api/admin/settings", json={"changes": {"backfill_lookback_days": 1}})
    assert hot.json()["rebuilt_runtimes"] == 0 and calls == [1]  # hot keys need no rebuild


def test_revert_reset_and_reload_after_restart(app):
    from src.core.runtime_settings import SettingsService, get_settings_service

    admin, _ = _admin(app)
    env_value = get_settings_service().env_values["web_search_cache_ttl_seconds"]
    first = admin.put("/api/admin/settings", json={"changes": {"web_search_cache_ttl_seconds": 60}}).json()
    admin.put("/api/admin/settings", json={"changes": {"web_search_cache_ttl_seconds": 120,
                                                       "backfill_lookback_days": 3}})
    # A new process reloads the overrides from ops.db
    fresh = SettingsService()
    settings.web_search_cache_ttl_seconds = env_value
    assert set(fresh.load()) == {"web_search_cache_ttl_seconds", "backfill_lookback_days"}
    assert settings.web_search_cache_ttl_seconds == 120
    latest = admin.get("/api/admin/settings/history").json()["history"][0]["change_id"]
    assert admin.post("/api/admin/settings/revert", json={"change_id": latest}).status_code == 200
    assert settings.web_search_cache_ttl_seconds == 60
    assert first["change_id"]
    assert admin.post("/api/admin/settings/reset-all").status_code == 200
    assert settings.web_search_cache_ttl_seconds == env_value
    rows = admin.get("/api/admin/settings").json()["settings"]
    assert all(r["source"] != "override" for r in rows)


def test_stale_version_is_refused(app):
    admin, _ = _admin(app)
    version = admin.get("/api/admin/settings").json()["version"]
    admin.put("/api/admin/settings", json={"changes": {"backfill_lookback_days": 1}, "base_version": version})
    stale = admin.put("/api/admin/settings", json={"changes": {"backfill_lookback_days": 2}, "base_version": version})
    assert stale.status_code == 409 and stale.json()["error"] == "settings_changed_meanwhile"


def test_console_routes_are_admin_only_and_session_only(app):
    admin, _ = _admin(app)
    user = TestClient(app)
    _register(user, "plain@example.com")
    for path in ("/api/admin/settings", "/api/admin/logs", "/api/admin/incidents", "/api/admin/health"):
        assert user.get(path).status_code == 403, path
    secret = admin.post("/api/account/tokens", json={"name": "a"}).json()["token"]["token"]
    machine = TestClient(app, headers={"Authorization": f"Bearer {secret}"})
    assert machine.get("/api/admin/settings").status_code == 403
    cross = admin.put("/api/admin/settings", json={"changes": {"backfill_lookback_days": 1}},
                      headers={"Origin": "http://evil.example"})
    assert cross.status_code == 403


def test_secrets_never_leave_the_server(app, probes, monkeypatch):
    monkeypatch.setattr(settings, "aws_secret_access_key", "SUPERSECRETVALUE123")
    monkeypatch.setattr(settings, "mantle_api_key", "bedrock-api-key-TOPSECRET")
    admin, _ = _admin(app)
    body = admin.get("/api/admin/settings").text
    assert "SUPERSECRETVALUE123" not in body and "TOPSECRET" not in body
    statuses = {s["key"]: s["status"] for s in admin.get("/api/admin/settings").json()["secrets"]}
    assert statuses["aws_secret_access_key"] == "configured" and statuses["mantle_api_key"] == "configured"
    probes["gatekeeper"] = RuntimeError("UnrecognizedClientException: key AKIAABCDEFGHIJKLMNOP bedrock-api-key-TOPSECRET")
    result = admin.post("/api/admin/settings/test", json={"changes": {"gatekeeper_model_id": "m.x-1"}}).text
    assert "AKIAABCDEFGHIJKLMNOP" not in result and "TOPSECRET" not in result
    raw = store_backend.dump_table("ops") if store_backend.DYNAMO else Path(get_ops_store().db_path).read_bytes()
    assert b"SUPERSECRETVALUE123" not in raw and b"TOPSECRET" not in raw


def test_incident_after_a_model_change_offers_the_revert(app, probes):
    from src.core.runtime_settings import get_settings_service

    admin, _ = _admin(app)
    before = settings.gatekeeper_model_id
    saved = admin.put("/api/admin/settings", json={"changes": {"gatekeeper_model_id": "wrong.model-v9"},
                                                    "force": True}).json()
    m = Metrics()
    monitor = _monitor(metrics=m, settings_service=get_settings_service())
    m.incr("gatekeeper.calls", value=20)
    m.incr("event:gatekeeper.fallback", value=20)
    monitor.tick()
    [inc] = _active("check.gatekeeper_degraded")
    assert inc["change_id"] == saved["change_id"]
    assert admin.post("/api/admin/settings/revert", json={"change_id": inc["change_id"]}).status_code == 200
    assert settings.gatekeeper_model_id == before


# ---------------------------------------------------------------------------
# API: logs, incidents, health; T-AC-18 privacy
# ---------------------------------------------------------------------------

def test_logs_incidents_and_health_routes(app):
    admin, _ = _admin(app)
    user = TestClient(app)
    uid = _register(user, "streamer@example.com").json()["user"]["id"]
    for _ in range(3):
        report_event("storage.write_failed", "error", "disk I/O error", component="storage", user_id=uid)
    get_sink().flush()
    events = admin.get("/api/admin/logs", params={"level": "error"}).json()["events"]
    assert events and events[0]["user_email"] == "streamer@example.com"
    [inc] = admin.get("/api/admin/incidents").json()["incidents"]
    detail = admin.get(f"/api/admin/incidents/{inc['id']}").json()
    assert len(detail["events"]) == 3
    assert admin.post(f"/api/admin/incidents/{inc['id']}/ack").json()["incident"]["status"] == "acknowledged"
    assert admin.post(f"/api/admin/incidents/{inc['id']}/resolve").json()["incident"]["status"] == "resolved"
    health = admin.get("/api/admin/health").json()
    assert {"uptime_s", "memory", "disk", "streams", "llm", "incidents_open"} <= set(health)


def test_admin_console_never_returns_user_data(app):
    alice = TestClient(app)
    _register(alice, "alice-private@example.com")
    alice.post("/api/routines", json={"title": "SECRET-ROUTINE-4242"})
    with tenant_scope(alice.get("/api/auth/session").json()["user"]["id"]):
        logging.getLogger("examen.pipeline.persist").warning("Persisted 'SECRET-CONTACT-777' failed: x")
    get_sink().flush()
    admin, _ = _admin(app)
    for path in ("/api/admin/settings", "/api/admin/logs", "/api/admin/incidents", "/api/admin/health",
                 "/api/admin/settings/history"):
        text = admin.get(path).text
        assert "SECRET-ROUTINE-4242" not in text and "SECRET-CONTACT-777" not in text, path
    source = Path("src/serving/admin_console_routes.py").read_text()
    assert "get_storage_store" not in source and "get_tenant_store" not in source


def test_admin_sse_channel_receives_service_events():
    from src.serving.admin_console_routes import AdminHub

    hub = AdminHub()

    async def main():
        queue = hub.subscribe()
        get_sink().add_listener(hub.on_sink)
        try:
            report_event("llm.access_denied", "error", "AccessDeniedException", component="llm", user_id=None)
            await asyncio.to_thread(get_sink().flush)
            first = await asyncio.wait_for(queue.get(), timeout=2)
            second = await asyncio.wait_for(queue.get(), timeout=2)
        finally:
            get_sink().remove_listener(hub.on_sink)
            hub.unsubscribe(queue)
        return first, second

    first, second = asyncio.run(main())
    assert first["type"] == "service_event" and first["data"]["code"] == "llm.access_denied"
    assert second["type"] == "incident_opened"



# ---------------------------------------------------------------------------
# Token usage per model (03 §8)
# ---------------------------------------------------------------------------

def _usage_rows():
    from src.core import token_usage

    token_usage.flush()
    return get_ops_store().token_usage_summary()


def test_factory_models_report_their_tokens(monkeypatch):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.output_parsers import StrOutputParser

    from src.core.models import get_chat_model, get_fast_model
    from src.core.token_usage import TokenUsageHandler

    model = get_chat_model("bedrock", "us.anthropic.claude-haiku-4-5", role="probe")
    [handler] = [c for c in model.callbacks if isinstance(c, TokenUsageHandler)]
    assert (handler.provider, handler.model_id, handler.role) == ("bedrock", "us.anthropic.claude-haiku-4-5", "probe")
    assert get_fast_model(role="gatekeeper").callbacks[0].role == "gatekeeper"

    fake = GenericFakeChatModel(
        messages=iter([AIMessage(content="ok", usage_metadata={
            "input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
            "input_token_details": {"cache_read": 40, "cache_creation": 10}})]),
        callbacks=[TokenUsageHandler("bedrock", "model-x", "extraction")])
    with tenant_scope(UID_A):
        assert (fake | StrOutputParser()).invoke("hi") == "ok"  # wrapped like with_structured_output
    summary = _usage_rows()
    [row] = summary["by_model"]
    assert row["model_id"] == "model-x" and row["calls"] == 1
    assert (row["input_tokens"], row["output_tokens"], row["cache_read_tokens"], row["cache_write_tokens"]) == (120, 30, 40, 10)
    assert row["roles"]["extraction"]["input_tokens"] == 120
    assert summary["by_user"][0]["user_id"] == UID_A


def test_embedding_tokens_are_read_from_the_bedrock_response(monkeypatch):
    from langchain_aws import BedrockEmbeddings

    from src.core.models import get_embedding_model

    monkeypatch.setattr(BedrockEmbeddings, "_invoke_model",
                        lambda self, input_body={}: {"embedding": [0.1, 0.2], "inputTextTokenCount": 7})
    assert get_embedding_model().embed_query("hello") == [0.1, 0.2]
    [row] = _usage_rows()["by_model"]
    assert row["roles"]["embeddings"]["input_tokens"] == 7 and row["output_tokens"] == 0


def test_flush_accumulates_and_survives_database_errors():
    from src.core import token_usage

    token_usage.record("mantle", "m", "reasoner", input_tokens=10, output_tokens=5, user_id="")
    token_usage.flush()
    token_usage.record("mantle", "m", "reasoner", input_tokens=1, output_tokens=1, user_id="")

    class _Broken:
        def add_token_usage(self, rows):
            raise RuntimeError("database is locked")

    assert token_usage.flush(lambda: _Broken()) == 0  # kept for the next flush
    totals = _usage_rows()["totals"]
    assert (totals["calls"], totals["input_tokens"], totals["output_tokens"]) == (2, 11, 6)


def test_counting_never_breaks_a_model_call():
    from src.core.token_usage import TokenUsageHandler

    TokenUsageHandler("bedrock", "m", "gatekeeper").on_llm_end(object())  # malformed result: no exception
    TokenUsageHandler("bedrock", "m", "gatekeeper").on_llm_end(None)


def test_usage_route_groups_by_model_and_user(app):
    from src.core import token_usage

    admin, _ = _admin(app)
    user = TestClient(app)
    uid = _register(user, "heavy@example.com").json()["user"]["id"]
    token_usage.record("bedrock", "gk", "gatekeeper", input_tokens=900, output_tokens=100, user_id=uid)
    token_usage.record("mantle", "rs", "reasoner", input_tokens=50, output_tokens=50, user_id="")
    token_usage.record("bedrock", "old", "gatekeeper", input_tokens=5, user_id=uid,
                       now=utcnow() - timedelta(days=3))
    body = admin.get("/api/admin/usage", params={"range": "24h"}).json()
    assert [m["model_id"] for m in body["by_model"]] == ["gk", "rs"]  # 3-day-old row outside the range
    assert body["by_model"][0]["share"] == pytest.approx(1000 / 1100, abs=1e-3)
    assert {u["user_email"] for u in body["by_user"]} == {"heavy@example.com", None}
    assert len(admin.get("/api/admin/usage", params={"range": "7d"}).json()["by_model"]) == 3
    assert admin.get("/api/admin/usage", params={"range": "1y"}).status_code == 400
    assert user.get("/api/admin/usage").status_code == 403
    secret = admin.post("/api/account/tokens", json={"name": "a"}).json()["token"]["token"]
    assert TestClient(app, headers={"Authorization": f"Bearer {secret}"}).get("/api/admin/usage").status_code == 403
    health = admin.get("/api/admin/health").json()
    assert health["tokens_24h"]["tokens"] == 1100 and health["tokens_24h"]["top_model"] == "gk"
    # Erasure removes the account's usage rows
    assert user.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 200
    assert {u["user_id"] for u in admin.get("/api/admin/usage", params={"range": "7d"}).json()["by_user"]} == {""}
