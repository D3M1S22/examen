# 🗄️ K3 deep-dive: EXAMEN's data on AWS (DynamoDB vs Aurora Serverless v2 vs Aurora DSQL)

> Status: research report, 21 Oct 2026. **DynamoDB chosen**: implementation spec in [next_steps/dynamodb_storage/](next_steps/dynamodb_storage/00_overview.md) (the cost there, ≈ $5–6/month, supersedes §5). Follows [15](15_aws_split_architecture_report.md) §3 (option K3), using the facts in [14](14_aws_and_hackathon_reference.md). Prices are us-east-1 list prices unless noted; Frankfurt (eu-central-1) is usually 10–20 % higher. Figures marked *(verify)* could not be confirmed on an official AWS page.

## 1. Verdict

- **Target: Amazon DynamoDB** (on-demand) for all three stores: the per-user store, `auth.db` and `ops.db`.
  - It is the only option that costs **nothing at idle and needs no VPC**.
  - It is the only option that can **enforce tenant isolation in IAM** (`dynamodb:LeadingKeys`) rather than in `WHERE` clauses. That keeps the strength of today's one-file-per-user model.
  - The codebase already reserves the slot: `STORAGE_BACKEND=dynamo` with "partition key = user_id" in [storage/__init__.py](../src/core/storage/__init__.py).
- **Second choice: Aurora DSQL**, if we want to keep SQL.
  - It is serverless, scales to zero, and is reached over a public IAM-authenticated endpoint.
  - It accepts PostgreSQL, so most queries survive.
  - Isolation becomes application-only: no row-level security, a cap of 10 schemas, and a cap of 1 000 tables.
- **Rejected: Aurora Serverless v2.** Auto-pause does not fit our workload. The ingestion path writes on every utterance, so the cluster would rarely pause during the day, and every wake-up costs about 15 s. It also needs a VPC and is the most expensive option.
- **Deadline reality.** K3 cannot replace the safe path for the submission (Fri 23 Oct, 21:00 CEST):
  - The per-user store alone has 60 methods. A parity port to DynamoDB is **about 3–5 days**, including tests.
  - §8 proposes a timeboxed path: build the per-user store on DynamoDB behind the existing flag, with SQLite as the default and S1/K1 from doc 15 as the fallback. Merge only if parity tests pass.
- **The always-on surface does not reach zero.**
  - The Bee streams are long-lived outbound SSE connections, one per user, so one small ingestion worker must stay up (Fargate Spot or `t4g.nano`).
  - K3 makes that worker **stateless and replaceable**. That is the real win: no EBS, no backups on the host, AgentCore reads and writes the data directly, and the API can move to Lambda later (doc 15 S2).

## 2. What has to move

Measured on the code (`src/core/…`) and on the homelab instance (CT 147, 21 Oct):

| Store | File today | Tables | Methods | Notes |
|---|---|---|---|---|
| Per-user context | `users/<id>/examen.db` | 19 + 3 FTS5 | 60 (`AbstractContextStore`) | 25 queries with aggregation or ordering; FTS5 for actions, contacts and briefings, with a **LIKE fallback already in the code** |
| Accounts | `auth.db` | 5 (users, sessions, api_tokens, bee_links, audit_log) | 32 | Lookups by email and by token hash |
| Service ops | `ops.db` | 6 (service_events, incidents, settings_overrides, settings_history, token_usage, ops_meta) | 17 | Hourly aggregates, retention purge |

The data volumes are tiny. The busiest real user holds a 7 MB file: about 4 700 ledger rows, 4 575 chunks, 15 dossiers and 46 briefings. **The largest row is about 25 KB** (a dossier or a briefing), far under DynamoDB's 400 KB item limit. `sqlite3` is imported only in these three modules, so the port is contained.

The pipeline itself (AgentCore, doc 15 §3) touches only 13 of the 60 methods. The ingestion worker touches the ledger, the coverage table, the chunks and the dossier or event state.

## 3. The three candidates

