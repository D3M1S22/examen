# 🗣️ Alexa+ MCP Add-on — 03: OAuth Server and Account Linking

> **Document Status:** Planned (assumes decision A1: OAuth server built into EXAMEN)
> **Related:** [01_alexa_requirements.md](01_alexa_requirements.md) §3, [13_multi_user_accounts.md](../../13_multi_user_accounts.md), [dynamodb_storage/03](../dynamodb_storage/03_auth_and_ops_data_model.md) (auth table)

---

## 1. Principles

- **EXAMEN accounts are the identities.** Linking Alexa signs the user in on EXAMEN's own page and issues tokens for that account. There is no second user directory.
- **One code path for `/mcp`.** An OAuth access token resolves to a user (tenant) exactly as an `exm_` token does. Tools, isolation and logging stay unchanged.
- **Hashed secrets.** Tokens, codes and client secrets are stored as SHA-256 digests, like `exm_` tokens and sessions today.
- **Both auth backends.** Storage lives in the auth store (SQLite `auth.db` and the DynamoDB `examen-auth` table), behind the existing `AuthStore` / `DynamoAuthStore` pair.
- **Spec-minimal.** Implement exactly what Alexa uses: static clients, authorization code + PKCE S256, refresh tokens, client credentials. No dynamic client registration, OIDC or implicit grant.

## 2. Configuration (environment, boot-only)

| Key | Example | Meaning |
|---|---|---|
| `OAUTH_ENABLED` | `true` | Mounts the OAuth routes and well-known documents |
| `OAUTH_ISSUER` | `https://examen.devgiov.com` | Issuer and base URL of the endpoints |
| `MCP_RESOURCE_URI` | `https://examen.devgiov.com/mcp` | Canonical resource: must equal the add-on manifest URI |
| `OAUTH_CLIENTS` | JSON or SSM parameter | Static clients: `client_id`, secret digest, `redirect_uris` (the list from the Alexa+ Developer Hub), `name` ("Amazon Alexa") |
| `OAUTH_ACCESS_TTL_SECONDS` | `3600` | Access token lifetime (≤ 3600 for the service token) |
| `OAUTH_REFRESH_TTL_DAYS` | `90` | Refresh token lifetime (rotated on use) |

- The Alexa client secret is generated once and stored in SSM, as the bootstrap admin password is.
- `scripts/oauth_clients.py` creates or rotates a client and prints the secret for `alexa-ai configure-account-linking` (`ALEXA_CLIENT_SECRET`).

## 3. Endpoints

All routes are public: they are added to `PUBLIC_API_PATHS` / `is_protected` exceptions in [auth_middleware.py](../../../src/serving/auth_middleware.py).

### `GET /.well-known/oauth-protected-resource`
```json
{
  "resource": "https://examen.devgiov.com/mcp",
  "authorization_servers": ["https://examen.devgiov.com"],
  "scopes_supported": ["mcp:tools", "mcp:resources"],
  "bearer_methods_supported": ["header"]
}
```
Also served at `/.well-known/oauth-protected-resource/mcp`, the RFC 9728 path-suffixed form other MCP clients probe.

### `GET /.well-known/oauth-authorization-server`
```json
{
  "issuer": "https://examen.devgiov.com",
  "authorization_endpoint": "https://examen.devgiov.com/oauth/authorize",
  "token_endpoint": "https://examen.devgiov.com/oauth/token",
  "revocation_endpoint": "https://examen.devgiov.com/oauth/revoke",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "scopes_supported": ["mcp:service", "mcp:tools", "mcp:resources"]
}
```

### `GET /oauth/authorize`
1. **Validate the request.**
   - `client_id` must be known.
   - `redirect_uri` must be in the client's list (exact match). If not, show an error page and **do not redirect**.
   - `response_type=code`, `code_challenge` present and `code_challenge_method=S256`.
   - `resource` must equal `MCP_RESOURCE_URI` (trailing slash tolerated).
   - Requested scopes must be within `mcp:tools mcp:resources`.
   - Errors that are safe to report go back to the `redirect_uri` with `error=` and `state`.
2. **Sign in.**
   - No dashboard session: show the EXAMEN sign-in form, the same `/api/auth/login` and rate limiter, then come back.
   - Signed in: show the consent page: "Amazon Alexa wants to: read and update your routines, notes, contacts and events".
3. **Approve.** Store a one-time **authorization code** (random, digest only, TTL 60 s) with user, client, `redirect_uri`, `code_challenge`, scopes and resource. Redirect to `redirect_uri?code=…&state=…`.
4. **Deny.** Redirect with `error=access_denied&state=…`.

The page is server-rendered HTML, small and CSP-strict. It is not part of the Next.js export: it must work in the Alexa app's in-app browser without the dashboard bundle.

### `POST /oauth/token` (form-encoded)

