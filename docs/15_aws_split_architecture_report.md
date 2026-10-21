# 🧭 Report: always-on ingestion + on-demand AgentCore

> **Date:** 2026-10-21 · **Question:** can EXAMEN be split so that only ingestion and the gatekeeper run all the time, on a low-cost service, while the rest of the workflow runs on AgentCore only when needed, with other AWS services used where they fit (front-end, databases)?
> **Inputs:** current code on `main`, [06](06_aws_cloud_deployment_architecture.md) (deployment plan), [14](14_aws_and_hackathon_reference.md) (rules, AWS facts and prices with sources).

---

## 1. Verdict

**The split follows a seam that already exists in the code, and it is the right target architecture.**

- **Where the line falls.** The gatekeeper screens every utterance, but only the qualified ones (≈ 15 % in our scenarios) need the expensive part: pipeline extraction, social web enrichment, Deep Topic syntheses and history backfill. That expensive part is exactly what AgentCore Runtime is built for: bursty work, per-session microVM isolation, asynchronous jobs up to 8 hours, CPU billed only while active.
- **What it does not change.** The **token bill stays the same**, and the always-on box barely shrinks: the gatekeeper and the pipeline are API calls to Bedrock, not local compute. The gains are elsewhere:
  - isolation between users;
  - independent scaling of heavy bursts (a backfill run no longer competes with live ingestion on the same host);
  - a clean AWS story for the jury.
- **The obstacle is data, not compute.** The pipeline, the syntheses and the backfill read and write the user's SQLite store on the host, which a remote runtime cannot reach. How AgentCore gets its data (§3) decides the effort, from about 1 day to several weeks.
- **The deadline is in two days:** Friday 23 October, 12:00 PT = 21:00 in Italy. The rules **do not require a hosted deployment**, and Bedrock at runtime already qualifies for the AWS Builder mini-challenge. A full migration before the deadline is not realistic; a minimal AgentCore step is possible but optional (§6).

---

## 2. What runs where

| Component (code) | Nature | In the split |
|---|---|---|
| Bee client + private `bee proxy` per user, orchestrator, ring buffer, speaker tags, location poll (`src/ingestion/stream_convo.py`, `orchestrator.py`) | Long-lived streams, stateful | **Always-on** |
| Gatekeeper (`gatekeeper.py`), ingest ledger, coverage tracker | One small call per utterance; must stay close to the stream | **Always-on** |
| Event Engine state machine: open / close events, timers, cues (`event_engine.py`) | Stateful, ticks every 15 s, cheap | **Always-on** (state); its LLM **synthesis jobs** move out |
| Pipeline: action, social, scheduler, topic research nodes (`src/pipeline/`) | Bursty, LLM-heavy, ≈ 15 % of utterances | **AgentCore Runtime** (HTTP protocol, `agent_invocation` already exists) |
| Deep Topic part / consolidated synthesis (event engine jobs, reasoner model) | Minutes, rare | **AgentCore** (async task) |
| History backfill runs (`backfill.py`) | Minutes to hours, heavy | **AgentCore** (async task, up to 8 h) |
| Social web enrichment (`social_profiler.py`, web search) | Slow external calls | **AgentCore** (inside the pipeline) |
| REST API, user SSE, admin console, MCP for Alexa+ (`mcp_server.py`) | Request-driven; SSE needs long connections | Always-on host now; **Lambda / ECS Express** later (§4) |
| Dashboard (Next.js static export) | Static files | **S3 + CloudFront** (or Amplify Hosting) |
| Accounts, sessions, settings, service log, token usage (`auth.db`, `ops.db`) | Small, transactional | SQLite now; **DynamoDB** later |
| Per-user data (`users/<id>/examen.db`, FTS5) | Relational, per user | SQLite now; **Aurora PostgreSQL** or **DynamoDB** later |
| Bee tokens (files per user) | Secrets | Encrypted EBS now; **Secrets Manager** later |

---

## 3. The key decision: how AgentCore reaches the user's data

The pipeline uses **13 store methods**:
- reads: `get_planned_task`, `list_planned_tasks`, `search_social_contact`, `get_verified_action`, `get_cached_search`;
- writes: `save_action`, `save_social_contact`, `save_planned_task`, `save_topic_briefing`, `update_contact_web_profile`, `link_micro_event_to_session`, `record_latency`, `put_cached_search`.

| Option | How | Effort | Benefits | Risks |
|---|---|---|---|---|
| **K1 — Context in, results out** | The host adds the read context to the payload (pending tasks, candidate contacts, cached searches); the AgentCore pipeline runs with an in-memory store and returns what it would have written; the host applies the writes with the existing store code | **1–2 days** | No database migration; the host stays the only writer (no concurrency issues); easy to fall back to in-process (`PIPELINE_MODE=local\|agentcore`) | Payload grows; contact merge and enrichment logic must use only the provided context (a contact created a second earlier by another chunk may be missed) |
| **K2 — Remote store over an internal API** | `RemoteContextStore` implements those 13 methods through an authenticated internal endpoint on the host (per-user token minted per invocation) | 2–3 days | Pipeline code unchanged; always reads fresh data | The host must be reachable from AgentCore (public HTTPS endpoint, auth to protect); one network round trip per store call; the host remains a single point of failure |
| **K3 — Shared database** | Both sides use DynamoDB or Aurora | 3–6 weeks (rewrite of ≈ 60 store methods, full-text search) | The real cloud-native end state; enables a stateless API (§4) | Large regression surface; not doable before the deadline |

