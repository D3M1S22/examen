"""Speaker review preference (docs/next_steps/speaker_review/02 §5).

Whether untagged speech (Bee recognised nobody) is accepted as the owner's at once, or waits for the
owner's confirmation. With accounts each user sets it (`PATCH /api/account`); in single-user mode it is
the runtime setting ``SPEAKER_AUTO_ACCEPT_UNTAGGED``. The value travels in the pipeline payload, so the
AgentCore runtime never reads the account table.
"""

from typing import Optional

from src.core.config import settings


def auto_accept_untagged(user_id: Optional[str] = None) -> bool:
    """The preference of ``user_id`` (default: the current tenant). Off when it cannot be read."""
    from src.core.tenancy import get_tenant_id

    uid = user_id if user_id is not None else get_tenant_id()
    if not settings.auth_enabled or uid is None:
        return bool(settings.speaker_auto_accept_untagged)
    try:
        from src.core.auth import get_auth_store

        user = get_auth_store().get_user(uid)
    except Exception:
        return False
    return bool(user and user.auto_accept_untagged)
