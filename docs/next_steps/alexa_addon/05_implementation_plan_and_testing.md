# 05 — Implementation Plan, Tests & Onboarding

> Part of the [Alexa+ MCP Add-on](00_overview.md) specification.

---

## 0. Status (2026-10-23)

| Phase | Status |
|---|---|
| P0 Onboarding and prerequisites | ⏳ blocked on Amazon onboarding (§1) |
| P1 Transport hardening | ⏳ planned |
| P2 OAuth server and `/mcp` auth | ⏳ planned |
| P3 Public pages, assets, tool adjustments | ⏳ planned |
| P4 Add-on project, deploy, simulator | ⏳ planned |
| P5 Device test, certification | ⏳ planned |
| P6 MCP Apps (optional) | ⏳ later |

---

## 1. P0: onboarding (people, not code)

1. **Alexa developer account.** Profile completed in the Alexa app; the Amazon account set to an Alexa+ marketplace (US) and locale (en-US).
2. **Program access.** Give an AWS account id to the Alexa Solutions Architect (hackathon contact) and get the role `AddOn3PDeveloperToolsRead` granted. Without it, CodeArtifact (the CLI) and CodeCommit are unreachable. **This is the blocker:** ask the organisers first.
3. **Workstation:** Node.js 24+, then the setup steps of [01](01_alexa_requirements.md) §6 (IAM user, AWS profiles, CodeArtifact login, `npm install -g @alexa-ai/cli`, `alexa-ai configure`).
4. **Redirect URIs:** copy the account-linking redirect URI list from the Alexa+ Developer Hub (needed in P2).

## 2. Phases

### P1: transport hardening (decisions A3, A4)
1. **TLS to the origin.** Either:
   - a CloudFront VPC origin (EC2 in a private subnet, no public port); or
   - TLS on the instance (Caddy or uvicorn with a certificate) plus CloudFront `https-only`;

   and, in both cases, a secret custom origin header checked by `AuthMiddleware` (`X-Examen-Origin`).
2. **Stateless MCP:** `FastMCP(..., stateless_http=True)`. Check that SSE responses and `tools/call` work without `Mcp-Session-Id`.
3. **Homelab:** add `examen.deggio.local` to `MCP_ALLOWED_HOSTS` (doc 11 §3). Unrelated to Alexa, but `/mcp` answers 421 there today.

### P2: OAuth server and `/mcp` auth ([03](03_oauth_and_account_linking.md))
1. Auth store: grants, codes and tokens on both backends; erasure and export.
2. Well-known documents, `/oauth/authorize` (sign-in + consent), `/oauth/token` (three grants), `/oauth/revoke`.
3. Middleware: OAuth tokens → tenant; service tokens limited to discovery (401 on `tools/call`); no `WWW-Authenticate`.
4. `scripts/oauth_clients.py`: create or rotate the Alexa client; secret in SSM; `OAUTH_*` keys in `.env.example`, `host.sh` and the compute stack.
5. Account → "Connected apps".

### P3: public pages, assets, tools ([04](04_addon_package_and_tools.md) §3–4)

### P4: add-on project
1. `alexa-ai new mcp --name "Examen" --locale en-US --mcp-server-url https://examen.devgiov.com/mcp` (account linking: Y).
2. Edit `addon.json` (04 §2), commit `deploy/alexa/`.
3. Configure account linking:
   ```
   ALEXA_CLIENT_SECRET=… alexa-ai configure-account-linking --addon-id <id> --stage development --client-id <client-id>
   ```
4. Deploy and keep the add-on id: `alexa-ai deploy`.
5. **Rule:** every change to tools or auth metadata on the server needs `alexa-ai deploy` again. Added to [17](../../17_aws_deployment_runbook.md) next to `aws_deploy.py update`.

### P5: test and certify
- Web simulator, then a physical device.
- Local Inspector readiness report.
- `alexa-ai submit` when green.

## 3. Tests

| ID | Test | Where |
|---|---|---|
| T-AX-1 | PRM and AS metadata: exact fields; `resource` equals `MCP_RESOURCE_URI`; `S256` advertised | `tests/test_oauth.py` (new) |
| T-AX-2 | `/oauth/authorize`: unknown client, unregistered `redirect_uri` (no redirect), missing PKCE, wrong `resource`, signed-out user → login form, consent → code + state, deny → `access_denied` | same |
| T-AX-3 | `/oauth/token` authorization code: wrong verifier, reused code (grant revoked), wrong `redirect_uri`, expired code; success returns access + refresh tokens with `no-store` | same |
| T-AX-4 | Refresh: rotation; reusing an old refresh token revokes the grant | same |
| T-AX-5 | Client credentials: Basic auth required; scope other than `mcp:service` → `invalid_scope`; no refresh token; `expires_in` ≤ 3600 | same |
| T-AX-6 | `/mcp` with a service token: `initialize` and `tools/list` succeed; `tools/call` → HTTP 401 without `WWW-Authenticate` | same |
| T-AX-7 | `/mcp` with a linked user's token: tools see that user's data only; a revoked or expired token → 401 | same, plus `tests/test_accounts.py` |
| T-AX-8 | Both auth backends (SQLite, DynamoDB/moto); erasure deletes grants and tokens; export lists grants | `tests/test_oauth.py`, `tests/test_dynamo_accounts_ops.py` |
| T-AX-9 | End-to-end OAuth flow with a real MCP client (the `mcp` SDK OAuth client provider) against a local server | `scripts/test_mcp_oauth.py` (new) |
| T-AX-10 | Latency of each Alexa-facing tool through CloudFront (p50 / p95) | `scripts/mcp_latency.py` (new), reported in 17 |
| T-AX-11 | Public `/privacy`, `/terms`, `/alexa/*.png` reachable without a session | `tests/test_mcp_server.py` |

## 4. Acceptance

- A US Alexa+ test account links its EXAMEN account from the Alexa app and gets correct answers to the four example phrases on a device.
- Unlinking in the Alexa app or disconnecting in EXAMEN stops access at once.
- The Local Inspector reports no blocking issue; `alexa-ai submit` is accepted for review.
