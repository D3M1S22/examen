# 🗄️ DynamoDB Storage — Overview

> **Document Status:** Implemented (decisions D1–D18 confirmed 2026-10-21). Status, verification and deviations: [07](07_implementation_plan_and_testing.md) §0. Pending: the real-AWS stack with its IAM check, and the homelab cutover.
> **Related:** [16_aws_data_layer_k3.md](../../16_aws_data_layer_k3.md) (why DynamoDB, comparison with Aurora and DSQL), [15_aws_split_architecture_report.md](../../15_aws_split_architecture_report.md) (always-on ingestion + AgentCore), [13_multi_user_accounts.md](../../13_multi_user_accounts.md) (tenancy), [admin_console/](../admin_console/00_overview.md) (`ops.db`)
> **Audience:** EXAMEN engineers implementing the DynamoDB backends

---

## 1. Why this exists

All of EXAMEN's state lives in SQLite files on one host:
- `users/<id>/examen.db`, one per user;
- `auth.db`;
- `ops.db`.

This layout forces three things:
- the host cannot be replaced without moving its disk;
- the AgentCore runtime cannot read or write a user's data, so doc 15 needed the K1 workaround (context in the payload, results out);
- every backup, restore and erasure is a file operation on that host.

Doc 16 chose **Amazon DynamoDB (on-demand)** as the target for every store. The reasons:
- it costs nothing at idle and needs no VPC;
- per-user isolation can be enforced by IAM (`dynamodb:LeadingKeys`);
- TTL, PITR and Streams replace jobs we run by hand today;
- the storage factory already reserves the slot: `STORAGE_BACKEND=dynamo`, partition key = `user_id`.

This folder is the implementation specification: current state, data model, security, infrastructure, migration, and the phased plan with tests.

## 2. Target model in one picture

```
              ┌───────────────── ingestion worker / API host (stateless) ──────────────────┐
 Bee SSE ───► │ gatekeeper · event engine · backfill · REST · MCP · admin console          │
              │   get_storage_store() ─► DynamoContextStore(user) ─┐                        │
              │   get_auth_store()    ─► DynamoAuthStore ──────────┤ service role           │
              │   get_ops_store()     ─► DynamoOpsStore ───────────┤                        │
              └────────────────────────────────────────────────────┼────────────────────────┘
                     tenant credentials: sts:AssumeRole + tag user_id │
                                                                      ▼
   ┌────────────────────────────── DynamoDB (on-demand, PITR, TTL) ──────────────────────────────┐
   │ examen-user   pk = <user_id>   sk = TASK#… ACTION#… CONTACT#… DOSSIER#… CHUNK#… LEDGER#…     │
   │               IAM: ForAllValues:StringLike LeadingKeys = [${tag}, ${tag}#*]  (no Scan)       │
   │ examen-auth   USER#… EMAIL#… SESSION#… TOKEN#… BEE#… AUDIT#…                                 │
   │ examen-ops    EVENT · INCIDENT · SETTING · HIST#… · USAGE#<day> · META                       │
   └─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                      ▲
 AgentCore Runtime (pipeline, syntheses, backfill) ── execution role ─┘ AssumeRole + tag user_id from the payload
```

## 3. Decisions (confirmed 2026-10-21)

