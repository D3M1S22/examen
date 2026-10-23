# 🗣️ Alexa+ MCP Add-on — Overview

> **Document Status:** Planned (analysis 2026-10-23; decisions to confirm in §4)
> **Related:** [03_alexa_mcp_serving.md](../../03_alexa_mcp_serving.md) (MCP tools for Alexa+), [13_multi_user_accounts.md](../../13_multi_user_accounts.md) (accounts, MCP access tokens), [17_aws_deployment_runbook.md](../../17_aws_deployment_runbook.md) (the public HTTPS deployment)
> **Audience:** EXAMEN engineers connecting the MCP server to real Alexa+ devices

---

## 1. Why this exists

EXAMEN already exposes an MCP server: Streamable HTTP at `/mcp`, 22 tools, one tenant per user, `Bearer exm_…` personal tokens. That is enough for the hackathon's Alexa+ track ("a self-hosted MCP server implementing MCP 2025-11-25"). It is **not** enough for a real Alexa+ device, for two reasons.

- **Alexa+ does not connect to a raw MCP URL.** It talks to an **Alexa+ MCP Add-on**: a registered package (`addon-package/addon.json`) deployed with the **Alexa AI CLI**. The add-on carries the store listing, the endpoint and the account-linking configuration. Alexa+ discovers the tools at deploy time and calls them when a customer's request fits.
- **Alexa+ cannot use EXAMEN's personal tokens.** It authenticates with **OAuth**:
  - a service token (client credentials) to discover the tools;
  - a per-customer token from **account linking** (authorization code + PKCE) to call them.

  EXAMEN has no OAuth authorization server today.

The goal is a private add-on, then a certified one, through which an EXAMEN user links their account in the Alexa app and asks Alexa+ things like "did I lock the door?", "what do I have to confirm?" or "remind me to push tonight". Each request reads and writes that user's data only.

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
