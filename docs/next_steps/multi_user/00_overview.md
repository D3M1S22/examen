# 👥 Multi-User Support — Overview

> **Document Status:** Implemented on branch `sessions` (phases 1–5; homelab rollout ready, AWS providers later). Status and deviations: [05](05_implementation_plan_and_testing.md) §0
> **Related specs:** [10_bee_cli_reference.md](../../10_bee_cli_reference.md) (observed Bee contract), [historical_backfill/](../historical_backfill/00_overview.md), [deep_topic_event_engine/](../deep_topic_event_engine/00_overview.md), [06_aws_cloud_deployment_architecture.md](../../06_aws_cloud_deployment_architecture.md), [11_homelab_test_deployment.md](../../11_homelab_test_deployment.md)
> **Audience:** EXAMEN engineers implementing identity, data isolation, per-user ingestion and the serving changes

---

## 1. Why this exists

Today one EXAMEN instance serves **one Bee account** and **one shared dataset**. The dashboard "login" only manages demo profiles held in memory, identified by a client-chosen `user_id` that is never verified, and every profile sees the same Bee account and the same actions, contacts, tasks and events ([01](01_current_state.md)).

The goal is for several people, each with their **own Bee account**, to use the same deployment (homelab test instance, then AWS) with:

1. **Real authentication** for the dashboard, the REST API, the SSE stream and the MCP endpoint (Alexa+).
2. **Their own Bee link**: each user pairs their own Bee account; one Bee account belongs to at most one EXAMEN user.
3. **Strict data isolation**: nothing extracted from one user's speech is ever visible to, merged with, or influenced by another user.
4. **Their own live ingestion**: stream, speaker identity, location, Deep Topic events, coverage and historical backfill per user.
5. **Per-user privacy operations**: logout, Bee disconnect and GDPR erasure affect only the requesting user.

---

## 2. Target model in one picture

