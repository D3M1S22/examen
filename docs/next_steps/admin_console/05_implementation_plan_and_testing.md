# 05 — Implementation Plan, Tests & Acceptance Criteria

> Part of the [Admin Console](00_overview.md) specification.

---

## 0. Status (2026-10-21, branch `admin`)

| Phase | Status | Code |
|---|---|---|
| 1 Logging foundation | ✅ | [logging_setup.py](../../../src/core/logging_setup.py), `Debug.warn` / `debug(log=False)` ([debug.py](../../../src/ingestion/debug.py)), user content removed from log lines |
| 2 Service log & incidents | ✅ | [ops_store.py](../../../src/core/ops_store.py), [service_log.py](../../../src/core/service_log.py), [error_capture.py](../../../src/serving/error_capture.py), codes at the sources (Bee client, orchestrator, gatekeeper, pipeline nodes, backfill, auth, Bee links) |
| 3 Health monitor | ✅ | [health_monitor.py](../../../src/serving/health_monitor.py), [metrics.py](../../../src/core/metrics.py), resizable limiter in [limits.py](../../../src/core/limits.py) |
| 4 Runtime settings | ✅ | [runtime_settings.py](../../../src/core/runtime_settings.py) (80 editable keys), `cfg` in [models.py](../../../src/core/models.py), P1 / P2 fixed, `rebuild_all_runtimes` in [mcp_server.py](../../../src/serving/mcp_server.py) |
| 5 Console UI | ✅ | [AdminConsole.tsx](../../../src/web_ui/src/components/views/AdminConsole.tsx), [admin.ts](../../../src/web_ui/src/utils/admin.ts) (+ `admin.test.ts`), API in [admin_console_routes.py](../../../src/serving/admin_console_routes.py) |
| 6 Docs & rollout | ✅ docs; rollout with the normal `main` update | `.env.example`, doc 11, doc 13, AGENTS.MD, README, ROADMAP |
| 7 Token usage per model (2026-10-21) | ✅ | [token_usage.py](../../../src/core/token_usage.py), `token_usage` table in `ops.db`, `GET /api/admin/usage`, *Token usage* card in Health ([03](03_service_log_and_anomalies.md) §8) |

Tests: [tests/test_admin_console.py](../../../tests/test_admin_console.py) (T-AC-1…18) and `src/web_ui/src/utils/admin.test.ts`.

### 0.1 Deviations from the specification

| Spec | Implementation | Reason |
|---|---|---|
| Revert and reset are change sets "tested when needed" (02 §7) | Revert and reset skip the probe requirement | They return to values that were in effect before; during an incident the way back must be one click |
| Generic `log.warning` opens an incident after 5 / 15 min (03 §6) | The rule applies to every `warning` event, catalogue codes included; `error`+ opens immediately | A single Bee reconnect or throttle is normal; repeated ones are the signal |
| Fingerprint = code, component, error type, location (03 §2) | Plus the user for `bee`, `orchestrator`, `backfill` | One user's broken stream must not hide another's |
| `GET /api/admin/audit` not listed in 04 §1 | Added | The *Security log* of the Accounts tab (04 §2.1) needs it |
| botocore wrapper around `invoke` / `ainvoke` (phase 2.4) | `note_llm_error()` called where model calls are caught (gatekeeper, `model_fallback()` in nodes) | Same classification without wrapping LangChain runnables |
| `system.events_dropped` via the sink | Written directly by the writer thread | The queue is the thing that overflowed |

## 1. Phases

Each phase leaves `.venv/bin/pytest tests/ -q` green and the homelab deployable. The order puts observability first: settings overrides are safer once failures are visible.

