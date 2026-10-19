# 03 — Tenant Isolation & Per-User Runtime

> Part of the [Multi-User Support](00_overview.md) specification. Decisions D2, D7, D9 of [00](00_overview.md) §3.

---

## 1. Propagating the user

| Path | How `user_id` travels |
|---|---|
| HTTP request (REST, SSE, MCP) | Auth middleware resolves `UserContext` ([02](02_identity_and_bee_accounts.md) §2) and stores it in `request.state.user`; handlers read it through a `current_user(request)` helper. A `contextvars.ContextVar` (`current_user_ctx`) is set for the duration of the request so MCP tool functions, which receive no `Request`, can resolve it |
| Background work (stream, engine timers, backfill, synthesis) | Explicit: each `UserRuntime` is constructed with its `user_id` and passes the scoped store / identity to its components. Tasks also set `current_user_ctx` so shared helpers behave identically |
| Pipeline (`agent_invocation`, AgentCore) | Explicit field `user_id` in the payload and in `ExamenState`; required (`agent_invocation` rejects payloads without it) |

Rule: **no function falls back to "the" user**. If no user can be resolved, the code raises `MissingUserContext` instead of guessing. `get_storage_store()` without a user is deleted.

---

## 2. Scoped storage (D2)

### 2.1 Registry

```python
class StoreRegistry:
    def system(self) -> SystemStore: ...                       # users, sessions, tokens, bee_links, audit
    def for_user(self, user_id: str) -> AbstractContextStore:  # cached per user, thread-safe
    def drop_user(self, user_id: str) -> None: ...             # GDPR erasure

get_store_registry() -> StoreRegistry                          # process singleton (backend chosen by settings)
```

`AbstractContextStore` keeps its **59 methods unchanged**: an instance is bound to one user at construction, so no query needs a `user_id` filter and none can forget one. This is why D2 prefers scoped stores over adding an owner column to every table.

| Backend | `for_user(user_id)` |
|---|---|
| SQLite (local, homelab) | `SQLiteContextStore(<data_dir>/users/<user_id>/examen.db)`; the existing schema and FTS5 indexes are created per file. `<data_dir>` = `EXAMEN_DATA_DIR` (default `./data`) |
| DynamoDB (AWS, future) | `DynamoContextStore(table, partition_prefix=user_id)`: every item key starts with `USER#<user_id>` |
| AgentCore Memory (AWS, future) | `AgentCoreMemoryStore(actor_id=user_id)`: namespaces `/users/{user_id}/…` (already sketched in doc 06) |

### 2.2 What moves where

| Data | Location | Reason |
|---|---|---|
| Actions, tasks, contacts, commitments, briefings, events, chunks, diarization, coverage, ledger, `bee_conversation_map`, backfill runs | **User store** | Speech-derived or per Bee account |
| `web_search_cache` | **User store** | Queries are derived from private speech ([01](01_current_state.md) §4) |
| `system_telemetry` (latencies) | User store, plus aggregated process metrics in memory | `/api/status` shows the caller's numbers; no speech content either way |
| Users, sessions, tokens, Bee links, audit | **System store** | Needed before a user is known |

Name-based de-duplication of contacts and commitments keeps working unchanged, now inside one user's file: two users who meet "Marco" get two independent cards.

### 2.3 File layout (local / homelab)

```
<EXAMEN_DATA_DIR>/
├── system.db
└── users/<user_id>/
    ├── examen.db            # scoped store
    └── bee/                 # BEE_CONFIG_DIR (0700): token-prod, pairing-prod.json
```

On the homelab `EXAMEN_DATA_DIR=/var/lib/examen/data` (outside the git checkout, so `update.sh` never touches it).

### 2.4 Migrating today's single-tenant database (D9)

`scripts/migrate_to_multi_user.py --owner <username> [--db examen.db]`:
1. creates the owner user (admin) in `system.db` if missing;
2. copies `examen.db` to `users/<owner_id>/examen.db` (SQLite backup API, then `PRAGMA integrity_check`);
3. moves the existing `~/.bee` token of the service user into `users/<owner_id>/bee/` and records the `bee_links` row (`bee me`);
4. leaves the old file renamed `examen.db.pre-multi-user` for rollback.

