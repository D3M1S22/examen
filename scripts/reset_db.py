"""Database Reset and Seed Utility for EXAMEN.

Allows resetting the local SQLite database to a completely clean state,
with optional backup and optional baseline seed tasks for peace-of-mind testing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import settings
from src.core.schemas import PlannedTask
from src.core.storage import get_storage_store
from src.core.storage.sqlite_store import SQLiteContextStore


# ANSI styling
BOLD = "\033[1m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


BASELINE_SEED_TASKS = [
    {
        "title": "unplug the clothes iron",
        "domain": "safety",
        "recurrence": "daily",
        "origin": "manual",
        "scheduled_time": "08:30:00",
    },
    {
        "title": "lock the front door",
        "domain": "safety",
        "recurrence": "daily",
        "origin": "manual",
        "scheduled_time": "09:00:00",
    },
    {
        "title": "turn off the kitchen stove and oven",
        "domain": "safety",
        "recurrence": "daily",
        "origin": "manual",
        "scheduled_time": "13:00:00",
    },
    {
        "title": "take evening blood pressure medication",
        "domain": "safety",
        "recurrence": "daily",
        "origin": "manual",
        "scheduled_time": "20:00:00",
    },
]


def reset_database(backup: bool = True, seed: bool = False, db_path: str | None = None) -> None:
    """Removes the existing database file and reinitializes a fresh schema."""
    current = get_storage_store()
    if db_path is None and not isinstance(current, SQLiteContextStore):
        # DynamoDB backend: erase the user's partition (no file to back up)
        print(f"\n{BOLD}{CYAN}=== EXAMEN Database Reset ==={RESET}")
        print(f"Target: {BOLD}{type(current).__name__}{RESET} (partition of the current user)")
        current.delete_all_data()
        print(f"{GREEN}✓ All records erased.{RESET}")
        _seed(current, seed)
        return
    # Multi-user: the current user's database (EXAMEN_CLI_USER); legacy mode: SQLITE_DB_PATH
    target_path = db_path or getattr(current, "db_path", None) or settings.sqlite_db_path

    print(f"\n{BOLD}{CYAN}=== EXAMEN Database Reset ==={RESET}")
    print(f"Target Database: {BOLD}{target_path}{RESET}")

    # 1. Backup if file exists and requested
    if os.path.exists(target_path):
        if backup:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{target_path}.backup_{timestamp}"
            shutil.copy2(target_path, backup_path)
            print(f"{GREEN}✓ Backup created:{RESET} {backup_path}")

        # Delete database file and WAL/SHM artifacts if present
        for ext in ["", "-wal", "-shm"]:
            fpath = f"{target_path}{ext}"
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception as e:
                    print(f"{RED}Error removing {fpath}: {e}{RESET}")
        print(f"{GREEN}✓ Old database wiped.{RESET}")
    else:
        print(f"{DIM}No existing database file found at '{target_path}'. Creating new one.{RESET}")

    # 2. Reinitialize fresh schema. get_storage_store() returns the cached singleton,
    # whose schema init already ran against the deleted file, so re-run it explicitly.
    store = get_storage_store()
    if isinstance(store, SQLiteContextStore) and os.path.abspath(store.db_path) == os.path.abspath(target_path):
        store._init_db()
    else:
        store = SQLiteContextStore(db_path=target_path)
    print(f"{GREEN}✓ Fresh schema and FTS5 indexes reinitialized successfully.{RESET}")

    _seed(store, seed)


def _seed(store, seed: bool) -> None:
    """Seeds the baseline peace-of-mind tasks if requested."""
    if seed:
        print(f"\n{YELLOW}Seeding baseline Peace of Mind tasks...{RESET}")
        created_count = 0
        for item in BASELINE_SEED_TASKS:
            task = PlannedTask(
                title=item["title"],
                domain=item["domain"],
                recurrence=item["recurrence"],
                origin=item["origin"],
                scheduled_time=item.get("scheduled_time"),
            )
            store.save_planned_task(task)
            created_count += 1
            print(f"  • Added task: {CYAN}{task.title}{RESET} ({task.domain})")
        print(f"{GREEN}✓ Seeded {created_count} baseline tasks.{RESET}")
    else:
        print(f"{DIM}Database is now completely empty (0 records).{RESET}")

    print(f"\n{BOLD}{GREEN}Database reset completed! Ready for clean testing.{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and optionally seed the EXAMEN SQLite database.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a backup before resetting")
    parser.add_argument("--seed", action="store_true", help="Seed baseline peace-of-mind tasks after reset")
    parser.add_argument("--db-path", type=str, default=None, help="Custom SQLite DB path (defaults to settings)")
    args = parser.parse_args()

    reset_database(backup=not args.no_backup, seed=args.seed, db_path=args.db_path)


if __name__ == "__main__":
    from src.core.cli import cli_tenant

    with cli_tenant():  # resets this user's database only (EXAMEN_CLI_USER=<email>)
        main()
