"""Who is speaking: maps Bee speaker identities to EXAMEN speaker roles (docs/10_bee_cli_reference.md §8,
docs/next_steps/08_speaker_identity.md).

Bee has no `speaker_0/1` labels. Live, a voice Bee recognises is reported by `tagged-utterance`
(`utterance_id`, `person_id`, `person_first_name`, `speaker_score`, ~1 s after the utterance); in REST
transcripts `speaker` is a person's first name or "Unknown".

The wearer (the EXAMEN account's Bee owner) is recognised, in order of strength:

1. ``person_id`` equal to a person id already bound to the wearer;
2. first name equal to `bee me` → ``first_name`` (or ``BEE_WEARER_NAME`` in single-user mode). The first
   tag that matches this way binds its ``person_id`` to the wearer, so later tags are matched by id and
   a namesake with another ``person_id`` becomes a ``contact``.

``person_id`` is NOT the `bee me` account id: on a real device (2026-10-22) the wearer's tags carried a
person id different from the `bee me` id. The two ids are different numbering schemes of similar size, so
comparing them could even match a contact by accident.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Set

from src.core.config import settings

logger = logging.getLogger("examen.ingestion.bee_identity")

SpeakerRole = Literal["user", "contact", "unknown"]
# How the role was decided (stored with entities, shown in the UI)
SpeakerSource = Literal["bee_voice_id", "bee_name", "history_name", "untagged", "internal"]

# Retry `bee me` at most this often when it fails (offline, not logged in)
_ME_RETRY_SECONDS = 600.0


def _norm_id(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


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


@dataclass(frozen=True)
class SpeakerMatch:
    """Who said one utterance, as far as Bee lets us know."""

    role: SpeakerRole
    name: Optional[str] = None
    person_id: Optional[str] = None
    score: Optional[float] = None
    source: SpeakerSource = "untagged"

    @property
    def is_wearer(self) -> bool:
        return self.role == "user"


UNTAGGED = SpeakerMatch(role="unknown", source="untagged")


def _score(value: Any) -> Optional[float]:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, score))


class WearerIdentity:
    """The wearer of one Bee account: first name from `bee me`, bound voice person ids.

    ``account_id`` (`bee me` → ``id``) is kept for diagnostics only: it is not a ``person_id``."""

    def __init__(self, first_name: Optional[str] = None, account_id: Optional[str] = None,
                 person_ids: Optional[Set[str]] = None):
        configured = first_name if first_name is not None else settings.bee_wearer_name
        self.first_name: Optional[str] = (configured or "").strip() or None
        self.account_id: Optional[str] = _norm_id(account_id)
        # person ids Bee uses for the wearer's voice (bound on the first matching tag)
        self.person_ids: Set[str] = {p for p in (_norm_id(x) for x in (person_ids or ())) if p}
        # person ids seen with another first name: never bound to the wearer
        self._other_person_ids: Set[str] = set()
        self._last_attempt: float = 0.0
        self.tags_seen = 0
        self.wearer_tags = 0

    @property
    def known(self) -> bool:
        return bool(self.first_name or self.person_ids)

    async def ensure_loaded(self) -> Optional[str]:
        if self.first_name or time.time() - self._last_attempt < _ME_RETRY_SECONDS:
            return self.first_name
        self._last_attempt = time.time()
        from src.ingestion.stream_convo import BeeClient

        profile = await BeeClient().run_json(["me"])
        self.apply_profile(profile)
        if not self.first_name:
            logger.warning("Wearer identity unavailable (bee me failed): tagged speakers stay 'unknown'")
        return self.first_name

    def apply_profile(self, profile: Any) -> None:
        """Takes first name and account id from a `bee me --json` payload."""
        if not isinstance(profile, dict):
            return
        name = (profile.get("first_name") or "").strip()
        if name:
            self.first_name = name
        account_id = _norm_id(profile.get("id"))
        if account_id:
            self.account_id = account_id

    def role_for(self, name: Optional[str]) -> SpeakerRole:
        return role_for_person(name, self.first_name)

    def match_tag(self, person_id: Any = None, name: Optional[str] = None, score: Any = None) -> SpeakerMatch:
        """Classifies one `tagged-utterance` and binds the wearer's person id on the first name match."""
        pid = _norm_id(person_id)
        label = (name or "").strip() or None
        value = _score(score)
        self.tags_seen += 1
        if pid and pid in self.person_ids:
            self.wearer_tags += 1
            return SpeakerMatch("user", label or self.first_name, pid, value, "bee_voice_id")
        by_name = self.role_for(label)
        if pid and self.person_ids:
            # The wearer's voice id is known and this is another one: a contact, even with the same name
            self._other_person_ids.add(pid)
            return SpeakerMatch("contact", label, pid, value, "bee_voice_id")
        if by_name == "user":
            if pid and pid not in self._other_person_ids:
                self.person_ids.add(pid)
                logger.info("Wearer voice id bound from the first name match")
            self.wearer_tags += 1
            return SpeakerMatch("user", label, pid, value, "bee_name")
        if pid and label:
            self._other_person_ids.add(pid)
        return SpeakerMatch(by_name, label, pid, value, "bee_name")

    def match_name(self, name: Optional[str], source: SpeakerSource = "history_name") -> SpeakerMatch:
        """Classifies a bare speaker name (REST history, simulator)."""
        label = (name or "").strip() or None
        if label and label.casefold() == "user":
            return SpeakerMatch("user", None, None, None, "internal")
        if label is None or label.casefold() == "unknown":
            return UNTAGGED
        return SpeakerMatch(self.role_for(label), label, None, None, source)

    def status(self) -> Dict[str, Any]:
        return {
            "wearer_identity_known": self.known,
            "wearer_voice_id_bound": bool(self.person_ids),
            "speaker_tags_seen": self.tags_seen,
            "wearer_tags": self.wearer_tags,
        }


_identity: Optional[WearerIdentity] = None
_tenant_identities: Dict[str, WearerIdentity] = {}


def get_wearer_identity() -> WearerIdentity:
    """The wearer of the current tenant's Bee (read from their own `bee me`), or the legacy singleton.

    ``BEE_WEARER_NAME`` is a host-wide override, so it only applies in single-user mode."""
    from src.core.tenancy import resolve_tenant

    tenant = resolve_tenant()
    if tenant is not None:
        identity = _tenant_identities.get(tenant)
        if identity is None:
            identity = WearerIdentity(first_name="")
            _tenant_identities[tenant] = identity
        return identity
    global _identity
    if _identity is None:
        _identity = WearerIdentity()
    return _identity


def drop_tenant_identity(user_id: str) -> None:
    _tenant_identities.pop(user_id, None)
