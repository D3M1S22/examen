# 02 — Runtime Settings (admin overrides)

> Part of the [Admin Console](00_overview.md) specification.

---

## 1. Model

Each value is resolved like this:

```
effective value = admin override (ops.db)  >  environment (.env / process env)  >  code default
```

- **Instance-wide (A1).** One value per key for the whole server. Per-user settings are a non-goal.
- **The env keeps its role.** It is the baseline the instance boots with, and *reset to default* goes back to it. Removing every override returns exactly the behaviour of today.
- **Source is always visible.** The console shows the effective value and where it comes from: `default`, `env` or `override`, with who set the override and when.

At start-up `SettingsService` takes an **env snapshot**: the values of the freshly built `Settings`, plus `model_fields_set` to tell env-provided values from code defaults. It then applies the stored overrides with `setattr` on the shared `settings` object ([01](01_current_state.md) §1).

---

## 2. Storage (`EXAMEN_DATA_DIR/ops.db`, A6)

```sql
CREATE TABLE settings_overrides (
    key         TEXT PRIMARY KEY,      -- registry key, e.g. "gatekeeper_model_id"
    value_json  TEXT NOT NULL,         -- JSON-encoded, validated value
    updated_at  TEXT NOT NULL,
    updated_by  TEXT NOT NULL          -- admin user id
);
CREATE TABLE settings_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id   TEXT NOT NULL,         -- one id per saved change set (several keys)
    key         TEXT NOT NULL,
    old_json    TEXT,                  -- NULL = was not overridden
    new_json    TEXT,                  -- NULL = override removed (reset)
    at          TEXT NOT NULL,
    by_user     TEXT NOT NULL,
    test_result TEXT                   -- JSON summary of the probe (§5), when one ran
);
```

`ops.db` sits next to `auth.db` and the user folders, and is backed up with them. On AWS the same interface moves to DynamoDB or AWS AppConfig, so that every instance reads the same overrides ([05](05_implementation_plan_and_testing.md) §4, Q3).

---

## 3. Registry (A2)

`src/core/runtime_settings.py` declares one `SettingSpec` per editable key:

```python
@dataclass(frozen=True)
class SettingSpec:
    key: str                    # Settings attribute
    env: str                    # env alias, shown in the console
    group: str                  # "AI models", "Event engine", ...
    label: str
    help: str
    apply: Literal["hot", "runtime", "boot"]
    choices: Optional[tuple] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    pattern: Optional[str] = None
    test: Optional[str] = None  # probe group (§5): "gatekeeper" | "reasoner" | "embeddings"
    risk: Optional[str] = None  # warning shown before saving
```

Values are checked against the field's type (`TypeAdapter(Settings.model_fields[key].annotation)`) and the spec's constraints. **Keys that are not in the registry cannot be written**, whatever the API receives.

---

## 4. Catalogue

Apply modes (A4):
- **hot**: read at each use; takes effect immediately.
- **runtime**: copied when a component is built. After saving, the server rebuilds every user's event engine and orchestrator (live streams reconnect within seconds; open events are rehydrated from the store).
- **boot**: listed read-only with "requires restart".

### 4.1 AI providers and models

| Key (env) | Apply | Constraints | Test | Notes |
|---|---|---|---|---|
| `GATEKEEPER_PROVIDER` | hot | `bedrock` \| `mantle` | gatekeeper | Gatekeeper and the fast extraction nodes (action, social, scheduler, topic extraction, profiler) |
| `BEDROCK_GATEKEEPER_MODEL` | hot | non-empty, `^[\w.:/-]+$` | gatekeeper | Region-scoped (P4) |
| `REASONER_PROVIDER` | hot | `bedrock` \| `mantle` | reasoner | Topic research synthesis |
| `BEDROCK_REASONER_MODEL` | hot | as above | reasoner | |
| `BEDROCK_MANTLE_ENDPOINT` | hot | empty or `https://…` | gatekeeper, reasoner (if a role uses Mantle) | Empty = regional default `bedrock-mantle.<region>.api.aws` |
| `AWS_REGION` | hot (chat), runtime (embeddings) | AWS region code `^[a-z]{2}(-[a-z]+)+-\d$` | all three | Fix P1 first: mint Mantle tokens with the explicit region, stop writing `os.environ` |
| `BEDROCK_EMBEDDING_MODEL` | runtime | as model id | embeddings | **Risk:** `TOPIC_SIM_*` were calibrated for Titan V2 512 (P3); recalibrate with `scripts/replay_event_scenarios.py --calibrate` |
| `BEDROCK_EMBEDDING_DIMENSIONS` | runtime | 256 \| 512 \| 1024 | embeddings | Same risk |
| `MOCK_AI` | hot | bool | — | **Risk:** every extraction becomes heuristic for every user; confirmation required |

### 4.2 Deep Topic Event Engine and topic continuity (runtime)

