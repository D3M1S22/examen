# 🧱 02 — Per-user Store Data Model (`examen-user`)

> Implements `AbstractContextStore` as `DynamoContextStore` in `src/core/storage/dynamo_store.py`. One instance per tenant, like the SQLite store. Every read of the user's data goes through a client whose credentials can touch only `pk = <user_id>` ([04](04_security_iam_and_tenancy.md)).

---

## 1. Table

| Property | Value |
|---|---|
| Name | `${DYNAMO_TABLE_PREFIX}user` (default `examen-user`) |
| Keys | `pk` (S) = user id (`usr_` + 32 hex; `_local` in single-user mode), `sk` (S) = `<ENTITY>#…` |
| GSI1 `timeline` | `g1pk` / `g1sk`, projection **ALL**: small items listed by time (actions, ledger) |
| GSI2 `timeline_keys` | `g2pk` / `g2sk`, projection **INCLUDE** (`status`, `final_status`, `kind`, `session_id`, `ingest_source`, `ingest_run_id`, `start_time`, `last_updated_at`, `created_at`): large items listed by time (briefings, dossiers) |
| GSI3 `group_keys` | `g3pk` / `g3sk`, same INCLUDE projection: briefings by event, dossiers by state |
| TTL attribute | `ttl` (epoch seconds; the same name in all three tables, because `expires_at` is already an ISO column of auth sessions) |
| Streams | `NEW_AND_OLD_IMAGES`, enabled but unused in this project |

Every GSI partition key starts with `<user_id>#`. The tenant policy (`LeadingKeys` ∈ {`<uid>`, `<uid>#*`}) therefore covers base-table and index queries alike.

Projections are chosen for **cost**. A 25 KB dossier rewritten on every utterance would cost 25 WRU more per index under ALL. Under INCLUDE it costs about 1. Listings of large items read keys from the index, then fetch full items with `BatchGetItem` (consistent).

## 2. Item types

The `sk` prefix identifies the entity. The attributes are the SQLite columns of that table (D5), plus the key and index attributes listed here.

| Entity (SQLite table) | `sk` | Index attributes | Notes |
|---|---|---|---|
| Planned task (`planned_tasks`) | `TASK#<id>` | — | Small collection: queried by prefix, filtered and sorted in code |
| Verified action (`verified_actions`) | `ACTION#<id>` | `g1pk = <uid>#ACTION`, `g1sk = <timestamp>#<id>` | |
| Social contact (`social_contacts`) | `CONTACT#<id>` | — | |
| Contact name guard | `CONTACTNAME#<lower(trim(name))>` | — | `{contact_id}`: replaces `WHERE LOWER(person_name) = LOWER(?)` and the duplicate purge at start-up |
| Commitment (`social_commitments`) | `COMMIT#<id>` | — | |
| Commitment guard | `COMMITKEY#<sha256(lower contact ∣ lower description ∣ debtor)>` | — | `{commitment_id}`: the dedup key of `save_social_commitment` |
| Briefing (`topic_briefings`) | `BRIEF#<id>` | `g2pk = <uid>#BRIEF`, `g2sk = <created_at>#<id>`; if `session_id`: `g3pk = <uid>#SESSION#<session_id>`, `g3sk = <created_at>#<id>` | Up to 25 KB |
| Diarization (`utterance_diarization`) | `DIAR#<chunk_id>` | — | Write-only today |
| Dossier / event (`session_dossiers`) | `DOSSIER#<session_id>` | `g2pk = <uid>#DOSSIER`, `g2sk = <start_time>#<sid>`; `g3pk = <uid>#DSTATE#<state>`, `g3sk = <last_updated_at>#<sid>` | `state` ∈ `open` · `pending_final` · `closed` (§3.4). Internal `version` (D8) |
| Chunk (`session_chunks`) | `CHUNK#<session_id>#<ts>#<seq>` | — | `seq` = `time_ns()` of the first insert (zero-padded), replaces SQLite's `rowid` tie-break and is kept on moves |
| Chunk pointer | `CHUNKREF#<chunk_id>` | — | `{session_id, chunk_sk}`: lets `assign_chunks` and idempotent appends find a chunk by id |
| Web search cache (`web_search_cache`) | `CACHE#<sha256(query_norm)>` | — | `query_norm` kept as an attribute; `ttl = fetched_at + WEB_SEARCH_CACHE_TTL_SECONDS` |
| Coverage (`ingest_coverage`) | `COV#<id>` | — | Small collection |
| Ledger (`ingest_ledger`) | `LEDGER#<source_key>` | `g1pk = <uid>#LEDGER`, `g1sk = <ledger_time>#<source_key>` | `ledger_time = received_at or ts` (stored, replaces `COALESCE`) |
| Bee conversation (`bee_conversation_map`) | `BEECONV#<uuid>` | — | |
| Bee conversation by id | `BEECONVID#<id>` | — | `{uuid}`: replaces `WHERE id = ?` |
| Backfill run (`backfill_runs`) | `RUN#<id>` | — | `payload_json` as today |
| Telemetry (`system_telemetry`) | `TEL#<timestamp>#<uuid8>` | — | `ttl` = +30 days (new, D10). `id` becomes the uuid |

