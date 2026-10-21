# 13 — Multi-User Accounts, Per-User Bee Pairing & GDPR

> **Status:** implemented on branch `feature/multi-user-auth` (2026-10-20); hardening and administration ported from branch `sessions` on `feature/multi-user-port` (2026-10-20, §10). Tests: [tests/test_accounts.py](../tests/test_accounts.py).
> **Replaces:** the demo "pseudonym" login (in-memory `_user_sessions`, profiles in `localStorage`) and the host-wide Bee login.
> **Related:** [10_bee_cli_reference.md](10_bee_cli_reference.md) (Bee data), [11_homelab_test_deployment.md](11_homelab_test_deployment.md) (deployment), [06_aws_cloud_deployment_architecture.md](06_aws_cloud_deployment_architecture.md) (target AWS layout).

---

## 1. What changed in one paragraph

Every person now has an account (email + password). Each account is a **tenant** with its own folder on the server: its own SQLite database and its own private bee-cli login. A user connects their Bee by scanning a QR code in the dashboard; from then on a dedicated **orchestrator** (Bee stream → gatekeeper → event engine → pipeline) runs for that user only, also when nobody has the dashboard open. Every REST call, SSE stream and MCP tool call is bound to the caller's tenant, so every number, card and briefing on the page belongs to the signed-in user.

```
EXAMEN_DATA_DIR/                      (default ./data, homelab /var/lib/examen/data)
├── auth.db                           users, sessions (SHA-256 of the cookie), MCP tokens (SHA-256)
└── users/
    └── usr_<32 hex>/                 mode 700, one per account
        ├── examen.db                 everything EXAMEN knows for this user
        └── bee/                      BEE_CONFIG_DIR of this user's bee-cli login (token-production)
```

## 2. Request flow

| Caller | Credential | Resolved by | Tenant bound to |
|---|---|---|---|
| Dashboard (browser) | `examen_session` cookie: HttpOnly, SameSite=Lax, Secure over HTTPS | `AuthMiddleware` ([auth_middleware.py](../src/serving/auth_middleware.py)) | the request, including streamed SSE |
| Alexa+ / MCP client | `Authorization: Bearer exm_…` personal access token | `AuthMiddleware`, then `tenant_tool` ([tenant_tools.py](../src/serving/tenant_tools.py)) | each tool call |
| Background work | — | created inside `tenant_scope(user_id)` | asyncio tasks and `to_thread` calls inherit it |

The tenant is a context variable ([tenancy.py](../src/core/tenancy.py)). `get_storage_store()`, `get_event_engine()`, `get_backfill_service()`, `get_wearer_identity()`, `OrchestratorManager.get_instance()` and `bee_subprocess_env()` all return the current tenant's instance, so the ~50 existing call sites did not change.

**Fail-closed.** They resolve the tenant with `resolve_tenant()`: with `AUTH_ENABLED=true` and no tenant in context it raises `MissingTenant`, instead of falling back to the legacy single-user store or the host's Bee login. A forgotten `tenant_scope` is an error, never a write into shared data. The legacy objects are returned only with `AUTH_ENABLED=false` (the default of the existing test suite). Developer scripts run as an account with `EXAMEN_CLI_USER=<email>` ([cli.py](../src/core/cli.py)); `run_live_benchmark.py` uses a throw-away tenant.

**Pipeline payload.** The orchestrator and the backfill put `user_id` in every pipeline payload. `agent_invocation` runs inside `tenant_scope(payload["user_id"])`, rejects an id that differs from the caller's tenant, and rejects a payload without a user when accounts are enabled. A remote AgentCore runtime has no request context: the payload is the only carrier of the tenant.

MCP tool calls run in the MCP session manager's tasks, not in the HTTP request's context, so the middleware also stores the user id on the request (`scope["state"]["examen_user_id"]`) and each tool is wrapped to read it from FastMCP's `Context` and enter `tenant_scope`. The extra `ctx` parameter is hidden from the tool schema.

