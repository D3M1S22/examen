"""Bee account linking per user and account erasure (docs/next_steps/multi_user/02 §4–5).

Each user pairs their own Bee account in their own ``BEE_CONFIG_DIR``. A Bee account (``bee me`` id)
belongs to at most one EXAMEN user. Disconnecting Bee or erasing an account never touches another
user's directory, data or runtime.
"""

import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional, Tuple

from src.core.schemas import BeeLink
from src.core.storage import get_store_registry
from src.ingestion.bee_identity import forget_wearer_identity
from src.ingestion.stream_convo import BeeClient
from src.serving.user_runtime import TooManyActiveUsers, get_runtime_manager

logger = logging.getLogger("examen.serving.bee_accounts")

PAIRING_TTL = timedelta(minutes=5)


class BeeLinkError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _client(user_id: str) -> BeeClient:
    return BeeClient(config_dir=str(get_store_registry().bee_config_dir(user_id)))


def _system():
    return get_store_registry().system()


def public_link(link: BeeLink) -> dict:
    data = link.model_dump()
    if link.state != "pairing":
        data["pairing_url"] = None
        data["pairing_expires_at"] = None
    return data


async def start_pairing(user_id: str) -> BeeLink:
    """Starts a fresh pairing request; returns the link with the real Bee authentication URL."""
    link = _system().get_bee_link(user_id)
    if link.state == "linked":
        return await refresh_link(user_id)
    url = await _client(user_id).login_no_wait()
    if not url:
        link.state, link.last_error = "unlinked", "Bee CLI did not return an authentication link"
        _system().save_bee_link(link)
        raise BeeLinkError("pairing_failed", link.last_error, status=502)
    link.state = "pairing"
    link.pairing_url = url
    link.pairing_expires_at = (datetime.now() + PAIRING_TTL).isoformat()
    link.last_error = None
    _system().save_bee_link(link)
    _system().audit("bee_pairing_started", user_id=user_id)
    return link


async def _verified(client: BeeClient) -> Optional[Tuple[int, str, Optional[str]]]:
    """(bee user id, first name, timezone) when the user's Bee token works."""
    if not await client.status():
        return None
    me = await client.run_json(["me"])
    if not me or me.get("id") is None:
        return None
    return int(me["id"]), (me.get("first_name") or "").strip(), me.get("timezone")


async def refresh_link(user_id: str) -> BeeLink:
    """Re-checks the user's Bee token; completes a pending pairing and starts live ingestion."""
    system = _system()
    link = system.get_bee_link(user_id)
    client = _client(user_id)
    verified = await _verified(client)
    if verified is None and link.state == "pairing":
        # An approved request is finalised by resuming the login (bee-cli keeps the pairing state)
        await client.run_text(["login", "--no-wait"], timeout=30)
        verified = await _verified(client)

    now = datetime.now().isoformat()
    if verified is None:
        if link.state == "linked":
            link.state, link.last_error = "invalid", "The Bee token is no longer valid: connect Bee again"
            system.save_bee_link(link)
            await get_runtime_manager().stop_stream(user_id)
        elif link.state == "pairing" and link.pairing_expires_at and link.pairing_expires_at < now:
            link.state, link.pairing_url, link.last_error = "unlinked", None, "The pairing request expired"
            system.save_bee_link(link)
        return link

    bee_user_id, first_name, timezone = verified
    owner = system.find_bee_link_by_bee_user(bee_user_id)
    if owner is not None and owner.user_id != user_id:
        await client.logout()
        link.state, link.last_error = "invalid", "This Bee account is already linked to another EXAMEN user"
        link.pairing_url = None
        system.save_bee_link(link)
        system.audit("bee_link_conflict", user_id=user_id, detail={"bee_user_id": bee_user_id})
        raise BeeLinkError("bee_account_taken", link.last_error, status=409)

    newly_linked = link.state != "linked"
    link.state, link.bee_user_id, link.bee_first_name = "linked", bee_user_id, first_name or None
    link.pairing_url = link.pairing_expires_at = None
    link.linked_at = link.linked_at if not newly_linked else now
    link.last_ok_at, link.last_error = now, None
    system.save_bee_link(link)
    if timezone:
        system.update_user(user_id, timezone=timezone)
    if newly_linked:
        system.audit("bee_linked", user_id=user_id, detail={"bee_user_id": bee_user_id})
        forget_wearer_identity(user_id)  # the runtime picks up the new first name
        await get_runtime_manager().drop(user_id)
    try:
        get_runtime_manager().start_stream(user_id)
    except TooManyActiveUsers as e:
        link.last_error = str(e)
        system.save_bee_link(link)
    return link


async def unlink(user_id: str) -> BeeLink:
    """Stops the user's ingestion and logs out their Bee account (their directory only). Data is kept."""
    await get_runtime_manager().stop_stream(user_id)
    client = _client(user_id)
    await client.logout()
    directory = client.config_dir
    if directory and os.path.isdir(directory):
        shutil.rmtree(directory, ignore_errors=True)
    system = _system()
    system.delete_bee_link(user_id)
    system.audit("bee_unlinked", user_id=user_id)
    forget_wearer_identity(user_id)
    return system.get_bee_link(user_id)


async def erase_account(user_id: str, actor_user_id: Optional[str] = None) -> None:
    """GDPR Art. 17: stops everything for the user and deletes their data, Bee link, sessions and account."""
    system = _system()
    system.update_user(user_id, status="erasing")
    await get_runtime_manager().drop(user_id)
    try:
        await _client(user_id).logout()
    except Exception as e:
        logger.warning(f"[{user_id}] bee logout during erasure failed: {e}")
    get_store_registry().drop_user(user_id)
    system.delete_user(user_id)  # cascades to sessions, tokens and the Bee link
    system.audit("account_erased", user_id=user_id, actor_user_id=actor_user_id)
