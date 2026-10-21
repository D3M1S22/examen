# 🛠️ Admin Console — Overview

> **Document Status:** Specification (not implemented). Decisions in §3 are proposals to confirm.
> **Related:** [13_multi_user_accounts.md](../../13_multi_user_accounts.md) (accounts, admin role), [11_homelab_test_deployment.md](../../11_homelab_test_deployment.md) (deployment), [06_aws_cloud_deployment_architecture.md](../../06_aws_cloud_deployment_architecture.md) (AWS target)
> **Audience:** EXAMEN engineers implementing the admin features on top of the multi-user code now on `main`

---

## 1. Why this exists

Today the admin can manage accounts only: list, create, disable, reset passwords ([13](../../13_multi_user_accounts.md) §6). Two needs are uncovered.

1. **Runtime settings.** Every tunable lives in `.env` and is read once at start-up. Changing a model, switching a role from Bedrock to Mantle, or moving to another AWS region needs SSH into the server, an `.env` edit and a restart. The admin should change these from the dashboard. The `.env` values become the **defaults** and the admin **overrides** them.
2. **Service log.** The admin has no view of how the service is doing. Errors are often invisible ([01](01_current_state.md) §3):
   - the `examen.*` loggers have no handler and lose every `INFO`;
   - ingestion errors go to `print()` calls that are disabled in production;
   - model failures fall back silently to heuristics.

   The admin needs a panel that collects errors and anomalous events, groups them, and shows the general health of the service.

The two features meet at one point. A wrong override (a model id that does not exist in the region) degrades extraction **silently** today. The settings flow must test a change before saving it, and the log must surface the degradation if it happens anyway.

---

## 2. Target model in one picture

```
                     ┌─────────────────────────── EXAMEN process ───────────────────────────┐
 Admin console ────► │ /api/admin/settings ──► SettingsService ──► ops.db: overrides, history  │
 (dashboard view)    │        │  validate · test · apply            │                          │
                     │        ▼                                     ▼                          │
                     │  settings (the one shared object)  ◄── env defaults (.env / environment)│
                     │        │ hot: next use   runtime: rebuild per-user runtimes   boot: RO   │
                     │                                                                         │
                     │ logging.examen.* ──► ServiceLogHandler ─┐                               │
                     │ report_event(code, …) ──────────────────┼──► EventSink ──► ops.db:      │
                     │ ASGI 500 / asyncio / thread hooks ──────┘      (redact, fingerprint,    │
                     │ HealthMonitor (60 s checks) ── anomalies ──►    group, retain)          │
 Admin console ◄──── │ /api/admin/logs · /incidents · /health · SSE admin channel             │
                     └─────────────────────────────────────────────────────────────────────────┘
 journald ◄── stdout handler (INFO+, configurable LOG_LEVEL) — full text stays on the server only
```

---

## 3. Decisions (proposals)

| # | Topic | Proposal | Alternatives | Details |
|---|---|---|---|---|
| **A1** | Scope of settings | **Instance-wide** only; no per-user overrides | Per-user model choice | [02](02_runtime_settings.md) §1 |
| **A2** | What is editable | An **allow-list registry**: each key has type, constraints, group, apply mode and risk. Anything not in the registry stays env-only | Expose every field of `Settings` | [02](02_runtime_settings.md) §3 |
| **A3** | Secrets (AWS keys, Mantle API key) | **Env-only**: the console shows *configured / missing*, never a value | Write-only secrets encrypted with a key from the env | [02](02_runtime_settings.md) §6 |
| **A4** | How a change takes effect | Three apply modes. **hot**: next use. **runtime**: the server rebuilds every user's engine and orchestrator (open events are rehydrated). **boot**: shown read-only with "requires restart" | Restart the process from the console | [02](02_runtime_settings.md) §4 |
| **A5** | Model / provider / region changes | **Test before save**: a probe call per affected role (gatekeeper, reasoner, embeddings) with the candidate values. Save is refused on failure unless the admin forces it | Save and watch the log | [02](02_runtime_settings.md) §5 |
| **A6** | Persistence | New `EXAMEN_DATA_DIR/ops.db`: `settings_overrides`, `settings_history`, `service_events`, `incidents`. `auth.db` stays limited to accounts and security | Tables in `auth.db` | [02](02_runtime_settings.md) §2, [03](03_service_log_and_anomalies.md) §2 |
| **A7** | Rollback | History of every change, with *revert to previous* and *reset to default* per key or for all keys | No history | [02](02_runtime_settings.md) §7 |
| **A8** | What the log may contain | **No user content.** Structured events (code, component, level, user id, sanitised message, exception type and code location). The full text stays in journald, which only the server operator reads | Mirror every log line into the panel | [03](03_service_log_and_anomalies.md) §3 |
| **A9** | Capture | (1) explicit `report_event()` with a code catalogue; (2) a handler on `examen.*` for `WARNING`+ with redaction; (3) unhandled errors: ASGI 500, asyncio tasks, threads. `Debug.debug()` errors are converted to logging | Only explicit events | [03](03_service_log_and_anomalies.md) §4 |
| **A10** | Anomalies | A `HealthMonitor` task evaluates rules every 60 s and opens / resolves **incidents** (grouped by fingerprint, with count, first and last seen, acknowledge) | Raw events only | [03](03_service_log_and_anomalies.md) §5–6 |
| **A11** | Retention | Events 30 days and at most 50 000 rows; incidents 90 days; settings history kept | Unlimited | [03](03_service_log_and_anomalies.md) §7 |
| **A12** | Console UI | A full-screen **Admin console** view (tabs *Accounts*, *Settings*, *Logs*, *Health*) instead of the narrow account-modal tab | Keep everything in the modal | [04](04_api_ui_and_security.md) §2 |
| **A13** | Live updates | Admin-only SSE channel for new events and incidents | Polling | [04](04_api_ui_and_security.md) §1 |
| **A14** | Notifications outside the dashboard (e-mail, Echo) | **Out of scope** for v1 | — | [05](05_implementation_plan_and_testing.md) §4 |

---

## 4. Goals and non-goals

**Goals**
- Change models, providers, region and tunables without SSH or restart, and see where each value comes from (default, env, override).
- Never leave the service silently degraded: a failing model, a dead Bee stream, a throttled provider or a crash loop is visible within a minute.
- Keep the multi-user rule: **an admin manages the service, never reads users' data.**

**Non-goals (v1)**
- Editing infrastructure values (ports, data directory, storage backend, CORS, MCP hosts, auth on/off).
- Editing secrets from the browser.
- Per-user settings, feature flags per user, A/B testing.
- Metrics storage for long-term dashboards (Prometheus / CloudWatch come with AWS).

---

## 5. Document map

| File | Content |
|---|---|
| [01_current_state.md](01_current_state.md) | How settings are read today (per call, at construction, at import), and what happens to logs and errors today, with code references |
| [02_runtime_settings.md](02_runtime_settings.md) | Registry, catalogue of editable settings with apply modes, storage, validation, test-before-save, apply, rollback, secrets |
| [03_service_log_and_anomalies.md](03_service_log_and_anomalies.md) | Event model, capture paths, redaction, event code catalogue, health checks, incidents, retention |
| [04_api_ui_and_security.md](04_api_ui_and_security.md) | Admin API, admin SSE channel, console views, authorisation and audit, privacy boundary |
| [05_implementation_plan_and_testing.md](05_implementation_plan_and_testing.md) | Phases, test matrix, acceptance criteria, open questions |
