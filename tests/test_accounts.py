"""Multi-user accounts: registration, sessions, per-user data isolation, MCP tokens, GDPR export and
erasure, per-user Bee login isolation and QR pairing (docs/13_multi_user_accounts.md)."""

import asyncio
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.core.auth import passwords
from src.core.auth.passwords import hash_password, password_problem, verify_password
from src.core.config import settings
from src.core.tenancy import (
    bee_subprocess_env,
    get_tenant_id,
    tenant_db_path,
    tenant_dir,
    tenant_has_bee_login,
    tenant_scope,
)
from tests import store_backend
from tests.store_backend import new_store

PASSWORD = "correct horse battery"


@pytest.fixture
def multi_user(monkeypatch):
    """AUTH_ENABLED with cheap password hashing and no background engines."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "event_engine_enabled", False)
    monkeypatch.setattr(settings, "backfill_enabled", False)
    monkeypatch.setattr(settings, "auth_max_login_failures", 3)
    monkeypatch.setattr(passwords, "_LOG2_N", 10)
    import src.serving.mcp_server as server_mod

    return server_mod


@pytest.fixture
def app(multi_user):
    return multi_user.create_app()


def _client(app) -> TestClient:
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = PASSWORD, consent: bool = True):
    return client.post("/api/auth/register", json={
        "email": email, "password": password, "display_name": email.split("@")[0], "privacy_consent": consent,
    })


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def test_password_hash_roundtrip(monkeypatch):
    monkeypatch.setattr(passwords, "_LOG2_N", 10)
    encoded = hash_password(PASSWORD)
    assert encoded.startswith("scrypt$10$8$2$")  # N=2^16-class parameters: r=8, p=2
    assert PASSWORD not in encoded
    assert verify_password(PASSWORD, encoded)
    assert not verify_password("wrong password!", encoded)
    assert hash_password(PASSWORD) != encoded  # salted


def test_password_policy():
    assert password_problem("short", "a@b.co", 10)
    assert password_problem("aaaaaaaaaaaa", "a@b.co", 10)
    assert password_problem("marco.rossi-2026!", "marco.rossi@example.com", 10)
    assert password_problem("password123", "x@y.io", 10)
    assert password_problem(PASSWORD, "x@y.io", 10) is None


# ---------------------------------------------------------------------------
# Registration, login, sessions
# ---------------------------------------------------------------------------

def test_register_requires_consent_and_valid_input(app):
    c = _client(app)
    assert _register(c, "ana@example.com", consent=False).status_code == 400
    assert _register(c, "not-an-email").status_code == 400
    assert _register(c, "ana@example.com", password="short").status_code == 400


def test_register_login_logout_cycle(app):
    c = _client(app)
    res = _register(c, "Ana@Example.com")
    assert res.status_code == 201
    user = res.json()["user"]
    assert user["email"] == "ana@example.com"
    assert user["id"].startswith("usr_")
    assert user["privacy_consent_version"] == settings.privacy_notice_version
    assert "password" not in json.dumps(res.json()).lower() or "password_hash" not in res.text
    cookie = res.headers["set-cookie"]
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower()

    session = c.get("/api/auth/session").json()
    assert session["authenticated"] is True and session["user"]["id"] == user["id"]

    assert _register(_client(app), "ana@example.com").status_code == 409

    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/session").json()["authenticated"] is False
    assert c.get("/api/status").status_code == 401

    fresh = _client(app)
    bad = fresh.post("/api/auth/login", json={"email": "ana@example.com", "password": "nope nope nope"})
    assert bad.status_code == 401 and bad.json()["message"] == "Invalid email or password."
    unknown = fresh.post("/api/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert unknown.json()["message"] == "Invalid email or password."  # no account enumeration
    ok = fresh.post("/api/auth/login", json={"email": "ANA@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and fresh.get("/api/status").status_code == 200


def test_login_rate_limit(app):
    c = _client(app)
    _register(c, "bob@example.com")
    attacker = _client(app)
    for _ in range(3):
        attacker.post("/api/auth/login", json={"email": "bob@example.com", "password": "wrong password 1"})
    res = attacker.post("/api/auth/login", json={"email": "bob@example.com", "password": PASSWORD})
    assert res.status_code == 429


def test_protected_routes_and_mcp_require_auth(app):
    c = _client(app)
    for path in ("/api/status", "/api/routines", "/api/contacts", "/api/events?limit=1", "/api/account"):
        assert c.get(path).status_code == 401, path
    res = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert res.status_code == 401
    assert "bearer" in res.headers.get("www-authenticate", "").lower()
    assert c.get("/api/auth/config").json()["auth_enabled"] is True
    assert c.get("/api/health").json()["status"] == "ok"  # deploy health check stays public


def test_cross_site_post_is_rejected(app):
    c = _client(app)
    _register(c, "carla@example.com")
    evil = c.post("/api/routines", json={"title": "x"}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    own = c.post("/api/routines", json={"title": "Water the plants"}, headers={"Origin": "http://testserver"})
    assert own.status_code in (200, 201)


# ---------------------------------------------------------------------------
# Per-user data isolation
# ---------------------------------------------------------------------------

def test_each_user_sees_only_their_data(app):
    alice, bob = _client(app), _client(app)
    a_id = _register(alice, "alice@example.com").json()["user"]["id"]
    b_id = _register(bob, "bob2@example.com").json()["user"]["id"]

    assert alice.post("/api/routines", json={"title": "Unplug the iron", "domain": "safety"}).status_code in (200, 201)
    assert bob.post("/api/routines", json={"title": "Feed the cat"}).status_code in (200, 201)

    a_titles = [t["title"] for t in alice.get("/api/routines").json()["tasks"]]
    b_titles = [t["title"] for t in bob.get("/api/routines").json()["tasks"]]
    assert "Unplug the iron" in a_titles and "Feed the cat" not in a_titles
    assert "Feed the cat" in b_titles and "Unplug the iron" not in b_titles

    if not store_backend.DYNAMO:  # SQLite: one file per user
        assert Path(tenant_db_path(a_id)).exists() and Path(tenant_db_path(b_id)).exists()
    assert tenant_db_path(a_id) != tenant_db_path(b_id)
    assert alice.get("/api/status").json()["stats"]["planned_tasks_total"] == 1


def test_simulated_pipeline_writes_to_the_callers_store(app, monkeypatch):
    alice, bob = _client(app), _client(app)
    _register(alice, "al@example.com")
    _register(bob, "bo@example.com")
    monkeypatch.setattr(settings, "mock_ai", True)
    res = alice.post("/api/simulate", json={"transcript_chunk": "I just unplugged the clothes iron before leaving."})
    assert res.status_code == 200
    assert len(alice.get("/api/actions").json()["actions"]) >= 1
    assert bob.get("/api/actions").json()["actions"] == []


def test_sse_events_are_routed_per_tenant(multi_user):
    server_mod = multi_user
    qa, qb = asyncio.Queue(), asyncio.Queue()
    server_mod._subscribers("usr_" + "a" * 32).add(qa)
    server_mod._subscribers("usr_" + "b" * 32).add(qb)
    with tenant_scope("usr_" + "a" * 32):
        server_mod.broadcast_event("action_verified", {"x": 1})
    assert qa.qsize() == 1 and qb.qsize() == 0
    server_mod.broadcast_event("contact_updated", {}, tenant="usr_" + "b" * 32)
    assert qb.qsize() == 1


# ---------------------------------------------------------------------------
# MCP access tokens
# ---------------------------------------------------------------------------

def test_api_token_scopes_requests_to_its_owner(app):
    alice, bob = _client(app), _client(app)
    _register(alice, "tok-a@example.com")
    _register(bob, "tok-b@example.com")
    alice.post("/api/routines", json={"title": "Lock the door"})

    created = alice.post("/api/account/tokens", json={"name": "Alexa+"}).json()["token"]
    secret = created["token"]
    assert secret.startswith("exm_")
    listed = alice.get("/api/account/tokens").json()["tokens"]
    assert listed[0]["prefix"] == secret[:10] and "token" not in listed[0]

    machine = TestClient(app)
    res = machine.get("/api/routines", headers={"Authorization": f"Bearer {secret}"})
    assert [t["title"] for t in res.json()["tasks"]] == ["Lock the door"]

    assert alice.delete(f"/api/account/tokens/{created['id']}").status_code == 200
    assert machine.get("/api/routines", headers={"Authorization": f"Bearer {secret}"}).status_code == 401


def test_mcp_tool_wrapper_runs_in_callers_tenant(multi_user):
    from src.serving.tenant_tools import tenant_tool

    seen = []
    wrapped = tenant_tool(lambda name="x": seen.append(get_tenant_id()) or name)

    class _Req:
        scope = {"state": {"examen_user_id": "usr_" + "c" * 32}}

    class _Ctx:
        class request_context:
            request = _Req()

    assert wrapped("hello", ctx=_Ctx()) == "hello"
    assert seen == ["usr_" + "c" * 32]
    with pytest.raises(PermissionError):
        wrapped("hello", ctx=None)


# ---------------------------------------------------------------------------
# GDPR: export, password change, erasure
# ---------------------------------------------------------------------------

def test_export_contains_the_users_records(app):
    c = _client(app)
    _register(c, "exp@example.com")
    c.post("/api/routines", json={"title": "Evening medication"})
    res = c.get("/api/account/export")
    assert res.status_code == 200
    assert "attachment" in res.headers["content-disposition"]
    body = res.json()
    assert body["account"]["email"] == "exp@example.com"
    titles = [r["title"] for r in body["data"]["planned_tasks"]]
    assert "Evening medication" in titles


def test_password_change_signs_out_other_sessions(app):
    one, two = _client(app), _client(app)
    _register(one, "pw@example.com")
    two.post("/api/auth/login", json={"email": "pw@example.com", "password": PASSWORD})
    assert two.get("/api/account").status_code == 200
    bad = one.post("/api/account/password", json={"current_password": "nope", "new_password": "another long secret"})
    assert bad.status_code == 403
    ok = one.post("/api/account/password", json={"current_password": PASSWORD, "new_password": "another long secret"})
    assert ok.status_code == 200 and ok.json()["other_sessions_signed_out"] == 1
    assert two.get("/api/account").status_code == 401
    assert one.get("/api/account").status_code == 200


def test_account_deletion_erases_everything(app):
    c = _client(app)
    uid = _register(c, "gone@example.com").json()["user"]["id"]
    c.post("/api/routines", json={"title": "Something private"})
    folder = tenant_dir(uid)
    assert folder.exists()

    assert c.request("DELETE", "/api/account", json={"password": "wrong password!"}).status_code == 403
    res = c.request("DELETE", "/api/account", json={"password": PASSWORD})
    assert res.status_code == 200 and res.json()["deleted"] is True
    assert not folder.exists()
    assert c.get("/api/auth/session").json()["authenticated"] is False
    again = _client(app).post("/api/auth/login", json={"email": "gone@example.com", "password": PASSWORD})
    assert again.status_code == 401


# ---------------------------------------------------------------------------
# Bee login isolation & pairing
# ---------------------------------------------------------------------------

def test_bee_env_is_private_per_user(monkeypatch, tmp_path):
    a, b = "usr_" + "1" * 32, "usr_" + "2" * 32
    env_a, env_b = bee_subprocess_env(a), bee_subprocess_env(b)
    assert env_a["BEE_FORCE_FILE_STORE"] == "1"  # never the shared OS keychain
    assert env_a["BEE_CONFIG_DIR"] != env_b["BEE_CONFIG_DIR"]
    assert oct(os.stat(env_a["BEE_CONFIG_DIR"]).st_mode & 0o777) == "0o700"
    assert bee_subprocess_env() is None  # single-user mode inherits the host login

    from src.ingestion.stream_convo import BeeClient

    with tenant_scope(a):
        assert BeeClient().env["BEE_CONFIG_DIR"] == env_a["BEE_CONFIG_DIR"]


FAKE_BEE = textwrap.dedent(
    """
    import os, sys, time
    args = sys.argv[1:]
    cfg = os.environ.get("BEE_CONFIG_DIR", "")
    if args[:1] == ["login"]:
        mode = open(os.path.join(cfg, "mode")).read().strip() if os.path.exists(os.path.join(cfg, "mode")) else "ok"
        print("Welcome to Bee AI!", flush=True)
        print("Authentication link: https://bee.computer/connect#req123", flush=True)
        time.sleep(0.3)
        if mode == "expire":
            print("Error: Pairing request expired. Please try again.", flush=True)
            sys.exit(1)
        open(os.path.join(cfg, "token-production"), "w").write("secret-token")
        print("Great news! I'm now connected to the Bee account of Test Wearer.", flush=True)
        sys.exit(0)
    if args[:1] == ["logout"]:
        p = os.path.join(cfg, "token-production")
        if os.path.exists(p):
            os.remove(p)
        print("Logged out.")
        sys.exit(0)
    sys.exit(3)
    """
)


@pytest.fixture
def fake_bee(tmp_path):
    script = tmp_path / "fake_bee.py"
    script.write_text(FAKE_BEE)
    return lambda args: [sys.executable, str(script), *args]


def test_pairing_completes_into_the_users_folder(fake_bee):
    from src.ingestion.bee_pairing import BeePairing, bee_logout

    uid = "usr_" + "d" * 32
    other = "usr_" + "e" * 32
    connected = []

    async def scenario():
        pairing = BeePairing(user_id=uid, on_connected=lambda snap: connected.append(snap), build_cmd=fake_bee)
        snap = await pairing.start()
        assert snap["status"] == "pending"
        assert snap["pairing_url"] == "https://bee.computer/connect#req123"
        for _ in range(50):
            if pairing.status == "connected":
                break
            await asyncio.sleep(0.05)
        return pairing

    pairing = asyncio.run(scenario())
    assert pairing.status == "connected" and pairing.account == "Test Wearer"
    assert connected and tenant_has_bee_login(uid)
    assert not tenant_has_bee_login(other)  # the token landed only in this user's folder

    assert asyncio.run(bee_logout(uid, build_cmd=fake_bee)) is True
    assert not tenant_has_bee_login(uid)


def test_pairing_expiry_is_reported(fake_bee):
    from src.core.tenancy import tenant_bee_dir
    from src.ingestion.bee_pairing import BeePairing

    uid = "usr_" + "f" * 32
    (tenant_bee_dir(uid) / "mode").write_text("expire")

    async def scenario():
        pairing = BeePairing(user_id=uid, build_cmd=fake_bee)
        await pairing.start()
        for _ in range(50):
            if pairing.status not in ("pending", "starting"):
                break
            await asyncio.sleep(0.05)
        return pairing

    pairing = asyncio.run(scenario())
    assert pairing.status == "expired"
    assert not tenant_has_bee_login(uid)


def test_orchestrator_is_per_user_and_waits_for_pairing(multi_user):
    from src.core.tenancy import tenant_bee_dir

    Mgr = multi_user.OrchestratorManager
    a, b = "usr_" + "3" * 32, "usr_" + "4" * 32
    with tenant_scope(a):
        mgr_a = Mgr.get_instance()
        assert mgr_a.get_status()["status"] == "DISCONNECTED"
        assert mgr_a.can_start() is False
    with tenant_scope(b):
        mgr_b = Mgr.get_instance()
    assert mgr_a is not mgr_b
    (tenant_bee_dir(a) / "token-production").write_text("t")
    assert mgr_a.can_start() is True and mgr_b.can_start() is False
    Mgr.drop_tenant(a)
    Mgr.drop_tenant(b)


def test_dashboard_logout_keeps_the_bee_connected(app, monkeypatch):
    calls = []

    async def _no_logout(*a, **k):
        calls.append(a)
        return True

    monkeypatch.setattr("src.serving.auth_routes.bee_logout", _no_logout)
    c = _client(app)
    _register(c, "keep@example.com")
    assert c.post("/api/auth/logout").status_code == 200
    assert calls == []


def test_mcp_endpoint_end_to_end_is_tenant_scoped(app):
    """A real MCP tools/call over streamable HTTP reaches only the token owner's data."""
    with TestClient(app, base_url="http://localhost") as c:
        _register(c, "mcp-a@example.com")
        secret = c.post("/api/account/tokens", json={"name": "Alexa+"}).json()["token"]["token"]
        c.post("/api/auth/logout")
        other = TestClient(app)
        _register(other, "mcp-b@example.com")

        headers = {"Authorization": f"Bearer {secret}", "Accept": "application/json, text/event-stream"}
        init = c.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "pytest", "version": "1"}},
        })
        assert init.status_code == 200, init.text
        sid = init.headers.get("mcp-session-id")
        if sid:
            headers["mcp-session-id"] = sid
        c.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        call = c.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "create_planned_task", "arguments": {"title": "Take vitamins"}},
        })
        assert call.status_code == 200, call.text
        assert "Take vitamins" in call.text and "isError\": true" not in call.text

        owner = TestClient(app)
        owner.post("/api/auth/login", json={"email": "mcp-a@example.com", "password": PASSWORD})
        assert "Take vitamins" in [t["title"] for t in owner.get("/api/routines").json()["tasks"]]
        assert other.get("/api/routines").json()["tasks"] == []

        # Regression (comparison doc §5.1): another user's token on this MCP session sees only its data
        other.post("/api/routines", json={"title": "Water the plants"})
        other_secret = other.post("/api/account/tokens", json={"name": "b"}).json()["token"]["token"]
        own = c.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "get_upcoming_tasks", "arguments": {}},
        })
        assert "Take vitamins" in own.text  # the owner of the session does see it
        reused = c.post("/mcp", headers={**headers, "Authorization": f"Bearer {other_secret}"}, json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "get_upcoming_tasks", "arguments": {}},
        })
        assert reused.status_code == 200, reused.text
        assert "Take vitamins" not in reused.text


