# 04 — Admin API, Console UI and Security

> Part of the [Admin Console](00_overview.md) specification.

---

## 1. API

Every route below sits under `/api/admin/`, so it inherits two existing guards:
- the **session-only** rule: `SESSION_ONLY_PREFIXES` in `auth_middleware.py` refuses MCP access tokens with `403`;
- the **admin check**: `_require_admin()` in `admin_routes.py` answers `403` for non-admins.

New routes live in `src/serving/admin_console_routes.py`.

### 1.1 Settings

| Route | Purpose |
|---|---|
| `GET /api/admin/settings` | Registry with, per key: `group`, `label`, `help`, `apply`, constraints, `risk`, `effective`, `source` (`default` \| `env` \| `override`), `env_value` (the default the admin can return to), `override_by`, `override_at`; plus `version`. Secrets: `{key, status: configured \| missing \| derived}` only |
| `POST /api/admin/settings/test` | `{changes: {key: value}}` → `{results: [{group, ok, latency_ms, error_type, message}]}` ([02](02_runtime_settings.md) §5) |
| `PUT /api/admin/settings` | `{changes: {key: value \| null}, base_version, force?: bool, note?: str}` → `{change_id, applied: [...], rebuilt_runtimes, requires_restart: [...]}`. `400` with per-key errors on validation failure; `409 test_required` when probes are missing or failed and `force` is not set; `409 settings_changed_meanwhile` on a stale `base_version` |
| `DELETE /api/admin/settings/{key}` | Remove one override (back to env / default) |
| `POST /api/admin/settings/reset-all` | Remove every override |
| `GET /api/admin/settings/history?limit=` | Change sets with keys, old → new, admin, time, test result |
| `POST /api/admin/settings/revert` | `{change_id}` → applies the inverse change set |

### 1.2 Service log, incidents, health

| Route | Purpose |
|---|---|
| `GET /api/admin/logs` | Events. Filters: `level` (min level), `component`, `code`, `user_id`, `since`, `until`, `q` (on the sanitised message), `limit` (≤ 500), `before_id` (pagination) |
| `GET /api/admin/incidents` | `status` (open, acknowledged, resolved, all), `severity`, `component`, `user_id` |
| `GET /api/admin/incidents/{id}` | Incident with its last 50 events |
| `POST /api/admin/incidents/{id}/ack` / `/resolve` | Lifecycle ([03](03_service_log_and_anomalies.md) §6) |
| `GET /api/admin/health` | Snapshot: version and commit, uptime, process RSS / cgroup limit, disk free, active streams / `MAX_ACTIVE_USERS`, LLM slots in use / max, per-user stream state (linked, streaming, last frame age, transport, capacity), last 15 min rates (gatekeeper calls, fallback %, dispatches, errors), latency averages, open incidents by severity, last backfill per user |
| `GET /api/admin/events` | **Admin SSE channel** (A13): `service_event` (level ≥ warning), `incident_opened` / `incident_updated` / `incident_resolved`, `settings_changed`, `health` (every 30 s) |

**Admin SSE channel.**
- It is a separate subscriber set, not a tenant: `broadcast_event` never routes user data there, and `report_event` never routes to user channels.
- It is authenticated like `/api/events` (session cookie).
- The subscriber is dropped when the admin session ends or the admin flag is revoked; the server re-checks every 60 s.

---

## 2. Console UI (A12)

The current *Admin* tab of the account modal is too narrow for tables. It becomes a dashboard view, **ADMIN CONSOLE**:
- shown in `SystemBar` only when `currentUser.is_admin`;
- rendered by `page.tsx` like the other views (`activeTab === "admin"`).

The modal keeps a link *Open admin console*. The view has four tabs.

### 2.1 Accounts
Today's `AdminSection` (accounts, Bee state, create, disable, reset password), moved here. A *Security log* section shows `audit_log`, read-only.

### 2.2 Settings
- **Layout.** Groups as collapsible cards (AI models, Event engine, Topic continuity, Backfill, Bee ingestion, Limits & logging, Accounts, Read-only, Secrets).
- **Each row:**
  - label and env name;
  - effective value with a **source badge** (`default` / `env` / `override by <admin> · <time>`);
  - an input matching the type (select for choices, number with min/max, toggle, text with pattern);
  - an apply-mode tag (`instant` / `restarts runtimes` / `needs server restart`) and the risk text.
- **Editing** builds a *pending changes* bar: list of keys, **Test** (when a test group is involved), **Save** (enabled after a passing test, or *Save without test* behind a confirmation), **Discard**.
- **AI models editor.** A compact block per role (Gatekeeper, Reasoner, Embeddings): provider radio (Bedrock / Mantle), model id with recently used values, region, *Test* per role with latency.
- **History drawer:** change sets, *Revert*, *Reset all to defaults*.

### 2.3 Logs
- **Incidents** first: open and acknowledged, sorted by severity and last seen. Each card shows code, title, user (e-mail), count, first / last seen, *Acknowledge*, *Resolve*, and *Revert settings change* when `change_id` is set.
- **Event stream** below:
  - filters (level, component, user, code, time range, text);
  - live updates from the admin SSE channel, with *pause*;
  - expandable rows (sanitised message, error type, code location, whitelisted context);
  - *Load older*.
- **Export** of the filtered events as JSON (sanitised content only).

### 2.4 Health
- **Cards:** uptime and version, memory and disk, LLM slots, active streams vs limit, last-15-minute rates.
- **Per-user stream table:** e-mail, Bee state, transport, last frame age, capacity, last backfill.
- Refreshed by the `health` SSE message.

All texts are English like the rest of the dashboard. Nothing in these views reads per-user stores.

---

## 3. Security

| Risk | Control |
|---|---|
| A non-admin or a leaked access token changes settings | `/api/admin/*` is session-only and admin-only (existing guards); tests cover both |
| CSRF on `PUT /api/admin/settings` | Existing `Origin` / `Referer` check on cookie requests |
| An admin breaks the service with a bad value | Registry constraints, cross-field rules, test-before-save, history and revert, health incidents linked to the change |
| An admin locks everyone out | Minimums on auth settings ([02](02_runtime_settings.md) §4.6); `AUTH_ENABLED` and cookie settings are read-only |
| Secrets leak through the console | Secrets are never stored in `ops.db` nor returned. Probe and event messages are sanitised, and key-like substrings are stripped too (`Authorization` values, `AKIA…`, `bedrock-api-key-…`) |
| The admin reads users' data through logs | Sanitising, context whitelist, the rewritten log lines, no access to user stores ([03](03_service_log_and_anomalies.md) §3) |
| Probe calls cost money or are abused | One probe per group per test; rate limit 10 per 10 min per admin; probes go through `llm_slot()` |
| Two admins edit at once | `PUT` carries `base_version` from `GET`; a stale version gets `409 settings_changed_meanwhile` |

**Audit.** Every settings change, revert, reset, forced save and incident action goes to `audit_log` (`settings_changed`, `settings_reverted`, `incident_acknowledged`, …) with the actor and the keys, never the value of a secret.
