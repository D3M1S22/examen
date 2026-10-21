"""DynamoDB implementation of the account store (docs/next_steps/dynamodb_storage/03 §1).

Same public methods and behaviour as ``AuthStore`` (which it extends for the shared logic such as
``ensure_bootstrap_admin``). Uniqueness of emails and Bee accounts uses guard items written in the same
transaction as the record. Secrets are stored as SHA-256 digests only, as in SQLite.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.core.auth.passwords import dummy_verify, hash_password, needs_rehash, verify_password
from src.core.auth.store import (
    API_TOKEN_PREFIX,
    SESSION_TOKEN_BYTES,
    ApiToken,
    AuthError,
    AuthStore,
    BeeLink,
    User,
    digest,
    is_plausible_email,
    iso,
    normalize_email,
    utcnow,
)
from src.core.config import settings
from src.core.storage.dynamo_io import DynamoTable, Expr, is_conditional_failure
from src.core.storage.dynamo_schema import AUTH, INDEX, table_name
from src.core.storage.errors import UniqueConflict

_USER_FIELDS = ("id", "email", "display_name", "created_at", "last_login_at", "privacy_consent_version",
                "privacy_consent_at", "is_admin", "status")
_LINK_FIELDS = ("user_id", "bee_user_id", "bee_first_name", "state", "last_error", "linked_at", "updated_at")


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp())


class DynamoAuthStore(AuthStore):
    """``examen-auth``: users, email guards, sessions, API tokens, Bee links and the audit log."""

    def __init__(self, client_getter=None, table: Optional[str] = None):
        from src.core.storage import dynamo_client

        self.db_path = None
        self._lock = threading.Lock()
        self.table = DynamoTable(client_getter or dynamo_client.service_client, table or table_name(AUTH))
        self._g1, self._g2 = INDEX[AUTH]["g1"], INDEX[AUTH]["g2"]

    def _conn(self):  # pragma: no cover - guards against an inherited SQLite method
        raise NotImplementedError("DynamoAuthStore has no SQLite connection")

    def _init_db(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    @staticmethod
    def _to_user(item: Dict[str, Any]) -> User:
        fields = {f: item.get(f) for f in _USER_FIELDS if f != "is_admin" and item.get(f) is not None}
        return User(**fields, is_admin=bool(item.get("is_admin")))

    def _user_item(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.table.get({"pk": f"USER#{user_id}", "sk": "PROFILE"})

    def create_user(self, email: str, password: str, display_name: Optional[str] = None,
                    consent_version: Optional[str] = None, is_admin: bool = False) -> User:
        from src.core.auth.passwords import password_problem

        email = normalize_email(email)
        if not is_plausible_email(email):
            raise AuthError("Enter a valid email address.")
        problem = password_problem(password, email, settings.auth_min_password_length)
        if problem:
            raise AuthError(problem)
        name = (display_name or "").strip()[:60] or None
        now = iso(utcnow())
        user_id = f"usr_{uuid.uuid4().hex}"
        item = {
            "pk": f"USER#{user_id}", "sk": "PROFILE", "id": user_id, "email": email,
            "password_hash": hash_password(password), "display_name": name, "created_at": now,
            "password_changed_at": now, "privacy_consent_version": consent_version,
            "privacy_consent_at": now if consent_version else None, "is_admin": int(is_admin), "status": "active",
            "g1pk": "USERS", "g1sk": f"{now}#{user_id}",
        }
        try:
            self.table.transact([
                self.table.tx_put(item, condition="attribute_not_exists(pk)"),
                self.table.tx_put({"pk": f"EMAIL#{email}", "sk": "EMAIL", "user_id": user_id},
                                  condition="attribute_not_exists(pk)"),
            ])
        except Exception as err:
            if is_conditional_failure(err):
                raise AuthError("An account with this email already exists.", status=409)
            raise
        return self.get_user(user_id)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> Optional[User]:
        item = self._user_item(user_id)
        return self._to_user(item) if item else None

    def _user_item_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        guard = self.table.get({"pk": f"EMAIL#{normalize_email(email)}", "sk": "EMAIL"})
        return self._user_item(guard["user_id"]) if guard else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        item = self._user_item_by_email(email)
        return self._to_user(item) if item else None

    def _user_keys(self) -> List[Dict[str, Any]]:
        return list(self.table.query("g1pk", "USERS", index=self._g1, sk_attr="g1sk"))

    def list_users(self) -> List[User]:
        return [self._to_user(i) for i in self._user_keys()]

    def count_users(self) -> int:
        return len(self._user_keys())

    def count_admins(self) -> int:
        return sum(1 for i in self._user_keys() if i.get("is_admin"))

    def _update_user(self, user_id: str, **fields: Any) -> None:
        try:
            self.table.update({"pk": f"USER#{user_id}", "sk": "PROFILE"}, set_=fields,
                              condition="attribute_exists(pk)")
        except Exception as err:
            if not is_conditional_failure(err):  # UPDATE of a missing row is a no-op in SQLite
                raise

    def set_admin(self, user_id: str, is_admin: bool) -> None:
        self._update_user(user_id, is_admin=int(is_admin))

    def set_status(self, user_id: str, status: str) -> None:
        """``disabled`` also signs the user out everywhere (sessions and access tokens)."""
        if status not in ("active", "disabled"):
            raise AuthError("Status must be 'active' or 'disabled'.")
        self._update_user(user_id, status=status)
        if status == "disabled":
            self.revoke_user_sessions(user_id)
            self.revoke_user_tokens(user_id)

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """Returns the user when the credentials match. Timing does not reveal unknown emails."""
        item = self._user_item_by_email(email)
        if item is None:
            dummy_verify(password or "")
            return None
        if not verify_password(password or "", item["password_hash"]) or item.get("status") != "active":
            return None
        fields: Dict[str, Any] = {"last_login_at": iso(utcnow())}
        if needs_rehash(item["password_hash"]):
            fields["password_hash"] = hash_password(password)
        self._update_user(item["id"], **fields)
        return self.get_user(item["id"])

    def verify_user_password(self, user_id: str, password: str) -> bool:
        item = self._user_item(user_id)
        return bool(item) and verify_password(password or "", item["password_hash"])

    def set_password(self, user_id: str, new_password: str) -> None:
        from src.core.auth.passwords import password_problem

        user = self.get_user(user_id)
        if user is None:
            raise AuthError("Account not found.", status=404)
        problem = password_problem(new_password, user.email, settings.auth_min_password_length)
        if problem:
            raise AuthError(problem)
        self._update_user(user_id, password_hash=hash_password(new_password), password_changed_at=iso(utcnow()))

    def update_profile(self, user_id: str, display_name: Optional[str]) -> Optional[User]:
        name = (display_name or "").strip()[:60] or None
        self._update_user(user_id, display_name=name)
        return self.get_user(user_id)

    def record_consent(self, user_id: str, version: str) -> None:
        self._update_user(user_id, privacy_consent_version=version, privacy_consent_at=iso(utcnow()))

    def delete_user(self, user_id: str) -> bool:
        """Deletes the account; sessions, tokens, the Bee link and the user's audit entries go with it.
        Login stops at step 1; every later step is idempotent, so a retry completes an interrupted erasure."""
        item = self._user_item(user_id)
        deleted = False
        if item:
            self.table.transact([
                self.table.tx_delete({"pk": f"USER#{user_id}", "sk": "PROFILE"}),
                self.table.tx_delete({"pk": f"EMAIL#{item['email']}", "sk": "EMAIL"}),
            ])
            deleted = True
        self.revoke_user_sessions(user_id)
        self.revoke_user_tokens(user_id)
        self.delete_bee_link(user_id)
        own = list(self.table.query("g1pk", f"USER#{user_id}#AUDIT", index=self._g1))
        self.table.batch_write(deletes=[{"pk": i["pk"], "sk": i["sk"]} for i in own])
        for key in self.table.query("g2pk", f"ACTOR#{user_id}", index=self._g2):
            self.table.update({"pk": key["pk"], "sk": key["sk"]}, remove=["actor_id", "g2pk", "g2sk"])
        return deleted

    # ------------------------------------------------------------------
    # Browser sessions
    # ------------------------------------------------------------------
    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        now = utcnow()
        expires = iso(now + timedelta(hours=settings.auth_session_ttl_hours))
        self.table.put({
            "pk": f"SESSION#{digest(token)}", "sk": "SESSION", "token_hash": digest(token), "user_id": user_id,
            "created_at": iso(now), "expires_at": expires, "last_seen_at": iso(now), "ttl": _epoch(expires),
            "g1pk": f"USER#{user_id}#SESSION", "g1sk": f"{iso(now)}#{digest(token)[:16]}",
        })
        return token

    def user_for_session(self, token: Optional[str]) -> Optional[User]:
        """The active user of a session. Sliding expiry: renewed once less than half of it is left."""
        if not token:
            return None
        h = digest(token)
        item = self.table.get({"pk": f"SESSION#{h}", "sk": "SESSION"})
        now = utcnow()
        if item is None or item["expires_at"] < iso(now):  # TTL deletion is lazy: check the expiry here
            return None
        user = self.get_user(item["user_id"])
        if user is None or not user.active:
            return None
        lifetime = timedelta(hours=settings.auth_session_ttl_hours)
        if datetime.fromisoformat(item["expires_at"]) - now < lifetime / 2:
            expires = iso(now + lifetime)
            self.table.update({"pk": f"SESSION#{h}", "sk": "SESSION"},
                              set_={"expires_at": expires, "last_seen_at": iso(now), "ttl": _epoch(expires)})
        return user

    def revoke_session(self, token: Optional[str]) -> None:
        if not token:
            return
        self.table.delete({"pk": f"SESSION#{digest(token)}", "sk": "SESSION"})

    def revoke_user_sessions(self, user_id: str, keep_token: Optional[str] = None) -> int:
        keep = digest(keep_token) if keep_token else None
        doomed = [{"pk": i["pk"], "sk": i["sk"]} for i in
                  self.table.query("g1pk", f"USER#{user_id}#SESSION", index=self._g1)
                  if i.get("token_hash") != keep]
        self.table.batch_write(deletes=doomed)
        return len(doomed)

    # ------------------------------------------------------------------
    # MCP / API access tokens
    # ------------------------------------------------------------------
    def create_api_token(self, user_id: str, name: str) -> Dict[str, Any]:
        """Returns the token in clear text once; only its digest is stored."""
        secret = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = ApiToken(
            id=f"tok_{uuid.uuid4().hex[:16]}", name=(name or "MCP client").strip()[:60] or "MCP client",
            prefix=secret[:10], created_at=iso(utcnow()),
        )
        self.table.put({
            "pk": f"TOKEN#{digest(secret)}", "sk": "TOKEN", "id": token.id, "user_id": user_id, "name": token.name,
            "prefix": token.prefix, "created_at": token.created_at,
            "g1pk": f"USER#{user_id}#TOKEN", "g1sk": f"{token.created_at}#{token.id}",
        })
        return {"token": secret, **token.model_dump()}

    def _token_items(self, user_id: str) -> List[Dict[str, Any]]:
        return list(self.table.query("g1pk", f"USER#{user_id}#TOKEN", index=self._g1, sk_attr="g1sk"))

    def list_api_tokens(self, user_id: str) -> List[ApiToken]:
        return [ApiToken(id=i["id"], name=i["name"], prefix=i["prefix"], created_at=i["created_at"],
                         last_used_at=i.get("last_used_at")) for i in self._token_items(user_id)]

    def revoke_user_tokens(self, user_id: str) -> int:
        items = self._token_items(user_id)
        self.table.batch_write(deletes=[{"pk": i["pk"], "sk": i["sk"]} for i in items])
        return len(items)

    def revoke_api_token(self, user_id: str, token_id: str) -> bool:
        for item in self._token_items(user_id):
            if item.get("id") == token_id:
                self.table.delete({"pk": item["pk"], "sk": item["sk"]})
                return True
        return False

    def user_for_api_token(self, secret: Optional[str]) -> Optional[User]:
        if not secret or not secret.startswith(API_TOKEN_PREFIX):
            return None
        key = {"pk": f"TOKEN#{digest(secret)}", "sk": "TOKEN"}
        item = self.table.get(key)
        if item is None:
            return None
        self.table.update(key, set_={"last_used_at": iso(utcnow())})
        user = self.get_user(item["user_id"])
        return user if user is not None and user.active else None

    # ------------------------------------------------------------------
    # Bee account links
    # ------------------------------------------------------------------
    @staticmethod
    def _to_link(item: Dict[str, Any]) -> BeeLink:
        return BeeLink(**{f: item.get(f) for f in _LINK_FIELDS if item.get(f) is not None})

    def get_bee_link(self, user_id: str) -> BeeLink:
        item = self.table.get({"pk": f"BEE#{user_id}", "sk": "BEE"})
        return self._to_link(item) if item else BeeLink(user_id=user_id)

    def find_bee_link(self, bee_user_id: int) -> Optional[BeeLink]:
        guard = self.table.get({"pk": f"BEEUSER#{int(bee_user_id)}", "sk": "BEEUSER"})
        if not guard:
            return None
        item = self.table.get({"pk": f"BEE#{guard['user_id']}", "sk": "BEE"})
        return self._to_link(item) if item and item.get("bee_user_id") == int(bee_user_id) else None

    def save_bee_link(self, link: BeeLink) -> BeeLink:
        link.updated_at = iso(utcnow())
        current = self.table.get({"pk": f"BEE#{link.user_id}", "sk": "BEE"})
        old_bee = current.get("bee_user_id") if current else None
        ops = [self.table.tx_put({"pk": f"BEE#{link.user_id}", "sk": "BEE",
                                  **{f: getattr(link, f) for f in _LINK_FIELDS}})]
        if link.bee_user_id is not None and link.bee_user_id != old_bee:
            e = Expr()
            ops.append(self.table.tx_put(
                {"pk": f"BEEUSER#{int(link.bee_user_id)}", "sk": "BEEUSER", "user_id": link.user_id},
                condition=f"attribute_not_exists(pk) OR {e.name('user_id')} = {e.value(link.user_id)}", expr=e))
        if old_bee is not None and old_bee != link.bee_user_id:
            ops.append(self.table.tx_delete({"pk": f"BEEUSER#{int(old_bee)}", "sk": "BEEUSER"}))
        try:
            self.table.transact(ops)
        except Exception as err:
            if is_conditional_failure(err):
                raise UniqueConflict("Bee account already linked to another user") from err
            raise
        return link

    def delete_bee_link(self, user_id: str) -> None:
        current = self.table.get({"pk": f"BEE#{user_id}", "sk": "BEE"})
        if not current:
            return
        ops = [self.table.tx_delete({"pk": f"BEE#{user_id}", "sk": "BEE"})]
        if current.get("bee_user_id") is not None:
            e = Expr()
            ops.append(self.table.tx_delete({"pk": f"BEEUSER#{int(current['bee_user_id'])}", "sk": "BEEUSER"},
                                            condition=f"attribute_not_exists(pk) OR {e.name('user_id')} = {e.value(user_id)}",
                                            expr=e))
        self.table.transact(ops)

    # ------------------------------------------------------------------
    # Audit log (security events only: no email, name or IP address)
    # ------------------------------------------------------------------
    def audit(self, event: str, user_id: Optional[str] = None, actor_id: Optional[str] = None,
              detail: Optional[Dict[str, Any]] = None) -> None:
        now = utcnow()
        at = iso(now)
        entry_id = f"{at}#{time.time_ns():020d}"
        item = {
            "pk": f"AUDIT#{at[:7]}", "sk": entry_id, "id": entry_id, "at": at, "event": event, "user_id": user_id,
            "actor_id": actor_id, "detail": json.dumps(detail) if detail else None,
            "ttl": int((now + timedelta(days=max(1, settings.auth_audit_retention_days))).timestamp()),
        }
        if user_id:
            item.update(g1pk=f"USER#{user_id}#AUDIT", g1sk=entry_id)
        if actor_id:
            item.update(g2pk=f"ACTOR#{actor_id}", g2sk=entry_id)
        self.table.put(item)

    def list_audit(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        cutoff = iso(utcnow() - timedelta(days=max(1, settings.auth_audit_retention_days)))
        if user_id:
            keys = list(self.table.query("g1pk", f"USER#{user_id}#AUDIT", index=self._g1, forward=False))
            actor_keys = list(self.table.query("g2pk", f"ACTOR#{user_id}", index=self._g2, forward=False))
            items = keys + self.table.batch_get([{"pk": k["pk"], "sk": k["sk"]} for k in actor_keys])
            unique = {i["sk"]: i for i in items}
            rows = sorted(unique.values(), key=lambda i: i["sk"], reverse=True)
        else:
            rows = []
            month = utcnow().replace(day=1)
            oldest = cutoff[:7]
            while month.strftime("%Y-%m") >= oldest and len(rows) < limit:
                for item in self.table.query("pk", f"AUDIT#{month.strftime('%Y-%m')}", forward=False):
                    rows.append(item)
                    if len(rows) >= limit:
                        break
                month = (month - timedelta(days=1)).replace(day=1)
        rows = [r for r in rows if r.get("at", "") >= cutoff][:limit]
        return [{"id": r["id"], "at": r["at"], "event": r["event"], "user_id": r.get("user_id"),
                 "actor_id": r.get("actor_id"), "detail": json.loads(r["detail"]) if r.get("detail") else None}
                for r in rows]
