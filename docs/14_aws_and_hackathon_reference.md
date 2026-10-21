# 📚 AWS & Hackathon Reference (saved 2026-10-21)

> Facts collected from the official hackathon pages and the AWS documentation that matter for EXAMEN's submission and AWS deployment. Each item links its source. Re-check the sources before acting on them: rules and quotas change.
> **Related:** [04_hackathon_strategy_demo.md](04_hackathon_strategy_demo.md) (pitch, video), [06_aws_cloud_deployment_architecture.md](06_aws_cloud_deployment_architecture.md) (deployment plan), [15_aws_split_architecture_report.md](15_aws_split_architecture_report.md) (always-on ingestion + on-demand AgentCore)

---

## 1. Amazon Developer Hackathon 2026 — rules that affect us

Source: [Official rules](https://amazonappdev2026.devpost.com/rules), [Resources](https://amazonappdev2026.devpost.com/resources), [AWS Builder Center post](https://builder.aws.com/content/3JP06xAFFqTUXpD9kECgYcjVHWQ/aws-hackathons-still-open-build-compete-and-ship-before-october-ends).

| Topic | Rule |
|---|---|
| **Deadline** | **Friday 23 October 2026, 12:00 Pacific Time = 21:00 Italy (CEST)**. Judging 9–20 November; winners around 3 December |
| Tracks | Fire TV, **Alexa+**, **Bee (Wearable AI)**, Ring; mini-challenges **AWS Builder** and Open Source (they add to a primary-track project) |
| **Bee track** | Must use data recorded by a Bee device or an Apple Watch running Bee, through Bee's CLI, MCP or Agent Skills. The demo must show that data delivering value to a user; the code must call Bee at runtime (mentioning it in the README is not enough). Priority: education, developer experience, personal productivity. Public-facing integration not required |
| **Alexa+ track** | A working Agent Skill **or** a self-hosted MCP server implementing MCP **2025-11-25** over Streamable HTTP; a *simulated* Alexa+ experience built with any agentic tool is also accepted (source in the repo, simulation clearly shown in the video). EXAMEN's MCP SDK (`mcp` 1.30.0) supports `2025-11-25` |
| **AWS Builder mini-challenge** | Any primary-track project that incorporates AWS services with documented integrations, for example Amazon Bedrock, AgentCore, Strands SDK, Kiro, SageMaker. **Bedrock at runtime already qualifies**; AgentCore is not mandatory. Describe which AWS services you used and how in the *Product Feedback* section. Prize: $5,000 + $5,000 AWS credits + meeting with the Amazon Developer team |
| Credits | Credit codes are exhausted (7 October update): AWS costs are on us |
| Judging | Stage 1 pass/fail: fits the theme and uses the required APIs/SDKs. Stage 2, four equally weighted criteria: **Tech Implementation, Design, Potential Impact, Quality of the Idea** |
| **Friction log bonus** | Optional entries (task, steps, expected vs actual, severity, workaround, suggestion) → up to **+10 %** of the final score. EXAMEN keeps [FRICTION_LOG.md](../FRICTION_LOG.md) |
| Video | **Under 3 minutes**; shows the project running on the intended device; public on YouTube or Vimeo; no unlicensed music or trademarks |
| Repository | All source, assets and **clear setup and run instructions**. Either public with an open-source license visible in *About*, or private shared with `testing@devpost.com` and the GitHub users `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar` |
| Testing | **No hosted deployment required**: judges may evaluate from repo, text, images and video. If a private website is offered, give login credentials; it must stay free and unrestricted until the end of judging |
| Product feedback | Per tool/API/SDK: what you used it for, what worked, what needs work, onboarding from zero to hello world, would you build with it again (yes/no + why) |
| Language | English (or English translations of video, description and testing instructions) |
| Pre-existing code | Allowed only if *significantly updated* after 31 August 2026; explain the update and demo the new features |

**Resources listed for our tracks:**
- Bee: [docs.bee.computer](https://docs.bee.computer/), [bee-cli](https://github.com/bee-computer/bee-cli), [bee-skill](https://github.com/bee-computer/bee-skill).
- Alexa+: [Build with Agent Skills](https://apps.extensions.modelcontextprotocol.io/api/#build-with-agent-skills), [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http).
- AWS: [AWS Builder Center](https://builder.aws.com/), [Learn on Builder Center](https://builder.aws.com/learn).
- All tracks: [Amazon Devices Builder Tools (MCP server + Agent Skills)](https://developer.amazon.com/docs/vega/0.24/mcp-server), [developer docs](https://developer.amazon.com/docs/apps-and-games/documentation.html), [AmazonAppDev samples](https://github.com/amazonappdev), [community forum](https://community.amazondeveloper.com/).
- Live office hours: schedule on the landing page.

---

## 2. Amazon Bedrock AgentCore

Sources: [Runtime overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html), [Quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html), [Service contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html), [HTTP contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html), [Async / long-running](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html), [Regions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html), [Direct code deploy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy.html).

### 2.1 Runtime
- **What it is:** serverless hosting for agents and tools, framework-agnostic (LangGraph, Strands, CrewAI, custom) and model-agnostic.
- **Session model:** each session runs in its own **microVM**, terminated and sanitised at the end. Session id header: `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` (≥ 33 characters).
- **Compute types:**
  - *microVMs*: serverless, sessions up to **8 h**;
  - *Instances*: managed EC2 in your account, sessions up to **14 days**, GPUs, several agents per instance. Instances are available in eu-central-1 and eu-west-1 but **not** in Milan or Paris.
- **Platform V2:** starts from a snapshot for fast, consistent cold starts; recommended.
- **Protocols:**

| Protocol | Port | Path |
|---|---|---|
| HTTP | 8080 | `POST /invocations` (JSON or SSE), `GET /ping`, optional `/ws` |
| MCP | 8000 | `/mcp` |
| A2A | 9000 | `/` |
| AG-UI | 8080 | `/invocations`, `/ws` |

  Inbound auth: SigV4 or OAuth 2.0 / JWT (Cognito, Okta, Entra ID).
- **Architecture: ARM64 only.** The direct-code ZIP must contain aarch64 wheels: `uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary=:all: --target=deployment_package -r pyproject.toml`. Container images must be `linux/arm64`; the AgentCore CLI can build them in CodeBuild.
- **Size limits:** ZIP ≤ 250 MB compressed and ≤ 750 MB uncompressed; Docker image ≤ 2 GB.
- **Per session:** at most 2 vCPU / 8 GB; session storage 1 GB.
- **Invocation limits:**
  - synchronous request timeout 15 min;
  - payload 100 MB;
  - streaming 60 min, chunks 10 MB;
  - **asynchronous jobs up to 8 h**;
  - idle session timeout 15 min, adjustable with `idleRuntimeSessionTimeout`;
  - max lifetime 8 h, adjustable with `maxLifetime`.
- **Throttling:** data plane 1 000 TPS per account; new sessions **25 TPS**; active sessions 5 000 in us-east-1 / us-west-2 and 2 500 elsewhere.
- **Async work:**
  - `app.add_async_task(name)` … `app.complete_async_task(id)`, or a custom `@app.ping` returning `HealthyBusy`, keeps the session alive while background work runs;
  - `@app.entrypoint` must not block, so `/ping` keeps answering: use threads or async;
  - never set `time_of_last_update` on every ping, or sessions never time out.
- **Billing:** consumption-based. CPU is billed only while active, so time spent waiting on the LLM is typically free. Memory is billed for the session's lifetime; V2 reclaims idle memory after 120 s. Rates in us-east-1:

| Platform | vCPU-hour | GB-hour |
|---|---|---|
| V1 | $0.0895 | $0.00945 |
| V2 | $0.1276 | $0.0169 |

  Sources for the rates: [CloudBurn](https://cloudburn.io/blog/amazon-bedrock-agentcore-pricing), [AWS Builder Center](https://builder.aws.com/content/3KC60kJzFVDfHVxJ5CNecLZVPmA/amazon-bedrock-agentcore-pricing-hidden-costs-that-bill-while-your-agent-idles).
- **EXAMEN today:**
  - `src/pipeline/app.py` already declares `BedrockAgentCoreApp` with `@app.entrypoint agent_invocation`, and the payload carries `user_id`;
  - `bedrock-agentcore` 1.24.1 is installed;
  - what blocks a remote run: the pipeline writes into the host's SQLite store (13 store methods, see [15](15_aws_split_architecture_report.md) §3).

### 2.2 Other AgentCore services
| Service | Use for EXAMEN | Notes |
|---|---|---|
| **Gateway** | Turn APIs and Lambdas into MCP tools behind one managed endpoint with auth | Up to 100 targets per gateway; 15-minute invocation timeout. Optional: EXAMEN's MCP server is already self-hosted |
| **Identity** | Inbound OAuth (Alexa+ account linking with Cognito); outbound credential vault | Available in every region |
| **Memory** | Not a primary store for EXAMEN's relational data; possible add-on for semantic recall | Events: max 100 messages and 10 MB per `CreateEvent`; 150 k tokens/min for long-term extraction. Not available in Milan |
| **Observability** | Traces of agent steps and model calls in CloudWatch | All regions |

### 2.3 Regions (EU)
| Region | Runtime microVMs | Runtime Instances | Memory | Gateway / Identity |
|---|---|---|---|---|
| eu-central-1 Frankfurt | ✓ | ✓ | ✓ | ✓ |
| eu-west-1 Ireland | ✓ | ✓ | ✓ | ✓ |
| eu-west-2 London | ✓ | — | ✓ | ✓ |
| eu-south-1 Milan | ✓ | — | — | ✓ |
| eu-west-3 Paris | ✓ | — | ✓ | ✓ |

Model availability (Bedrock and Mantle) must be checked per region separately: use the admin console *Test* button.

---

## 3. Compute for the always-on part

| Service | Fact | Source |
|---|---|---|
| **EC2** (x86, burstable) | t3a.small (2 GB) ≈ $0.0188/h ≈ $13.7/month; t3a.medium (4 GB) ≈ $0.0376/h; t4g.small (ARM) ≈ $0.0168/h. The Bee CLI ships only for linux-x64 today | [Holori](https://calculator.holori.com/aws/ec2/t3a.small/us-east-1) |
| **ECS on Fargate** | x86 $0.04048/vCPU-h + $0.004445/GB-h; ARM ≈ 20 % less; **Fargate Spot ≈ 70 % less** (can be interrupted with a 2-minute notice) | [AWS](https://aws.amazon.com/fargate/pricing/) |
| **ECS Express Mode** | Since November 2025: container image + roles → AWS sets up Fargate, an ALB with TLS, scaling and monitoring. No extra charge (you pay Fargate + ALB). Up to 25 services share one ALB. Recommended replacement for App Runner | [AWS announcement](https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/), [docs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.md) |
| **App Runner** | **Closed to new customers since 30 April 2026** (maintenance only). Do not use | [AWS](https://docs.aws.amazon.com/ja_jp/apprunner/latest/dg/apprunner-availability-change.html) |
| **Lambda** | 15-minute maximum per invocation: cannot hold a Bee stream; fine for request/response APIs and event handlers | [Docs](https://docs.aws.amazon.com/lambda/) |
| **Lightsail** | 2 GB at $12, 4 GB at $24 per month, IPv4 and transfer included; no IAM instance roles | [CloudBurn](https://cloudburn.io/blog/amazon-lightsail-pricing) |

---

## 4. Front-end, data, identity, glue

| Service | Fact for EXAMEN | Source |
|---|---|---|
| **S3 + CloudFront** | The Next.js dashboard is a static export (`src/web_ui/out`): S3 origin for `/*`, plus a second origin (the API host) for `/api/*` and `/mcp` in the **same distribution**. Same origin means no CORS and no cookie changes. CloudFront free tier: 1 TB and 10 M requests per month | [CloudFront docs](https://docs.aws.amazon.com/cloudfront/) |
| **Amplify Hosting** | Static hosting with CI from Git. Build minutes $0.01/min (1 000 free/month); egress $0.15/GB (15 GB free); storage $0.023/GB (5 GB free) | [AWS Amplify pricing](https://aws.amazon.com/amplify/pricing/) |
| **DynamoDB** | On-demand ≈ **$0.625 per million writes and $0.125 per million reads** since the 50 % cut of November 2024; free tier 25 GB storage. **No full-text search**: EXAMEN's FTS5 contact search would become per-user scans | [AWS Fundamentals](https://awsfundamentals.com/blog/amazon-dynamodb-pricing-explained) |
| **Aurora PostgreSQL Serverless v2** | Closest to the relational model, with full text search (`tsvector`); minimum 0.5 ACU ≈ $45/month | [RDS docs](https://docs.aws.amazon.com/rds/) |
| **Aurora DSQL** | Serverless distributed SQL (Postgres-compatible) with a pay-per-use model; check feature support (full text, extensions) before choosing | [Docs](https://docs.aws.amazon.com/aurora-dsql/) |
| **Cognito** | Lite / Essentials free up to **10 000 MAU**, then $0.015/MAU; OAuth 2.0 server for Alexa+ account linking and AgentCore inbound auth | [AWS](https://aws.amazon.com/cognito/pricing) |
| **Secrets Manager** | ≈ $0.40 per secret per month: one secret per user's Bee token in a split architecture | [computingforgeeks](https://computingforgeeks.com/aws-costs-explained-real-numbers/) |
| **SQS / EventBridge** | Durable hand-off from the ingestion worker to AgentCore (retries, back-pressure, dead-letter queue). Fractions of a cent at EXAMEN's volume | [SQS](https://docs.aws.amazon.com/sqs/), [EventBridge](https://docs.aws.amazon.com/eventbridge/) |
| **Step Functions** | Orchestrates multi-step jobs (backfill run → AgentCore calls); optional | [Docs](https://docs.aws.amazon.com/step-functions/) |
| Public IPv4 | $0.005/h ≈ $3.6/month per address | [computingforgeeks](https://computingforgeeks.com/aws-costs-explained-real-numbers/) |

---

## 5. Bedrock model prices (on-demand, per 1M tokens)

| Model | Input | Output | Source |
|---|---|---|---|
| NVIDIA Nemotron Super 3 120B (current EXAMEN default) | $0.15 | $0.65 | [cloudprice.net](https://cloudprice.net/models/nvidia-nemotron-super-3-120b) |
| Amazon Nova Micro | $0.035 | $0.14 | [ManageEngine](https://www.manageengine.com/cloudspend/articles/amazon-bedrock-pricing.html) |
| Amazon Nova Lite | $0.06 | $0.24 | [Caylent](https://caylent.com/blog/amazon-bedrock-pricing-explained) |
| Claude Haiku 4.5 | $1.00 | $5.00 | [CloudZero](https://www.cloudzero.com/blog/amazon-bedrock-pricing) |
| Titan Text Embeddings V2 | ≈ $0.02 | — | AWS list price (verify) |

Batch and Flex tiers cost about half the on-demand price on the models that offer them.

AWS documentation index: [docs.aws.amazon.com](https://docs.aws.amazon.com/). The Bedrock, AgentCore, Lambda, ECS, Fargate, Amplify, S3, CloudFront, DynamoDB, RDS/Aurora, EventBridge, SQS, Step Functions, Cognito and Secrets Manager guides are linked from there.
