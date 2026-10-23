# 🗣️ Alexa+ MCP Add-on — 01: What Alexa+ Requires

> **Document Status:** Summary of the official documentation as read on 2026-10-23. Amazon calls the certification criteria "preliminary": re-check before each phase.
> **Sources:**
> - [MCP Toolkit overview](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview)
> - [Create an MCP Add-on](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart)
> - [Authentication](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication)
> - [Account Linking for MCP Add-ons](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html)
> - [Client and App Lifecycle](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle)
> - [Test Your MCP Add-ons](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-test-add-ons)
> - [Certify and Publish](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-certify)
> - [Set Up Your Development Environment](https://developer.amazon.com/docs/alexaplus/add-ons/set-up-your-development-environment)
> - [MCP Design Guide](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-design-guide)

---

## 1. Model

- **Alexa+ is the MCP client.** It handles understanding, reasoning (which tool, when), speech and rendering. The server returns standard MCP responses.
- **The add-on** is the registered bridge between Alexa+ and the server: listing, endpoint, account linking. It is created with the **Alexa AI CLI** (`alexa-ai`), either manually or through the "add-on Agent Skill" with a coding agent.
- **Tools are registered at deploy time.** After any change to tools, resources or auth metadata, run `alexa-ai deploy` again: Alexa caches them.
- **Lifecycle:** Development → In-Review → Certified → Live.
  - CLI commands: `alexa-ai submit`, `withdraw`, `rollback`, `list`.
  - A live add-on below standards is suppressed: "soft" suppression goes back to Certified, "hard" suppression back to Development.

## 2. Server

| Requirement | Value |
|---|---|
| Transport | Streamable HTTP. Legacy HTTP+SSE must be migrated |
| Protocol | MCP **2025-11-25** (overview, quickstart). The lifecycle page's example `initialize` shows `2025-03-26`: version negotiation must work for both |
| Endpoint | Public **HTTPS** URL. A tunnel (cloudflared) is fine for development |
| Latency | "Round-trip query response must be under **500 ms**" |
| Capabilities | Advertise `tools` (and `resources` if any) in `initialize` |
| Responses | `content` (text), `structuredContent`, optional `_meta` |
| Custom UI (optional) | MCP Apps: `_meta.ui.resourceUri` = `ui://…`, optional `_meta.ui.invoking` / `invoked` status texts. Without it, Alexa renders the data itself ("data-only flow") |
| Missing context | Alexa first infers arguments from the conversation, then asks the customer through MCP **elicitation** |

## 3. Authentication

### Tier 1: service token (`client_credentials`)
- Alexa sends `POST /token`:
  - header `Authorization: Basic base64(client_id:client_secret)`;
  - form fields `grant_type=client_credentials`, `scope=mcp:service`, `resource=<canonical MCP URI>`.
- The token endpoint must:
  - validate `resource`;
  - return `token_type` `Bearer` with `expires_in` ≤ **3600** s;
  - grant only `mcp:service`;
  - issue **no refresh token** for this grant;
  - never accept credentials in the query string.
- Errors: 401 `invalid_client`, 400 `invalid_scope` or `invalid_request`, 403 `access_denied`.
- Alexa caches the service token and uses it for `initialize`, `tools/list` and similar calls.
- **A service token must not grant access to user data.**

### Tier 2: account linking (customer token)
- **Grant.** OAuth 2.1 authorization code with **PKCE S256**; the implicit grant is not supported. `code_challenge_methods_supported` must contain `S256`, otherwise deployment fails.
- **Authorization request:**
  - `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state`, `code_challenge`, `code_challenge_method=S256`;
  - `resource` = the MCP server's canonical URI.
- **Token request:** form POST with `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `code_verifier`, `resource`.
- **Token response:** `access_token`, `token_type`, `expires_in`, and **always a `refresh_token`**. Refresh requests omit `resource`.
- **Static client registration only.** Not supported:
  - Dynamic Client Registration;
  - Client ID Metadata Documents;
  - OpenID Connect;
  - step-up authorization.
- **Protected Resource Metadata** at `/.well-known/oauth-protected-resource`:
  - `resource` must equal the manifest URI (a trailing slash is tolerated);
  - only the **first** entry of `authorization_servers` is used;
  - requested scopes come from `scopes_supported` (omit `scope` if that list is not defined).
- **Authorization server metadata** at `/.well-known/oauth-authorization-server`.
- **Scopes** named by the Authentication page:
  - `mcp:service` for client credentials;
  - `mcp:tools` and `mcp:resources` for the authorization code grant.
- **Redirect URIs:** several, depending on where the customer's device is registered. The list is in the Alexa+ Developer Hub; register them all and reject any other.
- **Client configuration:**
  ```
  alexa-ai configure-account-linking --addon-id <id> --stage development --client-id <id>
  ```
  The secret is given through a masked prompt or `ALEXA_CLIENT_SECRET`, never as a flag. `accountLinking.enabled: true` goes in the manifest (answer "Y" at `alexa-ai new`).
- **Every request** carries the customer's token as `Authorization: Bearer …` (never in the query string).
- **No valid token on a tool call:** answer `401` or `403` (for example `{"error": "unauthorized"}`). Alexa then starts linking: a QR code on screen devices, a push notification on headless ones.
- **Unauthenticated requests: `401` _without_ a `WWW-Authenticate` header.** Alexa does not support it in 401 responses.

## 4. Client behaviour (lifecycle page)

- `initialize` from `"Alexa+ MCP Client"` 1.0.0, with capabilities `roots.listChanged: true`.
- Session continuity comes from the customer's Alexa conversation history, "rather than an explicit identifier for a session". `Mcp-Session-Id`, retries, timeouts and locale headers are not documented.

## 5. Add-on manifest (`addon-package/addon.json`)

- `manifestVersion` `"1.0"`; `storeListing.distributionCountries` (for example `["US"]`).
- Per locale (`en-US`):
  - `name.value` ≤ 30 characters, optional IPA `spokenForm`;
  - `shortDescription` ≤ 123; `fullDescription` ≤ 4000;
  - `examplePhrases`: 3–4, each ≤ 200 characters;
  - `privacyAndCompliance.privacyPolicyUrl` and `termsOfUseUrl` (HTTPS);
  - `mediaAssets`:
    - light icons in **all six sizes** (72, 64, 88, 126, 180, 241 px square); dark icons optional;
    - at least one **600×900** carousel image, with `altText` ≤ 250;
    - optional 1200×600 banners;
    - all HTTPS, PNG / JPG / WEBP.
- `integrations: [{ "type": "MCP", "config": { "endpoints": { "default": { "type": "HTTPS", "uri": "<MCP URL>" } } } }]`.

## 6. Developer environment

- **Accounts:**
  - an Alexa developer account (profile completed in the Alexa app);
  - an Alexa+ marketplace and locale on the Amazon account;
  - an **AWS account given to the Alexa Solutions Architect**. Program onboarding is needed: the CLI is distributed from Amazon's CodeArtifact.
- **Software:** Node.js **24+**, on macOS or Ubuntu.
- **Setup steps:**
  1. Create an IAM user allowed to `sts:AssumeRole` on `arn:aws:iam::372468808636:role/AddOn3PDeveloperToolsRead`.
  2. Configure the AWS profiles `alexa-ai-user` and `alexa-ai` (region `us-west-2`).
  3. Point the CodeCommit Git credential helper at that profile.
  4. Log npm in to CodeArtifact (`--domain alexa-ai --repository npm-packages --namespace @alexa-ai`).
  5. Install the CLI: `npm install -g @alexa-ai/cli`.
  6. Run `alexa-ai configure` (Login with Amazon; credentials in `~/.alexa-ai/credentials`, `--no-browser` on headless machines).

## 7. Testing and certification

- **Testing:**
  - MCP Inspector: schemas, valid and invalid inputs, idempotency;
  - the **Local Inspector**: readiness report against the certification checklist, rendering per device;
  - the **web simulator**: text, simulated screens, response details;
  - a **physical device**, routed from the simulator.
- **Certification (preliminary):**
  - complete the tasks customers ask through named invocations;
  - match the described features;
  - no high-severity dead ends;
  - accessibility (VoiceView, captions, magnifier, colour tools);
  - images neither pixelated nor stretched.