# ---------------------------------------------------------------------------
# Fail-closed tenancy, pipeline payload, token scope, shared limits (ported from `sessions`)
# ---------------------------------------------------------------------------

def test_user_data_without_a_tenant_fails_closed(multi_user):
    from src.core.storage import get_storage_store
    from src.core.tenancy import MissingTenant
    from src.ingestion.backfill import get_backfill_service
    from src.ingestion.bee_identity import get_wearer_identity
    from src.ingestion.event_engine import get_event_engine

    for accessor in (get_storage_store, get_event_engine, get_backfill_service, get_wearer_identity,
                     multi_user.OrchestratorManager.get_instance, bee_subprocess_env):
        with pytest.raises(MissingTenant):
            accessor()
    with tenant_scope("usr_" + "5" * 32):
        assert get_storage_store() is not None  # inside a tenant everything resolves


def test_legacy_mode_keeps_the_single_user_store(monkeypatch):
    from src.core.storage import get_storage_store

    monkeypatch.setattr(settings, "auth_enabled", False)
    assert get_tenant_id() is None and get_storage_store() is not None
    assert bee_subprocess_env() is None


def test_pipeline_payload_carries_and_checks_the_user(multi_user):
    from src.pipeline.app import agent_invocation

    a, b = "usr_" + "6" * 32, "usr_" + "7" * 32
    base = {"raw_transcript": "I locked the front door.", "categories": ["action"]}
    assert agent_invocation(dict(base))["error"] == "missing user_id"
    assert agent_invocation({**base, "user_id": "../etc"})["error"] == "invalid user_id"
    with tenant_scope(a):
        assert "does not match" in agent_invocation({**base, "user_id": b})["error"]


