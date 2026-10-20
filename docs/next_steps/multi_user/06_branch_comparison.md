# 06 — Comparison of the two multi-user implementations

> Part of the [Multi-User Support](00_overview.md) specification.
> **Date:** 2026-10-20 (second pass, after `ae18d7f`)
> **Compared:** branch `sessions` (commits `40dd02c`, `3f57f35`, `e5d810c`, on top of `main` `390699b`) and branch `feature/multi-user-auth` (commits `b094c69` and `ae18d7f`, on top of `823152f`, documented in its `docs/13_multi_user_accounts.md` and `docs/next_steps/historical_backfill/07_conversation_windows.md`).
> **Audience:** the EXAMEN team, to decide which implementation reaches `main` and what moves across.
> **Note:** written by the author of `sessions`. Each finding marked *verified* was reproduced with a throw-away test against both trees (§5); the rest comes from reading the code.

---

## 0. Changes since the first comparison

`feature/multi-user-auth` gained one commit, `ae18d7f`: *conversation-level history analysis* plus a *persistent stop* for backfill runs. It changes `backfill.py`, the backfill settings and schema, the backfill UI and `tests/test_backfill.py`. It does **not** touch authentication, MCP, Bee pairing or tenancy (0 files changed under `src/serving`, `src/core/auth`, `tenancy.py`, `bee_pairing.py`).

| Item | Result of the second pass |
|---|---|
| Findings §5.1 (MCP session reuse) and §5.2 (Bee pairing) | Unchanged: probe re-run on `ae18d7f`, same results |
| Finding §5.3 (`/mcp` behind the proxy) | **Corrected.** The first pass said `feature/multi-user-auth` answers `200`. Re-tested: with the default `MCP_ALLOWED_HOSTS` it also answers `421`, and `200` only after the host is added. Its doc 11 tells the operator to add it. The difference is that the setting exists |
| New feature | Backfill window screening and persistent stop, absent from `sessions` (§4.1). Worth porting (§6, item 8) |
| Merge | Still **18 conflicting files**; `backfill.py` still has one conflict hunk. **New hazard:** the auto-merged window path drops the global LLM limit of `sessions` without any conflict (§5.5) |
| Tests | §5.4 updated |

---

## 1. Summary

The two branches solve the same problem with the same core idea:
- one SQLite file per user under `EXAMEN_DATA_DIR/users/<user_id>/`;
- one private `BEE_CONFIG_DIR` per user, with `BEE_FORCE_FILE_STORE=1`;
- a context variable that carries the current user, and `get_storage_store()` resolving through it, so the ~50 call sites stay unchanged;
- one orchestrator, Event Engine and backfill service per user, and per-user SSE;
- an HttpOnly session cookie for the dashboard and personal access tokens for MCP;
- dashboard logout no longer runs `bee logout`.

They differ in four places:
1. **What happens when the user is missing.**
2. **How MCP tool calls get their user.**
3. **How Bee pairing completes.**
4. **Account model:** username + admin, or e-mail + consent, with no admin.

Each branch has defects the other one does not. Three of the defects in `sessions` were verified (§5):
- **An MCP session opened by user A serves A's data to user B** who reuses its session id.
- **Bee pairing never completes.**
- **`/mcp` answers `421` behind the homelab reverse proxy.**

`feature/multi-user-auth` gets the first two right. For the third it adds a setting (`MCP_ALLOWED_HOSTS`) that has to be configured on the server.

Since `ae18d7f`, `feature/multi-user-auth` also analyses Bee history **by conversation windows**, which needs about 3–5× fewer gatekeeper calls. `sessions` does not have this yet.

The branches cannot be merged: `git merge-tree` reports **18 conflicting files**, including `mcp_server.py`, `storage/__init__.py`, `event_engine.py`, `stream_convo.py`, the dashboard auth files and `conftest.py`. One branch has to be the base, and features are ported from the other (§6).

---

## 2. Architecture

