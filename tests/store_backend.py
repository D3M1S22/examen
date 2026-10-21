"""Storage backend switch for the test suite (docs/next_steps/dynamodb_storage/07 §3).

``EXAMEN_TEST_STORAGE=dynamo .venv/bin/pytest tests/`` runs the whole suite on the DynamoDB stores
(moto, in-process); the default run uses SQLite. Tests build stores with ``new_store(path)`` instead of
``SQLiteContextStore(path)``: on DynamoDB the same path maps to the same user partition, so a test that
reopens a store sees its data again.
"""

from __future__ import annotations

import hashlib
import os
import uuid

import pytest

BACKEND = os.environ.get("EXAMEN_TEST_STORAGE", "sqlite").strip().lower() or "sqlite"
DYNAMO = BACKEND == "dynamo"

sqlite_only = pytest.mark.skipif(DYNAMO, reason="SQLite-specific behaviour (files, raw SQL)")


def user_id_for(path) -> str:
    return "usr_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32]


def new_store(db_path):
    """A fresh store of the selected backend for ``db_path``."""
    if DYNAMO:
        from src.core.storage.dynamo_store import DynamoContextStore

        return DynamoContextStore(user_id=user_id_for(db_path))
    from src.core.storage.sqlite_store import SQLiteContextStore

    return SQLiteContextStore(str(db_path))


def start_dynamo(monkeypatch):
    """Starts moto and creates the three tables under a random prefix; returns the mock to stop."""
    from moto import mock_aws

    from src.core.config import settings
    from src.core.storage import dynamo_client
    from src.core.storage.dynamo_schema import create_tables

    for name, value in (("AWS_ACCESS_KEY_ID", "testing"), ("AWS_SECRET_ACCESS_KEY", "testing"),
                        ("AWS_SESSION_TOKEN", "testing"), ("AWS_DEFAULT_REGION", "us-east-1")):
        monkeypatch.setenv(name, value)
    for key in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token", "dynamo_endpoint_url",
                "dynamo_tenant_role_arn"):
        monkeypatch.setattr(settings, key, None)
    monkeypatch.setattr(settings, "dynamo_region", "us-east-1")
    prefix = f"t{uuid.uuid4().hex[:8]}-"
    monkeypatch.setattr(settings, "dynamo_table_prefix", prefix)
    endpoint = os.environ.get("EXAMEN_TEST_DYNAMO_ENDPOINT")
    if endpoint:  # DynamoDB Local: real DynamoDB semantics, tables dropped after the test
        monkeypatch.setattr(settings, "dynamo_endpoint_url", endpoint)
        dynamo_client.reset_clients()
        create_tables(dynamo_client.service_client(), prefix)
        return _LocalTables(prefix)
    mock = mock_aws()
    mock.start()
    dynamo_client.reset_clients()
    create_tables(dynamo_client.service_client(), prefix)
    return mock


class _LocalTables:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def stop(self) -> None:
        from src.core.storage import dynamo_client
        from src.core.storage.dynamo_schema import KINDS, table_name

        client = dynamo_client.service_client()
        for kind in KINDS:
            try:
                client.delete_table(TableName=table_name(kind, self.prefix))
            except Exception:
                pass


def dump_table(kind: str) -> bytes:
    """Every item of a table as raw bytes (the DynamoDB counterpart of reading the SQLite file)."""
    import json

    from src.core.storage.dynamo_client import service_client
    from src.core.storage.dynamo_schema import table_name

    items, kwargs = [], {"TableName": table_name(kind)}
    while True:
        page = service_client().scan(**kwargs)
        items += page.get("Items", [])
        if not page.get("LastEvaluatedKey"):
            return json.dumps(items, default=str).encode("utf-8")
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def stop_dynamo(mock) -> None:
    from src.core.storage import dynamo_client

    mock.stop()
    dynamo_client.reset_clients()
