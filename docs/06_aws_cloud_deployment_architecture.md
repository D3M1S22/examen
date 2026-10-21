# ☁️ AWS Deployment Plan

> **Document Status:** Plan, revised 2026-10-21 against the code on `main` (multi-user, admin console, token usage). It replaces the first version of this document, written before the code existed in its current form: §1 explains what changed and why the original "serverless-first" topology does not fit today's EXAMEN as it is.
> **Related:** [15_aws_split_architecture_report.md](15_aws_split_architecture_report.md) (always-on ingestion + on-demand AgentCore, hackathon deadline), [14_aws_and_hackathon_reference.md](14_aws_and_hackathon_reference.md) (rules, AWS facts), [11_homelab_test_deployment.md](11_homelab_test_deployment.md) (running instance), [13_multi_user_accounts.md](13_multi_user_acc ounts.md) (accounts, tenancy), [next_steps/admin_console/](next_steps/admin_console/00_overview.md) (runtime settings, service log, token usage), [10_bee_cli_reference.md](10_bee_cli_reference.md) (Bee contract)
> **Prices:** us-east-1 / EU on-demand list prices gathered in October 2026 from AWS pages and third-party trackers (sources at the end). Verify them in the [AWS Pricing Calculator](https://calculator.aws/) before committing: they change, and EU regions are typically 5–15 % more expensive than us-east-1.
[text](../../../42/42_github/mastery/ft_linear_regression/data.csv)
---

## 1. What EXAMEN is today (and why the first plan no longer fits)

The first version of this document assumed a stateless LangGraph pipeline on **AgentCore Runtime**, data in **AgentCore Memory + DynamoDB**, the MCP server as a separate AgentCore runtime and the dashboard on **S3 + CloudFront**. The code took a different shape:

| Aspect | First plan | Code on `main` today | Consequence for AWS |
|---|---|---|---|
| Process model | Many serverless pieces | **One long-running Python process** (`src/serving/mcp_server.py`): REST API, user SSE, admin SSE, MCP (`/mcp`), static Next.js dashboard, per-user runtimes, health monitor | Needs always-on compute; scale-to-zero services do not fit |
| Bee ingestion | A "companion" pushing chunks | **One private `bee proxy` subprocess + a long-lived outbound SSE stream per linked user**, started inside the server (`OrchestratorManager`, `MAX_ACTIVE_USERS`) | Lambda (15 min), App Runner (CPU throttled when no request is in flight) and AgentCore Runtime sessions (max 8 h) cannot hold these streams |
| Bee CLI binary | — | Bun-compiled `bee` shipped only for **`linux-x64`** (`resources/bee-cli/dist/platforms/`) | Use **x86** instances, or build `bee` for `linux-arm64` first (Graviton is ~20 % cheaper) |
| Storage | AgentCore Memory + DynamoDB | **SQLite**: `auth.db` (accounts, sessions, tokens, Bee links, audit), `ops.db` (settings overrides, service log, incidents, token usage, WAL mode), one `examen.db` per user (actions, tasks, contacts, commitments, events, ingest ledger, coverage, backfill runs, FTS5 search) under `EXAMEN_DATA_DIR` | Needs a **local block disk** (EBS). SQLite **WAL does not work on NFS/EFS**; moving to DynamoDB or Postgres is a rewrite of `AbstractContextStore` (≈ 60 methods, FTS5) |
| Pipeline | AgentCore Runtime | `agent_invocation` runs **in-process** (`asyncio.to_thread`); the payload already carries `user_id`; the pipeline **writes to the user's SQLite store** (persist node) | A remote AgentCore runtime cannot reach the host's SQLite: it needs either shared storage or a "return results, host persists" refactor (§5) |
| In-memory state | — | SSE hubs, login rate limiter, Bee pairing state, MCP sessions (stateful streamable HTTP), metrics, token counters | **One instance only** until that state moves to a shared store |
| Auth | Cognito | Local accounts (e-mail + scrypt password, HttpOnly cookie, PATs for MCP), admin console | Works as is behind HTTPS; Cognito becomes useful for Alexa+ OAuth account linking (§6) |
| Config | `.env` | `.env` defaults + **admin runtime overrides** in `ops.db` (models, Bedrock ↔ Mantle, region, …) | Fine on one host; multi-instance needs `ops.db` shared (already synced every 30 s, but SQLite is local) |
| Dashboard | S3 + CloudFront | Next.js static export served by the same process (`src/web_ui/out`) | No separate hosting needed; CloudFront in front is optional (HTTPS, caching) |
| Container | — | `Dockerfile` exists but is **stale**: Python 3.11 (project: 3.12), no `bee` binary, no Bun, no data volume, CLI flags that `mcp_server` ignores | Must be rewritten before any container option (§4.3) |

Measured on the homelab (CT 147, 2 vCPU / 2 GB): the server idles at **≈ 115 MB RSS**. One Bee stream adds a private Bun `bee proxy` (estimated 50–80 MB, **not yet measured**: verification MU-V2). LLM calls are network-bound; CPU stays low.

**Conclusion:** the fastest, cheapest and lowest-risk path is to run today's process unchanged on one always-on instance with a local disk (§4.1). Serverless and AgentCore pieces become worthwhile in a second step, after specific refactors (§5).

---

## 2. Cost structure in one sentence

**Model tokens dominate.** Infrastructure for one instance costs ≈ $25–45 per month; tokens cost from ≈ $3 to ≈ $90 **per active user per month** depending on the gatekeeper model (§7). The model choice and the volume of gatekeeper calls matter more than any hosting decision. The admin console's token counter ([03 §8](next_steps/admin_console/03_service_log_and_anomalies.md)) measures the real figure.

---

## 3. Decisions to take

| # | Topic | Options | Recommendation |
|---|---|---|---|
| **H1** | Hosting | A EC2 single instance · B Lightsail · C ECS Fargate single task · D cloud-native split (§4) | **A** now; D only when more users or HA are needed |
| **H2** | Region | us-east-1 · EU (eu-central-1 Frankfurt, eu-west-1 Ireland, eu-south-1 Milan) | **EU** (eu-central-1 or eu-west-1): users are in the EU (GDPR data residency). Check Bedrock **and Mantle** availability of the chosen models there: the admin console *Test* button probes each role in the candidate region |
| **H3** | HTTPS entry | Caddy + Let's Encrypt on the instance · CloudFront in front of the instance · ALB | **CloudFront** (free tier, ACM certificate, optional WAF) or **Caddy** (simplest, no extra service). ALB only with Fargate / several instances |
| **H4** | Bedrock credentials | IAM **instance profile** · IAM user access keys in `.env` | **Instance profile** (no long-lived keys; Lightsail cannot use one) |
| **H5** | Gatekeeper model | Nemotron Super 3 120B (current) · Amazon Nova Micro / Lite · Claude Haiku 4.5 | Measure on the homelab with the token counter and the quality of extractions; Nova Micro/Lite are 3–5× cheaper than Nemotron, Haiku ~7× more expensive (§7) |
| **H6** | Pipeline execution | In-process (today) · AgentCore Runtime | In-process in phase 1; AgentCore after the persist refactor (§5.1) if the hackathon showcase matters |
| **H7** | Storage | SQLite on EBS · Aurora PostgreSQL Serverless v2 · DynamoDB | **SQLite on EBS** in phase 1; Postgres if/when D is chosen (closest to the relational model + full-text search) |
| **H8** | Sign-up on the public internet | Open · closed (`AUTH_ALLOW_SIGNUP=false`, admin creates accounts) · invite | **Closed** at launch: an open sign-up on a public URL lets anyone consume model tokens |
| **H9** | Alexa+ / MCP auth | Personal access tokens (today) · Cognito OAuth account linking | PATs for the first cloud test; Cognito when the Alexa+ integration requires OAuth (§6) |

---

## 4. Hosting options

### 4.1 Option A ★ — One EC2 instance, unchanged code (lift-and-shift)

```
Internet ──HTTPS──► CloudFront (ACM cert) ──HTTP──► EC2 t3a.medium (x86, 4 GB)    ┌─► Amazon Bedrock / Mantle (models)
                    or Caddy on the instance       systemd: examen + examen-update ├─► api.bee.computer (per-user SSE)
                                                   /var/lib/examen/data  (EBS gp3, encrypted)
                                                   IAM instance profile (bedrock:InvokeModel*)
                                                   DLM daily snapshots · nightly SQLite backup → S3
```

- **What changes in the code:** nothing. `deploy/homelab/deploy.sh` and `update.sh` (pull-based updates from `main`) work on an EC2 host; only the host, the `.env` (`MCP_ALLOWED_HOSTS`, `AUTH_COOKIE_SECURE=auto`, `CORS_ALLOWED_ORIGINS`, no AWS keys) and the systemd unit paths are checked.
- **Sizing:** `t3a.small` (2 GB) up to ~3 linked users; **`t3a.medium` (4 GB)** for the 5 users of `MAX_ACTIVE_USERS`; `t3a.large` (8 GB) beyond. Burstable CPU is enough (network-bound).

| Item | Monthly (us-east-1) |
|---|---|
| t3a.medium on-demand ($0.0376/h) | ≈ $27.5 (≈ $17–19 with a 1-year Savings Plan) |
| EBS gp3 30 GB ($0.08/GB) | $2.4 |
| Public IPv4 address ($0.005/h) | $3.6 |
| EBS snapshots (incremental, ~10 GB) + S3 backups | ≈ $1 |
| CloudFront (≤ 1 TB / 10 M requests free tier) or Caddy | $0 |
| Route 53 hosted zone (+ domain ≈ $13/year) | $0.5 (+ ≈ $1.1) |
| **Total infrastructure** | **≈ $35 / month** (≈ $25 with Savings Plan) |

- **Benefits:** working in a day; every feature (Bee streams, SSE, MCP sessions, admin console, settings overrides, token counter) behaves exactly as on the homelab; no NAT gateway; lowest cost; IAM instance profile for Bedrock.
- **Risks:** single point of failure (an instance or AZ failure means downtime until restore; RTO ≈ 15–30 min from snapshot); vertical scaling only; OS patching is ours (unattended-upgrades + SSM Patch Manager); backups must be tested.

### 4.2 Option B — Amazon Lightsail

Same layout as A on a Lightsail 4 GB instance (**$24/month** including IPv4, 80 GB SSD and 4 TB transfer; 2 GB at $12).

- **Benefits:** cheapest predictable bill; simple console; included transfer.
- **Risks:** **no IAM instance profile** → Bedrock needs IAM user access keys in `.env` (long-lived secrets on disk, rotation is manual); limited integration with CloudWatch, Backup and VPC; moving later to EC2/ECS means a migration. Acceptable for a demo; not recommended for real users.

### 4.3 Option C — ECS Fargate, one task

- **Layout:** ALB (ACM) → one Fargate task (x86, 1 vCPU / 4 GB) with the image of the app + `bee` binary.
- **Data:** on EFS, or on an EBS volume attached to the task. The EBS volume is created from a snapshot at task start, so persistence means snapshot orchestration.
- **Required work:** rewrite the `Dockerfile`: Python 3.12, `uv`, `bee` for linux-x64, the built dashboard, and `EXAMEN_DATA_DIR` on the volume. `update.sh` is replaced by image builds (ECR + CI).
- **Storage risk:** SQLite on EFS needs **`journal_mode=DELETE`** (`ops.db` uses WAL today), suffers NFS latency and locking corner cases, and must never be opened by two tasks.

| Item | Monthly |
|---|---|
| Fargate x86 1 vCPU / 4 GB ($0.04048/vCPU-h + $0.004445/GB-h) | ≈ $42.5 |
| ALB ($0.0225/h + LCU) | ≈ $18–22 |
| Public IPv4 (ALB in 2 AZs + task) | ≈ $7–11 |
| EFS (few GB) / ECR / CloudWatch Logs | ≈ $3–5 |
| **Total infrastructure** | **≈ $75–80 / month** |

- **Benefits:** no OS to patch; the task restarts on failure; immutable deployments.
- **Risks:** still **one task** (in-memory state, Bee streams); roughly double A's cost for the same availability; SQLite-on-network-storage risk; more moving parts (ECR, task definitions, ALB health checks on `/api/health`). Little value over A until the state moves out (D).

### 4.4 Option D — Cloud-native split (target for scale / HA)

```
CloudFront ─► ALB ─► API service (Fargate, ≥ 2 tasks, stateless): REST, SSE, MCP, dashboard
                         │  sessions/rate limit/SSE fan-out → ElastiCache (Valkey) or DynamoDB TTL + pub/sub
                         ▼
              Aurora PostgreSQL Serverless v2  (or DynamoDB)  ◄── ingestion workers (Fargate, N users per task)
              Secrets Manager: one secret per user's Bee token     bee proxy per user, orchestrator, event engine
              Cognito (dashboard + Alexa+ OAuth)                    ──► AgentCore Runtime: pipeline (optional)
```

- **Required work (weeks):**
  - storage layer on Postgres: ≈ 60 store methods, FTS5 → `tsvector`;
  - shared session, rate-limiter and SSE fan-out state;
  - ingestion workers with user assignment and leases;
  - Bee tokens in Secrets Manager, materialised into tmpfs (doc 13 §8);
  - `ops.db` and token usage moved to the database;
  - MCP stateless mode or sticky sessions.

| Item | Monthly |
|---|---|
| ALB + 2 API tasks (0.5 vCPU / 1 GB) | ≈ $20 + $36 |
| 1 ingestion worker (1 vCPU / 4 GB, ~5 users) | ≈ $42.5 |
| Aurora Serverless v2 (min 0.5 ACU) **or** DynamoDB on-demand | ≈ $45–50 **or** ≈ $5 |
| ElastiCache Valkey serverless (minimum) or DynamoDB | ≈ $6–12 |
| NAT gateway if private subnets (or VPC endpoints) | ≈ $33 (+ $0.045/GB) — avoid with public subnets + security groups |
| Secrets Manager ($0.40/secret), Cognito (free ≤ 10k MAU), CloudWatch | ≈ $5–8 |
| **Total infrastructure** | **≈ $150–200 / month** |

- **Benefits:** horizontal scaling; no single point of failure; rolling deploys without dropping Bee streams (workers drain); clean AWS story for the hackathon.
- **Risks:** large rewrite with regression risk across every feature; higher cost floor whatever the usage; operational complexity. Justified only above ~10–20 active users or with an availability requirement.

---

## 5. AgentCore: where it fits now

### 5.1 Pipeline on AgentCore Runtime (optional, after a refactor)

`src/pipeline/app.py` already exposes `@app.entrypoint agent_invocation` (`BedrockAgentCoreApp`) and checks the payload's `user_id`. What blocks a remote runtime is persistence: the nodes write into the caller's SQLite store.

| Approach | Work | Benefits | Risks |
|---|---|---|---|
| **5.1a ★ "Pipeline returns, host persists"** | The remote runtime runs the graph without a store and returns the extracted entities (actions, contacts, tasks, briefings); the host's orchestrator / backfill persist them with today's code. Needed context, such as pending tasks and known contacts, travels in the payload. Effective model settings travel in the payload too, since admin overrides live on the host (admin_console/02 §8) | Showcases AgentCore Runtime; offloads the LLM-heavy work; keeps SQLite | Payloads grow; social enrichment and merge logic must be split between the two sides; two deployment units |
| 5.1b Shared storage | Requires option D's database | Natural in D | Only with D |
| 5.1c Keep in-process | None | Simplest, lowest latency | No AgentCore in the story |

**Cost of AgentCore Runtime** (active-consumption billing, v2 rates: $0.1276/vCPU-h, $0.0169/GB-h). About 225 qualified chunks per user per day × ~8 s ≈ 0.5 h of sessions; CPU is mostly idle waiting on the model. That comes to **< $3 per user per month**, negligible next to tokens.

### 5.2 AgentCore Memory

**Not recommended as the primary store.** EXAMEN's data is relational (tasks with schedules, commitments with debtors, events with parts, the ingest ledger, coverage intervals, backfill runs) and queried by id and range. AgentCore Memory is designed for conversational events and extracted facts. It could later **complement** the stores for semantic recall ("what did Marco say about the contract?"), per user (`actorId = user_id`).

### 5.3 MCP server on AgentCore Runtime

Not recommended now. The MCP tools read the user's store (same storage constraint as 5.1), and `/mcp` already runs in the main process with per-call tenancy (`tenant_tool`). Revisit with D.

---

## 6. Cross-cutting concerns

| Concern | Phase 1 (option A) |
|---|---|
| **HTTPS / cookies** | CloudFront or Caddy terminates TLS; `AUTH_COOKIE_SECURE=auto` uses `X-Forwarded-Proto`; set `CORS_ALLOWED_ORIGINS` and `MCP_ALLOWED_HOSTS` to the public domain (otherwise `/mcp` answers 421) |
| **SSE through CloudFront** | User and admin SSE send a keep-alive every 15 s (below CloudFront's 30–60 s origin read timeout); disable caching on `/api/*` and `/mcp` (managed policy *CachingDisabled*, forward cookies and the `Authorization` header) |
| **Security group** | 443 (or only CloudFront's managed prefix list) inbound; no SSH: use **SSM Session Manager**; IMDSv2 required |
| **IAM** | Instance profile with `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`, `bedrock:Converse*` on the used models / inference profiles; Mantle bearer tokens are minted from the same role (`aws_bedrock_token_generator`); S3 write for backups |
| **Secrets** | `.env` (mode 600, owned by `examen`) holds only non-AWS secrets; Bee tokens stay in each user's folder on the encrypted EBS volume |
| **Backups** | DLM daily EBS snapshots (7 days) + nightly `sqlite3 .backup` of `auth.db`, `ops.db` and users' DBs to a versioned S3 bucket with a lifecycle rule (30 days). Test a restore before inviting users |
| **Updates** | Same pull-based `examen-update.timer` from `main` (deploy key), health check on `/api/health` with automatic rollback |
| **Monitoring** | The admin console (incidents, health, token usage) + CloudWatch alarm on instance status check (auto-recover) + optional CloudWatch agent for journald (≈ $0.50/GB ingested) |
| **Alexa+ / Echo Show** | Public HTTPS `/mcp` with a PAT for the first tests. Production Alexa+ account linking needs an OAuth 2.0 authorization server: a Cognito user pool (Essentials, free ≤ 10k MAU) federated with EXAMEN accounts, or an OAuth endpoint in EXAMEN; to be designed with the Alexa+ requirements |
| **Sign-up & abuse** | `AUTH_ALLOW_SIGNUP=false` on the public internet; optional AWS WAF on CloudFront (≈ $5 + $1/rule + $0.60/M requests) for rate-based rules |
| **Data protection** | EU region, encrypted EBS and S3, per-user data folders, GDPR export / erasure already implemented; Bedrock does not store prompts by default (verify the model provider's terms for Mantle / third-party models) |

---

## 7. Model token costs (the dominant cost)

**Volume model per active user per day.** These are assumptions; the token counter of the admin console replaces them with real figures after a week on the homelab.

| Stage | Calls/day | Tokens per call (measured 2026-10-21) | Tokens/day |
|---|---|---|---|
| Gatekeeper (every utterance screened live) | 1 500 | ≈ 1 120 in / 60 out | 1.68 M in / 0.09 M out |
| Pipeline extraction (≈ 15 % qualified × ~2 nodes) | 450 | ≈ 1 260 in / 115 out | 0.57 M in / 0.05 M out |
| Reasoner (Deep Topic syntheses) | 5 | ≈ 10 000 in / 2 500 out | 0.05 M in / 0.01 M out |
| Embeddings (topic continuity) | 500 | ≈ 300 in | 0.15 M |
| **Total** | | | **≈ 2.3 M in / 0.16 M out per day ≈ 70 M in / 4.8 M out per month** |

**Monthly cost per active user**, with the same model for gatekeeper, extraction and reasoner, and on-demand list prices:

| Model (input / output per 1M tokens) | Per user / month | 5 users / month |
|---|---|---|
| Amazon Nova Micro ($0.035 / $0.14) | ≈ $3 | ≈ $15 |
| Amazon Nova Lite ($0.06 / $0.24) | ≈ $5 | ≈ $27 |
| **NVIDIA Nemotron Super 3 120B** — current ($0.15 / $0.65) | **≈ $13.5** | **≈ $68** |
| Claude Haiku 4.5 ($1 / $5) | ≈ $94 | ≈ $470 |
| Titan Text Embeddings V2 (≈ $0.02 per 1M, add-on) | ≈ $0.1 | ≈ $0.5 |

**Levers**, in order of impact:
1. **Gatekeeper model.** About 75 % of the tokens are gatekeeper input. A cheap screening model plus a stronger reasoner keeps quality where it matters. For example, Nova Micro gatekeeper and Nemotron reasoner come to ≈ $4–5 per user per month. The admin console switches models per role at runtime and tests them before saving.
2. **Prompt caching.** Most of the ~1 100 gatekeeper input tokens are the fixed system prompt. On models with Bedrock prompt caching (Claude, Nova), cached reads cost ≈ 10 % of input. The token counter already reports cache reads and writes.
3. **Fewer gatekeeper calls.** A cheap local pre-filter (very short or filler utterances → noop) and live window screening, as already done for history in `historical_backfill/07`, cut calls by 3–5×.
4. **Backfill budget.** `BACKFILL_MAX_ESTIMATED_COST_USD` caps each history catch-up.
5. **Batch / Flex tiers** for non-urgent work such as backfill: about half the price on the models that offer them.

---

## 8. Total monthly estimate (5 active users)

| Scenario | Infrastructure | Tokens (Nemotron, today) | Tokens (Nova Micro gatekeeper + Nemotron reasoner) | Total |
|---|---|---|---|---|
| **A — EC2 t3a.medium** ★ | ≈ $35 (≈ $25 with Savings Plan) | ≈ $68 | ≈ $22 | **≈ $50–100** |
| B — Lightsail 4 GB | ≈ $26 | ≈ $68 | ≈ $22 | ≈ $50–95 |
| C — Fargate single task | ≈ $75–80 | ≈ $68 | ≈ $22 | ≈ $100–150 |
| D — cloud-native | ≈ $150–200 | ≈ $68 | ≈ $22 | ≈ $175–270 + weeks of work |
| A + AgentCore pipeline (5.1a) | ≈ $35 + < $15 | ≈ $68 | ≈ $22 | ≈ $65–120 |

Data transfer is negligible at this scale: Bee streams are inbound (free), Bedrock in-region traffic from a public subnet is not billed as transfer, and the first 100 GB/month of internet egress are free.

---

## 9. Phased plan

| Phase | Scope | Effort | Exit criteria |
|---|---|---|---|
| **0 — Preparation** | Measure MU-V2 (Bee proxy RSS) and a week of real token usage on the homelab; choose region (H2) and gatekeeper model (H5) with the admin console *Test*; check Bedrock / Mantle model availability in that region; register a domain | 1–2 days | Sizing and model decided with numbers |
| **1 — Option A** | Account baseline (IAM roles, budgets and alerts, CloudTrail); EC2 + EBS + instance profile + SSM; CloudFront or Caddy; deploy with the existing scripts (x86, `bee` linux-x64); `.env` for the public domain; sign-up closed; backups (DLM + S3) with a tested restore; CloudWatch auto-recover; AWS Budgets alert on Bedrock spend | 1–2 days | Two real users with their Bee streams on the public URL; admin console green; restore drill done |
| **2 — Hardening** | WAF rate rules (optional); Infrastructure as Code (CDK or Terraform) for the phase-1 stack; Savings Plan once usage is stable; prompt caching / pre-filter for the gatekeeper | 2–4 days | Reproducible stack; token cost per user within the target |
| **3 — AgentCore pipeline (optional, 5.1a)** | Persist refactor; deploy `agent_invocation` to AgentCore Runtime (arm64 or x86 container); orchestrator switch `PIPELINE_MODE=local\|agentcore` | 1–2 weeks | Same test suite green with the remote pipeline; latency within +20 % |
| **4 — Cloud-native (only if needed)** | Option D: Postgres store, shared state, ingestion workers, Secrets Manager, Cognito / Alexa+ OAuth | 4–8 weeks | > 10–20 users or HA requirement |

---

## 10. Open questions

| # | Question | Default |
|---|---|---|
| Q1 | Is the hackathon evaluation tied to using AgentCore? | If yes, plan phase 3 right after phase 1 |
| Q2 | Expected number of users in the first months | ≤ 5 → option A |
| Q3 | EU region: which models (gatekeeper, reasoner, embeddings) and Mantle are available there? | Verify with the admin console probes before choosing |
| Q4 | Alexa+ account linking requirements (OAuth flow, scopes) | PATs until the Alexa+ integration is defined |
| Q5 | Availability target (acceptable downtime) | Best effort with snapshot restore (option A) |
| Q6 | Build `bee` for linux-arm64 to use Graviton (~20 % cheaper)? | Not in phase 1 |

---

## Sources (prices, October 2026)

- AgentCore pricing: [CloudBurn breakdown](https://cloudburn.io/blog/amazon-bedrock-agentcore-pricing), [AWS Builder Center](https://builder.aws.com/content/3KC60kJzFVDfHVxJ5CNecLZVPmA/amazon-bedrock-agentcore-pricing-hidden-costs-that-bill-while-your-agent-idles), [AWS AgentCore pricing](https://aws.amazon.com/vi/bedrock/agentcore/pricing/)
- Nemotron Super 3 120B on Bedrock: [cloudprice.net](https://cloudprice.net/models/nvidia-nemotron-super-3-120b), [Future AGI calculator](https://futureagi.com/llm-cost-calculator/bedrock/nvidia-nemotron-super-3-120b)
- Fargate: [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/), [CloudBurn Fargate](https://cloudburn.io/blog/aws-fargate-pricing)
- EC2: [Holori t3a.small](https://calculator.holori.com/aws/ec2/t3a.small/us-east-1), [Holori t3a.medium](https://calculator.holori.com/aws/ec2/t3a.medium/us-east-1), [Holori t4g.small](https://calculator.holori.com/aws/ec2/t4g.small/us-east-1)
- ALB and Lightsail: [Spendark ALB vs NLB](https://spendark.com/blog/alb-vs-nlb-pricing/), [CloudBurn Lightsail](https://cloudburn.io/blog/amazon-lightsail-pricing), [Lightsail bundles](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)
- Bedrock models (Claude Haiku 4.5, Nova, Titan): [ManageEngine](https://www.manageengine.com/cloudspend/articles/amazon-bedrock-pricing.html), [Caylent](https://caylent.com/blog/amazon-bedrock-pricing-explained), [CloudZero](https://www.cloudzero.com/blog/amazon-bedrock-pricing)
- Cognito, Secrets Manager, IPv4: [AWS Cognito pricing](https://aws.amazon.com/cognito/pricing), [computingforgeeks AWS costs](https://computingforgeeks.com/aws-costs-explained-real-numbers/)

Prices not found in these searches and quoted from AWS's standard published rates are marked with "≈": EBS gp3, snapshots, S3, Route 53, NAT gateway, Aurora Serverless v2, ElastiCache, WAF, CloudWatch. Re-check all of them in the AWS Pricing Calculator for the chosen region.