```
                        ┌──────────────────────────── EXAMEN process ─────────────────────────────┐
 browser / Echo Show ──►│ Auth middleware ──► UserContext(user_id) ──► REST · SSE · MCP tools      │
 Alexa+ (OAuth) ───────►│        │                                      │                          │
                        │        ▼                                      ▼                          │
                        │  System DB (users, sessions,       StoreRegistry.for_user(user_id)       │
                        │  api tokens, bee links)            └► one SQLite file per user (local)   │
                        │                                      └► DynamoDB PK=user_id (AWS)        │
                        │                                                                         │
                        │  UserRuntimeManager ── one UserRuntime per user with a linked Bee:      │
                        │    BeeClient(BEE_CONFIG_DIR=<user>/bee) ─ private bee proxy ─ /v1/stream │
                        │    BeeStreamOrchestrator ─ EventEngine ─ CoverageTracker ─ Backfill      │
                        │    WearerIdentity (that account's `bee me`)                             │
                        │                                                                         │
                        │  Shared, user-agnostic: model factory, Bedrock clients, telemetry        │
                        └─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Decisions (confirmed 2026-10-19)

| # | Topic | Proposal | Alternatives considered | Details |
|---|---|---|---|---|
| **D1** | Tenancy unit | **One EXAMEN user ↔ at most one Bee account**, and vice versa | Shared households/teams | [02](02_identity_and_bee_accounts.md) §1 |
| **D2** | Data isolation | **Scoped store per user**: the store is obtained already bound to a user (`StoreRegistry.for_user`). SQLite: one database file per user. DynamoDB: `user_id` partition key | `user_id` column in every table and every query (59 store methods, easy to forget a filter) | [03](03_tenant_isolation_and_runtime.md) §2 |
| **D3** | Authentication (homelab/local) | **Local accounts**: username + password (Argon2id), server-side session in an `HttpOnly`, `SameSite=Lax` cookie | Magic link by e-mail (needs SMTP), passkeys (more work), reverse-proxy auth | [02](02_identity_and_bee_accounts.md) §2 |
| **D4** | Authentication (AWS) | **Amazon Cognito** user pool behind the same `AuthProvider` interface (JWT validation); Cognito is also the OAuth server for Alexa account linking | Auth0 / custom OAuth | [04](04_serving_api_ui_aws.md) §5 |
| **D5** | MCP / Alexa+ | Local: **personal access tokens** (`Authorization: Bearer`) per user. AWS: **OAuth 2.0 account linking** (Cognito) | Single shared token | [04](04_serving_api_ui_aws.md) §3 |
| **D6** | Bee credentials | One `BEE_CONFIG_DIR` per user with `BEE_FORCE_FILE_STORE=1` (local). AWS: token in **Secrets Manager**, materialised into a private tmpfs dir by the ingestion worker | Sharing `~/.bee` (impossible: one token per directory) | [02](02_identity_and_bee_accounts.md) §4 |
| **D7** | Runtime | **One `UserRuntime` per linked user** inside one process (asyncio), supervised by `UserRuntimeManager`; global limits on concurrent LLM work | One process/container per user (heavier, needed only at larger scale on AWS) | [03](03_tenant_isolation_and_runtime.md) §3 |
| **D8** | Logout semantics | Dashboard logout ends **the web session only**. `bee logout` runs only on an explicit "Disconnect Bee" or GDPR erasure, and only for that user's `BEE_CONFIG_DIR` | Keep today's "logout = Bee logout" (decision C11) scoped to the user | [02](02_identity_and_bee_accounts.md) §5 |
| **D9** | Existing data | Migrate the current single-tenant `examen.db` into the first (owner) user's database | Discard it | [03](03_tenant_isolation_and_runtime.md) §2.4 |
| **D10** | Single code path | Multi-user is the only mode. Local dev gets a bootstrap owner account (`EXAMEN_BOOTSTRAP_ADMIN`) instead of a separate "single-user mode" | Keep a flag-guarded legacy single-user path | [05](05_implementation_plan_and_testing.md) §1 |

---

## 4. Goals and non-goals

**Goals**
- Isolation by construction: code that handles user data receives a store bound to one user; there is no default global store left.
- Every request, background task, pipeline invocation and SSE message carries an explicit `user_id`.
- Same design locally, on the homelab and on AWS; only the providers change (auth, storage, secrets).
- Per-user Bee lifecycle: link, stream, reconnect, backfill and unlink without restarting the server.

**Non-goals (this iteration)**
- Sharing data between users (households, shared contacts, delegated access).
- Role-based admin UI beyond a minimal `admin` flag (user creation and Bee status overview).
- Billing or quotas per user beyond simple budget guards.
- Several Bee accounts for one EXAMEN user.

---

## 5. Document map

| File | Content |
|---|---|
| [01_current_state.md](01_current_state.md) | Audit of everything that is single-tenant today, with code references and risks |
| [02_identity_and_bee_accounts.md](02_identity_and_bee_accounts.md) | Users, authentication, sessions, API tokens, Bee account linking per user, wearer identity, logout / disconnect / erasure |
| [03_tenant_isolation_and_runtime.md](03_tenant_isolation_and_runtime.md) | `UserContext`, scoped storage, migration, per-user ingestion runtime, pipeline and AgentCore payloads, shared resources and limits |
| [04_serving_api_ui_aws.md](04_serving_api_ui_aws.md) | REST and SSE authorisation, MCP / Alexa+ auth, dashboard changes, local vs homelab vs AWS mapping |
| [05_implementation_plan_and_testing.md](05_implementation_plan_and_testing.md) | Phases, test matrix (isolation tests first), acceptance criteria, open questions |

---

## 6. Glossary

| Term | Meaning |
|---|---|
| **User** | An EXAMEN account (`user_id`, username, credentials, flags). The tenant of all data |
| **Bee link** | The binding between a user and one Bee account (`bee_user_id` from `bee me`), plus the location of its credentials |
| **UserContext** | Immutable `{user_id, is_admin, auth_method}` resolved by the auth middleware or by the runtime that owns a background task |
| **Scoped store** | An `AbstractContextStore` instance bound to one user; it can only read and write that user's data |
| **System DB** | User-agnostic tables: users, sessions, API tokens, Bee links, audit log |
| **UserRuntime** | The per-user set of live components: Bee client + proxy, orchestrator, Event Engine, coverage tracker, backfill service |
