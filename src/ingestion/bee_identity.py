"""Who is speaking: maps Bee speaker identities to EXAMEN speaker roles (docs/10_bee_cli_reference.md §8).

Bee has no `speaker_0/1` labels. Live, the wearer is recognised through `tagged-utterance`
(`person_first_name`, ~1 s after the utterance, ~22 % of utterances); in REST transcripts `speaker`
is a person's first name or "Unknown". Both are compared with the account owner's first name
(`bee me`, or the ``BEE_WEARER_NAME`` override).
"""

import logging
import time
from typing import Dict, Literal, Optional

from src.core.config import settings

logger = logging.getLogger("examen.ingestion.bee_identity")

SpeakerRole = Literal["user", "contact", "unknown"]

# Retry `bee me` at most this often when it fails (offline, not logged in)
_ME_RETRY_SECONDS = 600.0


def role_for_person(name: Optional[str], wearer_first_name: Optional[str]) -> SpeakerRole:
    """``user`` for the wearer, ``contact`` for another named person, ``unknown`` otherwise."""
    label = (name or "").strip()
    if not label or label.casefold() == "unknown":
        return "unknown"
    if label.casefold() == "user":  # internal sources (simulator, tests)
        return "user"
    if not wearer_first_name:
        return "unknown"  # cannot tell the wearer apart from other people
    return "user" if label.casefold() == wearer_first_name.strip().casefold() else "contact"


class WearerIdentity:
    """Caches the wearer's first name (``BEE_WEARER_NAME``, the user's Bee link, or `bee me --json`)."""

    def __init__(self, first_name: Optional[str] = None, bee_config_dir: Optional[str] = None):
        configured = first_name if first_name is not None else settings.bee_wearer_name
        self.first_name: Optional[str] = (configured or "").strip() or None
        self.bee_config_dir = bee_config_dir
        self._last_attempt: float = 0.0

    async def ensure_loaded(self) -> Optional[str]:
        if self.first_name or time.time() - self._last_attempt < _ME_RETRY_SECONDS:
            return self.first_name
        self._last_attempt = time.time()
        from src.ingestion.stream_convo import BeeClient

        profile = await BeeClient(config_dir=self.bee_config_dir).run_json(["me"])
        name = ((profile or {}).get("first_name") or "").strip()
        if name:
            self.first_name = name
        else:
            logger.warning("Wearer identity unavailable (bee me failed): tagged speakers stay 'unknown'")
        return self.first_name

    def role_for(self, name: Optional[str]) -> SpeakerRole:
        return role_for_person(name, self.first_name)


# One wearer identity per user (docs/next_steps/multi_user/02 §4.3)
_identities: Dict[str, WearerIdentity] = {}


def get_wearer_identity(user_id: Optional[str] = None) -> WearerIdentity:
    """Wearer of ``user_id`` (default: the user in the current context), from their Bee link."""
    if not user_id:
        from src.core.identity import require_user

        user_id = require_user().user_id
    identity = _identities.get(user_id)
    if identity is None:
        from src.core.storage import get_store_registry

        registry = get_store_registry()
        link = registry.system().get_bee_link(user_id)
        identity = WearerIdentity(first_name=link.bee_first_name or settings.bee_wearer_name,
                                  bee_config_dir=str(registry.bee_config_dir(user_id)))
        _identities[user_id] = identity
    return identity


def forget_wearer_identity(user_id: str) -> None:
    _identities.pop(user_id, None)