**Recommendation:** **K1** for the first step. It keeps one writer, stays safe for multi-tenancy (the payload already carries `user_id`, checked by `agent_invocation`) and can be switched off. **K3** only with the full split (§4, S2). K3 deep-dive (DynamoDB vs Aurora DSQL vs Aurora Serverless v2): [16](16_aws_data_layer_k3.md).

Other points to solve in every option:
- **Runtime settings.** Admin overrides live on the host, so the effective model configuration travels in the payload (admin_console/02 §8).
- **Token usage.** The remote runtime must return its token counts, and the host records them, so the Health card stays complete.
- **Packaging.** The runtime needs an ARM64 package; the AgentCore CLI builds the container in CodeBuild. The Bee CLI is not needed there.
- **Retries.** A pipeline failure must leave the utterance `failed` in the ledger (already the case), so the backfill retries it.

---

## 4. Architecture options

### S0 — Monolith on one host (reference, [06](06_aws_cloud_deployment_architecture.md) option A)
EC2 t3a.medium running today's process, with CloudFront in front. Infrastructure ≈ **$35/month**. No split.

### S1 ★ — Hybrid: always-on host + AgentCore for the heavy work (1–3 days)

```
                 CloudFront ─┬─ /*            → S3 (dashboard static export)
 Browser / Alexa+ ───────────┴─ /api/*, /mcp  → EC2 t3a.small (always-on)
                                                 ├─ per-user Bee streams + gatekeeper + ledger + event state
                                                 ├─ REST, SSE, admin console, MCP
                                                 ├─ SQLite on encrypted EBS (single writer)
                                                 └─ InvokeAgentRuntime (SigV4, instance role) ──► AgentCore Runtime (ARM64, V2)
                                                       payload: user_id + utterance + context (K1)      pipeline · syntheses · backfill (async)
                                                       result: entities to persist + token counts       Bedrock / Mantle models
```

| Item | Monthly (5 users) |
|---|---|
| EC2 t3a.small (2 GB: no heavy work left on the host) | ≈ $13.7 |
| EBS 20 GB + snapshots, public IPv4 | ≈ $2.6 + $3.6 |
| CloudFront + S3 (dashboard, within the free tier) | ≈ $0–1 |
| AgentCore Runtime V2 (≈ 225 dispatches/user/day × ~10 s, CPU active ~2 s each, session stopped after each call; plus syntheses) | ≈ **$1–3 per user** → $5–15 |
| CloudWatch (AgentCore traces and logs) | ≈ $2–3 |
| **Total infrastructure** | **≈ $30–40** |

- **Benefits:**
  - the split as designed, reusing almost all the code;
  - the host shrinks to a 2 GB instance because backfill bursts leave it;
  - each pipeline run is isolated in its own microVM;
  - visible AgentCore usage (Runtime, Observability) for the mini-challenge.
- **Risks:**
  - two deployment units (host and runtime) that must stay compatible: version the payload;
  - pipeline latency rises by the invoke round trip and cold starts. Mitigated by platform V2, and the pipeline is asynchronous anyway;
  - K1 context limits (§3);
  - remote failures must fall back cleanly (retry via ledger, `PIPELINE_MODE=local`).

### S2 — Full split, serverless around the always-on worker (3–6 weeks)

```
 CloudFront ─┬─ /*                  → S3 or Amplify Hosting (dashboard)
             └─ /api/*, /mcp, SSE   → API: Lambda (Function URL, response streaming) or ECS Express (Fargate)
                                       Cognito (dashboard + Alexa+ OAuth) · DynamoDB / Aurora (shared data)
 Ingestion worker (no inbound traffic): Fargate Spot or EC2 t3a.small
   per-user Bee streams (tokens from Secrets Manager) · gatekeeper · ledger · event state → DynamoDB / Aurora
   qualified chunks ──► SQS (retries, DLQ) ──► AgentCore Runtime (pipeline, syntheses, backfill) ──► DynamoDB / Aurora
   UI events: DynamoDB Streams / EventBridge → API → SSE (or polling)
```