Unauthenticated `/api/*` (except `/api/auth/config|register|login|logout|session` and `/api/health`) and `/mcp` requests get `401`. Disabled accounts are treated as signed out. **Access tokens are for data and MCP only:** `/api/account*`, `/api/bee/*`, `/api/auth/sessions/*` and `/api/admin/*` need the dashboard session (`403 session_required` for a bearer token), so a leaked Alexa+ token cannot mint tokens, export or erase the account, or pair a Bee. Cookie-authenticated `POST/PUT/PATCH/DELETE` requests from a foreign `Origin` get `403` (CSRF). CORS only allows `CORS_ALLOWED_ORIGINS` (the old `*` with credentials is gone).

## 3. Accounts and GDPR

| Topic | Implementation |
|---|---|
| Password storage | scrypt (hashlib, N=2^16, r=8, p=2, 16-byte salt): one of OWASP's equivalent minimums, ≈ 64 MiB per hash (half of N=2^17, p=1, which matters on the 2 GB homelab), no extra dependency; older hashes are upgraded at the next login ([passwords.py](../src/core/auth/passwords.py)) |
| Password policy | ≥ `AUTH_MIN_PASSWORD_LENGTH` (10), ≤ 256, not containing the email, not trivially repetitive or common (NIST 800-63B style: length, no composition rules) |
| Brute force | per email `AUTH_MAX_LOGIN_FAILURES` (5) and per client address 5× that within `AUTH_LOCKOUT_MINUTES` (15) → `429` ([rate_limit.py](../src/core/auth/rate_limit.py)) |
| Registration | `AUTH_ALLOW_SIGNUP` (default `true`; `false` → `403 signup_disabled` and the sign-in page offers no *Create account*); at most `AUTH_SIGNUP_MAX_PER_IP` (5) **successful** registrations per client address per hour; a registration never creates an admin |
| Enumeration | one message for unknown email and wrong password; a dummy hash is verified for unknown emails so timing matches |
| Sessions | 32-byte random token in the cookie, only its SHA-256 in `auth.db`, `AUTH_SESSION_TTL_HOURS` (14 days), **sliding**: renewed once less than half is left; password change signs out other sessions; *Sign out everywhere* (`POST /api/auth/sessions/revoke-all`) ends every session and revokes every access token |
| Account status | `active` / `disabled` (admin or CLI): disabling signs the user out everywhere, revokes their tokens and stops their Bee stream; their data is kept |
| Audit | `audit_log` in `auth.db` with security events only (failed logins, admin actions, Bee conflicts, revocations, erasures) and **no email, name or IP address**; purged after `AUTH_AUDIT_RETENTION_DAYS` (90); a user's entries are deleted with the account |
| Data minimisation | `auth.db` holds email, password hash, optional display name, consent version and time; nothing personal in `localStorage`; logs never contain emails, names or Bee accounts |
| Consent (Art. 6, 7) | registration requires accepting the privacy notice (`privacy_consent: true`); its version and time are stored; bumping `PRIVACY_NOTICE_VERSION` asks every user again at the next visit |
| Access & portability (Art. 15, 20) | `GET /api/account/export`: JSON with the account record, token metadata and every row of the user's database |
| Erasure (Art. 17) | `DELETE /api/account` (password required): stops the user's orchestrator and engines, runs `bee logout` in their folder, deletes the folder and the account row (sessions and tokens cascade) |
| Third parties | the privacy notice tells users that contacts' names, roles and promises are recorded and to use ambient capture only where allowed |

**Not yet:** email verification and self-service password reset need a mail service; until then the operator resets passwords with `scripts/manage_users.py reset-password`. Encryption at rest is left to the disk / volume (per-user files make per-user keys a straightforward next step).

## 4. Bee pairing per user (how bee-cli logs in)

Facts from `resources/bee-cli/sources` that shaped the design:

