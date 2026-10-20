"""Tenant for developer scripts (with ``AUTH_ENABLED=true`` every access to user data needs a user).

``cli_tenant()`` runs a script on behalf of an existing account: ``EXAMEN_CLI_USER=<email>``. With
``AUTH_ENABLED=false`` it yields None and the script keeps the legacy single-user store.
``ephemeral_tenant()`` is for scripts that work on their own temporary stores (benchmarks) and only need
*a* valid tenant for the code paths that resolve one.
"""

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from src.core.config import settings
from src.core.tenancy import tenant_scope

EPHEMERAL_USER_ID = "usr_" + "0" * 30 + "ff"


@contextmanager
def cli_tenant(email: Optional[str] = None) -> Iterator[Optional[str]]:
    if not settings.auth_enabled:
        yield None
        return
    from src.core.auth import get_auth_store

    address = email or os.environ.get("EXAMEN_CLI_USER")
    if not address:
        raise SystemExit("Accounts are enabled: set EXAMEN_CLI_USER=<email> of an existing account "
                         "(or AUTH_ENABLED=false for the legacy single-user store)")
    user = get_auth_store().get_user_by_email(address)
    if user is None:
        raise SystemExit(f"No EXAMEN account for {address!r} in {settings.examen_data_dir} "
                         "(scripts/manage_users.py list)")
    with tenant_scope(user.id) as uid:
        yield uid


@contextmanager
def ephemeral_tenant() -> Iterator[Optional[str]]:
    if not settings.auth_enabled:
        yield None
        return
    with tenant_scope(EPHEMERAL_USER_ID) as uid:
        yield uid
