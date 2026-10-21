"""Operations store (``EXAMEN_DATA_DIR/ops.db``): service events, incidents and runtime settings overrides.

docs/next_steps/admin_console/02 §2 and 03 §2. Nothing here holds user content: events are sanitised
before they arrive (src/core/service_log.py), settings are instance-wide tunables, and secrets never
enter this database. ``auth.db`` stays limited to accounts and security.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.core.tenancy import data_root

LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class OpsStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            root = data_root()
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            db_path = str(root / "ops.db")
        else:
            Path(db_path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS service_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ref TEXT NOT NULL,
                    at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    code TEXT NOT NULL,
                    component TEXT NOT NULL,
                    user_id TEXT,
                    message TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    context_json TEXT,
                    error_type TEXT,
                    location TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_at ON service_events (at);
                CREATE INDEX IF NOT EXISTS idx_events_fp ON service_events (fingerprint, at);
                CREATE INDEX IF NOT EXISTS idx_events_user ON service_events (user_id);
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    code TEXT NOT NULL,
                    component TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    user_id TEXT,
                    status TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    resolved_at TEXT,
                    ack_by TEXT,
                    change_id TEXT,
                    details_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_incidents_fp ON incidents (fingerprint, status);
                CREATE INDEX IF NOT EXISTS idx_incidents_open ON incidents (status, last_seen);
                CREATE TABLE IF NOT EXISTS settings_overrides (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    change_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    old_json TEXT,
                    new_json TEXT,
                    at TEXT NOT NULL,
                    by_user TEXT NOT NULL,
                    test_result TEXT,
                    note TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_history_change ON settings_history (change_id);
                CREATE TABLE IF NOT EXISTS ops_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS token_usage (
                    hour TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    calls INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (hour, provider, model_id, role, user_id)
                );
                """
            )
        try:
            Path(self.db_path).chmod(0o600)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Service events
    # ------------------------------------------------------------------

    def insert_events(self, events: Iterable[Dict[str, Any]]) -> None:
        rows = [
            (e["ref"], e["at"], e["level"], e["code"], e["component"], e.get("user_id"), e["message"],
             e["fingerprint"], json.dumps(e["context"]) if e.get("context") else None, e.get("error_type"),
             e.get("location"))
            for e in events
        ]
        if not rows:
            return
        with self._lock, self._conn() as conn:
            conn.executemany(
                "INSERT INTO service_events (ref, at, level, code, component, user_id, message, fingerprint,"
                " context_json, error_type, location) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    @staticmethod
    def _event(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["context"] = json.loads(out.pop("context_json")) if out.get("context_json") else {}
        return out

    def list_events(self, *, level: Optional[str] = None, component: Optional[str] = None,
                    code: Optional[str] = None, user_id: Optional[str] = None, since: Optional[str] = None,
                    until: Optional[str] = None, q: Optional[str] = None, fingerprint: Optional[str] = None,
                    before_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        where, args = [], []
        if level and level in LEVELS:
            allowed = [name for name, value in LEVELS.items() if value >= LEVELS[level]]
            where.append(f"level IN ({','.join('?' * len(allowed))})")
            args += allowed
        for column, value in (("component", component), ("code", code), ("user_id", user_id),
                              ("fingerprint", fingerprint)):
            if value:
                where.append(f"{column} = ?")
                args.append(value)
        if since:
            where.append("at >= ?")
            args.append(since)
        if until:
            where.append("at <= ?")
            args.append(until)
        if q:
            where.append("message LIKE ?")
            args.append(f"%{q}%")
        if before_id:
            where.append("id < ?")
            args.append(before_id)
        sql = "SELECT * FROM service_events" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        with self._conn() as conn:
            return [self._event(r) for r in conn.execute(sql, args).fetchall()]

    def count_events(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM service_events").fetchone()[0])

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------

    @staticmethod
    def _incident(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        out["details"] = json.loads(out.pop("details_json")) if out.get("details_json") else {}
        return out

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return self._incident(row) if row else None

    def latest_incident(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM incidents WHERE fingerprint = ? ORDER BY last_seen DESC LIMIT 1",
                               (fingerprint,)).fetchone()
        return self._incident(row) if row else None

    def save_incident(self, inc: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO incidents (id, fingerprint, code, component, severity, title, user_id, status, count,"
                " first_seen, last_seen, resolved_at, ack_by, change_id, details_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET"
                " severity = excluded.severity, title = excluded.title, status = excluded.status,"
                " count = excluded.count, last_seen = excluded.last_seen, resolved_at = excluded.resolved_at,"
                " ack_by = excluded.ack_by, change_id = excluded.change_id, details_json = excluded.details_json",
                (inc["id"], inc["fingerprint"], inc["code"], inc["component"], inc["severity"], inc["title"],
                 inc.get("user_id"), inc["status"], inc["count"], inc["first_seen"], inc["last_seen"],
                 inc.get("resolved_at"), inc.get("ack_by"), inc.get("change_id"),
                 json.dumps(inc["details"]) if inc.get("details") else None),
            )
        return inc

    def list_incidents(self, *, status: Optional[str] = None, severity: Optional[str] = None,
                       component: Optional[str] = None, user_id: Optional[str] = None,
                       limit: int = 200) -> List[Dict[str, Any]]:
        where, args = [], []
        if status == "active":
            where.append("status IN ('open', 'acknowledged')")
        elif status and status != "all":
            where.append("status = ?")
            args.append(status)
        for column, value in (("severity", severity), ("component", component), ("user_id", user_id)):
            if value:
                where.append(f"{column} = ?")
                args.append(value)
        sql = "SELECT * FROM incidents" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY last_seen DESC LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        with self._conn() as conn:
            return [self._incident(r) for r in conn.execute(sql, args).fetchall()]

    # ------------------------------------------------------------------
    # Retention and erasure
    # ------------------------------------------------------------------

    def purge(self, *, event_days: float, max_events: int = 50_000, incident_days: float = 90,
              usage_days: float = 90) -> Dict[str, int]:
        now = utcnow()
        with self._lock, self._conn() as conn:
            events = conn.execute("DELETE FROM service_events WHERE at < ?",
                                  (iso(now - timedelta(days=event_days)),)).rowcount
            total = int(conn.execute("SELECT COUNT(*) FROM service_events").fetchone()[0])
            if total > max_events:
                # Oldest info events first, then the oldest of any level
                extra = total - max_events
                events += conn.execute(
                    "DELETE FROM service_events WHERE id IN (SELECT id FROM service_events WHERE level = 'info'"
                    " ORDER BY id LIMIT ?)", (extra,)).rowcount
                total = int(conn.execute("SELECT COUNT(*) FROM service_events").fetchone()[0])
                if total > max_events:
                    events += conn.execute(
                        "DELETE FROM service_events WHERE id IN (SELECT id FROM service_events ORDER BY id LIMIT ?)",
                        (total - max_events,)).rowcount
            incidents = conn.execute("DELETE FROM incidents WHERE status = 'resolved' AND resolved_at < ?",
                                     (iso(now - timedelta(days=incident_days)),)).rowcount
            usage = conn.execute("DELETE FROM token_usage WHERE hour < ?",
                                 (iso(now - timedelta(days=usage_days)),)).rowcount
        return {"events": events, "incidents": incidents, "token_usage": usage}

    def vacuum_if_fragmented(self, ratio: float = 0.2) -> bool:
        with self._lock, self._conn() as conn:
            pages = conn.execute("PRAGMA page_count").fetchone()[0] or 1
            free = conn.execute("PRAGMA freelist_count").fetchone()[0]
            if free / pages < ratio:
                return False
            conn.execute("VACUUM")
            return True

    def delete_user(self, user_id: str) -> None:
        """Account erasure: the user's events and incidents go with the account."""
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM service_events WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM incidents WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM token_usage WHERE user_id = ?", (user_id,))

    # ------------------------------------------------------------------
    # Token usage (03 §8): hourly totals per provider, model, role and user
    # ------------------------------------------------------------------

    _USAGE_FIELDS = ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")

    def add_token_usage(self, rows: Iterable[Dict[str, Any]]) -> None:
        values = [(r["hour"], r["provider"], r["model_id"], r["role"], r.get("user_id") or "",
                   *(int(r.get(f, 0) or 0) for f in self._USAGE_FIELDS)) for r in rows]
        if not values:
            return
        updates = ", ".join(f"{f} = {f} + excluded.{f}" for f in self._USAGE_FIELDS)
        with self._lock, self._conn() as conn:
            conn.executemany(
                "INSERT INTO token_usage (hour, provider, model_id, role, user_id, " + ", ".join(self._USAGE_FIELDS)
                + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(hour, provider, model_id, role, user_id)"
                " DO UPDATE SET " + updates, values)

    def token_usage_summary(self, since: Optional[str] = None) -> Dict[str, Any]:
        """Totals since ``since`` (UTC ISO hour), by model (with roles), by user and per hour."""
        where, args = ("WHERE hour >= ?", [since]) if since else ("", [])
        sums = ", ".join(f"SUM({f}) AS {f}" for f in self._USAGE_FIELDS)
        with self._conn() as conn:
            total = dict(conn.execute(f"SELECT {sums} FROM token_usage {where}", args).fetchone())
            by_model_role = [dict(r) for r in conn.execute(
                f"SELECT provider, model_id, role, {sums} FROM token_usage {where} "
                "GROUP BY provider, model_id, role", args).fetchall()]
            by_user = [dict(r) for r in conn.execute(
                f"SELECT user_id, {sums} FROM token_usage {where} GROUP BY user_id", args).fetchall()]
            series = [dict(r) for r in conn.execute(
                f"SELECT hour, SUM(input_tokens + output_tokens) AS tokens, SUM(calls) AS calls "
                f"FROM token_usage {where} GROUP BY hour ORDER BY hour", args).fetchall()]
            first = conn.execute("SELECT MIN(hour) FROM token_usage").fetchone()[0]

        def clean(row: Dict[str, Any]) -> Dict[str, Any]:
            """SUM() is NULL on an empty range: counters become 0."""
            return {**row, **{f: int(row.get(f) or 0) for f in self._USAGE_FIELDS}}

        models: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for row in by_model_role:
            row = clean(row)
            entry = models.setdefault((row["provider"], row["model_id"]), {
                "provider": row["provider"], "model_id": row["model_id"], "roles": {},
                **dict.fromkeys(self._USAGE_FIELDS, 0)})
            entry["roles"][row["role"]] = {f: row[f] for f in self._USAGE_FIELDS}
            for f in self._USAGE_FIELDS:
                entry[f] += row[f]
        return {
            "totals": clean(total),
            "by_model": sorted(models.values(), key=lambda m: -(m["input_tokens"] + m["output_tokens"])),
            "by_user": sorted((clean(r) for r in by_user), key=lambda u: -(u["input_tokens"] + u["output_tokens"])),
            "series": [{"hour": r["hour"], "tokens": int(r["tokens"] or 0), "calls": int(r["calls"] or 0)}
                       for r in series],
            "tracking_since": first,
        }

    # ------------------------------------------------------------------
    # Runtime settings overrides
    # ------------------------------------------------------------------

    def list_overrides(self) -> Dict[str, Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM settings_overrides").fetchall()
        return {r["key"]: {"value": json.loads(r["value_json"]), "updated_at": r["updated_at"],
                           "updated_by": r["updated_by"]} for r in rows}

    def settings_version(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM ops_meta WHERE key = 'settings_version'").fetchone()
        return int(row["value"]) if row else 0

    def save_change_set(self, changes: Dict[str, Any], old: Dict[str, Any], by_user: str,
                        test_result: Optional[Dict[str, Any]] = None, note: Optional[str] = None) -> str:
        """One transaction: overrides (value None = removed), history rows, version bump."""
        change_id = f"chg_{uuid.uuid4().hex[:12]}"
        now = iso(utcnow())
        with self._lock, self._conn() as conn:
            for key, value in changes.items():
                if value is None:
                    conn.execute("DELETE FROM settings_overrides WHERE key = ?", (key,))
                else:
                    conn.execute(
                        "INSERT INTO settings_overrides (key, value_json, updated_at, updated_by) VALUES (?, ?, ?, ?)"
                        " ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,"
                        " updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                        (key, json.dumps(value), now, by_user))
                conn.execute(
                    "INSERT INTO settings_history (change_id, key, old_json, new_json, at, by_user, test_result, note)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (change_id, key, None if old.get(key) is None else json.dumps(old[key]),
                     None if value is None else json.dumps(value), now, by_user,
                     json.dumps(test_result) if test_result else None, note))
            version = conn.execute("SELECT value FROM ops_meta WHERE key = 'settings_version'").fetchone()
            conn.execute("INSERT INTO ops_meta (key, value) VALUES ('settings_version', ?) ON CONFLICT(key)"
                         " DO UPDATE SET value = excluded.value", (str(int(version["value"]) + 1 if version else 1),))
        return change_id

    def list_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Change sets, newest first, each with its keys."""
        with self._conn() as conn:
            ids = [r["change_id"] for r in conn.execute(
                "SELECT change_id, MAX(id) AS last FROM settings_history GROUP BY change_id ORDER BY last DESC LIMIT ?",
                (max(1, min(limit, 200)),)).fetchall()]
            out = []
            for change_id in ids:
                rows = conn.execute("SELECT * FROM settings_history WHERE change_id = ? ORDER BY id",
                                    (change_id,)).fetchall()
                first = rows[0]
                out.append({
                    "change_id": change_id, "at": first["at"], "by_user": first["by_user"], "note": first["note"],
                    "test_result": json.loads(first["test_result"]) if first["test_result"] else None,
                    "changes": [{"key": r["key"],
                                 "old": json.loads(r["old_json"]) if r["old_json"] is not None else None,
                                 "new": json.loads(r["new_json"]) if r["new_json"] is not None else None}
                                for r in rows],
                })
        return out

    def get_change_set(self, change_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM settings_history WHERE change_id = ? ORDER BY id",
                                (change_id,)).fetchall()
        return [{"key": r["key"], "old": json.loads(r["old_json"]) if r["old_json"] is not None else None,
                 "new": json.loads(r["new_json"]) if r["new_json"] is not None else None, "at": r["at"]}
                for r in rows]


_ops_store: Optional[OpsStore] = None
_ops_lock = threading.Lock()


def get_ops_store() -> OpsStore:
    global _ops_store
    with _ops_lock:
        if _ops_store is None:
            from src.core.config import settings

            if settings.ops_store_backend == "dynamo":
                from src.core.ops_dynamo_store import DynamoOpsStore

                _ops_store = DynamoOpsStore()
            else:
                _ops_store = OpsStore()
        return _ops_store


def reset_ops_store(store: Optional[OpsStore] = None) -> None:
    """Test seam: replace (or forget) the process-wide store."""
    global _ops_store
    with _ops_lock:
        _ops_store = store
