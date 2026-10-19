"""Multi-user support (docs/next_steps/multi_user/05 §2): authentication, isolation, Bee links, erasure.

Offline: temporary data directory (conftest), no real Bee CLI, no Bedrock.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from starlette.testclient import TestClient

from src.core.identity import MissingUserContext, UserContext, acting_as, current_user_ctx
from src.core.schemas import PlannedTask, SocialEntity
from src.core.storage import get_storage_store, get_store_registry, get_system_store
from src.ingestion.backfill import get_backfill_service
from src.ingestion.bee_identity import get_wearer_identity
from src.serving import bee_accounts
from src.serving.mcp_server import broadcast_event, create_app
from src.serving.user_runtime import get_event_hub, get_runtime_manager
from tests.conftest import CSRF_HEADERS, TEST_PASSWORD, create_test_user, login_client

USER_A = "usr_00000000000000aa"
USER_B = "usr_00000000000000bb"


@pytest.fixture
def app():
    return create_app()


def client_for(app, user_id, username, is_admin=False):
    return login_client(TestClient(app), user_id=user_id, username=username, is_admin=is_admin)


# ---------------------------------------------------------------------------
# T-MU-11: authentication
# ---------------------------------------------------------------------------

def test_protected_routes_require_a_session(app):
    anon = TestClient(app)
    assert anon.get("/api/status").status_code == 401
    assert anon.get("/api/actions").status_code == 401
    assert anon.post("/mcp", json={}).status_code == 401
    assert anon.get("/api/health").json()["status"] == "ok"
    assert anon.get("/api/auth/session").json()["authenticated"] is False


def test_login_session_logout_cycle(app):
    create_test_user(USER_A, "alice")
    c = TestClient(app)
    c.headers.update(CSRF_HEADERS)
    assert c.post("/api/auth/login", json={"username": "alice", "password": "wrong password!!"}).status_code == 401
    res = c.post("/api/auth/login", json={"username": "alice", "password": TEST_PASSWORD})
    assert res.status_code == 200 and "examen_session" in res.cookies
    assert "httponly" in res.headers["set-cookie"].lower()
    session = c.get("/api/auth/session").json()
    assert session["authenticated"] and session["user"]["user_id"] == USER_A
    assert "password_hash" not in session["user"]
    assert c.get("/api/status").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/status").status_code == 401


def test_login_rate_limit(app):
    create_test_user(USER_A, "alice")
    c = TestClient(app)
    for _ in range(5):
        c.post("/api/auth/login", json={"username": "alice", "password": "wrong password!!"})
    res = c.post("/api/auth/login", json={"username": "alice", "password": TEST_PASSWORD})
    assert res.status_code == 429


def test_cookie_requests_need_the_csrf_header(app):
    c = client_for(app, USER_A, "alice")
    del c.headers["x-requested-with"]
    assert c.post("/api/routines", json={"title": "Water the plants"}).status_code == 403
    c.headers.update(CSRF_HEADERS)
    assert c.post("/api/routines", json={"title": "Water the plants"}).status_code == 201


def test_personal_access_tokens(app):
    c = client_for(app, USER_A, "alice")
    created = c.post("/api/account/tokens", json={"name": "Claude Desktop"}).json()
    token = created["token"]
    assert token.startswith("exm_pat_")
    bearer = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    assert bearer.get("/api/actions").status_code == 200
    assert bearer.post("/api/account/tokens", json={"name": "x"}).status_code == 403  # tokens cannot mint tokens
    listed = c.get("/api/account/tokens").json()["tokens"]
    assert [t["name"] for t in listed] == ["Claude Desktop"] and "token_hash" not in listed[0]
    assert c.delete(f"/api/account/tokens/{created['info']['token_id']}").status_code == 200
    assert bearer.get("/api/actions").status_code == 401


def test_admin_manages_accounts_only(app):
    admin = client_for(app, USER_A, "alice", is_admin=True)
    user = client_for(app, USER_B, "bob")
    assert user.get("/api/admin/users").status_code == 403
    res = admin.post("/api/admin/users", json={"username": "carol"})
    assert res.status_code == 201
    carol_password = res.json()["initial_password"]
    carol_id = res.json()["user"]["user_id"]
    assert TestClient(app).post("/api/auth/login", json={"username": "carol", "password": carol_password}).status_code == 200
    names = [u["username"] for u in admin.get("/api/admin/users").json()["users"]]
    assert names == ["alice", "bob", "carol"]
    assert admin.post(f"/api/admin/users/{carol_id}/status", json={"status": "disabled"}).status_code == 200
    assert TestClient(app).post("/api/auth/login", json={"username": "carol", "password": carol_password}).status_code == 401


def test_bootstrap_admin(monkeypatch):
    from src.core.config import settings
    from src.serving.auth import get_auth_provider

    monkeypatch.setattr(settings, "examen_bootstrap_admin", "owner")
    password = get_auth_provider().ensure_bootstrap_admin()
    assert password and get_system_store().get_user_by_username("owner").is_admin
    assert get_auth_provider().ensure_bootstrap_admin() is None  # only on an empty user table


# ---------------------------------------------------------------------------
# T-MU-1..4: data isolation
# ---------------------------------------------------------------------------

def test_users_never_see_each_others_data(app):
    a = client_for(app, USER_A, "alice")
    b = client_for(app, USER_B, "bob")
    task_id = a.post("/api/routines", json={"title": "Take the medicine"}).json()["task_id"]
    assert [t["title"] for t in a.get("/api/routines").json()["tasks"]] == ["Take the medicine"]
    assert b.get("/api/routines").json()["tasks"] == []
    assert b.put(f"/api/routines/{task_id}", json={"title": "hijack"}).status_code == 404
    assert b.delete(f"/api/routines/{task_id}").status_code == 404
    assert a.get("/api/routines").json()["tasks"][0]["title"] == "Take the medicine"


def test_same_contact_name_stays_independent():
    get_storage_store(user_id=USER_A).save_social_contact(SocialEntity(person_name="Marco", company_or_role="Acme"))
    get_storage_store(user_id=USER_B).save_social_contact(SocialEntity(person_name="Marco", company_or_role="Globex"))
    a = get_storage_store(user_id=USER_A).search_social_contact("Marco")
    b = get_storage_store(user_id=USER_B).search_social_contact("Marco")
    assert [c.company_or_role for c in a] == ["Acme"] and [c.company_or_role for c in b] == ["Globex"]


def test_web_search_cache_is_per_user():
    get_storage_store(user_id=USER_A).put_cached_search("raft consensus", "ddg", [{"url": "https://raft.github.io"}])
    assert get_storage_store(user_id=USER_A).get_cached_search("raft consensus", 3600) is not None
    assert get_storage_store(user_id=USER_B).get_cached_search("raft consensus", 3600) is None


def test_store_access_without_a_user_fails_closed():
    token = current_user_ctx.set(None)
    try:
        with pytest.raises(MissingUserContext):
            get_storage_store()
    finally:
        current_user_ctx.reset(token)
    with pytest.raises(ValueError):
        get_store_registry().for_user("../../etc")


def test_pipeline_runs_only_as_the_payload_user():
    from src.pipeline.app import agent_invocation

    token = current_user_ctx.set(None)
    try:
        assert agent_invocation({"raw_transcript": "hi", "categories": ["noop"]})["error"] == "invalid_user"
    finally:
        current_user_ctx.reset(token)
    with acting_as(UserContext(user_id=USER_A)):
        foreign = agent_invocation({"raw_transcript": "hi", "categories": ["noop"], "user_id": USER_B})
    assert foreign["error"] == "invalid_user"


# ---------------------------------------------------------------------------
# T-MU-5..8, 13: per-user runtime, SSE, Bee links, erasure
# ---------------------------------------------------------------------------

def test_runtime_components_are_per_user():
    assert get_backfill_service(USER_A) is not get_backfill_service(USER_B)
    assert get_backfill_service(USER_A).store is get_storage_store(user_id=USER_A)
    a, b = get_runtime_manager().runtime(USER_A), get_runtime_manager().runtime(USER_B)
    assert a.engine is not b.engine and a.store is not b.store
    assert a.bee_config_dir != b.bee_config_dir and a.bee_config_dir.endswith(f"{USER_A}/bee")
    assert a.new_bee_client().subprocess_env()["BEE_CONFIG_DIR"] == a.bee_config_dir
    assert a.new_bee_client().subprocess_env()["BEE_FORCE_FILE_STORE"] == "1"


def test_coverage_is_per_user():
    from src.core.schemas import CoverageInterval

    now = datetime.now()
    get_storage_store(user_id=USER_A).save_coverage_interval(
        CoverageInterval(source="live", start=(now - timedelta(hours=1)).isoformat(), end=now.isoformat()))
    assert len(get_storage_store(user_id=USER_A).list_coverage()) == 1
    assert get_storage_store(user_id=USER_B).list_coverage() == []


def test_sse_events_reach_only_their_user():
    hub = get_event_hub()
    qa, qb = hub.subscribe(USER_A), hub.subscribe(USER_B)
    with acting_as(UserContext(user_id=USER_A)):
        broadcast_event("routine_created", {"title": "secret"})
    assert qa.qsize() == 1 and qb.qsize() == 0
    token = current_user_ctx.set(None)
    try:
        broadcast_event("routine_created", {"title": "nobody"})  # no user: dropped, never broadcast to all
    finally:
        current_user_ctx.reset(token)
    assert qa.qsize() == 1 and qb.qsize() == 0


def test_wearer_identity_is_per_user():
    system = get_system_store()
    for uid, name, first in ((USER_A, "alice", "Ada"), (USER_B, "bob", "Bob")):
        create_test_user(uid, name)
        link = system.get_bee_link(uid)
        link.state, link.bee_first_name = "linked", first
        system.save_bee_link(link)
    assert get_wearer_identity(USER_A).role_for("Ada") == "user"
    assert get_wearer_identity(USER_A).role_for("Bob") == "contact"
    assert get_wearer_identity(USER_B).role_for("Bob") == "user"


@pytest.fixture
def fake_bee(monkeypatch):
    """Bee accounts by user: pairing links and `bee me` answers without the real CLI."""
    accounts = {}
    started = []

    async def fake_verified(client):
        uid = client.config_dir.split("/")[-2]
        return accounts.get(uid)

    async def fake_login(self):
        return "https://bee.computer/connect#test"

    async def fake_logout(self):
        return True

    monkeypatch.setattr(bee_accounts, "_verified", fake_verified)
    monkeypatch.setattr(bee_accounts.BeeClient, "login_no_wait", fake_login)
    monkeypatch.setattr(bee_accounts.BeeClient, "logout", fake_logout)
    monkeypatch.setattr(get_runtime_manager(), "start_stream", lambda uid: started.append(uid))
    return accounts, started


def test_bee_pairing_flow_and_account_uniqueness(app, fake_bee):
    accounts, started = fake_bee
    a = client_for(app, USER_A, "alice")
    b = client_for(app, USER_B, "bob")
    res = a.post("/api/bee/link").json()
    assert res["bee_link"]["state"] == "pairing" and res["bee_link"]["pairing_url"].startswith("https://bee.computer/")
    accounts[USER_A] = (42, "Ada", "Europe/Rome")  # approved in the Bee app
    linked = a.get("/api/bee/link").json()
    assert linked["bee_link"]["state"] == "linked" and linked["bee_link"]["bee_first_name"] == "Ada"
    assert started == [USER_A]
    assert get_system_store().get_user(USER_A).timezone == "Europe/Rome"

    b.post("/api/bee/link")
    accounts[USER_B] = (42, "Ada", "Europe/Rome")  # B approves with A's Bee account
    conflict = b.get("/api/bee/link")
    assert conflict.status_code == 409 and conflict.json()["error"] == "bee_account_taken"
    assert get_system_store().get_bee_link(USER_A).state == "linked"


def test_logout_keeps_bee_linked_and_unlink_is_scoped(app, fake_bee):
    accounts, _ = fake_bee
    a = client_for(app, USER_A, "alice")
    b = client_for(app, USER_B, "bob")
    for client, uid, bee_id, name in ((a, USER_A, 1, "Ada"), (b, USER_B, 2, "Bob")):
        client.post("/api/bee/link")
        accounts[uid] = (bee_id, name, None)
        client.get("/api/bee/link")
    a.post("/api/auth/logout")
    assert get_system_store().get_bee_link(USER_A).state == "linked"  # D8: logout is session-only
    assert b.post("/api/bee/unlink").status_code == 200
    assert get_system_store().get_bee_link(USER_B).state == "unlinked"
    assert get_system_store().get_bee_link(USER_A).state == "linked"


def test_account_erasure_is_scoped(app, fake_bee):
    a = client_for(app, USER_A, "alice")
    b = client_for(app, USER_B, "bob")
    a.post("/api/routines", json={"title": "A's routine"})
    b.post("/api/routines", json={"title": "B's routine"})
    a_dir = get_store_registry().user_dir(USER_A)
    assert a_dir.exists()
    assert a.post("/api/account/erase", json={"password": "wrong"}).status_code == 401
    assert a.post("/api/account/erase", json={"password": TEST_PASSWORD}).json()["erased"] is True
    assert not a_dir.exists() and get_system_store().get_user(USER_A) is None
    assert a.get("/api/status").status_code == 401
    assert [t["title"] for t in b.get("/api/routines").json()["tasks"]] == ["B's routine"]


# ---------------------------------------------------------------------------
# T-MU-9: MCP tools run as the token's user
# ---------------------------------------------------------------------------

def _mcp_call(client, tool, arguments=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    init = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
    assert init.status_code == 200, init.text
    sid = init.headers.get("mcp-session-id")
    if sid:
        headers["mcp-session-id"] = sid
    client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    res = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": arguments or {}}})
    body = res.text
    return body[body.index("{"):] if not body.startswith("{") else body


def test_mcp_tools_use_the_token_owner(app):
    a = client_for(app, USER_A, "alice")
    b = client_for(app, USER_B, "bob")
    soon = (datetime.now() + timedelta(hours=2)).isoformat()
    get_storage_store(user_id=USER_A).save_planned_task(PlannedTask(title="Call the dentist", scheduled_time=soon))
    token_a = a.post("/api/account/tokens", json={"name": "mcp"}).json()["token"]
    token_b = b.post("/api/account/tokens", json={"name": "mcp"}).json()["token"]
    with TestClient(app, base_url="http://localhost:8000") as mcp_client:  # one MCP lifespan per app
        mcp_client.headers["Authorization"] = f"Bearer {token_a}"
        assert "Call the dentist" in _mcp_call(mcp_client, "get_upcoming_tasks")
        mcp_client.headers["Authorization"] = f"Bearer {token_b}"
        result_b = _mcp_call(mcp_client, "get_upcoming_tasks")
        assert '"isError":false' in result_b.replace(" ", "") and "Call the dentist" not in result_b


# ---------------------------------------------------------------------------
# T-MU-12: migration of a single-tenant install
# ---------------------------------------------------------------------------

def test_migration_moves_data_and_bee_token_to_the_owner(tmp_path):
    from scripts.migrate_to_multi_user import migrate
    from src.core.storage.sqlite_store import SQLiteContextStore

    legacy = tmp_path / "examen.db"
    SQLiteContextStore(str(legacy)).save_planned_task(PlannedTask(title="Legacy routine"))
    bee_dir = tmp_path / "bee"
    bee_dir.mkdir()
    (bee_dir / "token-prod").write_text("secret-token")

    report = migrate("owner", str(legacy), str(bee_dir), TEST_PASSWORD)
    assert report["created_owner"] and report["copied_db"] and report["moved_bee_token"]
    owner_id = report["user_id"]
    assert [t.title for t in get_storage_store(user_id=owner_id).list_planned_tasks()] == ["Legacy routine"]
    assert not legacy.exists() and (tmp_path / "examen.db.pre-multi-user").exists()
    assert (get_store_registry().bee_config_dir(owner_id) / "token-prod").read_text() == "secret-token"
    assert not (bee_dir / "token-prod").exists()
    assert get_system_store().get_user(owner_id).is_admin

    again = migrate("owner", str(legacy), str(bee_dir), TEST_PASSWORD)
    assert not (again["created_owner"] or again["copied_db"] or again["moved_bee_token"])


async def test_llm_calls_are_bounded_across_users(monkeypatch):
    from src.core import limits
    from src.core.config import settings

    monkeypatch.setattr(settings, "max_concurrent_llm_calls", 2)
    monkeypatch.setattr(limits, "_semaphores", {})
    running, peak = 0, 0

    async def call():
        nonlocal running, peak
        async with limits.llm_slot():
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.02)
            running -= 1

    await asyncio.gather(*(call() for _ in range(6)))
    assert peak == 2
