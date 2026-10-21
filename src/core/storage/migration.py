"""One-shot SQLite → DynamoDB copy (docs/next_steps/dynamodb_storage/06).

Items are built directly from the SQLite rows (the store's save methods would re-run domain rules
such as task matching and commitment scheduling). Every write is a ``PutItem`` of a deterministic key,
so running the copy twice gives the same result. Reports hold counts only, never user content.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.core.storage import rules
from src.core.storage.dynamo_schema import key_part
from src.core.storage.dynamo_store import COLUMNS, PREFIX_TABLE, DynamoContextStore, dossier_state

_TABLE_PREFIX = {table: prefix for prefix, table in PREFIX_TABLE.items()}


def read_sqlite(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Every data table of a SQLite file, read-only, in rowid order (``_rowid`` added)."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND sql NOT LIKE '%VIRTUAL TABLE%'").fetchall()]
        out = {}
        for name in names:
            if name.startswith("fts_"):
                continue
            rows = conn.execute(f'SELECT rowid AS _rowid, * FROM "{name}" ORDER BY rowid').fetchall()
            out[name] = [dict(r) for r in rows]
        return out
    finally:
        conn.close()


def _row(table: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    return {c: raw.get(c) for c in COLUMNS[table]}


def user_items(store: DynamoContextStore, tables: Dict[str, List[Dict[str, Any]]],
               telemetry_ttl_days: int = 30) -> List[Dict[str, Any]]:
    """The DynamoDB items (data, index, guard and pointer items) of one user's SQLite tables."""
    items: List[Dict[str, Any]] = []
    for raw in tables.get("planned_tasks", []):
        items.append(store._item(f"TASK#{raw['id']}", _row("planned_tasks", raw)))
    for raw in tables.get("verified_actions", []):
        row = _row("verified_actions", raw)
        items.append(store._item(f"ACTION#{row['id']}", row, g1pk=store._gpk("ACTION"),
                                 g1sk=f"{row['timestamp']}#{row['id']}"))
    names: Dict[str, str] = {}
    for raw in tables.get("social_contacts", []):  # SQLite keeps the newest row per name
        row = _row("social_contacts", raw)
        items.append(store._item(f"CONTACT#{row['id']}", row))
        if rules.contact_name_key(row["person_name"]):
            names[rules.contact_name_key(row["person_name"])] = row["id"]
    items += [store._item(f"CONTACTNAME#{k}", {"contact_id": v}) for k, v in names.items()]
    commit_keys: Dict[str, str] = {}
    for raw in tables.get("social_commitments", []):  # SQLite keeps the earliest row per key
        row = _row("social_commitments", raw)
        items.append(store._item(f"COMMIT#{row['id']}", row))
        commit_keys.setdefault(rules.commitment_key(row["contact_name"], row["description"], row["debtor"]), row["id"])
    items += [store._item(f"COMMITKEY#{k}", {"commitment_id": v}) for k, v in commit_keys.items()]
    for raw in tables.get("topic_briefings", []):
        row = _row("topic_briefings", raw)
        items.append(store._item(f"BRIEF#{row['id']}", row,
                                 **store._briefing_index(row["id"], row["created_at"], row.get("session_id"))))
    for raw in tables.get("utterance_diarization", []):
        items.append(store._item(f"DIAR#{raw['chunk_id']}", _row("utterance_diarization", raw)))
    for raw in tables.get("session_dossiers", []):
        row = _row("session_dossiers", raw)
        sid = key_part(row["session_id"])
        items.append(store._item(
            f"DOSSIER#{row['session_id']}", row, version=1,
            g2pk=store._gpk("DOSSIER"), g2sk=f"{row['start_time']}#{sid}",
            g3pk=store._gpk(f"DSTATE#{dossier_state(row)}"), g3sk=f"{row['last_updated_at']}#{sid}",
        ))
    for raw in tables.get("session_chunks", []):
        row = _row("session_chunks", raw)
        seq = int(raw["_rowid"])  # SQLite orders ties on ts by rowid
        chunk_sk = store._chunk_sk(row["session_id"], row["ts"], seq)
        items.append(store._item(chunk_sk, row, seq=seq))
        items.append(store._item(f"CHUNKREF#{row['chunk_id']}", {"chunk_sk": chunk_sk, "seq": seq,
                                                                 "session_id": row["session_id"]}))
    from src.core.config import settings

    cache_ttl_days = max(1, settings.web_search_cache_ttl_seconds) / 86400
    for raw in tables.get("web_search_cache", []):
        row = _row("web_search_cache", raw)
        items.append(store._item(store._cache_sk(row["query_norm"]), row,
                                 ttl=_epoch(row.get("fetched_at"), cache_ttl_days)))
    for raw in tables.get("ingest_coverage", []):
        items.append(store._item(f"COV#{raw['id']}", _row("ingest_coverage", raw)))
    for raw in tables.get("ingest_ledger", []):
        row = _row("ingest_ledger", raw)
        lt = row["received_at"] if row.get("received_at") is not None else row["ts"]
        items.append(store._item(f"LEDGER#{row['source_key']}", row, ledger_time=lt, g1pk=store._gpk("LEDGER"),
                                 g1sk=f"{lt}#{row['source_key']}"))
    for raw in tables.get("bee_conversation_map", []):
        row = _row("bee_conversation_map", raw)
        items.append(store._item(f"BEECONV#{row['uuid']}", row))
        if row.get("id") is not None:
            items.append(store._item(f"BEECONVID#{int(row['id'])}", {"uuid": row["uuid"]}))
    for raw in tables.get("backfill_runs", []):
        items.append(store._item(f"RUN#{raw['id']}", _row("backfill_runs", raw)))
    cutoff = (datetime.now() - timedelta(days=telemetry_ttl_days)).isoformat()
    for raw in tables.get("system_telemetry", []):
        row = _row("system_telemetry", raw)
        if (row.get("timestamp") or "") < cutoff:
            continue  # beyond the telemetry TTL: the DynamoDB store would already have expired it
        rec_id = uuid.uuid5(uuid.NAMESPACE_URL, f"telemetry:{raw['_rowid']}").hex
        row["id"] = rec_id
        items.append(store._item(f"TEL#{row['timestamp']}#{rec_id[:8]}", row,
                                 ttl=_epoch(row["timestamp"], telemetry_ttl_days)))
    return items