`EVENT_ENGINE_ENABLED`, `EVENT_PROFILE` (`default` \| `demo`), `EVENT_T_SOFT_SECONDS`, `EVENT_T_HARD_SECONDS`, `EVENT_T_HARD_AFTER_CLOSE_CUE_SECONDS`, `EVENT_T_HARD_TRANSIT_SECONDS`, `EVENT_T_CHECKPOINT_SECONDS`, `EVENT_MIN_SEGMENT_WORDS`, `EVENT_LOCATION_SHIFT_METERS`, `EVENT_TICK_SECONDS` (≥ 5), `EVENT_SYNTHESIS_MAX_WORDS`, `TOPIC_SIMILARITY_BACKEND` (`embedding` \| `heuristic` \| `none`), `TOPIC_SIM_SAME`, `TOPIC_SIM_DIFFERENT` (0–1, `same > different`), `TOPIC_SIM_*_HEURISTIC`, `TOPIC_WINDOW_MIN_CHUNKS`, `TOPIC_WINDOW_MIN_WORDS`, `TOPIC_PENDING_MAX_AGE_SECONDS`, `TOPIC_DRIFT_WINDOWS`, `TOPIC_DRIFT_MIN_SECONDS`, `TOPIC_LLM_JUDGE`.

Cross-field rules: `t_soft < t_hard`, and `topic_sim_same > topic_sim_different`. `EVENT_PROFILE=demo` carries the risk "compressed timers split real conversations".

### 4.3 Historical backfill (hot: read at the next run or step)

`BACKFILL_ENABLED`, `BACKFILL_AUTO_ON_STARTUP`, `BACKFILL_AUTO_ON_RECONNECT`, `BACKFILL_LOOKBACK_DAYS`, `BACKFILL_MAX_WINDOW_DAYS`, `BACKFILL_MAX_UTTERANCES_PER_RUN`, `BACKFILL_MAX_ESTIMATED_COST_USD` (≥ 0), `BACKFILL_SCREEN_CONCURRENCY` (1–16), `BACKFILL_SCREENING` (`window` \| `utterance`), `BACKFILL_WINDOW_UTTERANCES`, `BACKFILL_WINDOW_MAX_WORDS`, `BACKFILL_WINDOW_CONTEXT_UTTERANCES`, `BACKFILL_WHOLE_CONVERSATIONS`, `BACKFILL_COST_PER_*`, `BACKFILL_ENRICH_CONTACTS_PER_RUN`, `BACKFILL_LEDGER_RETENTION_DAYS`.

The matching thresholds (`BACKFILL_MATCH_WINDOW_SECONDS`, `BACKFILL_FUZZY_THRESHOLD`, `BACKFILL_LIVE_COVERAGE_FRACTION`, …) stay **env-only**. They decide de-duplication, and a wrong value creates duplicate entities in every user's data.

### 4.4 Bee ingestion (runtime)

`BEE_STREAM_TRANSPORT` (`proxy` \| `cli`), `BEE_STREAM_PING_TIMEOUT_SECONDS` (≥ 35: pings arrive every 30 s), `BEE_SPEAKER_TAG_WAIT_SECONDS` (0–5), `BEE_LOCATION_POLL_SECONDS` (0 or ≥ 30), `COVERAGE_FLUSH_SECONDS`, `COVERAGE_DEGRADED_ERROR_RATE` (0–1).

`BEE_PROXY_PORT` stays **boot**, because a fixed port breaks with more than one user. `BEE_WEARER_NAME` is not listed: it applies only in single-user mode.

### 4.5 Limits, web search, logging (hot)

| Key | Constraints | Notes |
|---|---|---|
| `MAX_CONCURRENT_LLM_CALLS` | 1–64 | Needs a **resizable** limiter: replace the per-loop `asyncio.Semaphore` with a counter + `Condition` that reads the setting on each acquire |
| `MAX_ACTIVE_USERS` | 1–50 | Applies to stream starts; running streams are not stopped. Raising it starts waiting users on their next status poll |
| `WEB_SEARCH_CACHE_TTL_SECONDS` | ≥ 0 | |
| `SEARXNG_URL` | empty or URL | Becomes a `Settings` field first (P2) |
| `LOG_LEVEL` (new) | `DEBUG` \| `INFO` \| `WARNING` | Level of the stdout (journald) handler; the console sink keeps `WARNING`+ ([03](03_service_log_and_anomalies.md)) |
| `SERVICE_LOG_RETENTION_DAYS` (new) | 1–365 | |
| Health-check thresholds (new) | see [03](03_service_log_and_anomalies.md) §5 | |

### 4.6 Accounts (hot)

`AUTH_ALLOW_SIGNUP`, `AUTH_SIGNUP_MAX_PER_IP` (1–100), `AUTH_MIN_PASSWORD_LENGTH` (8–64, new passwords only), `AUTH_MAX_LOGIN_FAILURES` (3–50), `AUTH_LOCKOUT_MINUTES` (1–1440), `AUTH_SESSION_TTL_HOURS` (1–2160, new and renewed sessions), `AUTH_AUDIT_RETENTION_DAYS` (7–3650).

These minimums keep an admin from locking everyone out, themselves included.

### 4.7 Read-only (boot) and env-only

