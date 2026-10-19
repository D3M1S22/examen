# 05 — Implementation Plan, Tests & Acceptance Criteria

> Part of the [Multi-User Support](00_overview.md) specification.

---

## 0. Status

| Phase | Status |
|---|---|
| 0 Verifications | ⏳ Not started |
| 1–6 | ⏳ Not started (specification only; decisions D1–D10 of [00](00_overview.md) §3 to confirm) |

---

## 1. Phases

Each phase leaves the suite green (`.venv/bin/pytest tests/ -q`) and the homelab instance deployable. Multi-user is the only mode (D10): until phase 6 is deployed, the homelab keeps running `main`.

### Phase 0: Verifications (½ day)
| # | Question | How |
|---|---|---|
| MU-V1 | Can a token produced by the interactive login be restored with `bee login --token-stdin` (AWS secrets path)? | Copy `token-prod` into a fresh `BEE_CONFIG_DIR`, run `--token-stdin`, then `bee status` |
| MU-V2 | RSS of one private `bee proxy` + stream over 1 h | `ps` / `smem` on the homelab |
| MU-V3 | CPU / memory of 5 Event Engine runtimes ticking | Synthetic users with the simulator |
| MU-V4 | Two **different** Bee accounts streaming concurrently from one host | Needs a second Bee account (open question Q1) |
| MU-V5 | `BEE_CONFIG_DIR` + `BEE_FORCE_FILE_STORE=1` isolate two logins on a host **with** a keychain (developer laptop) | Two directories, two `bee status` |

### Phase 1: Identity core
1. `src/core/identity.py`: `UserContext`, `current_user_ctx`, `MissingUserContext`.
2. `SystemStore` (SQLite) with `users`, `web_sessions`, `api_tokens`, `bee_links`, `audit_log` ([02](02_identity_and_bee_accounts.md) §1).
3. `LocalAuthProvider` (Argon2id, cookie sessions, PATs, rate limit, CSRF header); `AUTH_PROVIDER` setting.
4. Auth middleware; `/api/auth/*`, `/api/account/*`, `/api/admin/*`, `/api/health`.
5. Bootstrap admin (`EXAMEN_BOOTSTRAP_ADMIN`).
- **Exit:** every route except the public ones returns `401` without a session; login / logout / PAT tests pass.

### Phase 2: Scoped storage
1. `StoreRegistry` (`system()`, `for_user()`, `drop_user()`); `EXAMEN_DATA_DIR`.
2. Replace the 49 `get_storage_store()` call sites ([01](01_current_state.md) §4) with `ctx.store` (requests), the runtime store (background) or `registry.for_user(state["user_id"])` (pipeline). Delete the global accessor.
3. Move `web_search_cache` and latency telemetry into the user store.
4. `scripts/migrate_to_multi_user.py` ([03](03_tenant_isolation_and_runtime.md) §2.4).
- **Exit:** isolation tests T-MU-1…4 pass; grep finds no unscoped store access.

### Phase 3: Per-user Bee & runtime
1. `BeeClient(config_dir=…)` passing `BEE_CONFIG_DIR` / `BEE_FORCE_FILE_STORE` to every subprocess (stream, proxy, login, status, me, locations, conversations).
2. Bee link API and pairing state machine ([02](02_identity_and_bee_accounts.md) §4.2), `bee_user_id` uniqueness.
3. `UserRuntime` / `UserRuntimeManager` replacing `OrchestratorManager`, `get_event_engine*`, `get_backfill_service`, `get_wearer_identity`; global limits ([03](03_tenant_isolation_and_runtime.md) §3.3).
4. Per-user SSE bus; `broadcast_event(user_id, …)`.
- **Exit:** two fake users with fake Bee streams run concurrently and never cross (T-MU-5…8).

### Phase 4: Pipeline & MCP
1. `ExamenState.user_id` (required) and pipeline nodes on scoped stores; AgentCore payload field.
2. FastMCP `token_verifier` (`PatTokenVerifier`) and tools resolving the user from the access token.
- **Exit:** an MCP client with user A's token only sees A's data (T-MU-9).