| Topic | `sessions` | `feature/multi-user-auth` |
|---|---|---|
| User context | `UserContext{user_id, is_admin, auth_method}` in `current_user_ctx` ([identity.py](../../../src/core/identity.py)) | Plain `user_id` in a `ContextVar` (`src/core/tenancy.py`, `tenant_scope`) |
| **No user in context** | **Fail-closed:** `get_storage_store()` raises `MissingUserContext` | **Fail-open:** falls back to the legacy single-user store `SQLITE_DB_PATH` and the host's own Bee login. Also used on purpose by `AUTH_ENABLED=false`, the CLI scripts and the test suite |
| Single-user mode | None (decision D10): local dev uses the bootstrap admin | `AUTH_ENABLED=false` keeps the old behaviour (no login, shared DB) |
| System data | `system.db`: users, web_sessions, api_tokens, **bee_links**, **audit_log** | `auth.db`: users, sessions, api_tokens |
| Per-user runtime | `UserRuntime` / `UserRuntimeManager` ([user_runtime.py](../../../src/serving/user_runtime.py)) that owns stream, orchestrator, engine, coverage and backfill; restart back-off | Per-tenant dictionaries in each module (`OrchestratorManager._tenant_instances`, `_tenant_engines`, `_tenant_services`, `_tenant_identities`) plus `start_tenant_runtime` / `stop_tenant_runtime` hooks |
| Resource limits | `MAX_ACTIVE_USERS` (live streams) and a global `MAX_CONCURRENT_LLM_CALLS` semaphore ([limits.py](../../../src/core/limits.py)) | None |
| Pipeline / AgentCore payload | `user_id` in the payload; `agent_invocation` rejects a missing or foreign id | No `user_id`: works locally (`to_thread` inherits the context) but **loses the user when the pipeline runs remotely on AgentCore** |
| Bee subprocess env | `BeeClient(config_dir=…)`, explicit | `BeeClient()` reads the current tenant **when constructed**; no tenant means the host login |
| Wearer identity | Per user, `forget_wearer_identity` on relink | Per user; `BEE_WEARER_NAME` applies only in single-user mode |
| Migration of an existing install | `scripts/migrate_to_multi_user.py`: data **and Bee token** to the owner, idempotent | `manage_users.py claim-legacy-db`: data only; the Bee is paired again on purpose |
| Merge base | `main` (includes the pull-based homelab updater `390699b`) | `823152f`: missing `390699b`. With its `update.sh` checking `/api/status` (now `401`), the first auto-update after merging would roll itself back |

**Risk of the fail-open model.** Any code path that runs without the tenant set writes silently into the shared legacy database or uses the host's Bee login. Examples: a task created outside `tenant_scope`, a `BeeClient` built too early, an MCP tool registered without `tenant_tool`. No error is raised. With `sessions` the same mistake raises `MissingUserContext`. This was the reason for decision D10 ([00](00_overview.md) §3).

---

## 3. Authentication and accounts

| Topic | `sessions` | `feature/multi-user-auth` |
|---|---|---|
| Identifier | Username (3–32 `[A-Za-z0-9._-]`, case-insensitive) | E-mail (normalised, plausibility check) |
| Registration | `POST /api/auth/signup` (`AUTH_ALLOW_SIGNUP`, default on), never admin, **5 sign-ups per IP per hour** | `POST /api/auth/register`, always on in multi-user mode; the rate limiter counts **failed** attempts only, so successful sign-ups are unlimited |
| Privacy consent | Not collected | Required at registration (`privacy_consent: true`), version and time stored; bumping `PRIVACY_NOTICE_VERSION` asks again; privacy notice page |
| Admin | Bootstrap admin (`EXAMEN_BOOTSTRAP_ADMIN`, created while no admin exists); admin panel: list with Bee state, create, disable, reset password | **No admin role.** Accounts are managed from the server shell (`scripts/manage_users.py list/create/reset-password/delete`). Users cannot be disabled, only deleted |
| Password hashing | Argon2id (`argon2-cffi`, 64 MiB, t=3, p=4), rehash on login | scrypt (`hashlib`, N=2^17 ≈ 128 MiB per hash), rehash on login. **No extra dependency**, but ≈ 128 MiB for every login or registration on a 2 GB container |
| Password policy | ≥ 12 characters | ≥ 10, ≤ 256, not containing the e-mail, not repetitive or common (NIST 800-63B style) |
| Account enumeration | Same message for unknown user and wrong password; no timing protection | Same message **and** a dummy hash is checked for unknown e-mails (equal timing) |
| Login rate limit | 5 per username, 20 per IP, 15 min | 5 per e-mail, 25 per IP, 15 min |
| Session | 14 days, **sliding** expiry; logout; "sign out everywhere" | 14 days, fixed expiry; logout |
| Password change | Revokes every session, including the current one | Revokes the **other** sessions and keeps the current one |
| CSRF | Custom header `X-Requested-With: examen` on cookie requests (forces a CORS pre-flight) | `Origin` / `Referer` must match the server or `CORS_ALLOWED_ORIGINS`; requests with neither header are allowed |
| CORS | Regex allowing `localhost` / `127.0.0.1` with credentials | Explicit `CORS_ALLOWED_ORIGINS` list |
| Cookie `Secure` | `AUTH_COOKIE_SECURE=true/false` | `auto`: set when the request (or `X-Forwarded-Proto`) is HTTPS |
| Personal access tokens | `exm_pat_…`, a token cannot mint tokens | `exm_…` with a visible prefix in the list |
| Audit | `audit_log` (login, failures, sign-up, admin actions, Bee link events) | Logs without personal data; no audit table |