### Phase 1: Logging foundation
1. `src/core/logging_setup.py`: stdout handler at `LOG_LEVEL`, `examen` logger hierarchy, idempotent setup called from `create_app()` and `main()`.
2. `Debug.debug()` forwards to `logging` at `DEBUG`; the error calls of [01](01_current_state.md) §3.2 become `logger.warning(..., extra={"event_code": …})`.
3. Rewrite the log lines that interpolate user content ([01](01_current_state.md) §3.5) to use ids.
- **Exit:** `journalctl -u examen` shows `INFO` lines of `examen.*` with timestamp and logger; no log line contains a contact name, title or summary (grep test).

### Phase 2: Service log and incidents
1. `ops.db` (`src/core/ops_store.py`): `service_events`, `incidents`, retention job.
2. `src/core/service_log.py`: `report_event()`, `ServiceLogHandler`, sanitiser, fingerprint, non-blocking queue + writer thread.
3. Unhandled-error hooks: ASGI middleware, asyncio exception handler, `threading.excepthook`, done-callbacks on per-user tasks.
4. Event codes of [03](03_service_log_and_anomalies.md) §4.5 at their sources:
   - Bee client and orchestrator;
   - gatekeeper and node fallbacks;
   - botocore / Mantle error mapping to `llm.*` in the model factory: a wrapper around `invoke` / `ainvoke` that classifies the exception and re-raises it;
   - backfill, storage, auth lockout, lifespan.
5. Incident grouping and lifecycle; erasure hook in `_erase_account`.
- **Exit:** T-AC-1…6 pass.

### Phase 3: Health monitor
1. `src/serving/health_monitor.py`: sliding counters, rules of [03](03_service_log_and_anomalies.md) §5, cgroup / disk readers, incident open and resolve.
2. Resizable LLM limiter in `limits.py`, with occupancy sampling.
3. `GET /api/admin/health`, admin SSE channel.
- **Exit:** T-AC-7…9 pass.

### Phase 4: Runtime settings
1. `src/core/runtime_settings.py`:
   - registry ([02](02_runtime_settings.md) §4);
   - `SettingsService` (env snapshot, load and apply overrides at start-up, validation, cross-field rules, atomic apply, runtime rebuild, 30 s version re-read).
2. `ops.db` tables `settings_overrides`, `settings_history`.
3. Fix P1 (explicit region for the Mantle token, no `os.environ` writes) and P2 (`SEARXNG_URL` into `Settings`).
4. `get_chat_model` / `get_embedding_model` accept a `cfg`; probes ([02](02_runtime_settings.md) §5).
5. Settings routes ([04](04_api_ui_and_security.md) §1.1), audit entries, link between incidents and change sets.
- **Exit:** T-AC-10…16 pass.

### Phase 5: Admin console UI
- `ADMIN CONSOLE` view with the Accounts, Settings, Logs and Health tabs ([04](04_api_ui_and_security.md) §2).
- The account-modal tab becomes a link to the view.
- `utils/admin.ts` client; `bun test` for the pending-changes reducer, source badges and SSE event handling.
- **Exit:** build and `bun test` green; manual check on a local server.

### Phase 6: Docs and rollout
- Doc 13 (admin section), doc 11 (journald now shows `INFO`; `ops.db` backed up with `EXAMEN_DATA_DIR`), `.env.example` (`LOG_LEVEL`, `SERVICE_LOG_RETENTION_DAYS`, `HEALTH_*`), AGENTS.MD (use `report_event` codes, never log user content), README, ROADMAP.
- Rollout on the homelab via the normal `main` update; no migration is needed (`ops.db` is created on first start).

---

## 2. Test matrix

All tests are offline. Model calls go through fakes; botocore errors are built with `botocore.exceptions.ClientError` and error codes; a temporary data dir is used.

