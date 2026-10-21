# 01 — Current State

> Part of the [Admin Console](00_overview.md) specification. Audit of `main` after the multi-user merge (`0aeca0d`).

---

## 1. How settings are read today

`src/core/config.py` defines one `Settings` object (`settings = Settings()`, pydantic-settings, `.env` + process environment), imported by 25 modules as `from src.core.config import settings`. Because every module holds **the same object**, `setattr(settings, name, value)` is seen everywhere. The test suite already relies on this (`monkeypatch.setattr(settings, …)`). This is the hook for runtime overrides.

The open question for each value is **when** it is read:

| When | Examples | Consequence for an override |
|---|---|---|
| **At each use** | `get_fast_model()` / `get_reasoner_model()` ([models.py](../../../src/core/models.py)) build a new client per call from `gatekeeper_provider`, `gatekeeper_model_id`, `reasoner_*`, `aws_region`, `mantle_endpoint`; the backfill reads `backfill_*` per run or per step; auth reads `auth_*` per request (`rate_limit.py`, `auth_routes.py`); `max_active_users` per stream start | Takes effect on the next use (**hot**) |
| **When a component is built** | `EngineConfig.from_settings()` ([event_engine.py:92](../../../src/ingestion/event_engine.py)) and `ContinuityConfig.from_settings()` ([topic_continuity.py:111](../../../src/ingestion/topic_continuity.py)) when a user's engine is created; `TopicSimilarity` caches the embedding client (`_resolve_embedder`); `BeeStreamOrchestrator.__init__` copies `bee_speaker_tag_wait_seconds`, `bee_location_poll_seconds`, `event_engine_enabled`; `BeeClient` copies `bee_stream_transport`; `llm_slot()` creates its semaphore once per event loop with `max_concurrent_llm_calls` ([limits.py](../../../src/core/limits.py)) | Needs the component to be rebuilt (**runtime**). Engines rehydrate their open event from the store (`EventEngine.rehydrate`, line 468), so a rebuild loses nothing |
| **At import / app build** | `FastMCP(..., transport_security=_mcp_transport_security())` from `mcp_allowed_hosts` ([mcp_server.py:69](../../../src/serving/mcp_server.py)); CORS middleware from `cors_allowed_origins`; uvicorn host and port; `auth_enabled`; `examen_data_dir`; storage backend; bootstrap admin; `auto_start_user_orchestrators` (start-up only) | Process restart only (**boot**) |

### 1.1 Pitfalls found

| # | Finding | Code | Impact on overrides |
|---|---|---|---|
| P1 | `get_mantle_api_key()` copies `aws_region` into `os.environ["AWS_REGION"]` **only if it is not set yet**, then mints the token | `config.py` `get_mantle_api_key` | After a region override the minted Mantle token may still use the old region. Pass the region explicitly and stop writing to `os.environ` |
| P2 | `SEARXNG_URL` is read from `os.environ`, not from `Settings` | `web_search.py:429` | Cannot be overridden until it becomes a `Settings` field |
| P3 | Topic-similarity thresholds `TOPIC_SIM_*` are calibrated for Titan Text Embeddings V2 at 512 dimensions | `config.py` comments | Changing `BEDROCK_EMBEDDING_MODEL` / `_DIMENSIONS` without recalibrating makes topic continuity wrong. The console must warn |
| P4 | Model ids are region-scoped (cross-region inference profiles `us.` / `eu.` …) | Bedrock | A region change can make the configured model ids invalid. Test-before-save is needed |
| P5 | Settings are validated only at start-up; `setattr` does not validate | pydantic `BaseSettings` | The override layer must validate each value itself |
| P6 | A multi-field change (provider + model + region) applied key by key can be seen half-applied by a call in flight | shared object | Apply a change set in one step, and accept that one in-flight call can mix values |

---

## 2. Secrets

`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` and `BEDROCK_MANTLE_API_KEY` are `Settings` fields read by the model factory. On the homelab they live in `/opt/examen/.env`, readable by the service user only. Nothing exposes them today. The `/api/status` payload reports providers and model ids, not keys.

