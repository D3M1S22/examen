"""Who is acting: the user context that scopes every request, background task and pipeline run.

Multi-user isolation (docs/next_steps/multi_user/03 §1): code that touches user data resolves the
current user from ``current_user_ctx`` (set by the auth middleware for requests and by the per-user
runtime for background work). There is no fallback user: without a context the call fails closed.
"""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal, Optional

from pydantic import BaseModel, ConfigDict

AuthMethod = Literal["session", "api_token", "oauth", "system"]

# user ids are generated server-side ("usr_" + 16 hex); the pattern also guards file paths
USER_ID_RE = re.compile(r"^usr_[0-9a-f]{16}$")


class UserContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    is_admin: bool = False
    auth_method: AuthMethod = "system"


class MissingUserContext(RuntimeError):
    """User data was accessed without an authenticated user or an owning runtime."""


current_user_ctx: ContextVar[Optional[UserContext]] = ContextVar("examen_current_user", default=None)


def is_valid_user_id(user_id: Optional[str]) -> bool:
    return bool(user_id) and bool(USER_ID_RE.match(user_id))


def get_current_user() -> Optional[UserContext]:
    return current_user_ctx.get()


def require_user() -> UserContext:
    ctx = current_user_ctx.get()
    if ctx is None:
        raise MissingUserContext("No user context: user data cannot be accessed")
    return ctx


@contextmanager
def acting_as(ctx: UserContext) -> Iterator[UserContext]:
    """Runs a block (and the tasks / threads it starts with copied contexts) as ``ctx``."""
    token = current_user_ctx.set(ctx)
    try:
        yield ctx
    finally:
        current_user_ctx.reset(token)


def system_context(user_id: str) -> UserContext:
    """Context for background work owned by ``user_id`` (stream, engine timers, backfill)."""
    return UserContext(user_id=user_id, auth_method="system")
