# 03 — Service Log, Anomalies and Incidents

> Part of the [Admin Console](00_overview.md) specification.

---

## 1. Goals

1. Every error and anomaly of the service reaches **one place**, with enough context to act: which component, which user (pseudonymous id), since when, how often.
2. Repeated problems are **grouped** (one incident, many occurrences), not a flood of lines.
3. Slow problems that never raise an exception are detected by **health checks**: a Bee stream silent for an hour, the gatekeeper always falling back, a backfill always failing.
4. Nothing a user said or stored reaches the admin (A8).

---

## 2. Storage (`ops.db`, A6)

```sql
CREATE TABLE service_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           TEXT NOT NULL,              -- UTC ISO
    level        TEXT NOT NULL,              -- info | warning | error | critical
    code         TEXT NOT NULL,              -- catalogue code (§4.3), "log.warning" for generic records
    component    TEXT NOT NULL,              -- serving | auth | bee | orchestrator | gatekeeper | pipeline |
                                             -- event_engine | backfill | storage | settings | system
    user_id      TEXT,                       -- tenant, NULL for system events
    message      TEXT NOT NULL,              -- sanitised (§3), ≤ 300 chars
    fingerprint  TEXT NOT NULL,              -- sha1(code, component, error type, code location)
    context_json TEXT,                       -- whitelisted keys only (§3.2)
    error_type   TEXT,                       -- e.g. botocore.errorfactory.ThrottlingException
    location     TEXT                        -- "src/ingestion/orchestrator.py:333 process_incoming_utterance"
);
CREATE INDEX idx_events_at ON service_events (at);
CREATE INDEX idx_events_fp ON service_events (fingerprint, at);

CREATE TABLE incidents (
    id           TEXT PRIMARY KEY,           -- inc_<hex>
    fingerprint  TEXT NOT NULL,              -- of the event or the health check
    code         TEXT NOT NULL,
    component    TEXT NOT NULL,
    severity     TEXT NOT NULL,              -- warning | error | critical
    title        TEXT NOT NULL,              -- sanitised
    user_id      TEXT,                       -- when the incident concerns one user
    status       TEXT NOT NULL,              -- open | acknowledged | resolved
    count        INTEGER NOT NULL,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    resolved_at  TEXT,
    ack_by       TEXT,
    change_id    TEXT,                       -- settings change suspected (02 §7)
    details_json TEXT
);
CREATE INDEX idx_incidents_open ON incidents (status, last_seen);
```

- **Writes never block the event loop.** Events go into a bounded in-memory queue (10 000), and one writer thread flushes them in batches every second.
- **Back-pressure.** When the queue is full, the oldest `info` events are dropped first, and a `system.events_dropped` counter is reported.

---

## 3. Privacy boundary (A8)

Admins manage the service, never users' data ([13](../../13_multi_user_accounts.md) §6). The console therefore shows **no transcript, contact, task, topic or summary text**, and no e-mail or IP address.

### 3.1 Message sanitising

Applied to every message before storage:
1. Text between quotes (`'…'`, `"…"`, `“…”`) becomes `'…'`.
2. E-mail addresses become `<email>`; IPv4/IPv6 addresses become `<ip>`; URLs with a query string keep only their host.
3. Anything after `: ` that exceeds 120 characters is cut (exception messages from LLM SDKs can echo the prompt).
4. The total is limited to 300 characters.

In addition, the log lines listed in [01](01_current_state.md) §3.5 are rewritten so they no longer interpolate names, titles or summaries; ids replace them. This is a code change, not only redaction.

### 3.2 Context whitelist

`context_json` keeps only these keys: `session_id`, `event_id`, `run_id`, `conversation_uuid`, `source_key`, `model_id`, `provider`, `region`, `transport`, `attempt`, `latency_ms`, `status_code`, `count`, `threshold`, `value`, `change_id`. Any other key is dropped.

### 3.3 Tracebacks

The event stores only `error_type` and the innermost `location` inside `src/`. The full traceback goes to journald, which the server operator reads. Frame locals are never stored.

### 3.4 Users

