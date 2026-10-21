"""Copy EXAMEN's SQLite data into DynamoDB (docs/next_steps/dynamodb_storage/06).

Stop the service first (and the homelab auto-update timer). The SQLite files are opened read-only and
stay untouched as the rollback. Output: counts only.

    .venv/bin/python scripts/migrate_to_dynamo.py users --all [--dry-run]
    .venv/bin/python scripts/migrate_to_dynamo.py users --user usr_… [--verify-only]
    .venv/bin/python scripts/migrate_to_dynamo.py auth
    .venv/bin/python scripts/migrate_to_dynamo.py ops [--skip-events]
    .venv/bin/python scripts/migrate_to_dynamo.py restore --from-table examen-user-r20261022 --user usr_…
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import settings  # noqa: E402
from src.core.storage import migration  # noqa: E402
from src.core.storage.dynamo_store import DynamoContextStore  # noqa: E402
from src.core.tenancy import data_root, is_valid_user_id, users_root  # noqa: E402


def _users(args):
    root = users_root()
    if args.user:
        return [args.user]
    return sorted(p.name for p in root.iterdir() if p.is_dir() and is_valid_user_id(p.name)) if root.is_dir() else []


def cmd_users(args) -> int:
    failed = 0
    for uid in _users(args):
        path = users_root() / uid / "examen.db"
        if not path.exists():
            print(f"{uid}: no examen.db, skipped")
            continue
        store = DynamoContextStore(user_id=uid)
        if args.verify_only:
            tables = migration.read_sqlite(str(path))
            expected = migration.expected_counts(tables, settings.dynamo_telemetry_ttl_days)
            stored = migration.stored_counts(store)
            ok = all(stored.get(t, 0) >= n for t, n in expected.items())
            report = {"expected": expected, "stored": stored, "ok": ok, "items": None}
        else:
            report = migration.migrate_user(uid, str(path), dry_run=args.dry_run, store=store)
        failed += 0 if report["ok"] else 1
        print(f"{uid}: {'OK' if report['ok'] else 'MISMATCH'}"
              + (f" ({report['items']} items)" if report.get("items") is not None else ""))
        for table, count in sorted(report["expected"].items()):
            got = report["stored"].get(table, "-") if report["stored"] else "-"
            print(f"    {table:24} sqlite={count:<7} dynamo={got}")
    return 1 if failed else 0


def cmd_auth(args) -> int:
    counts = migration.migrate_auth(str(Path(data_root()) / "auth.db"), dry_run=args.dry_run)
    print("auth:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to copy")
    return 0


def cmd_ops(args) -> int:
    counts = migration.migrate_ops(str(Path(data_root()) / "ops.db"), dry_run=args.dry_run, skip_events=args.skip_events)
    print("ops:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to copy")
    return 0


def cmd_restore(args) -> int:
    if not args.user or not args.from_table:
        print("restore needs --from-table and --user")
        return 2
    copied = migration.copy_partition(args.from_table, DynamoContextStore(user_id=args.user))
    print(f"{args.user}: {copied} items copied from {args.from_table}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("users")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--user")
    group.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.set_defaults(func=cmd_users)
    p = sub.add_parser("auth")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_auth)
    p = sub.add_parser("ops")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-events", action="store_true")
    p.set_defaults(func=cmd_ops)
    p = sub.add_parser("restore")
    p.add_argument("--from-table", required=True)
    p.add_argument("--user", required=True)
    p.set_defaults(func=cmd_restore)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
