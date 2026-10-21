"""DynamoDB table specs: the single source of the key schema (docs/next_steps/dynamodb_storage/02, 03, 05).

``deploy/aws/dynamodb.yaml`` must declare the same keys, indexes and projections:
``tests/test_dynamo_schema.py`` compares the two. Tests and DynamoDB Local create tables from here
(``scripts/dynamo_tables.py``).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Iterable, List, Optional

USER, AUTH, OPS = "user", "auth", "ops"
KINDS = (USER, AUTH, OPS)
TTL_ATTRIBUTE = "ttl"

# Large items (briefings, dossiers) are listed through indexes that carry only these attributes;
# the full item is then fetched from the base table with a consistent BatchGetItem.
USER_INCLUDE = ["status", "final_status", "kind", "session_id", "ingest_source", "ingest_run_id",
                "start_time", "last_updated_at", "created_at"]


def _attrs(*names: str) -> List[Dict[str, str]]:
    return [{"AttributeName": n, "AttributeType": "S"} for n in names]


def _gsi(name: str, pk: str, sk: str, projection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "IndexName": name,
        "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}, {"AttributeName": sk, "KeyType": "RANGE"}],
        "Projection": projection,
    }


_BASE_KEYS = [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}]

TABLE_SPECS: Dict[str, Dict[str, Any]] = {
    USER: {
        "KeySchema": _BASE_KEYS,
        "AttributeDefinitions": _attrs("pk", "sk", "g1pk", "g1sk", "g2pk", "g2sk", "g3pk", "g3sk"),
        "GlobalSecondaryIndexes": [
            _gsi("timeline", "g1pk", "g1sk", {"ProjectionType": "ALL"}),
            _gsi("timeline_keys", "g2pk", "g2sk", {"ProjectionType": "INCLUDE", "NonKeyAttributes": USER_INCLUDE}),
            _gsi("group_keys", "g3pk", "g3sk", {"ProjectionType": "INCLUDE", "NonKeyAttributes": USER_INCLUDE}),
        ],
        "StreamSpecification": {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
    },
    AUTH: {
        "KeySchema": _BASE_KEYS,
        "AttributeDefinitions": _attrs("pk", "sk", "g1pk", "g1sk", "g2pk", "g2sk"),
        "GlobalSecondaryIndexes": [
            _gsi("by_owner", "g1pk", "g1sk", {"ProjectionType": "ALL"}),
            _gsi("by_actor", "g2pk", "g2sk", {"ProjectionType": "KEYS_ONLY"}),
        ],
    },
    OPS: {
        "KeySchema": _BASE_KEYS,
        "AttributeDefinitions": _attrs("pk", "sk", "g1pk", "g1sk", "g2pk", "g2sk"),
        "GlobalSecondaryIndexes": [
            _gsi("by_owner", "g1pk", "g1sk", {"ProjectionType": "KEYS_ONLY"}),
            _gsi("by_fingerprint", "g2pk", "g2sk", {"ProjectionType": "ALL"}),
        ],
    },
}

INDEX = {
    USER: {"g1": "timeline", "g2": "timeline_keys", "g3": "group_keys"},
    AUTH: {"g1": "by_owner", "g2": "by_actor"},
    OPS: {"g1": "by_owner", "g2": "by_fingerprint"},
}


def table_name(kind: str, prefix: Optional[str] = None) -> str:
    if prefix is None:
        from src.core.config import settings

        prefix = settings.dynamo_table_prefix
    return f"{prefix}{kind}"


def key_part(value: Any) -> str:
    """A key component that is followed by other components: no ``#``, bounded length."""
    text = "" if value is None else str(value)
    if "#" in text or len(text) > 200:
        return "h_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    return text


def create_table_kwargs(kind: str, prefix: Optional[str] = None) -> Dict[str, Any]:
    spec = TABLE_SPECS[kind]
    return {"TableName": table_name(kind, prefix), "BillingMode": "PAY_PER_REQUEST", **spec}


def create_tables(client: Any, prefix: Optional[str] = None, kinds: Iterable[str] = KINDS,
                  wait: bool = True) -> List[str]:
    """Creates the missing tables (DynamoDB Local, moto, dev accounts) and enables TTL. Returns created names."""
    created = []
    existing = set(client.list_tables().get("TableNames", []))
    for kind in kinds:
        name = table_name(kind, prefix)
        if name in existing:
            continue
        client.create_table(**create_table_kwargs(kind, prefix))
        created.append(name)
    for name in created:
        if wait:
            for _ in range(120):
                if client.describe_table(TableName=name)["Table"].get("TableStatus") == "ACTIVE":
                    break
                time.sleep(0.5)
        try:
            client.update_time_to_live(TableName=name, TimeToLiveSpecification={"Enabled": True,
                                                                                 "AttributeName": TTL_ATTRIBUTE})
        except Exception:  # pragma: no cover - DynamoDB Local versions without TTL support
            pass
    return created


def check_tables(client: Any, prefix: Optional[str] = None, kinds: Iterable[str] = KINDS) -> List[str]:
    """Start-up check: problems with the deployed tables (missing table, key schema or index mismatch)."""
    problems = []
    for kind in kinds:
        name = table_name(kind, prefix)
        try:
            table = client.describe_table(TableName=name)["Table"]
        except Exception as e:
            problems.append(f"{name}: {type(e).__name__}")
            continue
        spec = TABLE_SPECS[kind]
        if table.get("KeySchema") != spec["KeySchema"]:
            problems.append(f"{name}: key schema differs")
        deployed = {g["IndexName"]: g for g in table.get("GlobalSecondaryIndexes") or []}
        for gsi in spec["GlobalSecondaryIndexes"]:
            have = deployed.get(gsi["IndexName"])
            if have is None:
                problems.append(f"{name}: index {gsi['IndexName']} missing")
            elif have.get("KeySchema") != gsi["KeySchema"]:
                problems.append(f"{name}: index {gsi['IndexName']} key schema differs")
    return problems