**Key components.** A component that is not the last in a key (the session id inside `CHUNK#…`) must not contain `#`. Engine session ids are UUIDs. Any other value is replaced by `h_<sha256[:32]>` and the original is kept as an attribute. A helper `key_part()` enforces this, and a test covers it.

## 3. Access patterns, method by method

Notation:
- **Get** = `GetItem`, consistent;
- **Q(prefix)** = base-table `Query` on `pk` with `begins_with(sk, prefix)`, consistent;
- **Qi(GSIn, pk, range, order)** = index `Query`, eventually consistent;
- **BG** = `BatchGetItem`, consistent;
- **Tx** = `TransactWriteItems`.

"In code" means the filter, sort or limit runs in Python over the results, with the same predicate as the SQLite `WHERE` / `ORDER BY`.

`LIKE` in code is `rules.sql_like(value, pattern)`. It reproduces SQLite's default `LIKE`: ASCII-only case-insensitive, `%` and `_` wildcards, and `NULL` never matches. Plain `str.lower()` / `in` would differ for accented capitals and for user queries that contain `_`.

### 3.1 Planned tasks
| Method | Access | Parity notes |
|---|---|---|
| `save_planned_task` | `PutItem` | `INSERT OR REPLACE` semantics; `title` stripped |
| `get_planned_task` | Get `TASK#id` | |
| `list_planned_tasks(status, domain, origin, ingest_source)` | Q(`TASK#`), filter in code | Sort `(scheduled_time is not None, scheduled_time, created_at)`: SQLite sorts NULL first |
| `complete_planned_task` | `UpdateItem` SET status, completed_at, verified_action_id, condition `attribute_exists(sk)` | Returns False on a failed condition (= `rowcount 0`) |
| `update_planned_task` | `UpdateItem` of the 13 updatable columns, same condition | Does not touch `ingest_*`, `source_key`, `recovered`, `created_at` (as today) |
| `delete_planned_task` | `DeleteItem` `ReturnValues=ALL_OLD` | True if something was deleted |
| `match_and_resolve_task` | `list_planned_tasks(status="pending")`, then `rules.action_matches_task`; the commitment update uses Q(`COMMIT#`) filtered on `auto_scheduled_task_id` | Logic shared through `rules.py` (D7) |

