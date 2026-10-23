# 🗣️ Alexa+ MCP Add-on — Overview

> **Document Status:** Future Integration (Post-Hackathon Specification)
> **Hackathon Submission Status:** The hackathon Alexa+ track is **fully satisfied** by EXAMEN's deployed FastMCP server implementing MCP **2025-11-25** over Streamable HTTP (`/mcp` with 22 tools) live at `https://examen.devgiov.com/mcp`.
> **Deferred post-hackathon because:** (1) The `@alexa-ai/cli` tool requires Amazon program onboarding to grant `AddOn3PDeveloperToolsRead` on AWS for CodeArtifact/CodeCommit access. (2) The hackathon rules explicitly validate a self-hosted conforming MCP server.
> **Related:** [03_alexa_mcp_serving.md](../../03_alexa_mcp_serving.md) (MCP tools for Alexa+), [13_multi_user_accounts.md](../../13_multi_user_accounts.md) (accounts, MCP access tokens), [17_aws_deployment_runbook.md](../../17_aws_deployment_runbook.md) (the public HTTPS deployment)
> **Audience:** EXAMEN engineers planning the post-hackathon commercial Alexa+ store add-on release

---

## 1. Why this exists

EXAMEN already exposes a fully compliant MCP server: Streamable HTTP at `/mcp`, 22 tools, one tenant per user, and `Bearer exm_…` personal tokens. That satisfies the hackathon's Alexa+ track requirements ("a self-hosted MCP server implementing MCP 2025-11-25").

For a production consumer release on physical Alexa+ devices through the Amazon Alexa Store, Amazon requires an **Alexa+ MCP Add-on**:
- **Alexa+ Store Integration:** Talk to an **Alexa+ MCP Add-on**: a registered package (`addon-package/addon.json`) deployed with the **Alexa AI CLI** (`@alexa-ai/cli`).
- **OAuth 2.1 & Account Linking:** Authentication via OAuth 2.1:
  - A service token (`client_credentials`) for tool discovery;
  - A per-customer token via **account linking** (authorization code + PKCE) to execute tool calls on behalf of the linked user.

This document and sub-specs define the turnkey architecture to implement once developer program onboarding is finalized.

## 2. Target architecture

```
Echo / Alexa app ──► Alexa+ (reasoning, NLU, TTS, rendering)
                         │ discovers tools at `alexa-ai deploy`, calls them per request
                         ▼
                 Alexa+ MCP Add-on (addon.json: listing, endpoint, account linking)
                         │ Streamable HTTP + Bearer token (service or customer)
                         ▼
https://examen.devgiov.com ── CloudFront ── EC2 (one process)
   ├─ /.well-known/oauth-protected-resource      (new) PRM: resource, authorization server, scopes
   ├─ /.well-known/oauth-authorization-server    (new) AS metadata, S256, grants
   ├─ /oauth/authorize                           (new) EXAMEN sign-in + consent page
   ├─ /oauth/token                               (new) client_credentials, authorization_code, refresh_token
   └─ /mcp  ── AuthMiddleware: exm_ tokens (as today) + OAuth access tokens (new) → tenant
```

## 3. Documents

| Doc | Content |
|---|---|
| [01_alexa_requirements.md](01_alexa_requirements.md) | What the official docs require (with links), including their contradictions |
| [02_gap_analysis.md](02_gap_analysis.md) | Requirement by requirement: what EXAMEN has, what is missing |
| [03_oauth_and_account_linking.md](03_oauth_and_account_linking.md) | Design of the built-in OAuth 2.1 server and of the `/mcp` auth changes |
| [04_addon_package_and_tools.md](04_addon_package_and_tools.md) | `addon.json`, listing assets, public pages, tool adjustments, MCP Apps (optional) |
| [05_implementation_plan_and_testing.md](05_implementation_plan_and_testing.md) | Phases, tests, onboarding steps, blockers |

## 4. Decisions to confirm

| # | Proposal | Alternative |
|---|---|---|
| **A1** | **OAuth server built into EXAMEN.** Users, sessions and token hashing already exist ([13](../../13_multi_user_accounts.md)); linking signs the user in on EXAMEN's own page. | Amazon Cognito ([14](../../14_aws_and_hackathon_reference.md) lists it). It needs a user pool and a mapping to EXAMEN accounts, plus migration or federation. |
| **A2** | **The add-on targets the AWS deployment** (`https://examen.devgiov.com/mcp`). Alexa needs a public HTTPS endpoint; `examen.deggio.local` is LAN-only. A cloudflared tunnel to the homelab is for development only. | — |
| **A3** | **Fix the CloudFront → EC2 hop before linking real accounts.** It is plain HTTP today (review of branch `aws`), so OAuth tokens and authorization codes would cross the internet in clear. Use HTTPS to the origin or a CloudFront VPC origin, plus a shared secret header. | Accept the risk for a private test add-on only. |
| **A4** | **Stateless MCP** (`stateless_http=True`). Alexa+ ties conversations to its own history, not to an MCP session id ([01](01_alexa_requirements.md) §4). | Keep stateful sessions (in memory, one instance). |
| **A5** | **US / en-US first.** Distribution `US`, locale `en-US`, the marketplaces where Alexa+ add-ons are offered. Tool texts are English already. | — |
| **A6** | **MCP Apps (visual UI) later.** Text and structured data first; Alexa+ renders data-only responses itself. | Build `ui://` resources for the Echo Show now. |