def _epoch(at: Optional[str], days: float) -> int:
    try:
        base = datetime.fromisoformat(at) if at else datetime.now()
    except ValueError:
        base = datetime.now()
    return int((base + timedelta(days=days)).timestamp())


def expected_counts(tables: Dict[str, List[Dict[str, Any]]], telemetry_ttl_days: int = 30) -> Dict[str, int]:
    counts = {t: len(rows) for t, rows in tables.items() if t in COLUMNS and rows}
    if "system_telemetry" in counts:
        cutoff = (datetime.now() - timedelta(days=telemetry_ttl_days)).isoformat()
        counts["system_telemetry"] = sum(1 for r in tables["system_telemetry"] if (r.get("timestamp") or "") >= cutoff)
        if not counts["system_telemetry"]:
            del counts["system_telemetry"]
    return counts


def stored_counts(store: DynamoContextStore) -> Dict[str, int]:
    counts: Counter = Counter()
    for item in store.table.query("pk", store.user_id, attributes=["sk"]):
        table = PREFIX_TABLE.get(item["sk"].split("#", 1)[0])
        if table:
            counts[table] += 1
    return dict(counts)


def migrate_user(user_id: Optional[str], sqlite_path: str, dry_run: bool = False,
                 store: Optional[DynamoContextStore] = None) -> Dict[str, Any]:
    """Copies one SQLite file into the user's partition; returns the per-table counts and their check."""
    from src.core.config import settings

    store = store or DynamoContextStore(user_id=user_id)
    tables = read_sqlite(sqlite_path)
    items = user_items(store, tables, settings.dynamo_telemetry_ttl_days)
    expected = expected_counts(tables, settings.dynamo_telemetry_ttl_days)
    if not dry_run:
        store.table.batch_write(puts=items)
    stored = stored_counts(store) if not dry_run else {}
    return {"items": len(items), "expected": expected, "stored": stored,
            "ok": dry_run or all(stored.get(t, 0) >= n for t, n in expected.items())}