| Kind | Keys | Why |
|---|---|---|
| boot (shown, not editable) | `MCP_HOST`, `MCP_PORT`, `MCP_STREAMABLE_HTTP`, `MCP_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `AUTH_ENABLED`, `AUTH_COOKIE_SECURE`, `EXAMEN_DATA_DIR`, `STORAGE_BACKEND`, `SQLITE_DB_PATH`, `AUTO_START_USER_ORCHESTRATORS`, `BEE_PROXY_PORT`, `AGENTCORE_RUNTIME_ARN`, `PRIVACY_NOTICE_VERSION` | Read at import or app build; or security-critical; or (notice version) meaningless without a code change to the notice text |
| secrets (status only, A3) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `BEDROCK_MANTLE_API_KEY` | Never sent to the browser |
| hidden | `EXAMEN_BOOTSTRAP_ADMIN*`, de-duplication thresholds (§4.3) | Bootstrap only; data-integrity risk |

---

## 5. Test before save (A5)

When a change set touches a key with a `test` group, `POST /api/admin/settings/test` runs one probe per affected group with the **candidate** values. It uses a private `Settings` copy (`settings.model_copy(update=…)`) passed to the model factory, so the live configuration is not touched.

| Group | Probe | Pass condition |
|---|---|---|
| gatekeeper | `get_chat_model(provider, model).with_structured_output(ChunkClassification).invoke(<fixed synthetic sentence>)` | A valid `ChunkClassification` within 20 s |
| reasoner | One short completion (`"Reply with OK"`) | A non-empty answer within 30 s |
| embeddings | `embed_query("test")` | A vector with the configured dimension |

- **Fixed synthetic text.** The probes never use user data.
- **What the result shows.** Latency, and on failure the provider error class and message (`AccessDeniedException`, `ValidationException: model identifier is invalid`, `ResourceNotFoundException`, …). Secrets are stripped.
- **Save rules.** `PUT /api/admin/settings` refuses a change set whose required probes failed or did not run in the last 10 minutes, unless `force: true`. A forced save is flagged in history and raises a `settings.forced_untested` event.
- **Limits.** Probes go through `llm_slot()` and are rate-limited to 10 per admin per 10 minutes.
- **Factory change.** `get_chat_model` and `get_embedding_model` gain an optional `cfg: Settings` parameter (default: the shared `settings`), so a probe and the live path use the same code.

---

## 6. Secrets (A3)

The console shows, per secret: **configured** (env present), **missing**, or **derived**. *Derived* means the Mantle key is minted from IAM, or the AWS credentials come from the instance role or profile, through `has_aws_credentials` and `has_mantle_credentials`.

- **Why env-only.** Editing secrets in the browser would put AWS credentials into `ops.db` and into HTTP bodies on a LAN without TLS (doc 11 §5).
- **Follow-up for AWS.** Secrets Manager references, where the console picks which secret, not its value.

---

## 7. Apply, history, rollback (A4, A7)

1. **Validate.** `PUT /api/admin/settings` receives a change set `{key: value | null}`, where `null` removes the override. Every key is validated (§3) plus the cross-field rules. Any error rejects the whole set.
2. **Persist.** In one `ops.db` transaction: write `settings_overrides`, append `settings_history` rows with one `change_id`, and record an `audit_log` entry `settings_changed` with the keys only. Values are kept in history, which secrets never enter.
3. **Apply.** All `setattr` calls in one step on the shared object, under a process lock.
4. **Rebuild** when a `runtime` key changed: for each user with a runtime, stop the orchestrator, drop the engine and the continuity cache (`stop_tenant_runtime(uid, forget=False)`, then `drop_tenant_event_engine`), and start again (`start_tenant_runtime`). Users are processed in sequence; the response reports `rebuilt_runtimes: N`.
5. **Emit** a `settings.changed` event (keys, change id, admin id) to the service log and the admin SSE channel.

Rollback actions:
- `POST /api/admin/settings/revert {change_id}` applies the inverse of a change set.
- `DELETE /api/admin/settings/{key}` or `POST /api/admin/settings/reset-all` returns to the env defaults.

All of them are change sets themselves, validated, tested when needed, and audited.

**Safety net.** If the HealthMonitor sees the gatekeeper fallback rate or the pipeline error rate cross its threshold within 10 minutes of a change, it opens an incident linked to that `change_id`, with a *revert* button ([03](03_service_log_and_anomalies.md) §5). There is no automatic revert in v1 (Q2).

---

## 8. Concurrency and multi-process

- **In-flight calls.** A call already running keeps the client it built; one call can mix old and new values during the apply step (P6), which is accepted.
- **Several processes (AWS, a remote AgentCore runtime).** Each process applies overrides at start-up. `SettingsService` also re-reads `ops.db` every 30 s and compares a `version` counter, so a change reaches every process within 30 s. A remote AgentCore runtime does not share `ops.db`: until settings move to AppConfig, the orchestrator adds the effective model config (`gatekeeper_provider`, `gatekeeper_model_id`, `reasoner_*`, `aws_region`) to the pipeline payload, and `agent_invocation` applies it to a private `Settings` copy for that invocation.