### 3.2 Actions
| Method | Access | Parity notes |
|---|---|---|
| `save_action` | Matching as today, then `PutItem` | `action_type` lowercased |
| `get_verified_action` | Get `ACTION#id` | |
| `get_action_status(query, target_date)` | Candidate A: Get `ACTION#<query>`. Candidate B: Qi(GSI1, `<uid>#ACTION`, `begins_with(g1sk, target_date)` if given, descending), first item with `is_revoked = 0` matching `LIKE` in code, paging until found | Returns the newer of A and B, like `ORDER BY timestamp DESC LIMIT 1` over the `OR` |
| `list_recent_actions(limit, domain, ingest_source)` | Qi(GSI1, `<uid>#ACTION`, descending) with `FilterExpression` (`is_revoked`, `domain`, `ingest_source`), paging until `limit` | `domain == "all"` means no filter |

### 3.3 Contacts and commitments
| Method | Access | Parity notes |
|---|---|---|
| `save_social_contact` | Without an id: Get `CONTACTNAME#<name>` → id. Commitments saved first (unchanged loop). Get the stored contact for `web_profile_json` / `website_url` preservation. Then **Tx**: `Put CONTACT#id` + `Put CONTACTNAME#<name> = id` | The guard always points to the latest contact saved with that name. A renamed contact moves its guard (Delete old + Put new in the same Tx) |
| `get_social_contact(id_or_name)` | Get `CONTACT#<target>` and Get `CONTACTNAME#<lower target>` → Get contact; the newer `timestamp` wins. Commitments from `list_social_commitments(contact_name=…)`, fallback to `commitments_json` | |
| `update_contact_web_profile` | Resolve by id (UUID) or name guard, then `UpdateItem SET web_profile_json = :p, website_url = if_not_exists(website_url, :u)` | `COALESCE(website_url, ?)` |
| `search_social_contact(q)` | Q(`CONTACT#`), `LIKE` on lower `person_name`, `company_or_role`, `key_topics_json`; sort `timestamp` descending | |
| `save_social_commitment` | Get `COMMITKEY#k` → existing id, inheriting task and `created_at`. **Tx**: `Put COMMIT#id` + `Put COMMITKEY#k` (condition: not exists, or same id). Then the auto task: `save_planned_task`, then `UpdateItem COMMIT#id SET auto_scheduled_task_id` with condition `attribute_not_exists(auto_scheduled_task_id)`. If that fails, delete the new task | A concurrent creator of the same commitment loses the guard condition, re-reads and reuses the existing id. No duplicate task |
| `get_social_commitment` | Get | |
| `list_social_commitments(contact_name, debtor, status, limit)` | Q(`COMMIT#`), filter in code, `created_at` descending, `limit` | |
| `update_social_commitment_status` | Get, then `UpdateItem SET status`, then cascade (complete or cancel the task) | |
| `delete_social_commitment` | Get, then **Tx** `Delete COMMIT#id` + `Delete COMMITKEY#k`, then delete the task | The SQLite version leaves no guard, so nothing to mirror |

### 3.4 Briefings, dossiers and chunks
Dossier state for GSI3, computed on every write:
- `open`: `status ∈ {active, paused}` and `segments_json` is set;
- `pending_final`: `status = concluded` and `final_status ∈ {pending, synthesizing}`;
- `closed`: everything else.