| Item | Monthly (5 users) |
|---|---|
| Ingestion worker: Fargate **Spot** x86 0.5 vCPU / 2 GB (≈ $6.4) **or** EC2 t3a.small ($13.7) | ≈ $6–14 + IPv4 $3.6 |
| API on Lambda (low traffic, mostly free tier) **or** ECS Express (Fargate 0.5 vCPU + shared ALB ≈ $16) | ≈ $0–2 **or** ≈ $35 |
| DynamoDB on-demand (≈ 3 k writes / user / day ≈ $0.06/month each; storage in the free tier) **or** Aurora Serverless v2 (min 0.5 ACU) | ≈ $1–3 **or** ≈ $45 |
| AgentCore Runtime | ≈ $5–15 |
| SQS, EventBridge, Secrets Manager (5 × $0.40), Cognito (free ≤ 10 k MAU) | ≈ $2–3 |
| S3 + CloudFront / Amplify, CloudWatch | ≈ $3–5 |
| **Total infrastructure** | **≈ $20–40** (Lambda + DynamoDB) · **≈ $100–120** (ECS Express + Aurora) |

- **Benefits:**
  - the lowest always-on floor;
  - every piece scales on its own;
  - no single host for data;
  - the most complete AWS showcase (Runtime, Cognito, DynamoDB, SQS, CloudFront).
  - Spot interruptions are tolerable: EXAMEN's coverage ledger and backfill already detect and recover gaps.
- **Risks:**
  - rewrite of the storage layer (≈ 60 methods; DynamoDB has no full-text search, so contact search becomes per-user scans, or Aurora with `tsvector`);
  - SSE across Lambda's 15-minute limit (clients reconnect) or a move to WebSockets / polling;
  - MCP in stateless mode;
  - shared rate limiter and session state;
  - many moving parts to operate.

---

## 5. Sub-choices with trade-offs

| Topic | Options | Recommendation |
|---|---|---|
| Always-on compute | EC2 t3a.small · Fargate (x86) · **Fargate Spot** · Lightsail · ~~App Runner~~ (closed to new customers since 30 April 2026) · ~~Lambda~~ (15 min) | **EC2 t3a.small** in S1 (local disk for SQLite); Fargate Spot in S2 (no local state) |
| Hand-off to AgentCore | Direct `InvokeAgentRuntime` from the host · SQS between them | Direct in S1 (the ledger already tracks failures); SQS in S2 |
| Front-end | **S3 + CloudFront** (one distribution with S3 and API origins: same origin, cookies unchanged) · Amplify Hosting (CI from Git, simpler) | S3 + CloudFront: Amplify on a different origin would need CORS with credentials and same-site cookies |
| Accounts & auth | Local accounts (today) · Cognito | Local in S1; Cognito in S2 or when Alexa+ OAuth is needed |
| Per-user data | SQLite on EBS · DynamoDB · Aurora PostgreSQL / Aurora DSQL | SQLite in S1; DynamoDB (cheapest) or Aurora (least rewrite pain for queries and search) in S2 |
| AgentCore Memory | Primary store · add-on · none | None now; possible add-on for semantic recall |
| Region | us-east-1 · eu-central-1 / eu-west-1 | **eu-central-1 or eu-west-1** (Runtime, Memory, Gateway, Identity all available); verify models with the admin console *Test* |

---

## 6. With the deadline in two days

| Path | Content | Time | Risk |
|---|---|---|---|
| **P1 ★ Submission first** | No infrastructure change; record the video on the homelab (Bee live + Alexa+ via MCP or a simulated Alexa+ UI); fix the repository requirements; write the description, the product feedback per tool (Bee CLI, Bedrock, Mantle, AgentCore SDK, MCP) and the friction log (up to +10 %); present S1 / S2 as the deployment plan | 1–1.5 days | Low |
| P2 P1 + S1 minimal | P1, plus the pipeline on AgentCore Runtime with K1 behind `PIPELINE_MODE` (default `local`), deployed once and shown working in the video | + 1 day | Medium: new code path in the last hours; keep `local` as the safe default |
| P3 S2 | Full split | weeks | Not feasible before the deadline |

**Submission checklist** (from the rules, [14](14_aws_and_hackathon_reference.md) §1):
- [ ] **Repository:** public **with an open-source license** — there is **no LICENSE file today** — or private, shared with `testing@devpost.com` and `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar`. Today the origin is `github.com/D3M1S22/amazon_challenge`.
- [ ] **README:** clear setup and run instructions: `.env` keys, `uv sync`, `./scripts/build_ui.sh`, `bee login`, server start, first admin.
- [ ] **Video:** under 3 minutes, public on YouTube or Vimeo, the project running on the intended devices (Bee via the Apple Watch app, Echo Show / Alexa+ or the simulated Alexa+), no unlicensed music.
- [ ] **Text:** English description, product feedback per tool, track (Bee, Alexa+) and AWS Builder mini-challenge selected.
- [ ] **Friction log:** entries complete with task, steps, expected vs actual, severity, workaround and suggestion.
- [ ] **Testing instructions:** if a live URL is offered, give credentials and keep it free until 20 November.

---

## 7. Proposed next step

1. Choose **P1** or **P2** for the submission.
2. After the submission, implement **S1** (K1 + EC2 t3a.small in eu-central-1 + S3/CloudFront) following [06](06_aws_cloud_deployment_architecture.md) phase 1 and 3.
3. Measure a week of real token usage and AgentCore cost with the admin console.
4. Decide on **S2** (DynamoDB vs Aurora) only if users or availability require it.
