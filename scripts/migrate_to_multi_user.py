#!/usr/bin/env python3
"""Moves a single-tenant EXAMEN install to the multi-user layout (docs/next_steps/multi_user/03 §2.4).

1. Creates the owner account (admin) in <EXAMEN_DATA_DIR>/system.db if it does not exist.
2. Copies the old database (SQLITE_DB_PATH, default examen.db) into the owner's scoped store
   <EXAMEN_DATA_DIR>/users/<owner_id>/examen.db with the SQLite backup API, then checks integrity.
3. Moves the host Bee token (default ~/.bee) into the owner's BEE_CONFIG_DIR and records the Bee link
   (state "linked" only once `bee me` verifies it at the next start; here it stays "invalid" until then).
4. Renames the old database to <name>.pre-multi-user for rollback.

Idempotent: a second run only reports the existing state. Stop the server before running it.

    python scripts/migrate_to_multi_user.py --owner alice [--db examen.db] [--bee-dir ~/.bee] [--password …]
"""

import argparse
import getpass
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.core.storage import get_store_registry  # noqa: E402
from src.serving.auth import AuthError, get_auth_provider  # noqa: E402


def migrate(owner: str, db_path: str, bee_dir: str, password: str) -> dict:
    registry = get_store_registry()
    system = registry.system()
    report = {"owner": owner, "created_owner": False, "copied_db": False, "moved_bee_token": False}

    user = system.get_user_by_username(owner)
    if user is None:
        user = get_auth_provider().create_user(owner, password, is_admin=True)
        report["created_owner"] = True
    report["user_id"] = user.user_id

    target = registry.user_dir(user.user_id) / "examen.db"
    source = Path(db_path)
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
            src.backup(dst)
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            target.unlink()
            raise RuntimeError(f"Integrity check failed on the copy: {ok}")
        source.rename(source.with_name(source.name + ".pre-multi-user"))
        report["copied_db"] = True
    report["db"] = str(target)

    old_bee = Path(os.path.expanduser(bee_dir))
    new_bee = registry.bee_config_dir(user.user_id)
    tokens = [p for p in old_bee.glob("token-*")] if old_bee.is_dir() else []
    if tokens and not any(new_bee.glob("token-*")):
        for token in tokens:
            shutil.copy2(token, new_bee / token.name)
            os.chmod(new_bee / token.name, 0o600)
            token.unlink()
        link = system.get_bee_link(user.user_id)
        link.state, link.last_error = "invalid", "Migrated token: verify it with 'Connect Bee' / GET /api/bee/link"
        system.save_bee_link(link)
        report["moved_bee_token"] = True
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--owner", required=True, help="Username of the owner (admin) account")
    parser.add_argument("--db", default=settings.sqlite_db_path, help="Single-tenant database to migrate")
    parser.add_argument("--bee-dir", default="~/.bee", help="Existing Bee CLI config dir of the service user")
    parser.add_argument("--password", help="Owner password (prompted when the owner does not exist yet)")
    args = parser.parse_args()

    password = args.password
    if get_store_registry().system().get_user_by_username(args.owner) is None and not password:
        password = getpass.getpass(f"Password for the new owner '{args.owner}': ")
    try:
        report = migrate(args.owner, args.db, args.bee_dir, password or "")
    except AuthError as e:
        sys.exit(f"Cannot create the owner: {e.message}")
    for key, value in report.items():
        print(f"{key:>16}: {value}")


if __name__ == "__main__":
    main()
