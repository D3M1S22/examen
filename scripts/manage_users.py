#!/usr/bin/env python3
"""Administer EXAMEN accounts from the server shell (docs/13_multi_user_accounts.md §7).

    python scripts/manage_users.py list
    python scripts/manage_users.py create --email ana@example.com            # prompts for the password
    python scripts/manage_users.py reset-password --email ana@example.com    # signs the user out everywhere
    python scripts/manage_users.py claim-legacy-db --email ana@example.com [--db examen.db]
    python scripts/manage_users.py delete --email ana@example.com            # GDPR erasure, asks to confirm
    python scripts/manage_users.py promote --email ana@example.com [--revoke] # grant / remove admin
    python scripts/manage_users.py disable --email ana@example.com           # signs out everywhere
    python scripts/manage_users.py enable --email ana@example.com

There is no email service yet, so password resets are done here by the operator. Passwords are read
with getpass and never echoed or logged.
"""

from __future__ import annotations

import argparse
import getpass
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.auth import AuthError, get_auth_store  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.tenancy import delete_tenant_data, tenant_db_path, tenant_has_bee_login  # noqa: E402


def _ask_password() -> str:
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return first


def _user(email: str):
    user = get_auth_store().get_user_by_email(email)
    if user is None:
        sys.exit(f"No account for {email}.")
    return user


def cmd_list(_args) -> None:
    users = get_auth_store().list_users()
    if not users:
        print("No accounts.")
    for u in users:
        bee = "bee: linked" if tenant_has_bee_login(u.id) else "bee: -"
        flags = ("admin " if u.is_admin else "") + ("DISABLED " if not u.active else "")
        print(f"{u.id}  {u.email:<36} {flags}created {u.created_at}  last login {u.last_login_at or '-'}  {bee}")


def cmd_create(args) -> None:
    try:
        user = get_auth_store().create_user(args.email, _ask_password(), args.name, consent_version=None)
    except AuthError as e:
        sys.exit(e.message)
    print(f"Created {user.id}. The user accepts the privacy notice at first sign-in.")


def cmd_reset_password(args) -> None:
    store = get_auth_store()
    user = _user(args.email)
    try:
        store.set_password(user.id, _ask_password())
    except AuthError as e:
        sys.exit(e.message)
    print(f"Password changed; {store.revoke_user_sessions(user.id)} session(s) signed out.")


def cmd_claim_legacy_db(args) -> None:
    """Moves single-user data (SQLITE_DB_PATH) into one account. The Bee must be paired again."""
    user = _user(args.email)
    source = Path(args.db or settings.sqlite_db_path)
    if not source.exists():
        sys.exit(f"{source} not found.")
    target = Path(tenant_db_path(user.id))
    if target.exists() and target.stat().st_size > 0 and not args.force:
        sys.exit(f"{user.email} already has data ({target}). Use --force to overwrite it.")
    # Consistent copy even if the server is running (SQLite online backup)
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)
    target.chmod(0o600)
    print(f"Copied {source} into {user.email}'s store. Keep or delete the original yourself.")


def cmd_delete(args) -> None:
    user = _user(args.email)
    if not args.yes and input(f"Permanently delete {user.email} and all their data? [type 'delete'] ") != "delete":
        sys.exit("Aborted.")
    delete_tenant_data(user.id)
    get_auth_store().delete_user(user.id)
    print("Deleted. Restart the server if it is running, so the user's runtime stops.")


def cmd_promote(args) -> None:
    store = get_auth_store()
    user = _user(args.email)
    store.set_admin(user.id, not args.revoke)
    store.audit("cli_admin_revoked" if args.revoke else "cli_admin_granted", user_id=user.id)
    print(f"{user.email} is {'no longer' if args.revoke else 'now'} an administrator.")


def cmd_set_status(args) -> None:
    store = get_auth_store()
    user = _user(args.email)
    status = "disabled" if args.command == "disable" else "active"
    store.set_status(user.id, status)
    store.audit(f"cli_user_{status}", user_id=user.id)
    note = " Signed out everywhere; restart the server to stop a running Bee stream." if status == "disabled" else ""
    print(f"{user.email} is {status}.{note}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    p = sub.add_parser("create")
    p.add_argument("--email", required=True)
    p.add_argument("--name")
    p.set_defaults(func=cmd_create)
    p = sub.add_parser("reset-password")
    p.add_argument("--email", required=True)
    p.set_defaults(func=cmd_reset_password)
    p = sub.add_parser("claim-legacy-db")
    p.add_argument("--email", required=True)
    p.add_argument("--db")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_claim_legacy_db)
    p = sub.add_parser("delete")
    p.add_argument("--email", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_delete)
    p = sub.add_parser("promote")
    p.add_argument("--email", required=True)
    p.add_argument("--revoke", action="store_true")
    p.set_defaults(func=cmd_promote)
    for name in ("disable", "enable"):
        p = sub.add_parser(name)
        p.add_argument("--email", required=True)
        p.set_defaults(func=cmd_set_status)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