| `grant_type` | Client auth | Checks | Response |
|---|---|---|---|
| `client_credentials` | `Basic` | `scope` = `mcp:service` (or absent); `resource` = `MCP_RESOURCE_URI` | access token, `scope: mcp:service`, `expires_in` ≤ 3600, **no refresh token** |
| `authorization_code` | `Basic` or `client_secret_post` | code exists, unused and unexpired, same client; `redirect_uri` equal to the one in the code; `SHA256(code_verifier)` = `code_challenge` (base64url); `resource` equal | access token + **refresh token**, scopes of the grant. The code is burnt; reusing it revokes the grant (OAuth 2.1) |
| `refresh_token` | same | token exists and is active, same client (no `resource` needed) | new access token + **rotated** refresh token; the old refresh token is invalidated |

- Errors use the RFC 6749 shapes: `invalid_client` 401, `invalid_grant` / `invalid_request` / `invalid_scope` / `unsupported_grant_type` 400, `access_denied` 403.
- Responses carry `Cache-Control: no-store`.

### `POST /oauth/revoke` (RFC 7009)
Revokes an access or refresh token, and with it the whole grant. Used by the Account page and by Alexa if it calls it.

## 4. Data model (auth store)

| Record | Fields | Notes |
|---|---|---|
| `oauth_grants` | `id`, `user_id`, `client_id`, `scopes`, `created_at`, `last_used_at`, `revoked_at` | One per linked Alexa account. Shown in Account → "Connected apps" |
| `oauth_codes` | `code_hash`, `grant_id` or (`user_id`, `client_id`), `redirect_uri`, `code_challenge`, `scopes`, `resource`, `expires_at`, `used_at` | 60 s TTL; DynamoDB TTL attribute |
| `oauth_tokens` | `token_hash`, `kind` (`access` / `refresh` / `service`), `grant_id` (null for service), `client_id`, `scopes`, `expires_at`, `rotated_from` | Access tokens use the `exa_` prefix, refresh tokens `exr_`, so the middleware can tell them from `exm_` |

- **SQLite:** three tables in `auth.db`, created at start like the others.
- **DynamoDB:** items in `examen-auth`:
  - `OAUTHTOKEN#<hash>`, `OAUTHCODE#<hash>` (with `ttl`);
  - `OAUTHGRANT#<id>` with `g1pk = USER#<user_id>#GRANT` to list a user's grants.
  - The `examen-runtime-data` policy already covers the table, so no IAM change is needed.
- **Erasure and export:**
  - `delete_user` deletes the user's grants and tokens;
  - the GDPR export lists the grants (no secrets);
  - disabling a user revokes them, as it revokes sessions and `exm_` tokens.
- **Audit:** `audit()` events `oauth_linked`, `oauth_revoked`, `oauth_refresh_reuse` (ids only).

## 5. `/mcp` authentication changes ([auth_middleware.py](../../../src/serving/auth_middleware.py))

1. **Token resolution.**
   - `exm_…` → user, as today.
   - `exa_…` (OAuth access, `mcp:tools`) → the grant's user. Check expiry and revocation; update `last_used_at` at most once a minute (DynamoDB write cost).
   - Service token (`mcp:service`) → **no user**, flag `service=True`.
2. **Service tokens get discovery, not data.**
   - On `POST /mcp`, read the JSON-RPC body (already needed by FastMCP; the middleware buffers it and replays it to the app).
   - Allowed methods: `initialize`, `notifications/*`, `ping`, `tools/list`, `resources/list`, `resources/templates/list`, `prompts/list`.
   - `tools/call` and `resources/read` with a service token answer **HTTP 401** with `{"error": "unauthorized"}`. Alexa then starts account linking (01 §3, Tier 2).
3. **No `WWW-Authenticate` on 401.**
   - Today the header is added on `/mcp` rejects. Alexa does not support it.
   - Other MCP clients (Claude, the MCP Inspector) discover the PRM through the well-known URI when the header is missing (MCP 2025-11-25 lets clients fall back to well-known probing).
   - Decision: drop the header. Option: keep it behind `MCP_WWW_AUTHENTICATE=true` if a client needs it.
4. **`tools/list` without a user.**
   - `tenant_tool` resolves the tenant only when a tool runs, so listing works.
   - Check that FastMCP's `initialize` / `tools/list` path never touches the store: today the middleware always provides a user.
5. **Tests:** see [05](05_implementation_plan_and_testing.md) §2.

## 6. Dashboard

**Account → "Connected apps"**
- Lists the OAuth grants (client name, linked on, last used) with **Disconnect**, which calls `/oauth/revoke` on the grant.
- The existing "Alexa+ / MCP access tokens" block stays for Claude and scripts.
- Its help text explains that Alexa links from the Alexa app, so no token needs to be copied.

## 7. Security notes

- **Transport.** TLS is required end to end before real users link (decision A3): authorization codes, refresh tokens and passwords on the sign-in page must not cross the CloudFront → EC2 hop in clear.
- **Brute force.** The sign-in form on `/oauth/authorize` uses the same per-IP and per-email limiter as `/api/auth/login`.
- **Clickjacking.** The consent page sends `X-Frame-Options: DENY` and a CSP `frame-ancestors 'none'`.
- **Open redirect.** `redirect_uri` is an exact match against the registered list only. Never reflect an unregistered URI.
- **Refresh-token reuse.** Presenting a rotated refresh token revokes the grant and logs `oauth_refresh_reuse`.
