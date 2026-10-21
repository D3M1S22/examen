# 🔐 03 — Auth and Ops Data Model (`examen-auth`, `examen-ops`)

> Implements `AuthStore` as `DynamoAuthStore` and `OpsStore` as `DynamoOpsStore` (phase P3). Both are service-wide: they use the **service role**, never the tenant role ([04](04_security_iam_and_tenancy.md)). Selected by `AUTH_STORE_BACKEND` and `OPS_STORE_BACKEND` ([05](05_infrastructure_and_configuration.md) §2).
> Notation as in [02](02_user_store_data_model.md) §3. TTL attribute: `ttl` (epoch seconds).

---

## 1. `examen-auth`

Keys: `pk` (S), `sk` (S). GSI1 `g1pk` / `g1sk` (ALL), GSI2 `g2pk` / `g2sk` (KEYS_ONLY).

### 1.1 Item types
| Entity | `pk` | `sk` | Index attributes | TTL |
|---|---|---|---|---|
| User | `USER#<id>` | `PROFILE` | `g1pk = USERS`, `g1sk = <created_at>#<id>` | — |
| Email guard | `EMAIL#<normalised email>` | `EMAIL` | — | — |
| Session | `SESSION#<sha256>` | `SESSION` | `g1pk = USER#<uid>#SESSION`, `g1sk = <created_at>` | `ttl = expires_at` |
| API token | `TOKEN#<sha256>` | `TOKEN` | `g1pk = USER#<uid>#TOKEN`, `g1sk = <created_at>#<id>` | — |
| Bee link | `BEE#<uid>` | `BEE` | — | — |
| Bee account guard | `BEEUSER#<bee_user_id>` | `BEEUSER` | — | — |
| Audit entry | `AUDIT#<yyyy-mm>` | `<at>#<seq>` | `g1pk = USER#<uid>#AUDIT` (if `user_id`), `g1sk = <at>#<seq>`; `g2pk = ACTOR#<actor_id>` (if `actor_id`) | `ttl = at + AUTH_AUDIT_RETENTION_DAYS` |

**Audit ids.** `<seq>` is a zero-padded `time_ns()` value. The integer `id` of SQLite becomes the string `<at>#<seq>`. `list_audit` returns it in the same field. The admin UI only displays it ([admin_console/04](../admin_console/04_api_ui_and_security.md)).