def test_dispatch_payloads_name_the_tenant(multi_user, monkeypatch, tmp_path):
    import importlib

    from src.core.schemas import ChunkClassification
    from src.ingestion.orchestrator import BeeStreamOrchestrator

    seen = []
    importlib.import_module("src.pipeline.app")
    monkeypatch.setattr(sys.modules["src.pipeline.app"], "agent_invocation",
                        lambda payload: seen.append(payload) or {"ok": True})

    async def _classify(transcript, active_tasks=None, prior_context=None):
        return ChunkClassification(categories=["action"], confidence=0.9, summary_hint="door")

    monkeypatch.setattr("src.ingestion.orchestrator.aclassify_chunk", _classify)
    uid = "usr_" + "8" * 32

    async def main():
        with tenant_scope(uid):
            orch = BeeStreamOrchestrator(store=new_store(str(tmp_path / "o.db")), engine=None)
            orch.engine_enabled = False
            orch.speaker_tag_wait = 0
            await orch.process_incoming_utterance(
                {"id": "u1", "text": "I locked the front door.", "received_at": "2026-10-20T10:00:00"})

    asyncio.run(main())
    assert seen and seen[0]["user_id"] == uid


def test_access_tokens_cannot_manage_the_account(app):
    alice = _client(app)
    _register(alice, "scope@example.com")
    secret = alice.post("/api/account/tokens", json={"name": "Alexa+"}).json()["token"]["token"]
    machine = TestClient(app, headers={"Authorization": f"Bearer {secret}"})
    assert machine.get("/api/routines").status_code == 200  # data access is the token's job
    for method, path in (("GET", "/api/account/export"), ("POST", "/api/account/tokens"),
                         ("DELETE", "/api/account"), ("PATCH", "/api/account"), ("POST", "/api/bee/pair"),
                         ("POST", "/api/bee/disconnect")):
        res = machine.request(method, path, json={})
        assert res.status_code == 403 and res.json()["error"] == "session_required", path


