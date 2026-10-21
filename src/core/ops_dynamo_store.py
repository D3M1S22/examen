"""DynamoDB implementation of the operations store (docs/next_steps/dynamodb_storage/03 §2).

Same public methods and return shapes as ``OpsStore``. Service events keep integer ids from an atomic
counter, so ``before_id`` pagination is unchanged (D11); a settings change set is one item (D12).
Nothing here holds user content (events are sanitised upstream).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.core.ops_store import LEVELS, OpsStore, iso, utcnow
from src.core.storage import rules
from src.core.storage.dynamo_io import DynamoTable, Expr, PartialWrite
from src.core.storage.dynamo_schema import INDEX, OPS, table_name

_EVENT_COLUMNS = ("ref", "at", "level", "code", "component", "user_id", "message", "fingerprint", "context_json",
                  "error_type", "location")
_INCIDENT_COLUMNS = ("id", "fingerprint", "code", "component", "severity", "title", "user_id", "status", "count",
                     "first_seen", "last_seen", "resolved_at", "ack_by", "change_id", "details_json")
_INTERNAL = ("pk", "sk", "g1pk", "g1sk", "g2pk", "g2sk", "ttl")


def _epoch(at_iso: str, days: float) -> int:
    try:
        base = datetime.fromisoformat(at_iso)
    except (TypeError, ValueError):
        base = utcnow()
    return int((base + timedelta(days=days)).timestamp())


def _pad(event_id: int) -> str:
    return f"{int(event_id):012d}"


def _clean(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if k not in _INTERNAL}


class DynamoOpsStore(OpsStore):
    """``examen-ops``: one table, partitions EVENT / INCIDENT / SETTING / HIST#… / USAGE#<day> / META."""

    def __init__(self, client_getter=None, table: Optional[str] = None):
        from src.core.storage import dynamo_client

        self.db_path = None
        self._lock = threading.Lock()
        self.table = DynamoTable(client_getter or dynamo_client.service_client, table or table_name(OPS))
        self._g1, self._g2 = INDEX[OPS]["g1"], INDEX[OPS]["g2"]

    def _conn(self):  # pragma: no cover - guards against an inherited SQLite method
        raise NotImplementedError("DynamoOpsStore has no SQLite connection")

    def _init_db(self) -> None:
        return None

    # ------------------------------------------------------------------
    # Counters
    # ------------------------------------------------------------------
    def _add(self, sk: str, amount: int) -> int:
        attrs = self.table.update({"pk": "META", "sk": sk}, add={"value": amount}, return_values="UPDATED_NEW")
        return int((attrs or {}).get("value", 0))

    # ------------------------------------------------------------------
    # Service events
    # ------------------------------------------------------------------
    def insert_events(self, events: Iterable[Dict[str, Any]]) -> None:
        from src.core.config import settings

        events = list(events)
        if not events:
            return
        last = self._add("COUNTER#event", len(events))
        items = []
        for offset, e in enumerate(events):
            event_id = last - len(events) + 1 + offset
            row = {
                "id": event_id, "ref": e["ref"], "at": e["at"], "level": e["level"], "code": e["code"],
                "component": e["component"], "user_id": e.get("user_id"), "message": e["message"],
                "fingerprint": e["fingerprint"], "context_json": json.dumps(e["context"]) if e.get("context") else None,
                "error_type": e.get("error_type"), "location": e.get("location"),
            }
            item = {"pk": "EVENT", "sk": _pad(event_id), **row,
                    "ttl": _epoch(e["at"], max(1.0, float(settings.service_log_retention_days)))}
            if e.get("user_id"):
                item.update(g1pk=f"USER#{e['user_id']}", g1sk=f"EVENT#{_pad(event_id)}")
            items.append(item)
        self.table.batch_write(puts=items)
        self._add("COUNT#event", len(items))

    @staticmethod
    def _event(item: Dict[str, Any]) -> Dict[str, Any]:
        out = {"id": int(item["id"]), **{c: item.get(c) for c in _EVENT_COLUMNS}}
        out["context"] = json.loads(out.pop("context_json")) if out.get("context_json") else {}
        return out

    def list_events(self, *, level: Optional[str] = None, component: Optional[str] = None,
                    code: Optional[str] = None, user_id: Optional[str] = None, since: Optional[str] = None,
                    until: Optional[str] = None, q: Optional[str] = None, fingerprint: Optional[str] = None,
                    before_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        allowed = {name for name, value in LEVELS.items() if value >= LEVELS[level]} if level in LEVELS else None
        e = Expr()
        clauses = []
        for column, value in (("component", component), ("code", code), ("user_id", user_id),
                              ("fingerprint", fingerprint)):
            if value:
                clauses.append(f"{e.name(column)} = {e.value(value)}")
        if since:
            clauses.append(f"{e.name('at')} >= {e.value(since)}")
        if until:
            clauses.append(f"{e.name('at')} <= {e.value(until)}")
        pattern = f"%{q}%" if q else None  # message LIKE: applied in code (contains() is case-sensitive)
        kwargs: Dict[str, Any] = {"forward": False, "expr": e, "filter_expr": " AND ".join(clauses) or None}
        if before_id:
            kwargs.update(sk_attr="sk", lt=_pad(before_id))
        out = []
        for item in self.table.query("pk", "EVENT", **kwargs):
            if allowed is not None and item.get("level") not in allowed:
                continue
            if pattern and not rules.sql_like(item.get("message"), pattern):
                continue
            out.append(self._event(item))
            if len(out) >= limit:
                break
        return out

    def count_events(self) -> int:
        item = self.table.get({"pk": "META", "sk": "COUNT#event"})
        return int(item["value"]) if item else 0

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------
    @staticmethod
    def _incident(item: Dict[str, Any]) -> Dict[str, Any]:
        out = {c: item.get(c) for c in _INCIDENT_COLUMNS}
        out["details"] = json.loads(out.pop("details_json")) if out.get("details_json") else {}
        return out

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        item = self.table.get({"pk": "INCIDENT", "sk": incident_id})
        return self._incident(item) if item else None

    def latest_incident(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        for key in self.table.query("g2pk", f"FP#{fingerprint}", index=self._g2, sk_attr="g2sk", forward=False,
                                    page_size=5):
            item = self.table.get({"pk": "INCIDENT", "sk": key["sk"]})
            if item:
                return self._incident(item)
        return None

    def save_incident(self, inc: Dict[str, Any]) -> Dict[str, Any]:
        from src.core.config import settings

        existing = self.table.get({"pk": "INCIDENT", "sk": inc["id"]})
        row = {
            "id": inc["id"], "fingerprint": inc["fingerprint"], "code": inc["code"], "component": inc["component"],
            "severity": inc["severity"], "title": inc["title"], "user_id": inc.get("user_id"),
            "status": inc["status"], "count": inc["count"], "first_seen": inc["first_seen"],
            "last_seen": inc["last_seen"], "resolved_at": inc.get("resolved_at"), "ack_by": inc.get("ack_by"),
            "change_id": inc.get("change_id"),
            "details_json": json.dumps(inc["details"]) if inc.get("details") else None,
        }
        if existing:  # ON CONFLICT(id) keeps the identity columns of the first insert
            for column in ("fingerprint", "code", "component", "user_id", "first_seen"):
                row[column] = existing.get(column)
        item = {"pk": "INCIDENT", "sk": inc["id"], **row, "g2pk": f"FP#{row['fingerprint']}", "g2sk": row["last_seen"]}
        if row.get("user_id"):
            item.update(g1pk=f"USER#{row['user_id']}", g1sk=f"INCIDENT#{inc['id']}")
        if row["status"] == "resolved" and row.get("resolved_at"):
            item["ttl"] = _epoch(row["resolved_at"], float(getattr(settings, "incident_retention_days", 90) or 90))
        self.table.put(item)
        return inc

    def list_incidents(self, *, status: Optional[str] = None, severity: Optional[str] = None,
                       component: Optional[str] = None, user_id: Optional[str] = None,
                       limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        for item in self.table.query("pk", "INCIDENT"):
            if status == "active" and item.get("status") not in ("open", "acknowledged"):
                continue
            if status and status not in ("active", "all") and item.get("status") != status:
                continue
            if severity and item.get("severity") != severity:
                continue
            if component and item.get("component") != component:
                continue
            if user_id and item.get("user_id") != user_id:
                continue
            rows.append(item)
        rows.sort(key=lambda i: i.get("last_seen") or "", reverse=True)
        return [self._incident(i) for i in rows[:max(1, min(int(limit), 500))]]

    # ------------------------------------------------------------------
    # Retention and erasure
    # ------------------------------------------------------------------
    def _delete_events(self, items: List[Dict[str, Any]]) -> int:
        if not items:
            return 0
        self.table.batch_write(deletes=[{"pk": "EVENT", "sk": i["sk"]} for i in items])
        self._add("COUNT#event", -len(items))
        return len(items)

    def purge(self, *, event_days: float, max_events: int = 50_000, incident_days: float = 90,
              usage_days: float = 90) -> Dict[str, int]:
        now = utcnow()
        cutoff = iso(now - timedelta(days=event_days))
        with self._lock:
            old = []
            for item in self.table.query("pk", "EVENT", attributes=["sk", "at"]):
                if (item.get("at") or "") >= cutoff:
                    break  # ids grow with time
                old.append(item)
            events = self._delete_events(old)
            total = self.count_events()
            if total > max_events:
                extra = total - max_events
                infos = []
                for item in self.table.query("pk", "EVENT", attributes=["sk", "level"]):
                    if item.get("level") == "info":
                        infos.append(item)
                        if len(infos) >= extra:
                            break
                events += self._delete_events(infos)
                total = self.count_events()
                if total > max_events:
                    oldest = []
                    for item in self.table.query("pk", "EVENT", attributes=["sk"]):
                        oldest.append(item)
                        if len(oldest) >= total - max_events:
                            break
                    events += self._delete_events(oldest)
            incident_cutoff = iso(now - timedelta(days=incident_days))
            stale = [i for i in self.table.query("pk", "INCIDENT", attributes=["sk", "status", "resolved_at"])
                     if i.get("status") == "resolved" and i.get("resolved_at") and i["resolved_at"] < incident_cutoff]
            self.table.batch_write(deletes=[{"pk": "INCIDENT", "sk": i["sk"]} for i in stale])
            usage_cutoff = iso(now - timedelta(days=usage_days))
            usage = self._purge_usage(usage_cutoff, now)
        return {"events": events, "incidents": len(stale), "token_usage": usage}

    def _purge_usage(self, cutoff: str, now: datetime) -> int:
        first = self.table.get({"pk": "META", "sk": "USAGE#first_hour"})
        if not first:
            return 0
        start = datetime.fromisoformat(first["value"]).date()
        doomed: List[Tuple[str, str]] = []
        day = start
        while day.isoformat() <= cutoff[:10]:
            for item in self.table.query("pk", f"USAGE#{day.isoformat()}", attributes=["pk", "sk", "hour"]):
                if (item.get("hour") or "") < cutoff:
                    doomed.append((item["pk"], item["sk"]))
            day += timedelta(days=1)
        self.table.batch_write(deletes=[{"pk": p, "sk": s} for p, s in doomed])
        if doomed:  # keep "tracking since" equal to the oldest hour still stored
            self.table.update({"pk": "META", "sk": "USAGE#first_hour"}, set_={"value": max(first["value"], cutoff)})
        return len(doomed)

    def vacuum_if_fragmented(self, ratio: float = 0.2) -> bool:
        return False

    def delete_user(self, user_id: str) -> None:
        """Account erasure: the user's events, incidents and usage rows go with the account."""
        keys = list(self.table.query("g1pk", f"USER#{user_id}", index=self._g1))
        events = [k for k in keys if k["pk"] == "EVENT"]
        self.table.batch_write(deletes=[{"pk": k["pk"], "sk": k["sk"]} for k in keys])
        if events:
            self._add("COUNT#event", -len(events))

    # ------------------------------------------------------------------
    # Token usage
    # ------------------------------------------------------------------
    def add_token_usage(self, rows: Iterable[Dict[str, Any]]) -> None:
        """One transaction per 100 rows; raises ``PartialWrite`` with the rows not written."""
        from src.core.config import settings

        rows = [r for r in rows]
        if not rows:
            return
        retention = float(getattr(settings, "token_usage_retention_days", 90) or 90)
        first_hour = min(r["hour"] for r in rows)
        self.table.update({"pk": "META", "sk": "USAGE#first_hour"}, set_if_absent={"value": first_hour})
        for start in range(0, len(rows), 100):
            chunk = rows[start:start + 100]
            ops = []
            for r in chunk:
                user = r.get("user_id") or ""
                e = Expr()
                sets = [f"{e.name(k)} = if_not_exists({e.name(k)}, {e.value(r[k])})"
                        for k in ("hour", "provider", "model_id", "role")]
                sets.append(f"{e.name('user_id')} = if_not_exists({e.name('user_id')}, {e.value(user)})")
                sets.append(f"{e.name('ttl')} = {e.value(_epoch(r['hour'], retention))}")
                if user:
                    sets.append(f"{e.name('g1pk')} = {e.value(f'USER#{user}')}")
                    sets.append(f"{e.name('g1sk')} = {e.value('USAGE#' + r['hour'])}")
                adds = ", ".join(f"{e.name(f)} {e.value(int(r.get(f, 0) or 0))}" for f in self._USAGE_FIELDS)
                key = {"pk": f"USAGE#{r['hour'][:10]}",
                       "sk": f"{r['hour']}#{r['provider']}#{r['model_id']}#{r['role']}#{user}"}
                ops.append(self.table.tx_update(key, f"SET {', '.join(sets)} ADD {adds}", e))
            try:
                self.table.transact(ops)
            except Exception as err:
                raise PartialWrite(f"token usage write failed: {type(err).__name__}", rows[start:]) from err

    def token_usage_summary(self, since: Optional[str] = None) -> Dict[str, Any]:
        """Totals since ``since`` (UTC ISO hour), by model (with roles), by user and per hour."""
        first_item = self.table.get({"pk": "META", "sk": "USAGE#first_hour"})
        first = first_item["value"] if first_item else None  # MIN(hour) of the stored rows
        start = since or first
        rows: List[Dict[str, Any]] = []
        if start:
            day = datetime.fromisoformat(start).date()
            today = utcnow().date()
            while day <= today:
                for item in self.table.query("pk", f"USAGE#{day.isoformat()}"):
                    if since and (item.get("hour") or "") < since:
                        continue
                    rows.append(item)
                day += timedelta(days=1)
        zero = dict.fromkeys(self._USAGE_FIELDS, 0)
        totals = dict(zero)
        models: Dict[Tuple[str, str], Dict[str, Any]] = {}
        users: Dict[str, Dict[str, Any]] = {}
        hours: Dict[str, Dict[str, int]] = {}
        for item in rows:
            counts = {f: int(item.get(f) or 0) for f in self._USAGE_FIELDS}
            for f in self._USAGE_FIELDS:
                totals[f] += counts[f]
            entry = models.setdefault((item["provider"], item["model_id"]), {
                "provider": item["provider"], "model_id": item["model_id"], "roles": {}, **zero})
            role = entry["roles"].setdefault(item["role"], dict(zero))
            for f in self._USAGE_FIELDS:
                role[f] += counts[f]
                entry[f] += counts[f]
            user = users.setdefault(item.get("user_id") or "", {"user_id": item.get("user_id") or "", **zero})
            for f in self._USAGE_FIELDS:
                user[f] += counts[f]
            hour = hours.setdefault(item["hour"], {"tokens": 0, "calls": 0})
            hour["tokens"] += counts["input_tokens"] + counts["output_tokens"]
            hour["calls"] += counts["calls"]
        return {
            "totals": totals,
            "by_model": sorted(models.values(), key=lambda m: -(m["input_tokens"] + m["output_tokens"])),
            "by_user": sorted(users.values(), key=lambda u: -(u["input_tokens"] + u["output_tokens"])),
            "series": [{"hour": h, **v} for h, v in sorted(hours.items())],
            "tracking_since": first,
        }

    # ------------------------------------------------------------------
    # Runtime settings overrides
    # ------------------------------------------------------------------
    def list_overrides(self) -> Dict[str, Dict[str, Any]]:
        return {i["sk"]: {"value": json.loads(i["value_json"]), "updated_at": i["updated_at"],
                          "updated_by": i["updated_by"]} for i in self.table.query("pk", "SETTING")}

    def settings_version(self) -> int:
        item = self.table.get({"pk": "META", "sk": "VERSION#settings"})
        return int(item["value"]) if item else 0

    def save_change_set(self, changes: Dict[str, Any], old: Dict[str, Any], by_user: str,
                        test_result: Optional[Dict[str, Any]] = None, note: Optional[str] = None) -> str:
        """One transaction: overrides (value None = removed), the change-set item, version bump."""
        if len(changes) > 98:
            raise ValueError("a settings change set holds at most 98 keys (DynamoDB transaction limit)")
        change_id = f"chg_{uuid.uuid4().hex[:12]}"
        now = iso(utcnow())
        ops = []
        entries = []
        for key, value in changes.items():
            if value is None:
                ops.append(self.table.tx_delete({"pk": "SETTING", "sk": key}))
            else:
                ops.append(self.table.tx_put({"pk": "SETTING", "sk": key, "value_json": json.dumps(value),
                                              "updated_at": now, "updated_by": by_user}))
            entries.append({"key": key, "old_json": None if old.get(key) is None else json.dumps(old[key]),
                            "new_json": None if value is None else json.dumps(value)})
        ops.append(self.table.tx_put({
            "pk": f"HIST#{change_id}", "sk": "HIST", "change_id": change_id, "at": now, "by_user": by_user,
            "test_result": json.dumps(test_result) if test_result else None, "note": note,
            "entries": json.dumps(entries), "g1pk": "HIST", "g1sk": f"{now}#{time.time_ns():020d}#{change_id}",
        }))
        e = Expr()
        ops.append(self.table.tx_update({"pk": "META", "sk": "VERSION#settings"},
                                        f"ADD {e.name('value')} {e.value(1)}", e))
        with self._lock:
            self.table.transact(ops)
        return change_id

    @staticmethod
    def _entries(item: Dict[str, Any]) -> List[Dict[str, Any]]:
        return json.loads(item.get("entries") or "[]")

    def list_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Change sets, newest first, each with its keys."""
        keys = []
        for key in self.table.query("g1pk", "HIST", index=self._g1, sk_attr="g1sk", forward=False):
            keys.append({"pk": key["pk"], "sk": key["sk"]})
            if len(keys) >= max(1, min(limit, 200)):
                break
        out = []
        for item in self.table.batch_get(keys):
            out.append({
                "change_id": item["change_id"], "at": item["at"], "by_user": item["by_user"], "note": item.get("note"),
                "test_result": json.loads(item["test_result"]) if item.get("test_result") else None,
                "changes": [{"key": r["key"],
                             "old": json.loads(r["old_json"]) if r["old_json"] is not None else None,
                             "new": json.loads(r["new_json"]) if r["new_json"] is not None else None}
                            for r in self._entries(item)],
            })
        return out

    def get_change_set(self, change_id: str) -> List[Dict[str, Any]]:
        item = self.table.get({"pk": f"HIST#{change_id}", "sk": "HIST"})
        if not item:
            return []
        return [{"key": r["key"], "old": json.loads(r["old_json"]) if r["old_json"] is not None else None,
                 "new": json.loads(r["new_json"]) if r["new_json"] is not None else None, "at": item["at"]}
                for r in self._entries(item)]