def copy_partition(source_table: str, target: DynamoContextStore) -> int:
    """Restore path (05 §7): copies one user's partition from a PITR-restored table."""
    from src.core.storage.dynamo_io import DynamoTable

    source = DynamoTable(lambda: target.table.client, source_table)
    items = list(source.query("pk", target.user_id))
    target.table.batch_write(puts=items)
    return len(items)


# ---------------------------------------------------------------------------
# Accounts and ops
# ---------------------------------------------------------------------------

def migrate_auth(sqlite_path: str, dry_run: bool = False, store: Any = None) -> Dict[str, int]:
    from src.core.auth.dynamo_store import DynamoAuthStore
    from src.core.auth.store import iso, utcnow
    from src.core.config import settings

    store = store or DynamoAuthStore()
    tables = read_sqlite(sqlite_path)
    now = iso(utcnow())
    cutoff = iso(utcnow() - timedelta(days=max(1, settings.auth_audit_retention_days)))
    items: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    for u in tables.get("users", []):
        user = {k: v for k, v in u.items() if k != "_rowid"}
        items.append({"pk": f"USER#{user['id']}", "sk": "PROFILE", **user, "g1pk": "USERS",
                      "g1sk": f"{user['created_at']}#{user['id']}"})
        items.append({"pk": f"EMAIL#{user['email']}", "sk": "EMAIL", "user_id": user["id"]})
        counts["users"] += 1
    for s in tables.get("sessions", []):
        if s["expires_at"] < now:
            continue
        items.append({"pk": f"SESSION#{s['token_hash']}", "sk": "SESSION", "token_hash": s["token_hash"],
                      "user_id": s["user_id"], "created_at": s["created_at"], "expires_at": s["expires_at"],
                      "last_seen_at": s.get("last_seen_at"), "ttl": int(datetime.fromisoformat(s["expires_at"]).timestamp()),
                      "g1pk": f"USER#{s['user_id']}#SESSION", "g1sk": f"{s['created_at']}#{s['token_hash'][:16]}"})
        counts["sessions"] += 1
    for t in tables.get("api_tokens", []):
        items.append({"pk": f"TOKEN#{t['token_hash']}", "sk": "TOKEN", "id": t["id"], "user_id": t["user_id"],
                      "name": t["name"], "prefix": t["prefix"], "created_at": t["created_at"],
                      "last_used_at": t.get("last_used_at"), "g1pk": f"USER#{t['user_id']}#TOKEN",
                      "g1sk": f"{t['created_at']}#{t['id']}"})
        counts["api_tokens"] += 1
    for b in tables.get("bee_links", []):
        link = {k: v for k, v in b.items() if k != "_rowid"}
        items.append({"pk": f"BEE#{link['user_id']}", "sk": "BEE", **link})
        if link.get("bee_user_id") is not None:
            items.append({"pk": f"BEEUSER#{int(link['bee_user_id'])}", "sk": "BEEUSER", "user_id": link["user_id"]})
        counts["bee_links"] += 1
    for a in tables.get("audit_log", []):
        if a["at"] < cutoff:
            continue
        entry_id = f"{a['at']}#{int(a['id']):020d}"
        item = {"pk": f"AUDIT#{a['at'][:7]}", "sk": entry_id, "id": entry_id, "at": a["at"], "event": a["event"],
                "user_id": a.get("user_id"), "actor_id": a.get("actor_id"), "detail": a.get("detail"),
                "ttl": int((datetime.fromisoformat(a["at"]) + timedelta(days=settings.auth_audit_retention_days)).timestamp())}
        if a.get("user_id"):
            item.update(g1pk=f"USER#{a['user_id']}#AUDIT", g1sk=entry_id)
        if a.get("actor_id"):
            item.update(g2pk=f"ACTOR#{a['actor_id']}", g2sk=entry_id)
        items.append(item)
        counts["audit_log"] += 1
    if not dry_run:
        store.table.batch_write(puts=items)
    return dict(counts)