### 1.2 Methods
| Method | Access | Parity notes |
|---|---|---|
| `create_user` | **Tx**: `Put USER#id` (`attribute_not_exists(pk)`) + `Put EMAIL#e = {user_id}` (`attribute_not_exists(pk)`) | A cancelled Tx on the email guard raises `AuthError("An account with this email already exists.", 409)`, as the `UNIQUE` violation does today |
| `get_user` | Get | |
| `get_user_by_email` | Get `EMAIL#e`, then Get `USER#id` | |
| `list_users` / `count_users` | Qi(GSI1, `USERS`, ascending) / the same with `Select=COUNT` | Order by `created_at` |
| `count_admins` | Qi(GSI1, `USERS`) with filter `is_admin = 1`, `Select=COUNT` | |
| `ensure_bootstrap_admin` | Same logic over the methods above | |
| `set_admin`, `update_profile`, `record_consent`, `set_password`, `verify_user_password` | `UpdateItem` / Get on `USER#id` | `set_password` keeps `password_changed_at` |
| `set_status` | `UpdateItem`; when disabled, also `revoke_user_sessions` + `revoke_user_tokens` | |
| `authenticate` | Get by email (`dummy_verify` when missing: same timing defence), rehash `UpdateItem` if needed, `last_login_at` `UpdateItem` | |
| `delete_user` | (1) **Tx**: Delete `USER#id` + Delete `EMAIL#e`: login stops at once. (2) Sessions and tokens: Qi(GSI1) then batch delete. (3) Bee link and guard. (4) Own audit entries: Qi(GSI1 `USER#<uid>#AUDIT`) then delete. (5) `actor_id` cleared on entries where the user was the actor: Qi(GSI2 `ACTOR#uid`) then `UpdateItem REMOVE actor_id, g2pk, g2sk` | Not atomic after step 1. Every step is idempotent, and a retry finishes the job. Returns True if step 1 deleted the user |
| `create_session` | `PutItem` with `ttl` | The global `DELETE … WHERE expires_at < now` disappears (TTL) |
| `user_for_session` | Get. Expiry is checked in code (TTL deletion is lazy). Sliding renewal: `UpdateItem SET expires_at, last_seen_at, ttl` | |
| `revoke_session` | `DeleteItem` | |
| `revoke_user_sessions(uid, keep)` | Qi(GSI1 `USER#<uid>#SESSION`) then batch delete all but `keep`; returns the count | |
| `create_api_token` | `PutItem TOKEN#hash` | |
| `list_api_tokens` | Qi(GSI1 `USER#<uid>#TOKEN`, ascending) | Fields `id, name, prefix, created_at, last_used_at` |
| `revoke_user_tokens` / `revoke_api_token(uid, id)` | Qi(GSI1) then delete (all / the one with that `id`) | |
| `user_for_api_token` | Get `TOKEN#hash`, then `UpdateItem last_used_at`, then Get user | |
| `get_bee_link` | Get `BEE#uid`; a missing item gives `BeeLink(user_id=…)` (state `unlinked`), as today | |
| `find_bee_link(bee_user_id)` | Get `BEEUSER#id`, then Get `BEE#uid` | |
| `save_bee_link` | **Tx**: `Put BEE#uid`. When `bee_user_id` changes: `Put BEEUSER#new` (condition: not exists, or same `user_id`) + `Delete BEEUSER#old` | A guard conflict raises `UniqueConflict` on both backends (SQLite maps `IntegrityError` to it). The pairing flow already checks `find_bee_link` first |
| `delete_bee_link` | **Tx**: Delete `BEE#uid` + Delete `BEEUSER#id` | |
| `audit` | `PutItem` with `ttl` | The per-write purge disappears (TTL) |
| `list_audit(user_id, limit)` | With a user: Qi(GSI1 `USER#<uid>#AUDIT`, descending). Without: Q(`AUDIT#<month>`) descending, from the current month backwards, until `limit`. Entries older than the **current** retention are filtered out in code | Retention shortened at run time: the old TTLs stay longer, but the rows are hidden as SQLite would have deleted them |

## 2. `examen-ops`

Keys: `pk` (S), `sk` (S). GSI1 `g1pk` / `g1sk` (KEYS_ONLY): erasure by user and history listing. GSI2 `g2pk` / `g2sk` (ALL): incidents by fingerprint.

### 2.1 Service events and counters (D11)
| Item | `pk` | `sk` | Notes |
|---|---|---|---|
| Event | `EVENT` | `<id, 12-digit zero-padded>` | Same attributes as `service_events`. `ttl = at + SERVICE_LOG_RETENTION_DAYS`. `g1pk = USER#<uid>`, `g1sk = EVENT#<id>` when `user_id` is set |
| Event id counter | `META` | `COUNTER#event` | `insert_events(batch)` does one `UpdateItem ADD n` with `ReturnValues=UPDATED_NEW` and uses ids `[v-n+1 … v]` |
| Event count | `META` | `COUNT#event` | `ADD +n` on insert, `ADD -n` on purge; replaces `SELECT COUNT(*)` |

**Partition load.** One partition (`EVENT`) is fine at this volume. DynamoDB allows 1 000 WCU per second per partition; the service log writes a few events per minute.

| Method | Access | Parity notes |
|---|---|---|
| `insert_events` | Counter `ADD n`, then `BatchWriteItem` | Integer `id` kept: `before_id` pagination and `ServiceEvent.id?: number` in the UI stay unchanged |
| `list_events(level, component, code, user_id, since, until, q, fingerprint, before_id, limit)` | Q(`EVENT`, descending, `sk < pad(before_id)` if given) with `FilterExpression` for each filter. `q` uses `contains` on the message; then the exact `rules.sql_like` check in code. Pages until `limit` (≤ 500) | `level` keeps the "this level and above" set |
| `count_events` | Get `COUNT#event` | |
| `purge(event_days, max_events, incident_days, usage_days)` | Age: TTL. Cap: if the count exceeds `max_events`, Q(`EVENT`, ascending) deletes the oldest `info` events first, then the oldest of any level. Resolved incidents and usage: TTL plus an explicit sweep of the items TTL has not removed yet | The returned counts cover explicit deletions only (they feed a debug log line) |
| `vacuum_if_fragmented` | Returns False | Not applicable |
| `delete_user(uid)` | Qi(GSI1 `USER#<uid>`) then batch delete events, incidents and usage rows (count adjusted) | |

