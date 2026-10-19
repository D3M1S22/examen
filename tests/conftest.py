"""Shared test isolation.

1. The suite must never reach the developer's real Bee account: several endpoints run `bee logout`
   (Bee disconnect, account erasure), and the probes call `bee status` / `bee me` over the network.
   Every test therefore sees "no Bee binary" and a stub command that always fails; tests that need
   Bee output patch `BeeClient._build_cmd` / `run_json` themselves.
2. Multi-user: each test gets its own data directory, fresh per-user registries, and runs as
   ``TEST_USER_ID`` unless it signs in through the API (``login_client``) or clears the context.
"""

import sys

import pytest

TEST_USER_ID = "usr_00000000000000a1"
TEST_USERNAME = "tester"
TEST_PASSWORD = "correct horse battery staple"
CSRF_HEADERS = {"x-requested-with": "examen"}


@pytest.fixture(autouse=True)
def _no_real_bee_cli(monkeypatch):
    from src.ingestion import bee_identity, stream_convo

    monkeypatch.setattr(stream_convo, "get_bee_binary_path", lambda: None)
    monkeypatch.setattr(
        stream_convo.BeeClient, "_build_cmd",
        lambda self, args: [sys.executable, "-c", "import sys; sys.exit(3)"],
    )
    # Fresh wearer identities per test (the registry caches `bee me`)
    monkeypatch.setattr(bee_identity, "_identities", {})
    yield


@pytest.fixture(autouse=True)
def _isolated_multi_user(tmp_path, monkeypatch):
    from src.core import storage as storage_mod
    from src.core.config import settings
    from src.core.identity import UserContext, current_user_ctx
    from src.ingestion import backfill as backfill_mod
    from src.ingestion import event_engine as engine_mod
    from src.serving import auth as auth_mod
    from src.serving import user_runtime as runtime_mod

    data_dir = tmp_path / "examen-data"
    monkeypatch.setattr(settings, "examen_data_dir", str(data_dir))
    # The developer's .env must not change auth behaviour under test
    monkeypatch.setattr(settings, "auth_allow_signup", True)
    monkeypatch.setattr(settings, "examen_bootstrap_admin", None)
    monkeypatch.setattr(settings, "examen_bootstrap_admin_password", None)
    storage_mod.reset_store_registry(storage_mod.StoreRegistry(str(data_dir)))
    monkeypatch.setattr(engine_mod, "_engines", {})
    monkeypatch.setattr(engine_mod, "_runtimes", {})
    monkeypatch.setattr(backfill_mod, "_services", {})
    monkeypatch.setattr(runtime_mod, "_manager", None)
    monkeypatch.setattr(runtime_mod, "_hub", runtime_mod.UserEventHub())
    monkeypatch.setattr(auth_mod, "_provider", None)
    token = current_user_ctx.set(UserContext(user_id=TEST_USER_ID))
    yield
    current_user_ctx.reset(token)
    storage_mod.reset_store_registry(None)


def create_test_user(user_id: str = TEST_USER_ID, username: str = TEST_USERNAME,
                     password: str = TEST_PASSWORD, is_admin: bool = False):
    """Creates a user with a fixed id in the System DB (tests address per-user registries by id)."""
    from argon2 import PasswordHasher

    from src.core.storage import get_system_store

    system = get_system_store()
    existing = system.get_user(user_id)
    if existing is not None:
        return existing
    return system.create_user(user_id, username, PasswordHasher().hash(password), is_admin=is_admin)


def login_client(client, user_id: str = TEST_USER_ID, username: str = TEST_USERNAME,
                 password: str = TEST_PASSWORD, is_admin: bool = False):
    """Signs a Starlette TestClient in (session cookie + CSRF header) and returns it."""
    create_test_user(user_id, username, password, is_admin)
    client.headers.update(CSRF_HEADERS)
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return client
