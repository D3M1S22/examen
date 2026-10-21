# 🔎 01 — Current State of Persistence

> Measured on the code of branch `aws` (2026-10-21) and on the homelab instance (CT 147). Line references point to the files as they are today.

---

## 1. The three stores

| Store | Class and file | Opened by | Tables | Public methods |
|---|---|---|---|---|
| Per-user context | `SQLiteContextStore`, [sqlite_store.py](../../../src/core/storage/sqlite_store.py) (2 059 lines) | `get_storage_store()` / `get_tenant_store(uid)` in [storage/__init__.py](../../../src/core/storage/__init__.py), one instance per tenant | 19 tables + 3 FTS5 tables | 60 (interface [base.py](../../../src/core/storage/base.py)) |
| Accounts | `AuthStore`, [auth/store.py](../../../src/core/auth/store.py) | `get_auth_store()` singleton | `users`, `sessions`, `api_tokens`, `bee_links`, `audit_log` | 32 |
| Service ops | `OpsStore`, [ops_store.py](../../../src/core/ops_store.py) | `get_ops_store()` singleton | `service_events`, `incidents`, `settings_overrides`, `settings_history`, `token_usage`, `ops_meta` | 17 |

`sqlite3` is imported only in these three modules (AGENTS.MD rule E). Two tests open a raw connection on the store for setup: [test_event_engine.py:424](../../../tests/test_event_engine.py#L424) and [test_event_synthesis.py:76](../../../tests/test_event_synthesis.py#L76). They must move to store methods or become SQLite-only.

The per-user store has **no `AbstractAuthStore` or `AbstractOpsStore` counterpart**. Those two classes are concrete, and callers import them directly. Phase P3 adds a small protocol for each ([07](07_implementation_plan_and_testing.md)).

## 2. Per-user store: tables and sizes

The busiest real user on CT 147 has a 7 MB file:

| Table | Rows | Largest row | Grows with |
|---|---|---|---|
| `session_chunks` | 4 575 | 6.4 KB | every utterance kept by an event |
| `ingest_ledger` | 4 696 | 0.5 KB | every utterance (noop included) |
| `system_telemetry` | 362 | 0.1 KB | every pipeline run (never purged) |
| `topic_briefings` | 46 | 25 KB | syntheses |
| `session_dossiers` | 15 | 24 KB | events |
| `planned_tasks` | 19 | 0.4 KB | tasks |
| `verified_actions` | 7 | 0.6 KB | actions |
| `social_contacts` | 5 | 2.8 KB | contacts |
| others (`social_commitments`, `utterance_diarization`, `web_search_cache`, `ingest_coverage`, `bee_conversation_map`, `backfill_runs`) | small | < 10 KB | — |

Every row is far below DynamoDB's 400 KB item limit. The large rows are the dossier JSON (`segments_json`, `research_ledger_json`, `transitions_json`) and the briefing markdown.

## 3. Logic that lives inside the store

The SQLite store is not a thin persistence layer. These methods contain domain rules that a second backend must reproduce exactly:

| Method | Rule |
|---|---|
| `save_action` → `match_and_resolve_task` | Keyword overlap (≥ 3-letter words minus a stop list) between the action text and pending task titles. Completes the first match, fulfils the linked commitment, and falls back to matching open user commitments (description words plus contact name). Backfill actions only resolve tasks they may resolve in time (`historical_action_may_resolve`) |
| `save_social_contact` | Dedup by `LOWER(person_name)`. Persists each structured commitment (dedup by description and debtor), keeps the stored `web_profile_json` / `website_url` when the incoming contact has none |
| `save_social_commitment` | Dedup by (`LOWER(contact_name)`, `LOWER(description)`, `debtor`), inheriting the existing `auto_scheduled_task_id` and `created_at`. **Creates a planned task** for an open user commitment without a task |
| `update_social_commitment_status` | `fulfilled` completes the linked task; `cancelled` cancels it |
| `delete_social_commitment` | Deletes the linked task |
| `get_social_contact` / `search_social_contact` | Assemble the commitments from `social_commitments` (fallback to `commitments_json`) and the web profile |
| `append_chunk_to_session`, `link_micro_event_to_session`, `conclude_session_dossier` | Create the dossier on demand. Refuse to grow a concluded session. `link_micro_event_to_session` updates only the micro-event column, because the event engine may be writing the dossier at the same time |
| `_row_to_session_dossier` | Loads the **last 200 chunks** of the event from `session_chunks` (fallback to the legacy JSON column) and the final briefing |
| `get_cached_search` | Age check against `fetched_at` (naive local time) |
| `get_latency_metrics` | Average, min and max of the last *N* samples; excludes `backfill*` when no type is given |
| `_init_db` | Deletes duplicate commitments and contacts at every start |

**Decision D7:** the pure parts move into `src/core/storage/rules.py` before the new store is written:
- `task_keywords(title)`;
- `action_matches_task(action_text, task)`;
- `commitment_matches_action(...)`;
- `commitment_key(contact, description, debtor)`;
- `contact_name_key(name)`;
- `latency_summary(values)`.

`SQLiteContextStore` calls them unchanged. The orchestration (which rows to read and write) stays per backend.

## 4. Full-text search is never used to search

`fts_actions`, `fts_social` and `fts_briefings` are filled on save. But every search method uses `LIKE`:

| Method | Query |
|---|---|
| `get_action_status` | `id = ? OR action_type LIKE ? OR raw_statement LIKE ?`, `is_revoked = 0`, optional `timestamp LIKE 'YYYY-MM-DD%'`, newest first, 1 row |
| `search_social_contact` | `LOWER(person_name)`, `LOWER(company_or_role)` or `LOWER(key_topics_json)` `LIKE`, newest first |
| `get_topic_briefing(query)` | `id = ?` first, else `LOWER(topic_title)`, `LOWER(deep_dive_markdown)` or `LOWER(explanatory_synthesis)` `LIKE`, newest first, 1 row |

The FTS tables matter only to `delete_topic_briefing` (index clean-up) and `export_all` (skipped). **The DynamoDB store therefore needs no search index**: the same `LIKE` predicates run in Python over the user's own collection (D6).

## 5. Interface drift

The abstract interface is narrower than what callers use. The SQLite implementation is the de facto contract:

| Method | `base.py` | `sqlite_store.py` (used by callers) |
|---|---|---|
| `list_planned_tasks` | `status, domain, origin` | + `ingest_source` |
| `list_recent_actions` | `limit, domain` | + `ingest_source` |
| `list_session_dossiers` | `status, limit` | + `ingest_source, ingest_run_id` |
| `get_session_dossier` | `session_id` | `session_id: Optional` (none → latest by `last_updated_at`) |

In addition, 37 methods are concrete in `base.py`: they `raise NotImplementedError` or return a dummy value instead of being abstract. A new backend that forgets one fails only at run time.

Phase P0 aligns `base.py` with the SQLite signatures and adds a contract test. The test checks that every public method of `SQLiteContextStore` exists on `DynamoContextStore` with the same signature.

## 6. Filesystem state outside the databases

| State | Where | Used by | With DynamoDB |
|---|---|---|---|
| Tenant list | `list_tenant_ids()` lists `users/*` folders ([tenancy.py](../../../src/core/tenancy.py)) | `start_paired_user_runtimes`, `_stream_snapshot` in [mcp_server.py](../../../src/serving/mcp_server.py) | Comes from the auth store (`list_users`) when the user store is `dynamo` (D18) |
| Bee token per user | `users/<id>/bee/token-<env>` (`tenant_bee_dir`) | `bee proxy` / CLI subprocesses, `tenant_has_bee_login` | **Unchanged**: stays on the worker's disk. Listed as a dependency for a fully stateless worker ([04](04_security_iam_and_tenancy.md) §6) |
| Erasure | `delete_tenant_data(uid)` removes the folder | `auth_routes` GDPR purge, `manage_users.py` | Plus `DynamoContextStore.delete_all_data()`; the folder is still removed for the Bee token |
| Disk health check | `health_monitor` checks `data_root()` | Health view | Unchanged (it still guards the Bee folders and the logs) |

## 7. Callers

There are about 245 call sites of store methods in `src/`, across the three stores. The busiest per-user methods:

| Method | Call sites |
|---|---|
| `save_backfill_run` | 13 |
| `get_session_dossier` | 10 |
| `list_session_chunks` | 8 |
| `list_backfill_runs` | 8 |
| `search_social_contact` | 7 |
| `list_planned_tasks` | 7 |
| `save_session_dossier` | 6 |
| `assign_chunks` | 6 |

The event engine's `_save()` ([event_engine.py:1450](../../../src/ingestion/event_engine.py#L1450)) reads the dossier, merges the persisted micro-event links, then writes the whole dossier. That read currently loads up to 200 chunks only to be discarded. The new store adds `get_session_dossier(..., include_chunks=False)` for this path (both backends).

## 8. Scripts

| Script | Depends on SQLite paths | Change |
|---|---|---|
| [reset_db.py](../../../scripts/reset_db.py) | `store.db_path`, file backup | For `dynamo`: `delete_all_data()` plus optional seed, no file backup |
| [manage_users.py](../../../scripts/manage_users.py) | `tenant_db_path`, imports a legacy `examen.db` | The import goes through the migration module ([06](06_migration_and_cutover.md)) |
| [live_tester.py](../../../scripts/live_tester.py) | prints and resets `store.db_path` | Print the backend and table instead |
| [populate_db.py](../../../scripts/populate_db.py) | store methods only | None |

## 9. Tests

- 15 test files touch the store. `test_storage.py`, `test_event_engine.py`, `test_backfill.py`, `test_event_synthesis.py` and `test_session_manager.py` build `SQLiteContextStore(tmp_path)` directly (125 tests).
- `conftest.py` resets the auth and ops singletons per test with a temporary data directory.
- `boto3` 1.43 is already a dependency. `moto` is not installed.

Phase P1 adds:
- a `make_store` fixture parametrised by backend (`EXAMEN_TEST_BACKENDS=sqlite,dynamo`, default both);
- an autouse fixture that reaches the auth and ops backends through the same switch.