---

## 4. Bee, MCP, GDPR, dashboard

| Topic | `sessions` | `feature/multi-user-auth` |
|---|---|---|
| **MCP user resolution** | `AuthMiddleware` sets the context variable; tools rely on it reaching them. **Verified wrong for a reused MCP session** (§5.1) | `tenant_tool` wraps each of the 12 tools and reads the user from **the HTTP request carrying the call** (`ctx.request_context.request.state`). Verified correct |
| **`/mcp` behind a reverse proxy** | FastMCP's DNS-rebinding check allows only localhost: **`421 Invalid Host header`** with `Host: examen.deggio.local` (verified); no setting to change it | `MCP_ALLOWED_HOSTS` → `TransportSecuritySettings`. Default still localhost only (`421`, verified); `200` once the host is added in `.env` (verified), as its doc 11 instructs |
| **Bee pairing** | `bee login --no-wait`, then `GET /api/bee/link` re-runs `bee login --no-wait` to "resume". **bee-cli never completes a pairing that way** (§5.2), so the link stays `pairing` until it expires | A blocking `bee login` runs in the background for up to 330 s; the link is read from its output; exit code 0 means the token is saved and the user's runtime starts |
| Pairing UI | Link shown in the account panel, dashboard polls | **QR code** (`qrcode` package) plus link, countdown, cancel |
| One Bee account per user | Enforced: `bee_links` keyed by `bee_user_id`; a second EXAMEN user pairing the same account gets `409` and is logged out | Not enforced (listed as a known limit) |
| "Linked" means | `bee status` + `bee me` verified, state machine `unlinked → pairing → linked → invalid` | A non-empty `token-*` file exists in the user's Bee folder |
| Bee status probe | Read from the link and the runtime; no subprocess per request | `bee status` with the user's env, cached per user |
| Disconnect / erase | `POST /api/bee/unlink`; `POST /api/account/erase` (password): stops the runtime, `bee logout`, deletes the folder and the account | `POST /api/bee/disconnect`; `DELETE /api/account` (password): same steps |
| **Data export (Art. 15 / 20)** | Client-side JSON with profile and telemetry only: **does not contain the user's data** | `GET /api/account/export`: server-side JSON with the account, token metadata and **every row of the user's database** (`export_all`) |
| Legacy routes | Removed | `/api/auth/bee-link`, `/api/auth/bee-disconnect` kept as aliases |
| Dashboard | `LoginModal`: Sign in / Create account tabs, then account panel (Bee, tokens, password, admin) | `AuthScreen` (sign in / create account / re-consent) mounted before the dashboard, which unmounts on sign-out; account modal with tabs (Bee QR, profile, password, tokens, privacy) |

### 4.1 Historical backfill (`ae18d7f`)