1. **The token is in the OS keychain under a fixed key** (`bee-cli` / `token:<env>`, `secureStore.ts`); `BEE_CONFIG_DIR` is only used by the file fallback. Two users on one host would overwrite each other. EXAMEN therefore runs **every** `bee` call for a tenant with `BEE_FORCE_FILE_STORE=1` and `BEE_CONFIG_DIR=<user folder>/bee` (`bee_subprocess_env()`), including the stream, the private `bee proxy`, `bee me`, `bee locations`, history calls and `bee status`.
2. **`bee login --no-wait` never completes a pairing**: it prints the link and exits; re-running it only re-prints the link. Only a blocking `bee login` polls the API (every 2 s) and saves the token.
3. The link is `https://bee.computer/connect#<request id>` and expires after about 5 minutes.

Flow ([bee_pairing.py](../src/ingestion/bee_pairing.py), [auth_routes.py](../src/serving/auth_routes.py)):

```
Dashboard "Connect my Bee"  ──POST /api/bee/pair──►  BeePairing.start()
                                                      spawns `bee login` (user env), reads
                                                      "Authentication link: …" from stdout
          ◄── {status: pending, pairing_url, expires_in_seconds} ──
QR code of pairing_url (qrcode lib)  ── user scans / opens link, approves in the Bee app
          ── GET /api/bee/pair every 2 s ──►  `bee login` exits 0 → token in users/<id>/bee/
          ◄── {status: connected} ──           on_connected → start_tenant_runtime(user)
                                                → user's OrchestratorManager starts streaming
```

**One Bee account per EXAMEN user.** When `bee login` exits 0, `link_bee_account()` ([auth_routes.py](../src/serving/auth_routes.py)) runs `bee me` with the user's login (the pairing reports `verifying` meanwhile) and records the Bee account in `bee_links`. If another EXAMEN user already holds that Bee account, the new login is removed from **this** user's folder only, the pairing reports `conflict` and no runtime starts: two accounts reading one Bee would duplicate every action, contact and event. A token the Bee API stops accepting (`bee status` → *Not logged in* while a token file exists) turns the link `invalid` and the dashboard asks to reconnect.

`POST /api/bee/disconnect` stops the user's orchestrator, runs `bee logout` for that user only and deletes the link. **Signing out of the dashboard no longer disconnects the Bee** (the old behaviour logged the whole host out, audit item C11 in doc 10): ambient listening continues until the user disconnects or deletes the account.

The old `/api/auth/bee-link` and `/api/auth/bee-disconnect` routes remain as aliases. The fake fallback link (`bee_<random>`) the old code returned when the CLI was missing is gone: the UI now reports the error.

## 5. Per-user runtimes

| Component | Before | Now |
|---|---|---|
| Orchestrator | one `OrchestratorManager`, started by any status poll | one per user; starts only when the user's folder holds a Bee token; started on sign-in, after pairing and at server start for every paired user (`AUTO_START_USER_ORCHESTRATORS`) |
| Event engine | singleton `_engine` / `_runtime` | one per user, bound to the user's store |
| Backfill service | singleton | one per user, only once a Bee is paired |
| Wearer identity | `bee me` once per host (or `BEE_WEARER_NAME`) | `bee me` with the user's login (`BEE_WEARER_NAME` applies only in single-user mode) |
| SSE `/api/events` | one subscriber set | one set per user; `broadcast_event` targets the current tenant |
| `bee status` probe cache | one | one per user |

Each user's `bee proxy` takes its own free port from 8787 (`BEE_PROXY_PORT=0`); keep it at `0` with more than one user.

**Shared limits** ([limits.py](../src/core/limits.py)):
- `MAX_CONCURRENT_LLM_CALLS` (8): `llm_slot()` wraps every gatekeeper call and pipeline dispatch, live and backfill (utterance and window screening), across all users. One user's history backfill cannot starve the live stream of the others.
- `MAX_ACTIVE_USERS` (5): live Bee streams at once. Beyond it a user's Bee stays paired and the stream waits; the orchestrator and the Bee status report `CAPACITY` until a slot frees up (the next status poll starts it).

