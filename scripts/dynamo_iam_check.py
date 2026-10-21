"""Verify IAM tenant isolation on the real stack (docs/next_steps/dynamodb_storage/04, 07 P2).

Assumes the tenant-data role as two synthetic users A and B and checks, against the deployed tables:
  - A can write, read, query (base table and index) and delete in its own partition;
  - A is denied GetItem, PutItem, Query (base and index) and Scan on B's partition.
Only synthetic items under the two random test users are written, and they are deleted at the end.

    DYNAMO_TENANT_ROLE_ARN=arn:aws:iam::<acct>:role/examen-tenant-data DYNAMO_REGION=eu-central-1 \\
      .venv/bin/python scripts/dynamo_iam_check.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from botocore.exceptions import ClientError  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.core.storage.dynamo_client import _assume  # noqa: E402
from src.core.storage.dynamo_schema import USER, table_name  # noqa: E402


def _denied(fn) -> bool:
    try:
        fn()
    except ClientError as e:
        return e.response.get("Error", {}).get("Code") in ("AccessDeniedException", "AccessDenied")
    return False


def main() -> int:
    if not settings.dynamo_tenant_role_arn:
        print("Set DYNAMO_TENANT_ROLE_ARN to the TenantDataRoleArn output of the stack.")
        return 2
    table = table_name(USER)
    user_a, user_b = f"usr_{uuid.uuid4().hex}", f"usr_{uuid.uuid4().hex}"
    client_a, _ = _assume(user_a)
    client_b, _ = _assume(user_b)
    item = lambda uid: {"pk": {"S": uid}, "sk": {"S": "TASK#iam-check"}, "title": {"S": "iam check"},  # noqa: E731
                        "g1pk": {"S": f"{uid}#ACTION"}, "g1sk": {"S": "2026-01-01#iam-check"}}
    key = lambda uid: {"pk": {"S": uid}, "sk": {"S": "TASK#iam-check"}}  # noqa: E731
    query = lambda client, uid: client.query(  # noqa: E731
        TableName=table, KeyConditionExpression="pk = :p", ExpressionAttributeValues={":p": {"S": uid}})
    index_query = lambda client, uid: client.query(  # noqa: E731
        TableName=table, IndexName="timeline", KeyConditionExpression="g1pk = :p",
        ExpressionAttributeValues={":p": {"S": f"{uid}#ACTION"}})

    checks = []
    client_b.put_item(TableName=table, Item=item(user_b))
    checks.append(("A writes its own partition", not _denied(lambda: client_a.put_item(TableName=table, Item=item(user_a)))))
    checks.append(("A reads its own item", not _denied(lambda: client_a.get_item(TableName=table, Key=key(user_a)))))
    checks.append(("A queries its own partition", not _denied(lambda: query(client_a, user_a))))
    checks.append(("A queries its own index partition", not _denied(lambda: index_query(client_a, user_a))))
    checks.append(("A is denied B's item", _denied(lambda: client_a.get_item(TableName=table, Key=key(user_b)))))
    checks.append(("A is denied writing into B", _denied(lambda: client_a.put_item(TableName=table, Item=item(user_b)))))
    checks.append(("A is denied querying B", _denied(lambda: query(client_a, user_b))))
    checks.append(("A is denied B's index partition", _denied(lambda: index_query(client_a, user_b))))
    checks.append(("A is denied Scan", _denied(lambda: client_a.scan(TableName=table, Limit=1))))
    checks.append(("A deletes its own item", not _denied(lambda: client_a.delete_item(TableName=table, Key=key(user_a)))))
    client_b.delete_item(TableName=table, Key=key(user_b))

    for label, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    failed = [label for label, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed on {table}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