`user_id` is stored. The console shows it as the account's e-mail, which the admin already sees in *Accounts*, so the admin can tell which user's Bee stream is broken. It never shows that user's data. When an account is erased, its events and incidents are erased with it, as for `audit_log`.

---

## 4. Capture paths (A9)

### 4.1 Logging configuration (new `src/core/logging_setup.py`, called first in `mcp_server.main()` and `create_app()`)

- **stdout handler** at `LOG_LEVEL` (default `INFO`) with format `%(asctime)s %(levelname)s %(name)s: %(message)s`, so journald finally receives `INFO` from `examen.*`.
- **`ServiceLogHandler`** on the `examen` logger at `WARNING`+:
  - turns each record into a `log.<level>` event;
  - takes `component` from the logger name;
  - takes `user_id` from `get_tenant_id()`;
  - takes `error_type` and `location` from `exc_info`.
- `logger.warning(..., extra={"event_code": "...", "ctx": {...}})` lets existing call sites set a catalogue code without changing their message.

### 4.2 Explicit events: `report_event(code, level, message, **ctx)` (`src/core/service_log.py`)

Used where a meaningful state change happens without an exception (catalogue §4.3). Thread-safe and non-blocking. The tenant is resolved automatically.

### 4.3 Unhandled errors

| Source | Hook | Event |
|---|---|---|
| HTTP route raises | ASGI middleware wrapping the app (outermost after CORS) → `500 {"error": "internal_error", "event_id": …}` | `serving.unhandled_exception` |
| asyncio task fails unobserved | `loop.set_exception_handler` in the lifespan | `system.task_exception` |
| background thread | `threading.excepthook` | `system.thread_exception` |
| per-user background tasks (orchestrator, engine tick, synthesis worker, backfill worker) | `task.add_done_callback(report_task_failure)` where they are created | `orchestrator.crashed`, `event_engine.task_failed`, `backfill.worker_failed` |

### 4.4 `Debug.debug()` → logging

`Debug` keeps its `print` for the CLI tools. It also forwards to `logging.getLogger(f"examen.{sector}")` at `DEBUG`. The error calls listed in [01](01_current_state.md) §3.2 become `logger.warning(..., extra={"event_code": …})` with the codes below.

### 4.5 Event code catalogue (v1)

| Code | Level | Emitted when | Context |
|---|---|---|---|
| `bee.stream_disconnected` | warning | Proxy / connection error, the stream reconnects | transport, attempt |
| `bee.stream_stalled` | warning | No frame within `BEE_STREAM_PING_TIMEOUT_SECONDS` | transport |
| `bee.proxy_fallback_cli` | warning | 3 proxy failures → CLI transport | attempt |
| `bee.command_failed` | warning | `bee <cmd>` non-zero exit | — (command name only) |
| `bee.login_invalid` | warning | Link becomes `invalid` | — |
| `bee.account_conflict` | info | One-Bee-per-user conflict | — |
| `orchestrator.crashed` | error | Orchestrator task ended with an exception | error type |
| `orchestrator.capacity` | warning | A user's stream waits for a slot (`MAX_ACTIVE_USERS`) | value, threshold |
| `gatekeeper.fallback` | warning | Model call failed, heuristic used | provider, model_id, error type |
| `pipeline.node_fallback` | warning | A pipeline node fell back to heuristics | node, provider, model_id |
| `pipeline.dispatch_failed` | error | `agent_invocation` raised or returned `status=error` | session_id |
| `llm.throttled` | warning | botocore `ThrottlingException` / HTTP 429 from Mantle | provider, model_id |
| `llm.access_denied` | error | `AccessDeniedException`, `UnrecognizedClientException`, 401/403 | provider, region |
| `llm.invalid_model` | error | `ValidationException` / `ResourceNotFoundException` about the model id | model_id, region |
| `event_engine.task_failed` | error | Tick or synthesis task failed | event_id |
| `event_engine.synthesis_failed` | warning | Part / consolidated synthesis returned an error | event_id |
| `backfill.run_failed` | error | Run ended `failed` | run_id |
| `backfill.over_budget` | warning | Estimate above `BACKFILL_MAX_ESTIMATED_COST_USD`, run held | run_id, value, threshold |
| `coverage.gap_detected` | info | Gap opened in live coverage | — |
| `storage.write_failed` | error | Store write raised (ledger, persist) | — |
| `settings.changed` / `settings.forced_untested` / `settings.reverted` | info / warning / info | §02-7 | change_id |
| `auth.lockout` | warning | A login key reached the rate limit | — (no e-mail, no IP) |
| `serving.unhandled_exception` | error | §4.3 | status_code |
| `system.started` / `system.stopping` | info | Lifespan | version, commit |
| `system.events_dropped` | warning | Sink queue overflow | count |