### 2.2 Incidents
| Item | `pk` | `sk` | Index |
|---|---|---|---|
| Incident | `INCIDENT` | `<id>` | `g2pk = FP#<fingerprint>`, `g2sk = <last_seen>`; `g1pk = USER#<uid>` if set; `ttl = resolved_at + incident_days` once resolved |

| Method | Access |
|---|---|
| `get_incident` | Get |
| `latest_incident(fp)` | Qi(GSI2 `FP#fp`, descending, limit 1), then Get (consistent: the health monitor decides from it) |
| `save_incident` | `PutItem` (upsert, like `ON CONFLICT(id) DO UPDATE`) |
| `list_incidents(status, severity, component, user_id, limit)` | Q(`INCIDENT`), filter in code (`active` = `open` or `acknowledged`), sort by `last_seen` descending, `limit` |

### 2.3 Runtime settings (D12)
| Item | `pk` | `sk` | Notes |
|---|---|---|---|
| Override | `SETTING` | `<key>` | `value_json`, `updated_at`, `updated_by` |
| Change set | `HIST#<change_id>` | `HIST` | `at`, `by_user`, `entries` = list of `{key, old_json, new_json, test_result, note}` in order. `g1pk = HIST`, `g1sk = <at>#<change_id>` |
| Version | `META` | `VERSION#settings` | Number |

| Method | Access | Parity notes |
|---|---|---|
| `list_overrides` | Q(`SETTING`) | |
| `settings_version` | Get | The 30 s sync of every instance reads this one item |
| `save_change_set(changes, old, by_user, …)` | **Tx**: one Put or Delete per key (≤ 80) + `Put HIST#cid` + `UpdateItem META ADD 1`. That is ≤ 82 items, under the 100-item limit | Atomic as today. The registry size is asserted in a test: more than 98 keys would need a different layout |
| `list_history(limit)` | Qi(GSI1 `HIST`, descending, limit), then BG | Rows expanded from `entries`, with `id` = position in the change set (the old autoincrement `id` is not used by callers) |
| `get_change_set(cid)` | Get `HIST#cid`, entries expanded | |

### 2.4 Token usage
| Item | `pk` | `sk` | Notes |
|---|---|---|---|
| Usage row | `USAGE#<yyyy-mm-dd>` (from `hour`) | `<hour>#<provider>#<model_id>#<role>#<user_id>` | Counters `calls`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`. `ttl = hour + TOKEN_USAGE_RETENTION_DAYS`. `g1pk = USER#<uid>` if `user_id` |
| First hour | `META` | `USAGE#first_hour` | Set with `if_not_exists` |

| Method | Access | Parity notes |
|---|---|---|
| `add_token_usage(rows)` | **Tx** of `UpdateItem ADD` (≤ 100 rows each; one flush is far below). If a later chunk fails, raises `PartialWrite(remaining=…)` | **`token_usage.flush` changes**: on `PartialWrite` it puts back only `remaining`. Putting back everything would double-count the chunks already written |
| `token_usage_summary(since)` | Q(`USAGE#<day>`) for each day from `since` to today (≤ 31 queries), filter `hour >= since`, aggregate in Python: `totals`, `by_model` with `roles`, `by_user`, hourly `series` | `tracking_since = max(first_hour, now - retention)`: what `MIN(hour)` returns after a purge |

## 3. Who uses which role
| Store | Role | Reason |
|---|---|---|
| `examen-auth` | Service role (API / worker) | Login happens before a tenant exists |
| `examen-ops` | Service role. The AgentCore runtime also gets **write-only** access to `USAGE#*` and the `META` counters | AgentCore records its own token usage directly: the "remote token counts" item of doc 15 §3 goes away |