## 6. API reference

| Route | Auth | Purpose |
|---|---|---|
| `GET /api/health` | public | liveness probe (homelab updater) |
| `GET /api/auth/config` | public | `auth_enabled`, `signup_enabled`, password length, notice version |
| `POST /api/auth/register` | public | `{email, password, display_name?, privacy_consent: true}` → 201 + cookie |
| `POST /api/auth/login` | public | `{email, password}` → cookie, `consent_required` |
| `POST /api/auth/logout` | public | revokes the session cookie |
| `POST /api/auth/sessions/revoke-all` | session | sign out everywhere, revoke every access token |
| `GET /api/auth/session` | public | `{auth_enabled, authenticated, user, consent_required, bee_device, bee}` |
| `GET / PATCH / DELETE /api/account` | session | profile; `{display_name}` or `{privacy_consent: true}`; erasure with `{password}` |
| `POST /api/account/password` | session | `{current_password, new_password}` |
| `GET /api/account/export` | session | JSON download |
| `GET / POST /api/account/tokens`, `DELETE /api/account/tokens/{id}` | session | MCP tokens (shown once) |
| `GET / POST / DELETE /api/bee/pair` | session | pairing status / start / cancel |
| `POST /api/bee/disconnect` | session | remove this user's Bee login |
| `GET / POST /api/admin/users` | admin session | accounts with Bee link state and streaming flag / create one with a one-time password |
| `POST /api/admin/users/{id}/status` | admin session | `{"status": "active" \| "disabled"}` (not on yourself) |
| `POST /api/admin/users/{id}/reset-password` | admin session | one-time password; signs the user out |
| everything else under `/api/*`, and `/mcp` | session or bearer | scoped to the caller |

Admins manage **accounts only** ([admin_routes.py](../src/serving/admin_routes.py)): no admin route returns a user's speech-derived data, and every change is audited. Runtime settings and the service log for admins are specified in [next_steps/admin_console/](next_steps/admin_console/00_overview.md).

Dashboard: [AuthScreen.tsx](../src/web_ui/src/components/ui/AuthScreen.tsx) (sign in / create account / re-consent), the account modal [LoginModal.tsx](../src/web_ui/src/components/ui/LoginModal.tsx) (Bee QR pairing with `verifying` / `conflict` / `invalid` / `CAPACITY` states, name, password, MCP tokens, sign out everywhere, export, deletion, and the *Admin* tab of [AdminSection.tsx](../src/web_ui/src/components/ui/AdminSection.tsx) for admins), [utils/auth.ts](../src/web_ui/src/utils/auth.ts) and `installCredentialedFetch` in [utils/api.ts](../src/web_ui/src/utils/api.ts) (sends the cookie on API calls only, reports 401s). The dashboard mounts only after sign-in and unmounts on sign-out, so no data of one user survives in the browser for the next.

## 7. Operations

```bash
# Install / build (the dashboard gained the `qrcode` dependency)
uv sync
./scripts/build_ui.sh                       # bun install && bun run build

# Accounts from the server shell
python scripts/manage_users.py list
python scripts/manage_users.py create --email ana@example.com
python scripts/manage_users.py reset-password --email ana@example.com
python scripts/manage_users.py claim-legacy-db --email ana@example.com --db examen.db   # move single-user data in
python scripts/manage_users.py delete --email ana@example.com
python scripts/manage_users.py promote --email ana@example.com [--revoke]   # grant / remove admin
python scripts/manage_users.py disable --email ana@example.com              # or: enable
```

**First admin.** `EXAMEN_BOOTSTRAP_ADMIN=<email>` (optionally `EXAMEN_BOOTSTRAP_ADMIN_PASSWORD`) creates an admin at start-up **while no admin exists**; without a password, a one-time one is printed once in the log (`journalctl -u examen | grep "Bootstrap admin"`). An account that already holds the address is never promoted, since anyone can register any address. Use `manage_users.py promote` to promote an account on purpose.

