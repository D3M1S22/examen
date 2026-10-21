"""DynamoDB auth and ops stores (docs/next_steps/dynamodb_storage/03, 07 P3).

The shared behaviour runs in test_accounts.py / test_admin_console.py under EXAMEN_TEST_STORAGE=dynamo;
these cover the DynamoDB-specific mechanics.
"""

import inspect
from datetime import timedelta

import pytest

from src.core import token_usage
from src.core.auth.dynamo_store import DynamoAuthStore
from src.core.auth.store import AuthError, AuthStore, BeeLink, iso, utcnow
from src.core.config import settings
from src.core.ops_dynamo_store import DynamoOpsStore
from src.core.ops_store import OpsStore
from src.core.runtime_settings import REGISTRY
from src.core.storage.dynamo_io import PartialWrite
from src.core.storage.errors import UniqueConflict
from tests import store_backend

PASSWORD = "Correct horse battery 9"


@pytest.fixture
def moto_tables(monkeypatch):
    if store_backend.DYNAMO:
        yield
        return
    mock = store_backend.start_dynamo(monkeypatch)
    yield
    store_backend.stop_dynamo(mock)


@pytest.fixture
def auth(moto_tables):
    return DynamoAuthStore()


@pytest.fixture
def ops(moto_tables):
    return DynamoOpsStore()


@pytest.mark.parametrize("base,sub", [(AuthStore, DynamoAuthStore), (OpsStore, DynamoOpsStore)])
def test_every_sqlite_method_is_overridden(base, sub):
    """An inherited method that opens a SQLite connection would silently bypass DynamoDB."""
    for name, fn in inspect.getmembers(base, predicate=inspect.isfunction):
        if name.startswith("__") or name in ("_conn", "_init_db"):
            continue
        if "_conn()" in inspect.getsource(fn):
            assert name in sub.__dict__, f"{sub.__name__} must override {name}"


def test_email_guard_rejects_duplicates(auth):
    auth.create_user("ada@example.com", PASSWORD)
    with pytest.raises(AuthError) as err:
        auth.create_user(" ADA@example.com ", PASSWORD)
    assert err.value.status == 409
    assert auth.count_users() == 1


def test_delete_user_resumes_after_a_failure(auth, monkeypatch):
    user = auth.create_user("grace@example.com", PASSWORD)
    auth.create_session(user.id)
    auth.create_api_token(user.id, "Alexa")
    auth.save_bee_link(BeeLink(user_id=user.id, bee_user_id=7, state="linked"))
    auth.audit("login", user_id=user.id)
    real = auth.revoke_user_tokens
    monkeypatch.setattr(auth, "revoke_user_tokens", lambda uid: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        auth.delete_user(user.id)
    assert auth.get_user(user.id) is None and auth.authenticate("grace@example.com", PASSWORD) is None
    monkeypatch.setattr(auth, "revoke_user_tokens", real)
    assert auth.delete_user(user.id) is False  # already gone, the rest completes
    assert auth.list_api_tokens(user.id) == [] and auth.find_bee_link(7) is None
    assert auth.list_audit(user_id=user.id) == []
    assert auth.create_user("grace@example.com", PASSWORD)  # the email is free again


def test_bee_account_guard(auth):
    a = auth.create_user("a@example.com", PASSWORD)
    b = auth.create_user("b@example.com", PASSWORD)
    auth.save_bee_link(BeeLink(user_id=a.id, bee_user_id=42, state="linked"))
    with pytest.raises(UniqueConflict):
        auth.save_bee_link(BeeLink(user_id=b.id, bee_user_id=42, state="linked"))
    assert auth.find_bee_link(42).user_id == a.id
    auth.save_bee_link(BeeLink(user_id=a.id, bee_user_id=43, state="linked"))  # re-pairing frees 42
    auth.save_bee_link(BeeLink(user_id=b.id, bee_user_id=42, state="linked"))
    assert auth.find_bee_link(42).user_id == b.id


def test_audit_hides_entries_beyond_a_shortened_retention(auth, monkeypatch):
    auth.audit("old_event")
    item = next(iter(auth.table.query("pk", f"AUDIT#{iso(utcnow())[:7]}")))
    old_at = iso(utcnow() - timedelta(days=40))
    auth.table.update({"pk": item["pk"], "sk": item["sk"]}, set_={"at": old_at})
    auth.audit("new_event")
    monkeypatch.setattr(settings, "auth_audit_retention_days", 30)
    assert [e["event"] for e in auth.list_audit()] == ["new_event"]


def test_event_ids_are_monotonic_and_paginate(ops):
    def event(i):
        return {"ref": f"r{i}", "at": iso(utcnow()), "level": "warning" if i % 2 else "info", "code": "x.y",
                "component": "test", "message": f"message {i}", "fingerprint": "fp"}

    ops.insert_events([event(i) for i in range(3)])
    ops.insert_events([event(i) for i in range(3, 7)])
    ids = [e["id"] for e in ops.list_events(limit=500)]
    assert ids == [7, 6, 5, 4, 3, 2, 1]
    assert [e["id"] for e in ops.list_events(before_id=4, limit=2)] == [3, 2]
    assert [e["id"] for e in ops.list_events(level="warning")] == [6, 4, 2]
    assert [e["id"] for e in ops.list_events(q="MESSAGE 5")] == [6]  # LIKE is case-insensitive
    assert ops.count_events() == 7
    ops.purge(event_days=30, max_events=4)
    assert ops.count_events() == 4 and all(e["level"] == "warning" for e in ops.list_events()[-1:])


def test_change_set_of_every_key_is_atomic(ops):
    assert len(REGISTRY) <= 98, "a change set must fit one DynamoDB transaction"
    changes = {key: 1 for key in list(REGISTRY)[:80]}
    change_id = ops.save_change_set(changes, {}, "usr_admin")
    assert len(ops.list_overrides()) == 80 and ops.settings_version() == 1
    assert len(ops.get_change_set(change_id)) == 80
    reset = ops.save_change_set({key: None for key in changes}, changes, "usr_admin")
    assert ops.list_overrides() == {} and ops.settings_version() == 2
    assert [c["change_id"] for c in ops.list_history()] == [reset, change_id]


def test_partial_token_usage_write_is_not_double_counted(ops, monkeypatch):
    hour = iso(utcnow().replace(minute=0, second=0, microsecond=0))
    for i in range(150):
        token_usage.record("bedrock", f"model-{i}", "gatekeeper", input_tokens=10, user_id="usr_x", now=None)
    real = ops.table.transact
    calls = {"n": 0}

    def flaky(ops_list):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("throttled")
        return real(ops_list)

    monkeypatch.setattr(ops.table, "transact", flaky)
    written = token_usage.flush(lambda: ops)
    assert written == 100 and len(token_usage.pending()) == 50
    token_usage.flush(lambda: ops)
    summary = ops.token_usage_summary(hour)
    assert summary["totals"]["input_tokens"] == 1500 and summary["totals"]["calls"] == 150
    assert summary["tracking_since"] == hour
    with pytest.raises(PartialWrite):
        monkeypatch.setattr(ops.table, "transact", lambda o: (_ for _ in ()).throw(RuntimeError("down")))
        ops.add_token_usage([{"hour": hour, "provider": "p", "model_id": "m", "role": "r", "calls": 1}])
    ops.delete_user("usr_x")
    monkeypatch.setattr(ops.table, "transact", real)
    assert ops.token_usage_summary(hour)["totals"]["calls"] == 0
