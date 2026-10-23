# 🗣️ Alexa+ MCP Add-on — 02: Gap Analysis

> **Document Status:** Code survey of `main` (`788b910`, 2026-10-23), checked against [01_alexa_requirements.md](01_alexa_requirements.md). The self-hosted instance was probed over MCP the same day.

✅ ready · ⚠️ partly · ❌ missing

## 1. Server and transport

| Requirement | Status | EXAMEN today |
|---|---|---|
| Streamable HTTP | ✅ | `mcp.streamable_http_app()`, FastMCP from `mcp` 1.30.0 ([mcp_server.py:85](../../../src/serving/mcp_server.py#L85)) |
| Protocol 2025-11-25 (and 2025-03-26) | ✅ | The SDK supports `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`. The live server negotiated `2025-11-25` with a client |
| Public HTTPS endpoint | ⚠️ | `https://examen.devgiov.com/mcp` exists (CloudFront). The homelab `examen.deggio.local` is LAN-only and its `/mcp` currently answers **421** (`MCP_ALLOWED_HOSTS` lacks the host, doc 11 §3) |
| TLS end to end | ❌ | CloudFront → EC2 is plain HTTP on :8000. OAuth codes and tokens would cross the internet in clear (decision A3) |
| Session model | ⚠️ | FastMCP is stateful (`Mcp-Session-Id`, in memory) by default. Alexa does not document session ids; stateless is safer (A4) |
| Latency < 500 ms | ⚠️ | Tools are store reads and small writes, with no LLM call in a tool. Unmeasured through CloudFront; Alexa's US region to eu-central-1 adds about 100 ms. To measure (05 §3) |
| `tools` capability | ✅ | 22 tools; no resources or prompts |
| DNS-rebinding check | ⚠️ | AWS runs with `MCP_ALLOWED_HOSTS=*` (CloudFront rewrites Host). Correct, but the origin's only protection is the CloudFront prefix list (no shared secret) |

## 2. Authentication

| Requirement | Status | EXAMEN today |
|---|---|---|
| Bearer on `/mcp` | ⚠️ | Only personal `exm_…` tokens created in Account ([auth_middleware.py](../../../src/serving/auth_middleware.py)), mapped to the user (tenant). Alexa cannot obtain them |
| OAuth authorization server | ❌ | No `/oauth/authorize` or `/oauth/token`, no OAuth clients, codes or refresh tokens |
| `/.well-known/oauth-protected-resource` (PRM) | ❌ | — |
| `/.well-known/oauth-authorization-server` | ❌ | — |
| Tier 1 `client_credentials` → `mcp:service` | ❌ | `/mcp` rejects every request without a user. A service token must allow `initialize` / `tools/list` and nothing that reads user data |
| Tier 2 authorization code + PKCE S256 + refresh | ❌ | — |
| Static client, registered redirect URIs | ❌ | — |
| 401 **without** `WWW-Authenticate` | ❌ | The middleware adds `WWW-Authenticate: Bearer realm="examen-mcp"` on `/mcp` 401s ([auth_middleware.py](../../../src/serving/auth_middleware.py) `_reject`) |
| 401 / 403 on a tool call without a customer token | ❌ | No such case today. A service token on `tools/call` must answer HTTP 401, not a JSON-RPC tool error |
| Linked-account management | ❌ | The Account page lists `exm_` tokens only. Linked Alexa clients must be listed and revocable, and the GDPR export and erasure must cover OAuth grants |

## 3. Tools

| Topic | Status | EXAMEN today |
|---|---|---|
| Descriptions and argument docs | ✅ | Every tool has a docstring with `Args:`; destructive tools explain the two-step confirmation |
| Structured output | ⚠️ | Return type `Dict[str, Any]`, so FastMCP wraps the result as `structuredContent = {"result": {...}}` with a generic output schema. Typed results (TypedDict or Pydantic) give Alexa real field names |
| Response size and voice | ⚠️ | Read tools return `spoken_summary` plus Echo Show-specific `card_payload` / `display_template` blobs (56 places in `serving/tools/`). Alexa writes its own speech, so the blobs are noise and add size |
| Annotations | ⚠️ | Curation and review tools carry them; the 12 original tools have none (`readOnlyHint` missing on the read tools) |
| Elicitation for missing arguments | ✅ | Not required: Alexa infers arguments first. Our tools take explicit ids and return `not_found` |
| Destructive actions | ✅ | `confirm=true` two-step on deletes (manual curation D4) |
| MCP Apps (`ui://`) | ❌ | None. `/ext-app` is the whole dashboard mounted a second time (`mcp_server.py` `create_app`), not an MCP App. Optional (A6) |
| Tool count | ⚠️ | 22 tools, some admin-flavoured (`get_ingestion_coverage`, `get_live_event_outline`). Consider a smaller Alexa-facing set (04 §4) |

## 4. Add-on package and listing

| Item | Status |
|---|---|
| `addon-package/addon.json` | ❌ |
| Name, descriptions, example phrases | ❌ (texts can come from [03_alexa_mcp_serving.md](../../03_alexa_mcp_serving.md)) |
| Public privacy policy and terms of use (HTTPS) | ❌ The privacy notice exists only inside the dashboard (`PrivacyNotice.tsx`) |
| Icons in 6 sizes, 600×900 carousel image | ❌ |
| Hosting for assets | ⚠️ The dashboard's static export (`src/web_ui/public`, served by CloudFront) can host them |

## 5. Organisation

| Item | Status |
|---|---|
| Alexa developer account, Alexa+ marketplace / locale | ❓ to verify |
| Onboarding with an Alexa Solutions Architect (role `AddOn3PDeveloperToolsRead`, CodeArtifact) | ❓ **Blocker**: without it the CLI cannot be installed. Ask the hackathon organisers |
| Node.js 24+ on the machine that runs `alexa-ai` | ❓ |
| Redirect URI list from the Alexa+ Developer Hub | ❓ available after onboarding |

## 6. Already in place that helps

- **Accounts.** EXAMEN users, sessions and hashed tokens in SQLite or DynamoDB, with a tenant per request: an OAuth access token only needs to resolve to a user like `exm_` tokens do.
- **Login page.** The dashboard's sign-in (`/api/auth/login`, session cookie) can back the `/oauth/authorize` page.
- **Isolation.** IAM isolation per user (DynamoDB LeadingKeys) and tenant-scoped tools, so a linked Alexa account sees one user's data only.
- **Voice-oriented results.** Tool results already carry spoken summaries, ids for follow-up calls, the two-step deletes and the review queue.
