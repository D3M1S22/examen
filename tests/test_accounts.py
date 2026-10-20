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
    assert encoded.startswith("scrypt$10$8$1$")
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