def migrate_ops(sqlite_path: str, dry_run: bool = False, skip_events: bool = False,
                store: Any = None) -> Dict[str, int]:
    from src.core.config import settings
    from src.core.ops_dynamo_store import DynamoOpsStore, _epoch as ops_epoch, _pad

    store = store or DynamoOpsStore()
    tables = read_sqlite(sqlite_path)
    items: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    for o in tables.get("settings_overrides", []):
        items.append({"pk": "SETTING", "sk": o["key"], "value_json": o["value_json"], "updated_at": o["updated_at"],
                      "updated_by": o["updated_by"]})
        counts["settings_overrides"] += 1
    sets: Dict[str, List[Dict[str, Any]]] = {}
    for h in tables.get("settings_history", []):
        sets.setdefault(h["change_id"], []).append(h)
    for change_id, rows in sets.items():
        first = rows[0]
        items.append({"pk": f"HIST#{change_id}", "sk": "HIST", "change_id": change_id, "at": first["at"],
                      "by_user": first["by_user"], "test_result": first.get("test_result"), "note": first.get("note"),
                      "entries": json.dumps([{"key": r["key"], "old_json": r["old_json"], "new_json": r["new_json"]}
                                             for r in rows]),
                      "g1pk": "HIST", "g1sk": f"{first['at']}#{int(rows[-1]['id']):020d}#{change_id}"})
        counts["settings_history"] += 1
    for m in tables.get("ops_meta", []):
        if m["key"] == "settings_version":
            items.append({"pk": "META", "sk": "VERSION#settings", "value": int(m["value"])})
    for inc in tables.get("incidents", []):
        row = {k: v for k, v in inc.items() if k != "_rowid"}
        item = {"pk": "INCIDENT", "sk": row["id"], **row, "g2pk": f"FP#{row['fingerprint']}", "g2sk": row["last_seen"]}
        if row.get("user_id"):
            item.update(g1pk=f"USER#{row['user_id']}", g1sk=f"INCIDENT#{row['id']}")
        items.append(item)
        counts["incidents"] += 1
    hours = []
    for u in tables.get("token_usage", []):
        row = {k: v for k, v in u.items() if k != "_rowid"}
        user = row.get("user_id") or ""
        item = {"pk": f"USAGE#{row['hour'][:10]}",
                "sk": f"{row['hour']}#{row['provider']}#{row['model_id']}#{row['role']}#{user}", **row,
                "ttl": ops_epoch(row["hour"], float(settings.token_usage_retention_days))}
        if user:
            item.update(g1pk=f"USER#{user}", g1sk=f"USAGE#{row['hour']}")
        items.append(item)
        hours.append(row["hour"])
        counts["token_usage"] += 1
    if hours:
        items.append({"pk": "META", "sk": "USAGE#first_hour", "value": min(hours)})
    if not skip_events:
        events = tables.get("service_events", [])
        for e in events:
            row = {k: v for k, v in e.items() if k != "_rowid"}
            item = {"pk": "EVENT", "sk": _pad(row["id"]), **row,
                    "ttl": ops_epoch(row["at"], float(settings.service_log_retention_days))}
            if row.get("user_id"):
                item.update(g1pk=f"USER#{row['user_id']}", g1sk=f"EVENT#{_pad(row['id'])}")
            items.append(item)
        if events:
            items.append({"pk": "META", "sk": "COUNTER#event", "value": max(int(e["id"]) for e in events)})
            items.append({"pk": "META", "sk": "COUNT#event", "value": len(events)})
        counts["service_events"] = len(events)
    if not dry_run:
        store.table.batch_write(puts=items)
    return dict(counts)