| Topic | `sessions` | `feature/multi-user-auth` |
|---|---|---|
| Unit of analysis | Utterances inside the gap | `BACKFILL_WHOLE_CONVERSATIONS=true`: each Bee conversation overlapping the gap is taken whole; preview statuses `missed` / `partial` |
| Screening | One gatekeeper call per utterance, 3 lines of look-back | `BACKFILL_SCREENING=window` (default): windows of 10 utterances / 450 words with the Bee title and summary and 3 utterances before and after. Stage 1 is one call per window; stage 2 screens each utterance only in windows with signal. About `W + q·N` calls instead of `N` (3–5× fewer for ambient speech); `utterance` restores the old mode |
| Pipeline context | Utterance + 3 lines | Utterance + its window (look-ahead included) |
| Stop | In memory (`_cancelled`): lost if the process stops before the run does | `cancel_requested` stored on the run; `rehydrate()` marks it `cancelled` after a restart. *Stop analysis* button in the History Sync window, the Overview card and the dock |
| Per user | One `BackfillService` per user; gatekeeper calls take a slot of the global `MAX_CONCURRENT_LLM_CALLS` | One service per tenant; concurrency limited per run (`BACKFILL_SCREEN_CONCURRENCY`), no global limit across users |
| Isolation | — | The new code holds no module-level state; it uses the service's own store and engine, so it stays per user |

Trade-off stated by its author: a window classified *noop* skips all its utterances, so a very short action inside long chatter can be missed. Pending task titles are injected into the window prompt to reduce this.

---

## 5. Verified findings

The probes ran against both trees with the same virtualenv and were deleted afterwards (they are not in either branch).

### 5.1 MCP session reused by another user

Steps:
1. User A opens an MCP session (`initialize`) with A's token.
2. User B calls `tools/call get_upcoming_tasks` with **B's token** and **A's `mcp-session-id`**.

| Branch | A on A's session | B on A's session | B on B's session |
|---|---|---|---|
| `sessions` | A's data | **A's data** ❌ | B's data |
| `feature/multi-user-auth` | A's data | B's data ✅ | B's data |

Cause: in stateful streamable HTTP, the MCP SDK runs tool calls in the session's task. That task was created during the `initialize` request, so the context variable keeps A's user. The `sessions` test (T-MU-9) opens a new session for every call and therefore missed it.

Severity: the session id is a random UUID, so B must obtain it first (logs, proxy, shared client). It is still a cross-user data leak and must be fixed before real users. Two possible fixes:
- adopt `tenant_tool` from `feature/multi-user-auth`;
- bind each MCP session id to the user who opened it and reject other users with `404`.

### 5.2 `bee login --no-wait` cannot finish a pairing

Source: `resources/bee-cli/sources/commands/login/index.ts`, `loginWithAppPairing`. When a pairing state that has not expired exists, `--no-wait` prints the link again and returns **before** `pollForAppToken`. Only a blocking `bee login` polls the API and saves the token.

Effect on `sessions`: `refresh_link()` ([bee_accounts.py](../../../src/serving/bee_accounts.py)) relies on that "resume", so a pairing approved in the Bee app is never picked up. The link state ends as `unlinked` ("The pairing request expired"). The offline tests use a fake `bee` and cannot catch this. `feature/multi-user-auth` does it correctly.

### 5.3 `/mcp` behind the homelab proxy

`POST /mcp` with `Host: examen.deggio.local` gives:

| Branch | Default settings | Host added to the allow-list |
|---|---|---|
| `sessions` | `421 Invalid Host header` | Not possible: no setting |
| `feature/multi-user-auth` | `421 Invalid Host header` | `200` with `MCP_ALLOWED_HOSTS=localhost:*,127.0.0.1:*,examen.deggio.local` |

*Correction:* the first pass reported `200` for `feature/multi-user-auth` from reading the code. The test run in the second pass shows the default is `421` there too.

The same issue exists on `main` today, so Alexa+ / MCP clients cannot reach the homelab instance through NPM. The setting must be read when `FastMCP` is created (module import), so it goes in `.env`, not into a running process.

### 5.4 Test suites

| Branch | Full suite | Multi-user tests |
|---|---|---|
| `sessions` | 374 passed | `tests/test_multi_user.py`: 29 tests. Every existing test runs **as a user** (`TEST_USER_ID`) |
| `feature/multi-user-auth` | `b094c69`: 369 passed. `ae18d7f`: 375 passed, 6 of them new backfill tests (both run with the `sessions` virtualenv) | `tests/test_accounts.py`: 21 tests. Existing tests run in **single-user mode** (`AUTH_ENABLED=false`), so they do not exercise the per-user code paths |

