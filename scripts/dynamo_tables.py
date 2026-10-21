"""Create or check the EXAMEN DynamoDB tables (docs/next_steps/dynamodb_storage/05 §1, §5).

For DynamoDB Local and dev accounts; production tables come from deploy/aws/dynamodb.yaml.

    DYNAMO_ENDPOINT_URL=http://localhost:8001 .venv/bin/python scripts/dynamo_tables.py create
    .venv/bin/python scripts/dynamo_tables.py check
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import dynamo_region, settings  # noqa: E402
from src.core.storage.dynamo_client import service_client  # noqa: E402
from src.core.storage.dynamo_schema import KINDS, check_tables, create_tables, table_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["create", "check"])
    parser.add_argument("--prefix", default=None, help="Table prefix (default DYNAMO_TABLE_PREFIX)")
    args = parser.parse_args()
    prefix = args.prefix if args.prefix is not None else settings.dynamo_table_prefix
    client = service_client()
    where = settings.dynamo_endpoint_url or dynamo_region()
    if args.action == "create":
        created = create_tables(client, prefix)
        for kind in KINDS:
            name = table_name(kind, prefix)
            print(f"{name}: {'created' if name in created else 'exists'} ({where})")
    problems = check_tables(client, prefix)
    for problem in problems:
        print(f"PROBLEM {problem}")
    if not problems:
        print(f"Tables OK ({where}, prefix {prefix!r})")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