| ID | Scenario | Expectation |
|---|---|---|
| T-AC-1 | `logger.warning("Failed for 'Marco Rossi': boom")` inside a tenant | Event stored with `user_id`, message `Failed for '…': boom`, component from the logger name |
| T-AC-2 | Exception text echoing a prompt (> 120 chars after `: `), an e-mail, an IP, an `AKIA…` key | Cut and masked |
| T-AC-3 | Context with a non-whitelisted key (`transcript`) | Key dropped |
| T-AC-4 | Same error 50 times | 50 events, 1 incident with `count=50`; resolved after the quiet period; re-opened on recurrence |
| T-AC-5 | Route raising, unobserved task exception, thread exception | `serving.unhandled_exception` (+ `500` with `event_id`), `system.task_exception`, `system.thread_exception` |
| T-AC-6 | Account erasure | The user's events and incidents are deleted |
| T-AC-7 | Gatekeeper fake failing 30 % of 20 calls | `check.gatekeeper_degraded` opens; resolves when the rate drops |
| T-AC-8 | Fake stream with no frames for 15 min (fake clock) | `check.stream_silent` for that user only |
| T-AC-9 | Disk / memory readers with fake values | `check.disk_space` critical, `check.memory` warning |
| T-AC-10 | Override a hot key (`BEDROCK_GATEKEEPER_MODEL`) | The next `get_fast_model()` uses it; `GET` shows `source=override`; history and audit rows written |
| T-AC-11 | Invalid value (out of range, unknown choice, unknown key, `t_soft ≥ t_hard`) | `400` with per-key errors; nothing applied |
| T-AC-12 | AI change without a test / with a failed probe / `force` | `409 test_required` / `409` / applied and flagged with `settings.forced_untested` |
| T-AC-13 | Runtime key (`EVENT_T_SOFT_SECONDS`) while two users stream | Both runtimes rebuilt; open events rehydrated; new engines use the value |
| T-AC-14 | Revert and reset-all | Values back to env; restart keeps them (overrides reloaded from `ops.db`) |
| T-AC-15 | Non-admin, MCP token, cross-site `PUT` | `403` in all three |
| T-AC-16 | Secrets | Never in `GET /api/admin/settings`, `ops.db`, history or probe errors; status `configured` / `missing` / `derived` |
| T-AC-17 | Change of `GATEKEEPER_MODEL` followed by fallbacks | The incident carries the `change_id`; revert restores the previous value |
| T-AC-18 | Privacy | No admin route returns a value read from a user store (static check on imports + response scan for seeded user strings) |

---

## 3. Acceptance criteria

1. The admin switches the gatekeeper from Bedrock to Mantle, or changes model or region, from the console, tests it, saves it and sees it applied without SSH or restart; *Reset* returns to the `.env` values.
2. A wrong model id is refused by the test, or, when forced, shows up as an incident within 2 minutes with a revert button.
3. Stopping one user's Bee stream for 15 minutes opens an incident naming that user; resuming it resolves the incident.
4. Throttling, crashes of per-user tasks and unhandled route errors appear in the console with component, time and count.
5. No user content (speech, contacts, tasks, topics, summaries), e-mail outside the account mapping, IP or secret is visible in the console or stored in `ops.db`.
6. journald receives `INFO` logs of the application.

---

## 4. Open questions

| # | Question | Default if unanswered |
|---|---|---|
| Q1 | Should other admins' changes need a second admin's approval (four-eyes)? | No; history and audit are enough for a small team |
| Q2 | Automatic revert of an AI change when the health check fails within 10 min? | No: an incident with a revert button |
| Q3 | Remote AgentCore runtime: send the effective model config in the payload, or move settings to AppConfig first? | Payload fields when AgentCore runs remotely; AppConfig at the AWS stage |
| Q4 | Notifications outside the dashboard (e-mail, Echo, Telegram) for `critical` incidents | Out of scope for v1 |
| Q5 | Should a non-admin user see their own service events (e.g. "your Bee stream is down")? | Not in v1; the Bee status in *Account* already covers the main case |
| Q6 | Allowed model ids: free text, or a list fetched from Bedrock (`ListFoundationModels` / inference profiles for the region)? | Free text with recently used values; the probe is the real check |
| Q7 | Secrets editable later through AWS Secrets Manager references? | Yes, at the AWS stage |