### 5.5 Merge hazard: the global LLM limit is lost on the window path

`git merge-tree` of `sessions` and `ae18d7f` merges most of `backfill.py` without conflicts. In the result:
- the legacy path `_screen()` keeps the `async with llm_slot()` from `sessions`;
- the new `_screen_text()`, used by stage 1 and stage 2 of the **default** window mode, calls the gatekeeper **without** `llm_slot()`.

After such a merge, one user's backfill would no longer share `MAX_CONCURRENT_LLM_CALLS` with the live ingestion of every user, and no conflict would point at it. Whoever ports the feature must wrap `_screen_text()` in `llm_slot()` and add a test that counts concurrent gatekeeper calls across two users.

---

## 6. Recommendation

Use **`sessions` as the base**, for four reasons:
- it is already on top of `main`;
- it covers more of the multi-tenant surface: admin, Bee account uniqueness, audit, resource limits, the AgentCore payload, Bee token migration;
- its fail-closed model turns a forgotten user context into an error instead of a silent write to shared data;
- its whole suite runs per user.

From `feature/multi-user-auth`, port these in order:

| # | Item | Why |
|---|---|---|
| 1 | Per-call MCP user resolution (`tenant_tool`, adapted to `UserContext` and `acting_as`) | Fixes §5.1 |
| 2 | Pairing with a blocking `bee login` (`BeePairing`) and the QR code in the dashboard | Fixes §5.2; better UX |
| 3 | `MCP_ALLOWED_HOSTS` → `TransportSecuritySettings` | Fixes §5.3 (also needed on `main`) |
| 4 | Server-side export `GET /api/account/export` + `export_all()` | Real GDPR Art. 15 / 20 |
| 5 | Privacy consent at sign-up, notice versioning and re-consent | GDPR Art. 6 / 7 |
| 6 | Dummy-hash timing protection, password-policy checks, "keep this session" on password change | Hardening |
| 7 | `AUTH_COOKIE_SECURE=auto`, explicit `CORS_ALLOWED_ORIGINS` | Easier HTTPS rollout (open question Q3) |
| 8 | Backfill window screening, whole-conversation selection and persistent stop (`ae18d7f`, §4.1), with `_screen_text()` wrapped in `llm_slot()` (§5.5) | 3–5× fewer gatekeeper calls, better context; a stop survives restarts |

Decisions for the team before porting:

| Question | `sessions` | `feature/multi-user-auth` | Proposal |
|---|---|---|---|
| Account identifier | Username | E-mail | E-mail if password reset by e-mail is planned; otherwise username (the homelab has no SMTP) |
| Single-user mode | None (D10) | `AUTH_ENABLED=false` | Keep D10: one code path, and the fail-open fallback is what makes isolation bugs silent |
| Admin | Bootstrap admin + panel | Shell script | Keep the admin, and add `manage_users.py` as an operator fallback |
| Password hash | Argon2id (dependency) | scrypt 128 MiB (stdlib) | Argon2id: same security at half the memory per login on the 2 GB container |

If the team prefers `feature/multi-user-auth` as the base, these must move the other way before it reaches users:
- the `main` updater commit and `/api/health`;
- a global limit on concurrent LLM calls across users (the window backfill makes bursts of calls per run);
- a limit on successful sign-ups;
- `user_id` in the AgentCore payload;
- Bee account uniqueness;
- a fail-closed check when `AUTH_ENABLED=true` and no tenant is set.

---

## 7. Appendix: how this was produced

- First pass (`b094c69`): `git archive` into a scratch directory; full read of `tenancy.py`, `auth/*`, `auth_middleware.py`, `auth_routes.py`, `tenant_tools.py`, `bee_pairing.py`, the `mcp_server.py`, ingestion and storage diffs, `test_accounts.py` and doc 13.
- Second pass (`ae18d7f`): diff `b094c69..ae18d7f` (backfill only) and its doc 07; probes §5.1 and §5.3 re-run on the new tree, §5.3 also with `MCP_ALLOWED_HOSTS` set; full suite re-run.
- Probes: throw-away tests run with `pytest` on each tree, then deleted.
- §5.2: bee-cli source reading.
- Conflicts and §5.5: `git merge-tree --write-tree sessions <commit>`, then reading the merged `backfill.py`.