def test_llm_calls_share_one_limit_across_users(monkeypatch):
    from src.core.limits import llm_slot

    monkeypatch.setattr(settings, "max_concurrent_llm_calls", 2)
    peak, running = [0], [0]

    async def call(uid):
        with tenant_scope(uid):
            async with llm_slot():
                running[0] += 1
                peak[0] = max(peak[0], running[0])
                await asyncio.sleep(0.01)
                running[0] -= 1

    async def main():
        await asyncio.gather(*(call("usr_" + str(i % 2) * 32) for i in range(8)))

    asyncio.run(main())
    assert peak[0] == 2


def test_live_streams_are_capped(multi_user, monkeypatch):
    from src.core.tenancy import tenant_bee_dir

    Mgr = multi_user.OrchestratorManager
    monkeypatch.setattr(settings, "max_active_users", 1)
    a, b = "usr_" + "a1" * 16, "usr_" + "b2" * 16
    for uid in (a, b):
        (tenant_bee_dir(uid) / "token-production").write_text("t")

    async def main():
        gate = asyncio.Event()

        async def _fake_run(self):
            await gate.wait()

        monkeypatch.setattr(Mgr, "_run_orchestrator", _fake_run)
        with tenant_scope(a):
            Mgr.get_instance().ensure_started()
        with tenant_scope(b):
            mgr_b = Mgr.get_instance()
            mgr_b.ensure_started()
            assert mgr_b.capacity_blocked and mgr_b.get_status()["status"] == "CAPACITY"
        Mgr.drop_tenant(a)
        await asyncio.sleep(0)
        with tenant_scope(b):
            mgr_b.ensure_started()
            assert mgr_b.running and not mgr_b.capacity_blocked
        Mgr.drop_tenant(b)
        gate.set()

    asyncio.run(main())