---

## 5. Health monitor and anomaly rules (A10)

`HealthMonitor` is one asyncio task started in the lifespan. Every `HEALTH_CHECK_INTERVAL_SECONDS` (60) it evaluates the rules below. A rule that fails **opens** an incident with fingerprint `check:<rule>[:<user_id>]`, or updates it if already open. A rule that passes **resolves** its open incident. Thresholds are runtime settings ([02](02_runtime_settings.md) §4.5).

| Rule | Condition (defaults) | Severity |
|---|---|---|
| `check.stream_silent` | A user's Bee is linked, auto-start on, but no frame / ping for 15 min | warning |
| `check.stream_flapping` | ≥ 6 `bee.stream_disconnected` for one user in 30 min | warning |
| `check.gatekeeper_degraded` | `gatekeeper.fallback` / gatekeeper calls ≥ 20 % over the last 15 min (min. 10 calls) | error |
| `check.pipeline_errors` | `pipeline.dispatch_failed` + `pipeline.node_fallback` ≥ 20 % of dispatches over 15 min (min. 5) | error |
| `check.llm_throttling` | ≥ 5 `llm.throttled` in 5 min | warning |
| `check.llm_latency` | p95 gatekeeper latency > 8 s over 15 min (from latency telemetry) | warning |
| `check.backfill_failing` | 2 consecutive failed runs for one user | warning |
| `check.capacity` | `orchestrator.capacity` active for > 10 min | warning |
| `check.llm_slots_saturated` | All `MAX_CONCURRENT_LLM_CALLS` slots busy in ≥ 80 % of samples over 10 min | warning |
| `check.disk_space` | Free space of `EXAMEN_DATA_DIR` < 1 GB or < 10 % | critical |
| `check.memory` | Process RSS > 75 % of the cgroup limit (read from `/sys/fs/cgroup/memory.max`, `/proc/self/status`; no psutil dependency) | warning |
| `check.error_burst` | ≥ 20 `error`-level events in 5 min (any code) | error |

**Link to settings.** When `gatekeeper_degraded`, `pipeline_errors` or `llm.*` opens within 10 minutes of a `settings.changed` that touched an AI key, the incident gets `change_id` and the console offers *Revert this change*.

**Counters.** The rules need rates, not only events. `HealthMonitor` keeps in-memory sliding counters, fed by the same sink: calls per component, fallbacks, dispatches, LLM slot occupancy sampled every 10 s. On a restart the counters start empty, so rate rules wait for their minimum sample.

---

## 6. Incidents

- **Grouping.** Events with the same fingerprint update one incident: `count`, `last_seen`, and severity raised to the worst seen. Generic `log.warning` events open an incident only after 5 occurrences in 15 min; catalogue codes at `error`+ open one immediately.
- **Lifecycle.**

  ```
  open → acknowledged (admin) → resolved (rule passes, or no new event for 60 min, or admin resolves)
  ```

  A resolved incident that fires again within 30 min is **re-opened** (same id), so flapping stays visible.
- **Live channel.** Opening, re-opening and resolving are pushed on the admin SSE channel ([04](04_api_ui_and_security.md) §1).

---

## 7. Retention (A11)

- **Events:** deleted after `SERVICE_LOG_RETENTION_DAYS` (30), or when more than 50 000 rows (oldest `info` first).
- **Incidents:** resolved ones deleted after 90 days.
- **Housekeeping:** a daily job runs the purges and `VACUUM`s `ops.db` when ≥ 20 % is free pages.
- **Account erasure:** deletes the user's events and incidents (§3.4).