| | **DynamoDB (on-demand)** | **Aurora DSQL** | **Aurora Serverless v2 (PostgreSQL)** |
|---|---|---|---|
| Model | Key-value / document, NoSQL | Distributed PostgreSQL 16 (subset) | Full PostgreSQL |
| Idle cost | **$0** (storage only) | **$0** (storage only) | $0 only while paused (0 ACU); ≥ 0.5 ACU while any client is connected |
| Network | Public HTTPS endpoint, SigV4 / IAM, **no VPC** | Public endpoint, IAM auth token, **no VPC** | Cluster inside a VPC; the Data API (HTTPS + IAM + Secrets Manager) avoids VPC clients |
| Cold start | None | None | About 15 s after auto-pause (≥ 30 s after 24 h); the Data API returns `DatabaseResumingException` and the caller retries |
| Tenant isolation | **IAM `dynamodb:LeadingKeys`** on the partition key, with session tags | Application `WHERE user_id`; no RLS, ≤ 10 schemas and ≤ 1 000 tables per cluster, so no schema per user | PostgreSQL RLS, or a schema per user |
| Full-text search | None (filter in code within the user's partition) | `tsvector` not documented, so `ILIKE` | `tsvector` / GIN |
| Transactions | `TransactWriteItems` (up to 100 items) | Optimistic concurrency: SQLSTATE 40001 means retry; ≤ 3 000 rows and 10 MiB per transaction, ≤ 5 minutes; one DDL per transaction | Full ACID |
| Retention | **TTL** (free, background deletes) | Batched `DELETE` | `DELETE` / partitioning |
| Change events | **Streams → Lambda** (free reads for Lambda) | None | Logical replication (prevents the pause) |
| Backup | PITR (35 days), on-demand backups | Automatic, AWS Backup | Automatic snapshots |
| Port effort | Highest: rewrite every query | Medium: SQLite → PostgreSQL dialect, `user_id` everywhere, retries | Medium–low: dialect only |
| AWS showcase value | High: IAM FGAC, Streams, TTL, PITR | High (new service) | Low: a "classic" relational database |

### 3.1 DynamoDB facts that matter here
From the DynamoDB developer guide ([quotas](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html), [fine-grained access](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html)):

- **Capacity.** On-demand tables default to 40 000 read and 40 000 write request units per second per table.
- **Item limits.** Items are up to 400 KB. A batch write takes 25 items; a transaction takes 100 items.
- **Indexes.** Up to 20 GSIs and 5 LSIs per table. LSIs must exist when the table is created, and they cap each partition key at 10 GB.
- **New vector indexes** (5 per table) exist, but EXAMEN does not need them.
- **`dynamodb:LeadingKeys`** holds the partition key values of a request.
  - It must be used with the `ForAllValues:` modifier.
  - It applies to GetItem, BatchGetItem, Query, PutItem, UpdateItem, DeleteItem and BatchWriteItem.
  - **Scan must not be allowed**, because it ignores leading keys.
  - Indexes are separate resources in the policy.
- **Prices.**
  - On-demand: about **$0.625 per million writes and $0.125 per million reads**. AWS halved on-demand prices on 1 Nov 2024; some 2026 blogs still quote the old $1.25 / $0.25 *(verify for eu-central-1)*.
  - Storage costs $0.25 per GB-month, and the first 25 GB are free.
  - PITR costs about $0.20 per GB-month.

### 3.2 Aurora DSQL facts that matter here
From the DSQL user guide ([what is](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/what-is-aurora-dsql.html)), its migration and quota pages, and the AWS Database Blog dialect post:

- **Compatibility.** It speaks PostgreSQL 16 and runs in Repeatable Read only.
- **Not supported:** extensions, PL/pgSQL, triggers, temporary tables and `TRUNCATE`.
- **Indexes and JSON.** Indexes are created with `CREATE INDEX ASYNC`. JSON/JSONB columns are allowed but cannot be indexed.
- **Connections** last at most 1 hour.
- **Availability.** It runs in eu-central-1, eu-west-1/2/3, eu-south-2 and eu-north-1 (not Milan).
- **Price:** about $8 per million DPU plus $0.33 per GB-month, with 100 000 DPU and 1 GB free each month.
- **Fit for EXAMEN:**
  - Our schema migrations are `ALTER TABLE ADD COLUMN` in try/except. Under DSQL each runs as its own transaction *(verify `ADD COLUMN … DEFAULT` support)*.
  - Erasure and the ledger purge must be batched below 3 000 rows.
  - Every write path needs a 40001 retry wrapper.

### 3.3 Aurora Serverless v2 facts that matter here
From the [auto-pause guide](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html), the [Data API](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.html) docs and the [Aurora overview](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_AuroraOverview.html):

- **Auto-pause** works at 0 ACU on PostgreSQL ≥ 16.3. The idle delay (`SecondsUntilAutoPause`) is 300 to 86 400 s.
- **What prevents the pause:** RDS Proxy, logical replication and open connections. The Data API resumes a paused cluster on the first call, which fails with [`DatabaseResumingException`](https://docs.aws.amazon.com/botocore/latest/reference/services/rds-data/client/exceptions/DatabaseResumingException.html) until it is up.
- **Prices:**
  - compute about $0.12 per ACU-hour;
  - storage $0.10 per GB-month plus $0.20 per million I/O (Standard).
- **Fit for EXAMEN:** Bee utterances arrive all day, so at 0.5 ACU from 08:00 to 24:00 the cluster costs about **$29 per month** before storage. At 24 h it is about $44.

## 4. Proposed DynamoDB design

### 4.1 Tables
The tables follow the three current stores. Three tables keep IAM, TTL and retention per store simple. A full single-table design would put auth rows behind the same tenant policy, which is not what we want.

| Table | PK | SK | GSIs | TTL |
|---|---|---|---|---|
| `examen-user` | `user_id` | `<ENTITY>#<id>` (for example `TASK#…`, `ACTION#…`, `CONTACT#…`, `COMMIT#…`, `BRIEF#…`, `DOSSIER#…`, `CHUNK#<session>#<ts>`, `LEDGER#<source_key>`, `COV#<start>`, `RUN#…`, `TEL#<ts>`, `CACHE#<query_norm>`) | **GSI1** `g1pk = <user_id>#<ENTITY>`, `g1sk = <time>`: lists by entity ordered by time. **GSI2** `g2pk = <user_id>#LEDGERHASH`, `g2sk = <text_hash>#<received_at>`: ledger dedup lookup | `expires_at` on ledger, chunks, telemetry and cache rows (replaces `purge_ingest_ledger` and cache expiry) |
| `examen-auth` | `USER#<id>` / `EMAIL#<email>` / `SESSION#<hash>` / `TOKEN#<hash>` / `BEE#<user_id>` / `AUDIT#<yyyy-mm>` | `META` or `<ts>#<id>` | **GSI1** `user_id`: list a user's sessions and tokens for revocation and erasure | `expires_at` on sessions |
| `examen-ops` | `EVENT#<yyyy-mm-dd>`, `INCIDENT`, `SETTING`, `SETTINGHIST`, `USAGE#<yyyy-mm-dd>` | `<ts>#<id>` / `<key>` / `<hour>#<provider>#<model>#<role>#<user>` | **GSI1** `user_id`: erasure of a user's events and usage | `expires_at` replaces `purge()` (events 14 days, usage 90 days, incidents 90 days) |

Rules that keep the port mechanical:

- **Email uniqueness.** Registration writes `USER#id` and `EMAIL#email` in one `TransactWriteItems` with `attribute_not_exists`. This replaces `UNIQUE`.
- **Counters and upserts** use `UpdateItem ADD`. That covers `token_usage`, incident counts and coverage counters, and replaces `ON CONFLICT … DO UPDATE`.
- **Aggregates are computed in Python** after a `Query` of one user's partition or one day's ops rows. The volumes in §2 make this cheap: the heaviest call reads a few thousand items, about 1 MB, which is one or two pages.
- **Search** (FTS5 today) becomes a `Query` of `g1pk = <user>#CONTACT|ACTION|BRIEF` with the existing LIKE logic applied in code, on lowercase copies of the searchable fields. The current LIKE fallback in [sqlite_store.py](../src/core/storage/sqlite_store.py) defines the expected behaviour.
  - If ranking quality matters later: DynamoDB zero-ETL to OpenSearch. It needs an always-on ingestion pipeline (at least 1 OCU, about $0.24/h ≈ $175/month), so it is **not** worth it here.
- **Large JSON fields** (`segments_json`, `research_ledger_json`, `deep_dive_markdown`) stay inline: 25 KB maximum today against 400 KB allowed.
  - Add a guard: above 300 KB, gzip the field into a binary attribute.
  - Every rewrite of a 25 KB dossier costs 25 write units, so frequent dossier updates should use `UpdateItem SET` on the changed attributes only.
- **Sorted lists** (`ORDER BY created_at DESC LIMIT n`) become a GSI1 `Query` with `ScanIndexForward=False, Limit=n`.

### 4.2 Tenant isolation enforced by IAM
The per-user table is accessed only with credentials scoped to one tenant:

```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:PutItem",
             "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem", "dynamodb:ConditionCheckItem"],
  "Resource": ["arn:aws:dynamodb:eu-central-1:<acct>:table/examen-user",
               "arn:aws:dynamodb:eu-central-1:<acct>:table/examen-user/index/*"],
  "Condition": {"ForAllValues:StringLike": {"dynamodb:LeadingKeys": [
      "${aws:PrincipalTag/user_id}", "${aws:PrincipalTag/user_id}#*"]}}
}
```

- **Who obtains the scoped credentials.**
  - The ingestion worker (one task per user stream) and the AgentCore runtime (one invocation per user) call `sts:AssumeRole` on a `examen-tenant-data` role.
  - They pass the session tag `user_id=<tenant>` (`sts:TagSession`) for the user taken from the tenant context.
  - These credentials are cached for 15–60 minutes per user.
- **No `Scan`.** The tenant role has no `Scan` permission. Admin-wide jobs (erasure, exports) run under the service role, which has no tag condition.
- **What it guarantees.** A missing filter in a query cannot read another tenant: DynamoDB refuses the request. This is defence in depth on top of `tenant_scope`/`resolve_tenant`, and it is a strong point for the AWS demo: the isolation is visible in IAM.
- **User ids.** They have a fixed length (`usr_` + 32 hex), so the `#*` prefix pattern cannot match another user.
- **Erasure.** `delete_user` deletes every item of the partition (a `Query` on the PK, then batches of 25 writes). It runs as an asynchronous job, because the busiest user has about 9 000 items, which takes about 30 s at a modest rate.

### 4.3 Who reaches the data, and how

| Component | Credentials | Network |
|---|---|---|
| Ingestion worker (Fargate Spot or a small EC2) | Task/instance role → `AssumeRole` on the tenant role per user; service role for auth/ops | Public DynamoDB endpoint, or a free **gateway VPC endpoint** if it runs in a private subnet (no NAT needed for DynamoDB) |
| AgentCore Runtime (pipeline, syntheses, backfill) | Execution role → `AssumeRole` with `user_id` from the invocation payload (the host is the only principal allowed to `InvokeAgentRuntime`) | Public mode: no VPC |
| API (EC2 now; Lambda or ECS Express later) | Service role for auth/ops; tenant role per request | Same as above |
| Admin console | Service role (reads ops, settings and usage) | Same as above |

**K3 removes K1 entirely.** AgentCore reads pending tasks and contacts directly, so the payload no longer carries context, and the "contact created a second earlier" race from doc 15 §3 disappears.

The new risk is concurrency, because two writers now exist (the worker and AgentCore).
- Contact merge and task matching must use **conditional writes** (`attribute_not_exists` / a `version` attribute) instead of read-then-write.
- Today's SQLite code relies on a single writer in a few places (contact dedup by name, commitment dedup). These need deterministic keys: `CONTACT#<normalised name>` and `COMMIT#<hash(contact, description, debtor)>`. That also removes the duplicate-purge `DELETE`s run at startup.

## 5. Cost for 5 users (monthly)

Assumptions:
- writes per user per day: 1 500 utterances × (ledger 1 + chunk 2 + coverage, counters and dossier updates ≈ 6) ≈ 14 k write units (WRU), plus syntheses;
- reads similar, mostly as Query pages.

| Item | DynamoDB | DSQL | Aurora SV2 |
|---|---|---|---|
| Requests or compute | ≈ 2.1 M WRU + 2 M RRU ≈ **$1.6** | ≈ 150–400 k DPU (rough estimate) ≈ **$0.5–2.5** after 100 k free | 0.5 ACU × 16 h/day ≈ **$29** (24 h ≈ $44) |
| Storage (< 1 GB) | $0 (25 GB free) | $0 (1 GB free) | ≈ $0.1 + I/O ≈ $1 |
| Backup | PITR ≈ $0.2 | included | included up to the cluster size |
| Extras | Streams: free with Lambda | – | Secrets Manager $0.40; VPC (no NAT needed with the Data API) |
| **Data layer total** | **≈ $2** | **≈ $1–3** | **≈ $30–46** |

**What stays always on with K3:** the ingestion worker only.
- Fargate Spot ARM 0.25 vCPU / 0.5 GB costs about $3–4 per month; a `t4g.nano` about $3 plus $3.6 for its public IPv4.
- With S1 (API still on the host) the host stays at `t3a.small`, about $14, but it no longer has EBS state to protect.
- End to end, with the API on Lambda (doc 15 S2), the infrastructure is about **$15–25 per month**, against $30–40 for S1 with K1.

## 6. Migration plan

| Phase | Content | Effort | Gate |
|---|---|---|---|
| **M0** | Terraform or CDK for 3 tables, GSIs, TTL, PITR, the tenant role with the LeadingKeys policy, and the service role; **DynamoDB Local** (Docker `amazon/dynamodb-local`) for tests | 0.5 day | `aws dynamodb describe-table` and an IAM policy simulator check that a cross-tenant `GetItem` is denied |
| **M1** | `DynamoContextStore` (60 methods) behind `STORAGE_BACKEND=dynamo` in `_build_store`; the 15 store-dependent test files parametrised over `sqlite` and `dynamo` (DynamoDB Local) | 2–3 days | The full suite is green on both backends |
| **M2** | Pipeline on AgentCore reads and writes DynamoDB directly (replaces K1); conditional writes for contact and commitment dedup; scoped credentials per invocation | 1 day | Real Bedrock run: the same entities as the local pipeline on 20 recorded utterances |
| **M3** | `examen-auth` + `examen-ops` (49 methods); the host keeps no files | 1.5–2 days | Login, registration, admin console, token usage and erasure tests on `dynamo` |
| **M4** | One-shot migration script SQLite → DynamoDB (per user, idempotent via `PutItem`), then switch CT 147 / AWS to `dynamo`; SQLite files kept read-only for rollback | 0.5 day | Row counts per entity match; the dashboard shows the same data |
| **M5** *(optional)* | Streams → Lambda: an event-driven trigger for syntheses instead of polling; S2 API on Lambda | 2+ days | doc 15 S2 |

**Total to a stateless host: about 5–7 working days** (M0–M4). For comparison:
- DSQL: about 4–5 days (SQL survives, but every table gains `user_id` plus retry wrappers);
- Aurora SV2: about 3–4 days, which we would spend on the option that contradicts the goal.

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Behaviour drift in 60 rewritten methods (ordering, LIKE semantics, dedup) | Wrong dashboard and pipeline results | Parametrised suite on both backends (M1); SQLite stays the default until parity |
| Two writers (worker + AgentCore) | Duplicate contacts, lost updates on dossiers | Deterministic keys, conditional writes, a `version` attribute on dossiers |
| Dossier rewrites inflate write units | Cost (still in cents) | `UpdateItem` on changed attributes only |
| Admin aggregates over 30 days | Slow usage and log views | Daily partitions (`USAGE#day`), parallel `Query`; volumes are small |
| Item > 400 KB in the future (very long events) | Write fails | Size guard with gzip; chunks are already separate items |
| IAM policy mistakes | Denied requests or, worse, too-broad access | Policy simulator tests in M0; no `Scan` on the tenant role; separate service role |
| Local development needs AWS | Slower dev loop | DynamoDB Local in Docker, SQLite backend kept |
| Price figures | Small error in the estimate | Totals are dominated by compute, not by the data layer |

## 8. With the deadline (Fri 23 Oct, 21:00 CEST)

About 2.5 working days are left, against 5–7 days for the full K3.

1. **P-K3a, recommended if K3 must appear in the submission.**
   - Wed–Thu: do M0 and M1 for the per-user store only, timeboxed to Thursday 18:00.
   - Thu evening: if the parametrised suite is green, do M2, so the pipeline on AgentCore writes to DynamoDB with tenant-scoped IAM credentials.
   - `auth.db` and `ops.db` stay on the host until after the hackathon.
   - The video shows the IAM policy simulator denying a cross-tenant read, plus the DynamoDB console with the user's items.
2. **Fallback, automatic if the timebox fails.** Submit S1 with K1 (doc 15 §6, P1) with `STORAGE_BACKEND=sqlite`. The DynamoDB branch stays unmerged and K3 goes into the submission as roadmap with this document.
3. **Not recommended before the deadline:** porting auth and ops (M3), or migrating live data (M4). Both touch login and the admin console, which the demo depends on.

## 9. Sources
- Amazon Aurora overview: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_AuroraOverview.html
- Amazon RDS user guide: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html
- Aurora Serverless v2 auto-pause: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html
- RDS Data API: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.html · `DatabaseResumingException`: https://docs.aws.amazon.com/botocore/latest/reference/services/rds-data/client/exceptions/DatabaseResumingException.html
- Aurora DSQL: https://docs.aws.amazon.com/aurora-dsql/latest/userguide/what-is-aurora-dsql.html (plus its quotas, supported data types and PostgreSQL compatibility pages)
- DynamoDB documentation: https://docs.aws.amazon.com/dynamodb/ · quotas: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html · fine-grained access control: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html
- DynamoDB multi-tenancy modelling (AWS Database Blog): https://aws.amazon.com/blogs/database/amazon-dynamodb-data-modeling-for-multi-tenancy-part-2
- SaaS pooled storage isolation (AWS whitepaper): https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/pooled-storage-isolation-strategies.html
- DynamoDB zero-ETL to OpenSearch, best practices: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-integration-opensearch.html
- On-demand price cut of Nov 2024 (third party, verify on the pricing page): https://www.usage.ai/blogs/aws/database-savings-plans/dynamodb/on-demand-pricing/