# ---------------------------------------------------------------------------
# Admin, account status, registration control, sessions, audit (ported from `sessions`)
# ---------------------------------------------------------------------------

def _admin_client(app, email="root@example.com"):
    from src.core.auth import get_auth_store

    c = _client(app)
    uid = _register(c, email).json()["user"]["id"]
    get_auth_store().set_admin(uid, True)
    return c, uid


def test_admin_manages_accounts_but_not_their_data(app):
    admin, admin_id = _admin_client(app)
    user = _client(app)
    _register(user, "plain@example.com")
    user.post("/api/routines", json={"title": "Private routine"})
    assert user.get("/api/admin/users").status_code == 403

    listed = {u["email"]: u for u in admin.get("/api/admin/users").json()["users"]}
    assert set(listed) == {"root@example.com", "plain@example.com"}
    assert listed["plain@example.com"]["bee_link_state"] == "unlinked" and not listed["plain@example.com"]["streaming"]
    assert "Private routine" not in admin.get("/api/admin/users").text
    assert "Private routine" not in str(admin.get("/api/routines").json())  # admin sees only their own data

    created = admin.post("/api/admin/users", json={"email": "carol@example.com", "is_admin": False})
    assert created.status_code == 201
    one_time = created.json()["initial_password"]
    carol = TestClient(app)
    assert carol.post("/api/auth/login", json={"email": "carol@example.com", "password": one_time}).status_code == 200