### Phase 5: Dashboard
Sign-in screen, credentialed fetch / SSE, Bee link card, account page (tokens, erase), admin page; remove the profile directory ([04](04_serving_api_ui_aws.md) §4). Unit tests for the auth state reducer (`bun test`).

### Phase 6: Homelab rollout & docs
1. `EXAMEN_DATA_DIR=/var/lib/examen/data`; run the migration for the existing owner; `update.sh` health check on `/api/health`.
2. Update [11_homelab_test_deployment.md](../../11_homelab_test_deployment.md), [10_bee_cli_reference.md](../../10_bee_cli_reference.md) (C11 superseded), AGENTS.MD, README, `.env.example`.
- **Exit:** acceptance criteria §3 on the homelab with two real users.

### Phase 7 (later): AWS providers
`CognitoAuthProvider` + `CognitoTokenVerifier`, `DynamoContextStore` / `AgentCoreMemoryStore`, Secrets Manager Bee credentials, ingestion worker service ([04](04_serving_api_ui_aws.md) §5).

---

## 2. Test matrix

All tests are offline: fake Bee subprocesses (as in `tests/test_bee_stream.py`), fake gatekeeper / pipeline, temporary data dirs. `tests/conftest.py` keeps blocking the real `bee` binary.

| ID | Scenario | Expectation |
|---|---|---|
| T-MU-1 | User A creates an action, contact, task, event; user B lists everything | B sees nothing; B's `GET /api/sessions/{A's id}` → `404` |
| T-MU-2 | A and B both meet "Marco" | Two independent contacts, commitments and web profiles |
| T-MU-3 | Same web search query from A and B | Separate cache entries; B's search never hits A's cache |
| T-MU-4 | Unscoped access | Calling store-dependent code without a user raises `MissingUserContext`; a static check finds no `get_storage_store()` |
| T-MU-5 | A's stream is live, B's is down | B's coverage shows the gap; A's coverage does not close it |
| T-MU-6 | A's backfill run | Reads only A's ledger and Bee history (A's `BEE_CONFIG_DIR`) |
| T-MU-7 | SSE with two users and two tabs each | Each tab receives only its user's events |
| T-MU-8 | Unlink / disable / erase A while B streams | B's runtime and data unaffected; A's directory removed; `bee logout` ran only with A's config dir |
| T-MU-9 | MCP with A's PAT; revoked PAT; no token | A's data; `401`; `401` |
| T-MU-10 | Bee account already linked to A is paired by B | `409`, B's config dir logged out, A untouched |
| T-MU-11 | Auth | Wrong password, rate limit, expired / revoked session, CSRF header missing |
| T-MU-12 | Migration | Old `examen.db` → owner's store with identical row counts; second run is a no-op |
| T-MU-13 | Wearer identity | A's tags with A's first name → `user`; the same name in B's stream → `contact` unless it is B's name |

---

## 3. Acceptance criteria

1. Two people with two Bee accounts use the homelab instance concurrently; each sees only their own data, events and Bee status.
2. Every API, SSE and MCP request is authenticated; unauthenticated requests get `401`.
3. Logout never disconnects Bee; Bee disconnect and erasure affect one user only.
4. Restarting the server restores every linked user's runtime without re-pairing.
5. The existing single-tenant data is preserved for the owner account.
6. Live latency for one user is unaffected by another user's backfill (±10 %, as in the backfill spec).

---

## 4. Open questions

| # | Question | Default if unanswered |
|---|---|---|
| Q1 | Is a second Bee account available for MU-V4 and the acceptance test? | Test the second user with the simulator only |
| Q2 | Who creates accounts: admin only, or invitation links? | Admin only |
| Q3 | HTTPS on the homelab before inviting other people (NPM custom certificate for `*.deggio.local`)? | Trusted LAN only, no external users |
| Q4 | Password reset without e-mail: admin-issued one-time password? | Yes |
| Q5 | Per-user daily LLM budget | `BACKFILL_MAX_ESTIMATED_COST_USD` per user per day; live ingestion unlimited |
| Q6 | On AWS: one ingestion task for all users, or one per user? | One task until > 20 users |