| Method | Access | Parity notes |
|---|---|---|
| `save_topic_briefing` | `PutItem` with index attributes | |
| `get_topic_briefing(query)` | No query: Qi(GSI2, `<uid>#BRIEF`, descending, limit 1) → Get. With query: Get `BRIEF#<query>` first (exact id wins, like `ORDER BY (id = ?) DESC`). Else page Qi(GSI2) descending in pages of 100 keys → BG → first `LIKE` match on title, markdown or synthesis | Early stop: matches are usually recent. Cost bound noted in §8 |
| `list_topic_briefings(limit, kind, session_id)` | With `session_id`: Qi(GSI3, `<uid>#SESSION#sid`, descending). Else Qi(GSI2, `<uid>#BRIEF`, descending). Filter `kind` on the projection, take `limit` keys → BG | |
| `list_briefings_for_session` | Qi(GSI3, `<uid>#SESSION#sid`, ascending) → BG | |
| `delete_topic_briefing` | `DeleteItem ALL_OLD` | No FTS clean-up needed |
| `reassign_briefings(ids, sid)` | `UpdateItem` per id: SET `session_id`, `g3pk`, `g3sk` | |
| `patch_utterance_speaker` | `PutItem DIAR#chunk_id` | Returns True |
| `save_session_dossier(d)` | If chunks exist for the event (Q(`CHUNK#sid#`, limit 1)), `transcript_chunks_json` is not written. `PutItem` with `version = v + 1`, conditional on the version read (D8, §6) | `created_at = start_time`, as today |
| `get_session_dossier(sid, include_chunks=True)` | Get `DOSSIER#sid`. Without sid: Qi(GSI3) on the three state partitions (descending, limit 1 each) → newest `last_updated_at` → Get. Chunks: Q(`CHUNK#sid#`, descending, limit 200), reversed; fallback to `transcript_chunks_json`. Final briefing: Get | `include_chunks=False` is new on both backends (for the engine's `_save`) |
| `list_session_dossiers(status, limit, ingest_source, ingest_run_id)` | Qi(GSI2, `<uid>#DOSSIER`, descending by `start_time`), filter on the projection, `limit` keys → BG | |
| `get_open_event(ingest_source, run_id)` | Qi(GSI3, `<uid>#DSTATE#open`, descending), filter `COALESCE(ingest_source,'live')` and `run_id` → Get each candidate (consistent) and **confirm** the state; first confirmed wins | Confirm-on-read guards against index lag (§4) |
| `list_events_pending_final(limit, ingest_source, run_id)` | Qi(GSI3, `<uid>#DSTATE#pending_final`, ascending), filter → BG → confirm | |
| `append_session_chunk(chunk, sid, seg, on_topic)` | Get `CHUNKREF#cid`. New chunk: Tx `Put CHUNK#…` + `Put CHUNKREF`. Same event: `Put` the same key (replace). Other event: Tx `Delete` old + `Put` new + `Put CHUNKREF` | Idempotent on `chunk_id`, like `INSERT OR REPLACE` |
| `list_session_chunks(sid, segment_id, in_segments_only, limit)` | Q(`CHUNK#sid#`, ascending) with `FilterExpression` on `segment_id`, paging until `limit` | Order `ts, seq` = `ts, rowid` |
| `get_chunk_segments(sid)` | Q(`CHUNK#sid#`) with projection `chunk_id, segment_id` | |
| `assign_chunks(ids, sid, seg, on_topic)` | BG the pointers. Same event: `UpdateItem` `segment_id` / `on_topic`. Other event: Tx `Delete` + `Put` + `Put CHUNKREF`, ≤ 33 chunks per Tx | **Not atomic** across more than 33 chunks; every step is idempotent, and a retry completes the move |
| `delete_session_dossier` | `DeleteItem ALL_OLD` | The dossier only, as today |
| `append_chunk_to_session`, `link_micro_event_to_session`, `conclude_session_dossier` | Same logic as SQLite. `link_micro_event_to_session` does Get, adds the ref, then `UpdateItem SET linked_micro_events_json, last_updated_at, version = version + 1` conditional on the version read, retrying up to 5 times | Only the micro-event attributes change, as today |

### 3.5 Cache, telemetry
| Method | Access | Parity notes |
|---|---|---|
| `get_cached_search(q, max_age)` | Get `CACHE#h`; age check in code | Items past `ttl` are ignored |
| `put_cached_search` | `PutItem` with `ttl` | |
| `record_latency` | `PutItem TEL#…`; never raises (as today) | |
| `get_latency_metrics(event_type, limit)` | Q(`TEL#`, descending) with filter `event_type = :t` or `NOT begins_with(event_type, 'backfill')`, paging until `limit` → `rules.latency_summary` | |

### 3.6 Backfill bookkeeping
| Method | Access | Parity notes |
|---|---|---|
| `save_coverage_interval` | `PutItem COV#id` | |
| `list_coverage(start, end, source)` | Q(`COV#`), overlap filter in code (`end_ts >= start`, `start_ts <= end`), sort by `start_ts` | |
| `close_open_coverage_intervals(source)` | Q(`COV#`), filter `is_open = 1 ∧ source`, `UpdateItem` each; returns the count | |
| `last_coverage_end(source)` | Q(`COV#`), max `end_ts` in code | |
| `record_ingested_utterance` | `PutItem LEDGER#key` with `ledger_time`, `g1pk`, `g1sk` | |
| `get_ledger_entry` | Get | |
| `list_ledger_entries(t_from, t_to, source, status)` | Qi(GSI1, `<uid>#LEDGER`, `g1sk BETWEEN t_from AND t_to + "#￿"`), exact `FilterExpression` on `ledger_time`, `source`, `status`; ascending | Lexicographic order, like SQLite text comparison |
| `purge_ingest_ledger(before)` | Qi(GSI1, `g1sk < before`), exact filter, `BatchWriteItem` delete in batches of 25 (retrying unprocessed items); returns the count | Explicit purge kept (D10) |
| `map_bee_conversation(uuid, id)` | `UpdateItem BEECONV#uuid SET first_seen_at = if_not_exists(…)`, `id = :id` only when given; plus `Put BEECONVID#id` | `COALESCE(excluded.id, id)` |
| `get_bee_conversation_uuid(id)` | Get `BEECONVID#id` | |
| `save_backfill_run` / `get_backfill_run` | `PutItem` / Get `RUN#id` | |
| `list_backfill_runs(statuses, limit)` | Q(`RUN#`), filter, `created_at` descending, `limit` | |
| `purge_ingestion_history` | Q of `COV#`, `LEDGER#`, `BEECONV#`, `BEECONVID#`, `RUN#` (keys only) → batch delete | |

### 3.7 Whole partition
| Method | Access |
|---|---|
| `export_all` | Q(`pk`) over every item. Grouped by entity under the **SQLite table names**, with the SQLite columns only: key, index, guard, pointer and internal attributes (`version`, `ttl`, `ledger_time`) are dropped. Same JSON shape as today |
| `delete_all_data` (new on both backends) | Q(`pk`) keys only → batch delete, with retry and back-off. Used by GDPR erasure and `reset_db.py` |
| `close` | No-op (the boto3 client is shared) |

## 4. Consistency rules (D4)

1. **Base-table reads are strongly consistent.** All Get, Q and BG calls set `ConsistentRead=True`. Their cost is 2× an eventually consistent read, still cents per month.
2. **Index reads are eventually consistent** (DynamoDB does not offer anything else on a GSI). Propagation is usually under a second, but there is no guarantee. Index results are used only to **list** or to find **candidates**. A decision made from them (open event, pending final) confirms the candidate with a consistent Get.
3. **Read-after-write paths go through the base table:**
   - the chunks of an event live under the dossier's key range, not in an index;
   - guard items are looked up by Get;
   - the ledger is checked by `source_key` with a Get.
4. **Known window:** a listing (`list_session_dossiers`, `list_recent_actions`, ledger windows for backfill) can miss an item written in the last second. The UI refreshes on SSE events, and backfill works on windows that end well before "now", so this is accepted.

moto is strongly consistent everywhere, so tests do not reproduce rule 4. A unit test injects an index lag (a wrapper that hides the last write from index queries) for `get_open_event` and `list_events_pending_final`.

## 5. Encoding (D5)

- **Codec.** A `Codec` per entity, built from that table's SQLite column list (name → type): `str`, `int`, `float`, `flag` (0/1), `json` (string).
- **Writes:**
  - `None` is not written (the attribute is omitted);
  - floats are written as `Decimal(str(value))`;
  - `json` columns are stored exactly as the SQLite store serialises them (`json.dumps(…, ensure_ascii=False)`);
  - empty strings are allowed (non-key attributes).
- **Reads:** `Decimal` becomes `int` or `float` according to the column type. Missing attributes become `None`. The static row mappers of the SQLite store (`_row_to_planned_task`, `_row_to_action`, `_row_to_briefing`, `_row_to_coverage`, `_row_to_ledger`) are reused through a dict that behaves like `sqlite3.Row` (`keys()`, `[]`). They move to `rules.py` in P0. The dossier, contact and commitment mappers, which also read other tables, get a backend-neutral core there as well. The Pydantic conversion code is therefore shared, not rewritten.
- **Client.** `botocore` low-level client with `TypeSerializer` and `TypeDeserializer` (thread-safe, unlike `boto3.resource`), standard retry mode, `max_attempts = 8`.

## 6. Concurrency (D8)

| Writer pair | Risk | Mechanism |
|---|---|---|
| Event engine (worker) ↔ pipeline `link_micro_event_to_session` (AgentCore) | The engine rewrites the dossier from a stale copy and drops a link | `version` attribute. `SessionDossier` gets a Pydantic `PrivateAttr` `_store_version`, set by every read and write of the store and never serialised. `save_session_dossier` puts with `version = :v_read` (or `attribute_not_exists(sk)` when `_store_version` is 0). On `ConditionalCheckFailed` it re-reads, adds the persisted links that are missing from the given dossier (the merge `_save` already does), and retries up to 5 times |
| Two pipelines creating the same contact or commitment | Duplicates (SQLite purges them at start-up today) | Guard items with conditional `Put` inside a Tx |
| Two writers completing the same task | Double completion | `UpdateItem` is idempotent; last writer wins (as today) |
| Chunk move ↔ append | A chunk under two events | `CHUNKREF` pointer checked inside the same Tx (`ConditionCheck` on the pointer's `chunk_sk`) |

**As implemented** ([07](07_implementation_plan_and_testing.md) §0, V2–V3):
- The dossier is written with `UpdateItem` of every attribute, not `PutItem`. This preserves `link_versions_json`, which `link_micro_event_to_session` owns: it maps each link to the dossier version at which it was added.
- A conflicting save re-adds only the links added **after** the caller's version. Links the caller had seen and dropped (a manual split) stay dropped.
- The event engine adopts the stored version whenever it merges the persisted links (`_merge_persisted_links`, also before a split).

## 7. Retention (D10)

| Item | TTL | Explicit purge |
|---|---|---|
| `CACHE#` | `fetched_at + WEB_SEARCH_CACHE_TTL_SECONDS` | — |
| `TEL#` | 30 days (new: SQLite keeps telemetry forever) | — |
| `LEDGER#` | — | `purge_ingest_ledger(before)` (existing retention setting) |
| Everything else | — | GDPR erasure only |

TTL deletes in the background, usually within a few days of expiry. Reads that depend on freshness (`get_cached_search`) also check the age in code.

## 8. Size and cost guards

- **Item size.** If an encoded item exceeds 350 KB, its largest `*_json` or markdown attributes are compressed with zlib into a Binary attribute `<name>__z`, recorded in `compressed`, and decoded on read. Above 400 KB after compression, the write fails with `ItemTooLarge` (logged with the entity and id, never the content). The biggest item today is 25 KB.
- **Per-user scale limits** (acceptable at the current volumes; to revisit above about 1 000 items per collection):
  - collection reads of tasks, contacts, commitments, coverage and runs;
  - `get_topic_briefing(query)` paging through briefings (about 25 KB each) until the first match.
- **Write cost per utterance** ≈ 30 WRU:
  - ledger 1 + index 1;
  - chunk 1 + pointer 1;
  - dossier ≈ 25 (+ index projections ≈ 2).
- **Limits per request:** `BatchWriteItem` 25 items, `TransactWriteItems` 100 items or 4 MB, `BatchGetItem` 100 keys or 16 MB, Query pages 1 MB. Helpers in `dynamo_io.py` page and split everywhere.