def test_disabled_accounts_are_signed_out_everywhere(app):
    admin, admin_id = _admin_client(app)
    user = _client(app)
    uid = _register(user, "dis@example.com").json()["user"]["id"]
    secret = user.post("/api/account/tokens", json={"name": "Alexa+"}).json()["token"]["token"]
    assert admin.post(f"/api/admin/users/{admin_id}/status", json={"status": "disabled"}).status_code == 403
    assert admin.post(f"/api/admin/users/{uid}/status", json={"status": "disabled"}).status_code == 200
    assert user.get("/api/routines").status_code == 401
    assert TestClient(app).get("/api/routines", headers={"Authorization": f"Bearer {secret}"}).status_code == 401
    assert _client(app).post("/api/auth/login", json={"email": "dis@example.com", "password": PASSWORD}).status_code == 401
    assert admin.post(f"/api/admin/users/{uid}/status", json={"status": "active"}).status_code == 200
    assert _client(app).post("/api/auth/login", json={"email": "dis@example.com", "password": PASSWORD}).status_code == 200


def test_admin_password_reset_issues_a_one_time_password(app):
    admin, _ = _admin_client(app)
    user = _client(app)
    uid = _register(user, "forgot@example.com").json()["user"]["id"]
    res = admin.post(f"/api/admin/users/{uid}/reset-password")
    assert res.status_code == 200
    assert user.get("/api/routines").status_code == 401  # old sessions end
    login = _client(app).post("/api/auth/login", json={"email": "forgot@example.com",
                                                        "password": res.json()["initial_password"]})
    assert login.status_code == 200