**Developer scripts** need an account when `AUTH_ENABLED=true`: `EXAMEN_CLI_USER=ana@example.com python scripts/populate_db.py` (also `reset_db.py`, which resets that user's database only, `live_tester.py`, `simulate_mock_conversations.py`).

Migrating an existing single-user install: create (or register) the owner's account, run `claim-legacy-db`, then pair the Bee again from the dashboard (the old host-wide token is not reused, on purpose). Back up `EXAMEN_DATA_DIR` as a whole: `auth.db` and the user folders belong together.

Settings: see `.env.example` (`AUTH_*`, `EXAMEN_DATA_DIR`, `EXAMEN_BOOTSTRAP_ADMIN*`, `PRIVACY_NOTICE_VERSION`, `CORS_ALLOWED_ORIGINS`, `AUTO_START_USER_ORCHESTRATORS`, `MAX_ACTIVE_USERS`, `MAX_CONCURRENT_LLM_CALLS`, `MCP_ALLOWED_HOSTS`). `AUTH_ENABLED=false` restores the single-user behaviour.

**`MCP_ALLOWED_HOSTS`:** FastMCP's DNS-rebinding protection only accepted `localhost` / `127.0.0.1` Host headers, so `/mcp` answered `421 Misdirected Request` behind a reverse proxy (homelab `examen.deggio.local`, AWS). Add the public host name there.

## 8. Towards AWS

The tenant boundary maps directly onto the target design of doc 06: `user_id` becomes the DynamoDB partition key and the AgentCore Memory `actorId`; per-user Bee tokens move from files to Secrets Manager (one secret per user, KMS-encrypted); the in-memory login limiter and SSE fan-out move to a shared store (ElastiCache or DynamoDB TTL) when more than one server instance runs; Alexa+ account linking replaces manually created MCP tokens with OAuth.

## 9. Known limits

- One server process: the login limiter, pairing state and SSE subscribers are in memory.
- No email verification or self-service reset yet (§3).
- Each paired user runs one `bee proxy` subprocess and one stream (each a Bun process); `MAX_ACTIVE_USERS` caps them, but measure memory (MU-V2) before raising it on the 2 GB homelab container.
- A user waiting for a free stream slot (`CAPACITY`) starts on their next status poll, not the moment a slot frees up.
- Crashed per-user runtimes are not supervised beyond the Bee client's own reconnect back-off (1 → 60 s) and CLI fallback.

## 10. Decisions and provenance

The account model, tenancy, MCP tool wrapping, QR pairing and GDPR routes come from `feature/multi-user-auth`. The following were ported from the parallel implementation on branch `sessions`, compared in that branch's `docs/next_steps/multi_user/06_branch_comparison.md`:

| Decision | Choice |
|---|---|
| Missing tenant with accounts enabled | Fail-closed (`MissingTenant`) |
| Administration | Admin flag + dashboard *Admin* tab + `manage_users.py promote/disable/enable`; bootstrap admin while none exists |
| Registration | Open by default, `AUTH_ALLOW_SIGNUP` toggle, successful registrations limited per address |
| Bee accounts | One Bee account per EXAMEN user (`bee_links`), `invalid` login detection |
| Shared limits | `MAX_CONCURRENT_LLM_CALLS`, `MAX_ACTIVE_USERS` |
| Pipeline | `user_id` in every payload, checked by `agent_invocation` |
| Access tokens | Data and MCP only; account, Bee and admin routes need a session |
| Sessions | Sliding expiry, sign out everywhere |
| Audit | Minimal, no personal data, 90-day retention |
| Password hash | scrypt N=2^16, r=8, p=2 |
| Not ported | Bee token migration (the Bee is paired again after `claim-legacy-db`), a supervisor that restarts crashed runtimes, running the whole legacy suite as a user |
