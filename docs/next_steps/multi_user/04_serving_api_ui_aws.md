# 04 — Serving: REST, SSE, MCP, Dashboard & AWS Mapping

> Part of the [Multi-User Support](00_overview.md) specification. Decisions D3–D5 of [00](00_overview.md) §3.

---

## 1. REST API

### 1.1 Middleware

A Starlette middleware in front of every route ([mcp_server.py](../../../src/serving/mcp_server.py) `create_app`):

1. Skips `/api/auth/login`, `/api/health`, static assets and the OAuth protected-resource metadata.
2. Calls `AuthProvider.authenticate(request)` (cookie or `Authorization: Bearer`).
3. Rejects with `401` when no `UserContext` is found, and with `403` for `disabled` users.
4. Sets `request.state.user` and `current_user_ctx` ([03](03_tenant_isolation_and_runtime.md) §1).
5. Enforces the CSRF header for cookie-authenticated `POST/PUT/PATCH/DELETE`.

### 1.2 Route changes

| Route | Change |
|---|---|
| `/api/auth/login` | `{username, password}` → sets `examen_session`; returns `{user}` (no Bee pairing side effect) |
| `/api/auth/logout`, `/api/auth/session` | Session-only (D8); `session` returns `{user, bee_link}` |
| `/api/auth/users` | Removed → `GET/POST /api/admin/users`, `POST /api/admin/users/{id}/disable` (admin) |
| `/api/auth/bee-link`, `/api/auth/bee-disconnect` | Replaced by `GET/POST /api/bee/link`, `POST /api/bee/unlink` ([02](02_identity_and_bee_accounts.md) §4.2) |
| `/api/auth/gdpr-purge` | Replaced by `POST /api/account/erase` (re-auth) |
| `/api/account/tokens` | New: list / create / revoke personal access tokens |
| `/api/orchestrator/start\|stop\|status`, `/api/status`, `/api/backfill/*`, `/api/event-engine/status` | Operate on **the caller's** `UserRuntime` |
| Data routes (`/api/actions`, `/api/routines*`, `/api/contacts*`, `/api/commitments*`, `/api/topics`, `/api/sessions*`, `/api/cards/preview`) | Use `ctx.store`; foreign ids → `404` |
| `/api/simulate*`, `/api/event-scenarios` | Run in the caller's scope |
| `/api/health` | New, unauthenticated liveness probe (used by `deploy/homelab/update.sh` instead of `/api/status`) |

## 2. SSE (`/api/events`)

- Authenticated by the session cookie. `EventSource` sends cookies on same-origin requests; for the `next dev` setup on another port it needs `new EventSource(url, {withCredentials: true})` and a CORS policy that allows the dev origin with credentials (no `*`).
- `broadcast_event(user_id, event_type, data)`: the `user_id` argument is mandatory. Subscribers are kept per user (`Dict[user_id, set[Queue]]`); a user with several tabs gets every event on each tab.
- Engine listeners, backfill progress and coverage events are registered per `UserRuntime`, so they always know their user.
- Admin-only system notifications (a user's runtime crashed) go to admins through the same mechanism, tagged `system_*`.

## 3. MCP endpoint (`/mcp`) & Alexa+

`mcp` 1.30.0 (installed, within the `<2.0` pin) supports a resource server mode: `FastMCP(..., token_verifier=…, auth=AuthSettings(issuer_url=…, resource_server_url=…, required_scopes=["mcp"]))`. Tools read the caller with `get_access_token()`.

| Environment | Token | Verifier |
|---|---|---|
| Local / homelab | Personal access token created in the dashboard (`exm_pat_…`, shown once) | `PatTokenVerifier`: sha256 lookup in `api_tokens`, revocation and `last_used_at` |
| AWS | OAuth 2.0 access token from **Cognito** issued through Alexa account linking | `CognitoTokenVerifier`: JWT signature (JWKS), `iss`, `aud`/`client_id`, expiry, scope `mcp` |

Each of the 12 tools resolves `UserContext` from the token and uses that user's store ([03](03_tenant_isolation_and_runtime.md) §2). Tool signatures do not change: the user is never a tool parameter, so a model cannot ask for another user's data.

## 4. Dashboard (`src/web_ui`)

| Area | Change |
|---|---|
| Login | `LoginModal` becomes a real sign-in form (username + password) in front of the app; the `localStorage` profile directory ([auth.ts](../../../src/web_ui/src/utils/auth.ts)) and the "switch profile" list are removed |
| API client | `fetch(..., {credentials: "include"})` plus the CSRF header; a `401` redirects to sign-in |
| Bee card | "Connect Bee" shows the real pairing link + QR, polls `GET /api/bee/link`, displays `linked` / `invalid` / last error; "Disconnect Bee" is a separate, confirmed action |
| Account page | Personal access tokens (create / revoke), log out everywhere, erase my data |
| Admin page | Users list (no data), create / disable user, Bee link state per user |
| System bar | Shows the signed-in user and **their** Bee status |
| Echo Show ext-app (`/ext-app/`) | Uses the same cookie when opened in the browser; on the device it runs inside Alexa with the account-linked token (AWS) |

## 5. Local vs homelab vs AWS

| Concern | Local dev | Homelab (CT 147) | AWS |
|---|---|---|---|
| Auth provider | `local` (bootstrap admin) | `local` | `cognito` (Hosted UI, Alexa account linking) |
| Transport security | `http://localhost` | LAN HTTP via NPM: cookies without `Secure`; acceptable on a trusted LAN only (an NPM certificate is recommended before inviting other people) | HTTPS (CloudFront / ALB); `Secure` cookies |
| System store | `data/system.db` | `/var/lib/examen/data/system.db` | DynamoDB `examen-system` |
| User store | `data/users/<id>/examen.db` | `/var/lib/examen/data/users/<id>/examen.db` | DynamoDB `examen-data` (PK `USER#<id>`), AgentCore Memory actor `<id>` |
| Bee credentials | `data/users/<id>/bee/` | same, `0700`, service user | Secrets Manager `examen/bee/<id>` → tmpfs `BEE_CONFIG_DIR` in the worker |
| Ingestion runtime | In-process `UserRuntimeManager` | In-process | Ingestion worker service (ECS/App Runner). Hackathon scale: one task hosting all users; larger scale: shard users over tasks by `hash(user_id)` |
| Pipeline | In-process `agent_invocation` | In-process | AgentCore Runtime, `user_id` in the payload, `runtimeSessionId` prefixed by the user |
| MCP / Alexa | PAT bearer | PAT bearer | OAuth (Cognito) bearer |
| Erasure | Delete user dir | Delete user dir | Delete DynamoDB partition, AgentCore Memory namespace, secret |

The code paths are identical; only `AUTH_PROVIDER`, `STORAGE_BACKEND` and the secrets provider change.