def test_bootstrap_admin_is_created_once_and_never_promotes(multi_user):
    from src.core.auth import get_auth_store

    store = get_auth_store()
    taken = store.create_user("owner@example.com", PASSWORD)
    assert store.ensure_bootstrap_admin("owner@example.com") is None  # registered first: not promoted
    assert store.get_user(taken.id).is_admin is False
    generated = store.ensure_bootstrap_admin("admin@example.com")
    assert generated and store.get_user_by_email("admin@example.com").is_admin
    assert store.ensure_bootstrap_admin("second@example.com") is None  # an admin exists
    assert store.count_admins() == 1


def test_registration_can_be_closed(app, monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_signup", False)
    c = _client(app)
    assert c.get("/api/auth/config").json()["signup_enabled"] is False
    res = _register(c, "closed@example.com")
    assert res.status_code == 403 and res.json()["error"] == "signup_disabled"


def test_successful_registrations_are_limited_per_address(app, monkeypatch):
    monkeypatch.setattr(settings, "auth_signup_max_per_ip", 3)
    for i in range(3):
        assert _register(_client(app), f"bulk{i}@example.com").status_code == 201
    res = _register(_client(app), "bulk3@example.com")
    assert res.status_code == 429


def test_sign_out_everywhere_revokes_sessions_and_tokens(app):
    first, second = _client(app), _client(app)
    _register(first, "every@example.com")
    second.post("/api/auth/login", json={"email": "every@example.com", "password": PASSWORD})
    secret = first.post("/api/account/tokens", json={"name": "Alexa+"}).json()["token"]["token"]
    machine = TestClient(app, headers={"Authorization": f"Bearer {secret}"})
    assert machine.post("/api/auth/sessions/revoke-all").status_code == 403  # a token cannot do it
    assert first.post("/api/auth/sessions/revoke-all").status_code == 200
    for client in (first, second, machine):
        assert client.get("/api/routines").status_code == 401


def test_sessions_slide_when_used(multi_user, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from src.core.auth import get_auth_store
    from src.core.auth.store import digest, iso

    store = get_auth_store()
    user = store.create_user("slide@example.com", PASSWORD)
    token = store.create_session(user.id)
    soon = iso(datetime.now(timezone.utc) + timedelta(hours=1))
    if store_backend.DYNAMO:
        key = {"pk": f"SESSION#{digest(token)}", "sk": "SESSION"}
        store.table.update(key, set_={"expires_at": soon})
        assert store.user_for_session(token) is not None
        renewed = store.table.get(key)["expires_at"]
    else:
        with store._conn() as conn:
            conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (soon, digest(token)))
        assert store.user_for_session(token) is not None
        with store._conn() as conn:
            renewed = conn.execute("SELECT expires_at FROM sessions WHERE token_hash = ?",
                                   (digest(token),)).fetchone()[0]
    assert renewed > soon


def test_audit_log_holds_no_personal_data_and_is_erased(app):
    from src.core.auth import get_auth_store

    admin, admin_id = _admin_client(app)
    user = _client(app)
    uid = _register(user, "audited@example.com").json()["user"]["id"]
    _client(app).post("/api/auth/login", json={"email": "audited@example.com", "password": "wrong password 1"})
    admin.post(f"/api/admin/users/{uid}/status", json={"status": "disabled"})
    store = get_auth_store()
    events = [e["event"] for e in store.list_audit(user_id=uid)]
    assert "login_failed" in events and "admin_user_disabled" in events
    dump = json.dumps(store.list_audit(limit=1000))
    assert "audited@example.com" not in dump and "testclient" not in dump
    store.delete_user(uid)
    assert store.list_audit(user_id=uid) == []


def test_password_hashes_use_64_mib_scrypt_and_upgrade(multi_user, monkeypatch):
    from src.core.auth import get_auth_store

    monkeypatch.setattr(passwords, "_LOG2_N", 10)
    monkeypatch.setattr(passwords, "_P", 1)
    store = get_auth_store()
    user = store.create_user("hash@example.com", PASSWORD)
    monkeypatch.setattr(passwords, "_P", 2)  # parameters changed since the hash was made
    assert store.authenticate("hash@example.com", PASSWORD) is not None
    if store_backend.DYNAMO:
        upgraded = store._user_item(user.id)["password_hash"]
    else:
        with store._conn() as conn:
            upgraded = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()[0]
    assert upgraded.startswith("scrypt$10$8$2$")


# ---------------------------------------------------------------------------
# One Bee account per EXAMEN user (ported from `sessions`)
# ---------------------------------------------------------------------------

def test_a_bee_account_links_to_one_user_only(multi_user, monkeypatch):
    from src.core.auth import get_auth_store
    from src.core.tenancy import tenant_bee_dir
    from src.ingestion.stream_convo import BeeClient
    from src.serving import auth_routes

    store = get_auth_store()
    alice = store.create_user("bee-a@example.com", PASSWORD)
    bob = store.create_user("bee-b@example.com", PASSWORD)
    logged_out = []

    async def _me(self, args, timeout=None):
        return {"id": 4242, "first_name": "Ada"}  # both logged into the same Bee account

    async def _logout(user_id=None, build_cmd=None):
        logged_out.append(user_id)
        return True

    monkeypatch.setattr(BeeClient, "run_json", _me)
    monkeypatch.setattr(auth_routes, "bee_logout", _logout)
    for uid in (alice.id, bob.id):
        (tenant_bee_dir(uid) / "token-production").write_text("t")

    first = asyncio.run(auth_routes.link_bee_account(alice.id))
    assert first.state == "linked" and first.bee_user_id == 4242 and first.bee_first_name == "Ada"
    second = asyncio.run(auth_routes.link_bee_account(bob.id))
    assert second.state == "conflict" and second.bee_user_id is None
    assert logged_out == [bob.id]  # only the second user's folder is logged out
    assert store.get_bee_link(alice.id).state == "linked"
    store.delete_user(alice.id)  # erasure frees the Bee account
    assert store.find_bee_link(4242) is None