| # | Topic | Proposal ★ | Alternatives | Details |
|---|---|---|---|---|
| **D1** | Scope and order | All three stores, in phases: per-user store first, then AgentCore direct access, then `auth` + `ops` | Per-user store only | [07](07_implementation_plan_and_testing.md) §1 |
| **D2** | Table layout | **Three tables**, one per current store, with overloaded keys and generic GSIs | One table per entity (~30 tables); one table for everything | [02](02_user_store_data_model.md) §1 |
| **D3** | User partition | `pk = <user_id>`, `sk = <ENTITY>#<id>`. Chunks are grouped by event in the base table (`CHUNK#<session>#<ts>#<seq>`), with pointer items for `chunk_id` | Chunks in a GSI by event | [02](02_user_store_data_model.md) §2 |
| **D4** | Consistency rule | **Every read-modify-write and every state lookup reads the base table with `ConsistentRead`.** GSIs serve listings only (KEYS / INCLUDE projections, then `BatchGetItem`) | GSIs everywhere | [02](02_user_store_data_model.md) §4 |
| **D5** | Attribute format | Attribute names equal the SQLite column names. `*_json` columns stay JSON strings; flags stay 0/1 numbers; floats are stored as `Decimal` | Native maps and lists | [02](02_user_store_data_model.md) §5 |
| **D6** | Search | In-code `LIKE` semantics over the user's own collection. FTS5 is not ported: it is written but **never queried** today | OpenSearch zero-ETL (≈ $175/month) | [01](01_current_state.md) §4 |
| **D7** | Domain logic inside the store | Extract the pure rules (task matching, commitment dedup, contact merge) into `src/core/storage/rules.py`, shared by both backends; a contract test checks the signatures | Copy the logic into the new store | [01](01_current_state.md) §3, [07](07_implementation_plan_and_testing.md) |
| **D8** | Concurrency (the worker and AgentCore both write) | Guard items with `attribute_not_exists` for uniqueness (contact name, commitment key, email, Bee account). The dossier carries a `version` with a conditional put and a re-merge of `linked_micro_events` on conflict | Last writer wins | [02](02_user_store_data_model.md) §6 |
| **D9** | Tenant isolation | One tenant role with a `LeadingKeys` policy on the `user_id` session tag; `AssumeRole` per user, cached. Active when `DYNAMO_TENANT_ROLE_ARN` is set. A service role (no tag) handles `auth`, `ops`, erasure and migration | Application filtering only | [04](04_security_iam_and_tenancy.md) |
| **D10** | Retention | TTL for sessions, web cache, telemetry (new: 30 days), ops events, usage, resolved incidents and audit. Explicit purge methods are kept, with the same semantics as today; reads ignore items that expired but are not yet deleted | Purge jobs only | [02](02_user_store_data_model.md) §7, [03](03_auth_and_ops_data_model.md) |
| **D11** | Service-event ids | Numeric ids from an atomic counter (one `ADD n` per batch), so `before_id` pagination and the UI stay unchanged | Opaque string cursor (API and UI change) | [03](03_auth_and_ops_data_model.md) §2.1 |
| **D12** | Settings history | **One item per change set** (all keys inside). "Reset all" (80 keys) then fits the 100-item transaction limit | One item per key change | [03](03_auth_and_ops_data_model.md) §2.3 |
| **D13** | Infrastructure as code | CloudFormation template `deploy/aws/dynamodb.yaml` (tables, roles, alarms). The tests build the same tables from `TABLE_SPECS` in Python, and a test checks that the two match | CDK; console clicks | [05](05_infrastructure_and_configuration.md) §1 |
| **D14** | Tests | **moto** in-process (dev dependency) with a store fixture parametrised over `sqlite` and `dynamo`; DynamoDB Local optional; IAM checked with the policy simulator against the real account | DynamoDB Local only (needs Docker) | [07](07_implementation_plan_and_testing.md) §3 |
| **D15** | Region | New boot-only key `DYNAMO_REGION`. It never follows the runtime-editable `AWS_REGION`, which the admin console can change for Bedrock | Reuse `AWS_REGION` | [05](05_infrastructure_and_configuration.md) §2 |
| **D16** | Capacity, backup and encryption | On-demand, PITR on, deletion protection on, AWS-owned encryption key (a customer-managed KMS key is optional) | Provisioned capacity; KMS key from day one | [05](05_infrastructure_and_configuration.md) §3 |
| **D17** | Migration | Offline per-user copy script (idempotent, verified by counts). SQLite files stay read-only as the rollback; no dual-write | Dual-write period | [06](06_migration_and_cutover.md) |
| **D18** | Filesystem state that is not a database (Bee token folder, tenant listing) | Tenants are listed from the auth store; the Bee token stays on the worker's disk in this project (moving it to Secrets Manager is a follow-up) | Move it now | [01](01_current_state.md) §6, [04](04_security_iam_and_tenancy.md) §6 |

## 4. Goals and non-goals

**Goals**
- `STORAGE_BACKEND=dynamo`, `AUTH_STORE_BACKEND=dynamo` and `OPS_STORE_BACKEND=dynamo` behave exactly like SQLite: the whole test suite passes on both backends.
- A missing filter in our own code cannot read another user's data. DynamoDB refuses the request.
- The AgentCore runtime reads and writes the user's data directly, so the K1 payload context goes away.
- The host keeps no database files: it can be replaced at any time.
- Cost at idle ≈ $0. Cost for 5 active users ≈ $5 per month ([05](05_infrastructure_and_configuration.md) §4).

**Non-goals**
- Removing the SQLite backend: it stays the default for local development, tests and the homelab.
- Full-text ranking or semantic search over user data.
- Multi-region (global tables), DAX caching, and Streams-driven processing. Streams are prepared in the infrastructure but nothing consumes them in this project.
- Moving the Bee token off the worker's disk.
- Changing the Bee ingestion model: the worker remains always on (doc 16 §1).

## 5. Document map

| File | Content |
|---|---|
| [01_current_state.md](01_current_state.md) | Inventory of the three SQLite stores: methods, callers, logic embedded in the store, signature drift, filesystem state, scripts, tests, measured volumes |
| [02_user_store_data_model.md](02_user_store_data_model.md) | `examen-user`: item types, keys, GSIs, the access pattern of each of the 60 methods, consistency, encoding, size guards, concurrency |
| [03_auth_and_ops_data_model.md](03_auth_and_ops_data_model.md) | `examen-auth` and `examen-ops`: item types and the access pattern of each of the 32 + 17 methods |
| [04_security_iam_and_tenancy.md](04_security_iam_and_tenancy.md) | Roles and policies, scoped credentials, encryption, erasure and export, threat model |
| [05_infrastructure_and_configuration.md](05_infrastructure_and_configuration.md) | CloudFormation, settings, local development, capacity and cost, monitoring, backup and restore |
| [06_migration_and_cutover.md](06_migration_and_cutover.md) | SQLite → DynamoDB copy, verification, cutover per environment, rollback |
| [07_implementation_plan_and_testing.md](07_implementation_plan_and_testing.md) | Phases, file list, test matrix, acceptance criteria, timebox before the hackathon deadline, open questions |
