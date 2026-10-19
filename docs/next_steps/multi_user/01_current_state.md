# 01 — Current State: What Is Single-Tenant Today

> Part of the [Multi-User Support](00_overview.md) specification. Audit of branch `sessions` at `390699b` (2026-10-19).

---

## 1. Summary

| Layer | Today | Consequence with several real users |
|---|---|---|
| Dashboard login | Demo profiles in an in-memory dict, identity = client-chosen `user_id` | Anyone can act as anyone; profiles vanish on restart |
| Authorisation | None on REST, SSE or `/mcp` | Every caller reads and writes every record |
| Bee account | One token per host user (`~/.bee`) | All profiles share one Bee account; any profile can re-pair or log out the whole server |
| Data | One SQLite file, no owner column | Actions, contacts, tasks, events and history are mixed across users |
| Live ingestion | One orchestrator, one Event Engine, one backfill service | Only one Bee stream; one user's events, pauses and gaps drive everyone's state |
| SSE | Broadcast to every subscriber | One user's toasts and speech-derived events reach every open dashboard |
| Privacy ops | Logout / disconnect / GDPR purge act on the whole instance | One user can erase or disconnect everyone |

---

## 2. Identity & sessions ([mcp_server.py](../../../src/serving/mcp_server.py))

| Item | Where | Behaviour |
|---|---|---|
| Session store | `_user_sessions` (line ~320) | `Dict[user_id, dict]` in process memory; no expiry, no persistence |
| Login | `POST /api/auth/login` (`api_auth_login`) | Accepts any `handle`; `user_id` is taken from the body or generated (`usr_<8 hex>`); no credential |
| Identity on later calls | `_extract_user_id_from_request` | `x-user-id` header, `user_id` query or body field, trusted as is |
| Profile directory | [auth.ts](../../../src/web_ui/src/utils/auth.ts), [LoginModal.tsx](../../../src/web_ui/src/components/ui/LoginModal.tsx) | Saved in browser `localStorage`; the server never authenticates it |
| User list | `GET /api/auth/users` | Lists every in-memory profile to any caller |
| SSE client | `new EventSource(/api/events)` in [page.tsx](../../../src/web_ui/src/app/page.tsx) | `EventSource` cannot send custom headers: an `x-user-id` scheme cannot authenticate SSE. Cookie-based auth is required (see [04](04_serving_api_ui_aws.md) §2) |

## 3. Bee account handling

| Item | Where | Behaviour |
|---|---|---|
| Token storage | bee-cli `secureStore.ts`: `BEE_CONFIG_DIR` (default `~/.bee`), OS keychain unless `BEE_FORCE_FILE_STORE=1` | One token per config directory. With a keychain, the entry name is fixed (`bee-cli` / `token:<env>`), so different directories would still collide |
| Status probe | `_get_bee_device_telemetry` | `bee status` of the host user; result copied into every session as `bee_account` |
| Pairing | `_initiate_bee_login_pairing` | `bee login --no-wait` on the host. Whoever approves links **the server**. On CLI failure it returns a fabricated `https://bee.computer/connect#bee_<random>` link that cannot work |
| Logout / disconnect / purge | `_disconnect_bee_device` | `bee logout` on the host for everyone (decision C11 in [10](../../10_bee_cli_reference.md) §10) |
| Wearer identity | `get_wearer_identity()` ([bee_identity.py](../../../src/ingestion/bee_identity.py)) | Process singleton: one `bee me` first name |

## 4. Data layer ([sqlite_store.py](../../../src/core/storage/sqlite_store.py))

- **One store instance** per process: `_store_instance` / `get_storage_store()` ([storage/__init__.py](../../../src/core/storage/__init__.py)); 49 call sites in `src/` resolve it implicitly (23 in `mcp_server.py`, 6 in the orchestrator, 11 in MCP tools, 7 in the pipeline, 1 each in the Event Engine and session manager).
- **14 tables + 3 FTS5 indexes**, none with an owner: `planned_tasks`, `verified_actions`, `social_contacts`, `social_commitments`, `topic_briefings`, `utterance_diarization`, `session_dossiers`, `session_chunks`, `web_search_cache`, `ingest_coverage`, `ingest_ledger`, `bee_conversation_map`, `backfill_runs`, `system_telemetry`, `fts_actions`, `fts_social`, `fts_briefings`.
- **Cross-user merges by construction**: contacts are de-duplicated by `LOWER(person_name)` (`save_social_contact`, line ~772) and commitments by `(contact_name, debtor, description)`. Two users who both meet a "Marco" would share one contact card and its web profile.
- **Global coverage and ledger**: gap detection and backfill de-duplication assume one stream; with two users, one user's live coverage would hide the other user's gaps.
- **Non-SQLite backends**: `STORAGE_BACKEND=dynamo` / `agentcore_memory` raise `NotImplementedError`.
- **Erasure**: `purge_ingestion_history()` truncates the ingestion tables for everybody.
- **`web_search_cache`**: keyed by normalised query text. Queries are derived from private speech, so a shared cache leaks topics between users through timing and hits.

## 5. Runtime singletons

| Singleton | Where | Owns |
|---|---|---|
| `OrchestratorManager.get_instance()` | `mcp_server.py` line ~144 | The only `BeeStreamOrchestrator` (one `BeeClient`, one private `bee proxy`, coverage tracker, speaker-tag cache, location poller) |
| `get_event_engine()` / `get_event_engine_runtime()` | [event_engine.py](../../../src/ingestion/event_engine.py) line ~1797 | The live Event Engine (open event, timers, synthesis worker), also used by `/api/simulate` |
| `get_backfill_service()` | [backfill.py](../../../src/ingestion/backfill.py) line ~1190 | Run queue, startup / reconnect triggers, hand-over with the live engine |
| `get_wearer_identity()` | `bee_identity.py` | Wearer first name |
| `_sse_subscribers` + `broadcast_event()` | `mcp_server.py` line ~56 | Fan-out of every event to every dashboard |

The components already accept injected dependencies: `BeeStreamOrchestrator(store=, engine=, identity=)`, `EventEngine(store=…)`, `BackfillService(store_getter=…, source_factory=…)`, `CliBeeHistorySource(client=…)`. Only their **wiring** is global, which keeps the per-user change mostly in the serving layer.

## 6. Pipeline & MCP tools

- `agent_invocation(payload)` ([app.py](../../../src/pipeline/app.py)) is stateless, but `node_persist`, the action and social nodes and the social profiler call `get_storage_store()` themselves. `ExamenState` has no `user_id`.
- The 12 MCP tools (`create_planned_task`, `verify_action_status`, `get_daily_actions_recap`, `query_social_contact`, `get_contact_profile`, `get_social_commitments`, `get_topic_briefing`, `get_session_dossier`, `list_session_dossiers`, `get_live_event_outline`, `get_upcoming_tasks`, `get_ingestion_coverage`) read the global store; `/mcp` has no authentication.
- `/api/simulate` accepts an `actor_id` that is only echoed into telemetry details.

## 7. Deployments

| | Local | Homelab CT 147 | AWS (doc 06) |
|---|---|---|---|
| Bee token | `~/.bee` of the developer | `/var/lib/examen/.bee` | "a container connected to the user's Bee account" (one) |
| Storage | SQLite | SQLite | DynamoDB / AgentCore Memory planned, not implemented |
| Auth | none | none (LAN HTTP) | not designed; AgentCore Memory namespaces `/users/{actorId}/` are the only multi-user hint |
