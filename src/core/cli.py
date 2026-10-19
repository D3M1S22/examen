"""User context for developer scripts (multi-user: every store access needs a user).

``cli_user_context()`` runs a script as an existing EXAMEN account: ``EXAMEN_CLI_USER`` (username),
falling back to ``EXAMEN_BOOTSTRAP_ADMIN``. ``ephemeral_user_context()`` is for scripts that work on
their own temporary stores (benchmarks) and only need *a* valid user for the pipeline.
"""

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from src.core.config import settings
from src.core.identity import UserContext, acting_as, system_context

EPHEMERAL_USER_ID = "usr_00000000000000ff"


@contextmanager
def cli_user_context(username: Optional[str] = None) -> Iterator[UserContext]:
    from src.core.storage import get_system_store

    name = username or os.environ.get("EXAMEN_CLI_USER") or settings.examen_bootstrap_admin
    if not name:
        raise SystemExit("Set EXAMEN_CLI_USER=<username> (an existing EXAMEN account) to run this script")
    user = get_system_store().get_user_by_username(name)
    if user is None:
        raise SystemExit(f"No EXAMEN user named {name!r} in {settings.examen_data_dir}: "
                         "create it from the dashboard (Account → Accounts) or set EXAMEN_BOOTSTRAP_ADMIN")
    with acting_as(system_context(user.user_id)) as ctx:
        yield ctx


@contextmanager
def ephemeral_user_context() -> Iterator[UserContext]:
    with acting_as(system_context(EPHEMERAL_USER_ID)) as ctx:
        yield ctx