The migration is idempotent and refuses to run while the server is up.

---

## 3. Per-user runtime (D7)

### 3.1 Components

```python
class UserRuntime:
    user_id: str
    store: AbstractContextStore              # StoreRegistry.for_user(user_id)
    identity: WearerIdentity                 # bee_links.bee_first_name
    bee: BeeClient                           # config_dir = users/<user_id>/bee
    engine: EventEngine                      # EventEngine(store=store, …) + its EventEngineRuntime
    orchestrator: BeeStreamOrchestrator      # (store, engine, identity, bee)
    backfill: BackfillService                # (store_getter=lambda: store, source_factory=CliBeeHistorySource(client=bee))
    events: UserEventBus                     # SSE fan-out for this user only (04 §2)

class UserRuntimeManager:                    # replaces OrchestratorManager
    async def start(self, user_id) / stop(user_id) / restart(user_id)
    def get(self, user_id) -> Optional[UserRuntime]
    async def start_all_linked(self)         # on server start: every bee_links.state == "linked"
    def status(self, user_id) -> dict        # /api/orchestrator/status for the caller
```

Everything in `UserRuntime` already accepts injected dependencies ([01](01_current_state.md) §5); the work is replacing the module singletons (`OrchestratorManager`, `get_event_engine*`, `get_backfill_service`, `get_wearer_identity`, `_sse_subscribers`) with per-user instances owned by the manager.

### 3.2 Lifecycle

| Trigger | Action |
|---|---|
| Server start | `start_all_linked()` (staggered by 2 s per user to avoid a burst of `bee proxy` start-ups) |
| Bee linked / re-linked | `start(user_id)`; startup backfill uses that user's coverage only |
| Bee unlinked / `invalid` / user disabled / erasure | `stop(user_id)`: cancels the stream, stops the private proxy, concludes or hands over open events like today's shutdown |
| Runtime crash | Restart with back-off (5 s → 5 min); after 5 failures in 1 h, `bee_links.last_error` is set and the UI shows it |

### 3.3 Shared resources and limits

| Resource | Sharing | Guard |
|---|---|---|
| Model factory, Bedrock clients, embeddings | Shared (stateless) | — |
| LLM calls (gatekeeper, pipeline, synthesis) | Shared quota | Global `asyncio.Semaphore`: `MAX_CONCURRENT_LLM_CALLS` (default 8); live work has priority over backfill as today |
| Backfill execution | One run at a time per user; global `MAX_CONCURRENT_BACKFILL_RUNS` (default 1) | Per-user budget (`BACKFILL_MAX_ESTIMATED_COST_USD` applies per user and per day) |
| Processes | One private `bee proxy` per linked user (Bun, ≈ 50–80 MB RSS, to be measured: **MU-V2**) | `MAX_ACTIVE_USERS` (homelab default 5 with 2 GB RAM) |
| Event Engine tick | One tick loop per user | Cheap (deadline jumps); measure with 5 users (**MU-V3**) |

### 3.4 Pipeline & AgentCore

- `ExamenState.user_id: str` (required); every node obtains its store through `get_store_registry().for_user(state["user_id"])`.
- Payload from the orchestrator / backfill: `{..., "user_id": "<id>"}`.
- AgentCore (AWS): `invoke_agent_runtime(..., runtimeSessionId=f"{user_id}:{session_id}", payload={..., "user_id": user_id})`. The AgentCore entrypoint trusts `user_id` only from the authenticated ingestion worker (IAM-signed call), never from end users.
- `/api/simulate` and scenario replays run in the caller's scope, with `ingest_source="simulator"`.

### 3.5 Isolation invariants (tested in [05](05_implementation_plan_and_testing.md))

1. Data written for user A is never returned by any API, MCP tool or SSE stream authenticated as user B.
2. Two users with the same contact name, task title or search query produce independent records.
3. A's live coverage never closes B's gaps; A's backfill never reads B's ledger.
4. Stopping, unlinking or erasing A leaves B's runtime and data untouched.
5. A request without a resolvable user fails closed (`401` / `MissingUserContext`).