---

## 3. What happens to logs and errors today

### 3.1 Logging is not configured

- No `logging.basicConfig`, no handler, no level anywhere in `src/`. The `examen.*` loggers (≈ 30 names: `examen.serving.mcp`, `examen.ingestion.backfill`, `examen.pipeline.social`, …) have no handler. Python's *last resort* handler prints only `WARNING`+ to stderr, without timestamp or logger name. **Every `logger.info` is lost**, including "Ingestion Orchestrator background service started", backfill run summaries and "Resumed ambient ingestion for N paired user(s)". Verified: effective level `WARNING`, no root handler.
- uvicorn configures only its own loggers (`log_level="info"`, `mcp_server.py:2009`): access logs reach journald, application logs mostly do not.

### 3.2 Ingestion errors go to disabled `print()` calls

`BeeStreamOrchestrator` and `BeeClient` inherit `Debug` ([debug.py](../../../src/ingestion/debug.py)): `self.debug(msg)` prints only when `debug_mode` matches. Production builds them with `debug_mode="none"` (`mcp_server.py:256`, `orchestrator.py:60`, `stream_convo.py:291`). These errors are therefore **never visible**:

| Where | Message |
|---|---|
| `stream_convo.py:500 / 504 / 510` | Stream stalled · Proxy error (n/3) · Connection error |
| `stream_convo.py:328` | `bee <cmd> failed: …` |
| `orchestrator.py:333` | Pipeline dispatch error |
| `orchestrator.py:349` | Ingest ledger write error |
| `orchestrator.py:181, 293, 495` | Event engine errors |
| `orchestrator.py:439` | Location poll error |
| `orchestrator.py:512` | Utterance processing error |

### 3.3 Model failures degrade silently

- The gatekeeper (`gatekeeper.py:264`) and the pipeline nodes (`action_state.py:255`, `social_profiler.py:469 / 759 / 838`, …) catch every exception and **fall back to heuristics** with a `WARNING`.
- A wrong model id, an expired credential or Bedrock throttling makes EXAMEN keep running at a much lower quality.
- Nothing counts or reports it.
- There is no special handling of `botocore` `ThrottlingException` / `AccessDeniedException` / `ValidationException`.

### 3.4 Unhandled errors

No ASGI exception middleware: a route that raises returns `500` and logs the traceback via uvicorn only. There is also no `loop.set_exception_handler`, no `threading.excepthook` and no `add_done_callback` on background tasks. A crashed per-user task (engine tick, backfill, synthesis) ends without a trace in the application log.

### 3.5 Log lines contain user content

Several messages include personal or speech-derived data, which an admin must not see ([13](../../13_multi_user_accounts.md) §6):

| Where | Content |
|---|---|
| `persist.py:96, 118` | contact name, topic title |
| `social.py:339`; `social_profiler.py:469, 759, 838` | contact names |
| `action_tools.py:80` | planned task title |
| `pipeline/app.py:228` | pipeline summary of what was said |

They must be fixed, or redacted, before any log text reaches the console ([03](03_service_log_and_anomalies.md) §3).

### 3.6 What already exists and can be reused

| Piece | Where | Reuse |
|---|---|---|
| `audit_log` (security events, no personal data, 90-day purge) | `AuthStore.audit` / `list_audit` ([store.py](../../../src/core/auth/store.py)) | Settings changes are audited there; the console shows it read-only |
| Latency telemetry per user (`record_latency`, `get_latency_metrics`) | `sqlite_store.py`, `/api/status` | Health view: per-stage averages |
| Orchestrator and Bee status per user (`get_status`, `CAPACITY`, `invalid` link) | `mcp_server.py` `OrchestratorManager`, `bee_links` | Health checks |
| Coverage gaps, backfill run status and errors | `coverage.py`, `BackfillService` | Health checks and events |
| Per-tenant SSE hub (`broadcast_event`) | `mcp_server.py` | Pattern for the admin channel |
| Admin authorisation (`_require_admin`, session-only prefixes) | `admin_routes.py`, `auth_middleware.py` | Same guard for every new route |
