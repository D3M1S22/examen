# 🐝 EXAMEN: Ambient Knowledge & Action Engine

> **Amazon Developer Hackathon 2026**  
> **Primary Track:** Bee Wearable AI (Ambient Intelligence)  
> **Ecosystem Integrations:** Alexa+ (Echo Show MCP Server & Ext-Apps UI)  
> **Mini-Challenge:** AWS Builder Challenge (AWS Bedrock & AgentCore)  
> **Etymology & Vision:** *From Latin "exāmen" (a swarm of bees, but also a careful examination and weighing).*  
> **Tagline:** *From ambient listening to augmented action: relational memory, daily peace of mind, and autonomous cross-device research.*

---

## 🌟 Vision & Key Value

Most voice assistants and wearable applications suffer from two structural bottlenecks:
1. **Require Active Input:** You must stop, unlock a phone, open an app, press a button, or speak awkward wake words (*"Alexa, add to list..."*).
2. **Passive, Unintelligent Storage:** Current wearables merely record or transcribe raw logs, shifting the cognitive burden onto the user to re-read and organize the data.

**EXAMEN** transforms the continuous audio stream captured by the **Bee** wearable into a proactive **Knowledge & Action Fabric**. Powered by an intelligent agentic pipeline on **AWS Bedrock** and **AgentCore**, the system passively filters ambient speech, extracts entities and intentions, autonomously enriches topics via web research, and serves the knowledge on demand through **Alexa+** on **Echo Show**.

```
    [ Bee Wearable AI ] (Continuous passive listening)
            │
            ▼ (beemcp / audio transcript stream)
 ┌────────────────────────────────────────────────────────┐
 │ 1. SCREENING (Fast Semantic Gatekeeper on AWS Bedrock) │ ──> [ Drop Irrelevant Chit-chat (90%+) ]
 └──────────────────────────┬─────────────────────────────┘
                            │ (Valuable categorized chunks)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 2. ROUTING & STATE GRAPH (AgentCore / LangGraph)       │
 └──────┬───────────────────┼────────────────────┬────────┘
        │                   │                    │
        ▼                   ▼                    ▼
 ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐
 │ 3A. SOCIAL   │   │ 3B. ACTION   │   │ 3C. DEEP TOPIC & LECTURE │
 │     RECALL   │   │     STATE    │   │     RESEARCH ENGINE      │
 │ (Names, Roles│   │ (Routine &   │   │ (Bugs, Features, Tech &  │
 │  Promises)   │   │  Task Ledger)│   │  Lectures + Web Search)  │
 └──────┬───────┘   └───────┬──────┘   └─────────────┬────────────┘
        │                   │                        │
        └───────────────────┼────────────────────────┘
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 4. PERSISTENT CONTEXT STORE (SQLite / DynamoDB / ACMem)│
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │ 5. SERVING VIA MCP SERVER (Alexa+ & Echo Show UI)      │
 └────────────────────────────────────────────────────────┘
            │                               │
            ▼ (Voice Interaction)           ▼ (Visual Dashboard)
     "Alexa, did I unplug             Relational Rolodex,
      the clothes iron?"              Task Timeline, Tech Briefings
```

---

## 🎯 The Three Core Application Domains

| Channel | Input Captured by Bee | Autonomous Enrichment | Output on Alexa+ / Echo Show |
| :--- | :--- | :--- | :--- |
| **🧠 Social Recall** | *"Nice to meet you Marco, I'm Tech Lead at Acme Corp, send me your repo..."* | Extracts name, company, role, salient topics, and bilateral commitments. | *"Alexa, who did I meet today?"* ➔ Visual profile card on Echo Show with pending follow-up action items. |
| **🔒 Action-State & Routine** | *"I'm turning off the stove and unplugging the iron."* or *"I just merged PR #42."* | Verifies first-person completed actions, classifies safety vs work domains, timestamps with confidence score. | *"Alexa, did I unplug the iron?"* ➔ Instant voice confirmation and certified green verification badge on screen. |
| **📚 Deep Meeting & Lecture Intelligence** | Discussions on complex bugs, architecture, new libraries (*AgentCore, DuckDB*), or whole academic lectures. | Groups the speech into **events** (a lecture survives its coffee break; two back-to-back lectures in the same room are told apart), synthesizes a briefing **per part** at each break and a **consolidated event briefing** at the end, reusing web research across parts. | *"Alexa, what is this lecture about so far?"* / *"summarize my afternoon meeting"* ➔ Event timeline on Echo Show with part briefings, final synthesis, sources and linked actions/contacts/tasks. |

---

## 🏗️ 5-Stage System Architecture

1. **Screening (Semantic Gatekeeper):** Ultra-fast, cost-effective evaluation of incoming audio chunks via lightweight Bedrock foundation models (*GPT-5.6 Luna* or *Claude 3.5 Haiku*). If text is trivial chit-chat or background silence, it drops immediately at zero downstream computation cost.
2. **Semantic Routing:** Qualified chunks are categorized (`social`, `action`, `deep_topic`) and dynamically dispatched to specialized sub-agents.
3. **Extraction & Autonomous Enrichment:**
   - **Social:** Structured Pydantic schema for contacts, roles, and commitments.
   - **Action-State:** Strict veracity filtering to prevent false positives (completed actions only, discarding doubts or future intentions).
   - **Deep Topic Research:** Formulates search queries, retrieves documentation via web search, and synthesizes executive dossiers with Claude 3.5 Sonnet.
   - **Deep Topic Event Engine:** Instead of researching every utterance, deep-topic speech is accumulated into events (time, GPS, explicit cues and topic similarity via Titan Text Embeddings V2) and synthesized per part and per event — see [deep_topic_event_engine](docs/next_steps/deep_topic_event_engine/00_overview.md).
4. **Context Knowledge Store:** Unified persistence layer with SQLite + FTS5 for local zero-latency development, and AWS DynamoDB + AgentCore Memory for cloud scale.
5. **Serving Layer (Alexa+ MCP Server & Ext-Apps UI):** Streamable-HTTP **Model Context Protocol (MCP)** server exposing tools to Alexa+, coupled with an interactive touch UI for Echo Show via **ext-apps iframe SDK**.

---

## 💻 Tech Stack & Ecosystem Integrations

- **Wearable Ingestion:** Bee Wearable AI via [`resources/bee-cli/`](resources/bee-cli/) SSE stream (`new-utterance`) and `beemcp` bridge.
- **Dual-Provider LLM Engine:**
  - **AWS Bedrock Native (Converse API):** `langchain-aws` with IAM SigV4 auth (`amazon.nova-*`, `anthropic.claude-*`, `nvidia.nemotron-*`).
  - **AWS Bedrock Mantle (OpenAI-compatible):** `langchain-openai` via `bedrock-mantle.{region}.api.aws/openai/v1` with automated short-term token minting (`aws-bedrock-token-generator`).
  - **Dynamic Tiering:** Independent configuration for Fast Screening (`GATEKEEPER_PROVIDER`) and Deep Reasoning (`REASONER_PROVIDER`).
- **Agent Harness:** **AWS Bedrock AgentCore Runtime** & **LangGraph** (`StateGraph`) for state management, conditional routing, and serverless hosting.
- **Search Tooling:** Autonomous DuckDuckGo Search (`ddgs`) with SSRF security validation and query refinement loops.
- **Storage:** SQLite with Full-Text Search (FTS5) for local zero-latency development; Amazon DynamoDB, S3, and Bedrock AgentCore Memory for cloud scale.
- **Serving & Voice UI:** Alexa+ (Echo Show) via Model Context Protocol (FastMCP Streamable HTTP JSON-RPC 2.0).
- **Frontend UI:** Ext-Apps Iframe SDK for multimodal Echo Show touch displays.

---

## 📊 Live Evaluation & Benchmark Highlights

The engine underwent a rigorous 25-scenario live evaluation against **NVIDIA Nemotron 3 Super 120B** on AWS Bedrock (`scripts/run_live_benchmark.py`):
- **Overall Pass Rate:** **100.0% (25 / 25 Scenarios)** across English and Italian.
- **Gatekeeper Screening:** Average latency **0.95s** with precise chitchat dropping, prompt injection defense, and multi-label dispatch.
- **Action Verifier:** Sub-second extraction with automated matching and resolution of pre-scheduled tasks.
- **Deep Technical Research:** Autonomous synthesis of 16.5 KB technical dossiers with 6 external web citations.
- **Operational Cost:** Total cost for 25 live scenarios was **$0.0084 USD** (< 1 cent), estimating **~$0.04/day** for continuous wearable ambient listening.

---

## 🚀 Running & Deployment Guide

EXAMEN supports three deployment modes:
1. **Local Development (Bare Metal)**
2. **Single Container Deployment (Docker)**
3. **Production AWS Cloud Deployment (EC2, DynamoDB, CloudFront, AgentCore)**

---

### 1. Local Development (Bare Metal)

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/) (or standard `venv`), [Bun](https://bun.sh/) (for building the Next.js UI), and AWS credentials with Bedrock access (or set `MOCK_AI=true` to test locally without an AWS account).

```bash
# 1. Clone the repository and initialize submodules (bee-cli, agentcore-samples)
git clone --recurse-submodules <repo-url> && cd amazon_challenge
# If already cloned:
git submodule update --init

# 2. Setup virtual environment and dependencies
uv sync                          # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
source .venv/bin/activate
cp .env.example .env             # configure AWS_REGION / credentials, or set MOCK_AI=true

# 3. Run the automated test suite (588 tests)
pytest

# 4. Build the Next.js dashboard (static export served by the FastMCP server)
./scripts/build_ui.sh            # executes: cd src/web_ui && bun install && bun run build

# 5. Launch the FastMCP Server & Web Dashboard (port 8000 by default)
python -m src.serving.mcp_server
```

- **Web Dashboard & Echo Show UI:** Open [http://localhost:8000/](http://localhost:8000/) (or `/ext-app/`).
- **Alexa+ FastMCP Endpoint:** Connect any MCP-compliant assistant to `http://localhost:8000/mcp` (Bearer token: *Account → Alexa+ / MCP access tokens*).
- **Accounts:** Create an account (email + password), then go to *Account → Bee device → Connect my Bee* and scan the QR code to pair your wearable.
- **Offline Mock Mode:** Setting `MOCK_AI=true` in `.env` allows running the entire UI, simulator, and MCP tools with synthetic AI responses at zero cost.

---

### 2. Single Container Deployment (Docker)

You can containerize the entire application (FastMCP server, background ingestion loop, and Next.js frontend) into a single self-contained Docker container using the multi-stage [`Dockerfile`](Dockerfile).

```bash
# 1. Ensure the Next.js static UI is built
./scripts/build_ui.sh

# 2. Build the Docker container image
docker build -t examen:latest .

# 3. Run the container with your environment configuration
docker run -d \
  --name examen \
  -p 8000:8000 \
  -v examen_data:/app/data \
  --env-file .env \
  --restart unless-stopped \
  examen:latest

# 4. Verify container logs and health probe
docker logs -f examen
curl -f http://localhost:8000/api/health
```

- Data persistence is guaranteed by mounting a volume to `/app/data` (which preserves SQLite storage and Bee device tokens).
- The web dashboard will be immediately accessible on `http://localhost:8000` and the MCP server at `http://localhost:8000/mcp`.

---

### 3. Production AWS Cloud Deployment

For production, EXAMEN is designed to run cloud-native with high availability, low latency, and per-tenant data isolation:
- **CloudFront:** SSL/TLS termination at your custom domain (`https://examen.devgiov.com`), edge caching, and SSE streaming.
- **EC2 (`t3a.small`):** Runs the always-on ingestion daemon and FastMCP server behind NGINX in `eu-central-1`.
- **Amazon DynamoDB:** Multi-table cloud storage (`examen-user`, `examen-auth`, `examen-ops`) partitioned by `user_id`.
- **AWS Bedrock & AgentCore:** Nova Micro gatekeeper, Claude 3.5 Sonnet reasoning, Titan V2 embeddings, and AgentCore runtime microVMs.

Complete infrastructure is provisioned declaratively via AWS CloudFormation templates in [`deploy/aws/`](deploy/aws/):

```bash
# 1. Set target AWS region and credentials
export AWS_DEFAULT_REGION="eu-central-1"

# 2. Deploy DynamoDB multi-table stack
aws cloudformation deploy \
  --stack-name examen-dynamodb \
  --template-file deploy/aws/dynamodb.yaml \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Store initial bootstrap administrator credentials in AWS SSM Parameter Store
.venv/bin/python scripts/aws_deploy.py params --admin-email admin@example.com

# 4. Build release bundle (code + built UI + Bee binary) and upload to artifacts S3 bucket
.venv/bin/python scripts/aws_bundle.py --bucket <your-artifacts-bucket>

# 5. Deploy compute stack (VPC, Security Groups, EC2 Launch Template, CloudFront)
.venv/bin/python scripts/aws_deploy.py stack

# 6. Check host bootstrap log and service status
.venv/bin/python scripts/aws_deploy.py logs
```

> **Full Production Runbook:** For comprehensive zero-downtime updates, rollback procedures, CloudWatch alarm setups, and custom DNS / ACM certificate cutovers, see [`docs/17_aws_deployment_runbook.md`](docs/17_aws_deployment_runbook.md).

---

### Operational Features & Controls

> **History Sync:** if EXAMEN was offline, Bee conversations recorded meanwhile are recovered automatically on restart/reconnect (`BACKFILL_LOOKBACK_DAYS`). To analyse any past period, open *Overview → History Sync → Analyse past period…* (free preview first). Spec: [historical_backfill/](docs/next_steps/historical_backfill/00_overview.md).

> **Event engine demo:** in the dashboard open *Ambient Simulator → Deep Topic Event Engine*, pick a scenario (e.g. "Single lecture interrupted by a coffee break"), press **Play scenario**, then **Close events** and open *Topic Dossiers → Events*. `EVENT_PROFILE=demo` compresses the timers (20 s / 90 s) for live typing.

- **Accounts:** multi-user with per-user data, per-user Bee pairing and GDPR export/erasure — see [13_multi_user_accounts.md](docs/13_multi_user_accounts.md). Self-registration (`AUTH_ALLOW_SIGNUP`), a bootstrap admin (`EXAMEN_BOOTSTRAP_ADMIN=<email>`) with an *Admin* tab, one Bee account per user and shared LLM / stream limits. `AUTH_ENABLED=false` restores the single-user mode.
- **Admin console:** runtime overrides of `.env` tunables (models, Bedrock / Mantle, region, …) with test-before-save and rollback, a sanitised service log with incidents, and a health view — see [admin_console/](docs/next_steps/admin_console/00_overview.md).

---

## 🏆 Hackathon Alignment & Target Awards

| Track / Challenge | How EXAMEN Maximizes Score |
| :--- | :--- |
| **Track 1: Bee Wearable AI ($12,000)** | Goes beyond passive audio logging by providing real-time ambient understanding, proactive web enrichment, and cross-device intelligence. |
| **Alexa+ (self-hosted MCP server)** | FastMCP server implementing MCP **2025-11-25** over **Streamable HTTP** (`/mcp`, bearer token per user), deployed on AWS at `https://examen.devgiov.com/mcp`. 22 tools: action verification, routines, contacts and commitments, event dossiers, manual curation with two-step deletes, speaker review queue. (Official Alexa+ Add-on package with OAuth 2.1 is planned for post-hackathon store release). |
| **Mini-Challenge: AWS Builder ($5,000 + $5,000 credits)** | Native deep integration with AWS Bedrock multi-model tiering (Bedrock Native & Mantle dual-provider) and orchestration on Bedrock AgentCore. |
| **Cross-Device Orchestration** | Frictionless synergy: **Bee** captures context in the physical world on the go; **Alexa+ on Echo Show** synthesizes and surfaces it at home or office. |

---

## 📂 Project Documentation Structure

Detailed technical, architectural, and operational documentation is organized across the following dedicated guides:

* 📄 [01_architecture_flow.md](docs/01_architecture_flow.md): In-depth 5-stage architecture, end-to-end dataflow, and Mermaid diagrams *(Baseline v1.0)*.
* 📄 [02_bedrock_agentcore_pipeline.md](docs/02_bedrock_agentcore_pipeline.md): LangGraph state graph implementation, dual-provider model factory, Pydantic V2 schemas, and search tools *(Baseline v1.0)*.
* 📄 [03_alexa_mcp_serving.md](docs/03_alexa_mcp_serving.md): MCP Server specifications for Alexa+, JSON-RPC tool schemas, and Echo Show ext-apps wireframes *(Baseline v1.0)*.
* 📄 [04_hackathon_strategy_demo.md](docs/04_hackathon_strategy_demo.md): 3-minute video demo script, judging criteria alignment, and 4-sprint roadmap.
* 📄 [05_tech_stack_resources.md](docs/05_tech_stack_resources.md): Comprehensive tech stack, frameworks, APIs, and submodule references (`agentcore-samples`, `bee-cli`).
* 📄 [06_aws_cloud_deployment_architecture.md](docs/06_aws_cloud_deployment_architecture.md): AWS Cloud deployment architecture (EC2 lift-and-shift, DynamoDB, AgentCore Runtime, S3, CloudFront).
* 📄 [07_repository_structure_modules.md](docs/07_repository_structure_modules.md): Detailed repository layout, modular monorepo mapping by deployment target, and developer quickstart *(Baseline v1.0)*.
* 📄 [08_real_telemetry_and_bee_hardware_spec.md](docs/08_real_telemetry_and_bee_hardware_spec.md): Real hardware telemetry integration, Bee Wearable CLI capabilities, latency tracking architecture, and sector-by-sector frontend data contracts.
* 📄 [09_frontend_gaps_from_next_steps.md](docs/09_frontend_gaps_from_next_steps.md): Frontend enhancements audit, links tray, disambiguation drawer, and simulator presets.
* 🐝 [10_bee_cli_reference.md](docs/10_bee_cli_reference.md): Observed bee-cli / Bee API contract (commands, payloads, timestamps, stream events, conversation lifecycle, locations) and the conformance audit of the EXAMEN code.
* 🏠 [11_homelab_test_deployment.md](docs/11_homelab_test_deployment.md): Single-LXC test deployment on the homelab (before AWS): service layout, redeploy script, Bee login on the server.
* 📑 [12_full_repo_recap.md](docs/12_full_repo_recap.md): Comprehensive repository recap and technical audit of the codebase and documentation.
* 👥 [13_multi_user_accounts.md](docs/13_multi_user_accounts.md): Multi-user accounts (email + password, GDPR), per-user data folders, per-user Bee QR pairing and orchestrators, MCP access tokens, operator CLI.
* 📚 [14_aws_and_hackathon_reference.md](docs/14_aws_and_hackathon_reference.md): Official hackathon rules, quotas, pricing, and AWS service references.
* 🧭 [15_aws_split_architecture_report.md](docs/15_aws_split_architecture_report.md): Architectural report on always-on ingestion + on-demand AgentCore Runtime split.
* 🗄️ [16_aws_data_layer_k3.md](docs/16_aws_data_layer_k3.md): Cloud-native data layer evaluation: DynamoDB vs Aurora vs Aurora DSQL.
* 🚀 [17_aws_deployment_runbook.md](docs/17_aws_deployment_runbook.md): Production AWS deployment runbook, live on CloudFront (`examen.devgiov.com`), DynamoDB eu-central-1, and AgentCore Runtime.
* 🚀 [ROADMAP.md](docs/next_steps/ROADMAP.md): Master Evolution Roadmap, milestone progress, and execution status dashboard (Phases 0–13).
* 🧠 [deep_topic_event_engine/](docs/next_steps/deep_topic_event_engine/00_overview.md): Deep Topic Event Engine specification (R0–R9 state machine, Titan V2 embeddings, segment/final synthesis).
* ⏪ [historical_backfill/](docs/next_steps/historical_backfill/00_overview.md): Historical Transcript Backfill specification (coverage ledger, gap detection, virtual-clock replay, History Sync UI).
* 🗄️ [dynamodb_storage/](docs/next_steps/dynamodb_storage/00_overview.md): DynamoDB cloud storage specification (three tables: user, auth, ops; IAM tenant isolation via LeadingKeys).
* 🛠️ [admin_console/](docs/next_steps/admin_console/00_overview.md): Admin Console specification (runtime settings overrides, service log, health monitor incidents, token usage).
* ✏️ [manual_curation/](docs/next_steps/manual_curation/00_overview.md): Manual Curation specification (action/routine/contact edit and two-step delete over REST and MCP).
* 🎙️ [speaker_review/](docs/next_steps/speaker_review/00_overview.md): Speaker Review specification (confirmation queue for untagged speech).
* 🗣️ [alexa_addon/](docs/next_steps/alexa_addon/00_overview.md): Alexa+ MCP Add-on specification (OAuth 2.1 server, account linking, listing assets; planned post-hackathon).

---

## 📋 Comprehensive Architecture TODO & Future Model Enhancements Roadmap

> **Reference Specification:** For full technical schematics, hardware probe contracts, and telemetry data models, see [docs/08_real_telemetry_and_bee_hardware_spec.md](docs/08_real_telemetry_and_bee_hardware_spec.md).

In strict accordance with the non-modifying model directive, the current LLM model call signatures in `src/pipeline/nodes/` and `src/ingestion/gatekeeper.py` are preserved. Below is the comprehensive master checklist of frontend data expectations, hardware integration points, and future model enhancements:

### 1. Frontend Real Telemetry & Data Expectations
- [x] **Real Rolling Averages in `/api/status`:** Persisted in SQLite `system_telemetry` and queried via `get_latency_metrics()` (rolling average, sample counts, min/max).
- [x] **Dynamic Hardware & Sensor Placeholders:**
  - `PeaceOfMind`: Bound to `telemetry.sensor_mesh`, `telemetry.processing_model.reasoner`, and `telemetry.latency.average_ms`.
  - `SystemBar`: Dynamic `BEE: STREAMING` / `BEE: STANDBY (${USER})` / `BEE: DISCONNECTED` badges reflecting real `bee status` probes.
  - `SystemBar`: Dynamic `BEDROCK: ${MODEL} (${REGION})` badge reflecting active AWS Bedrock configuration.
  - `SystemBar`: Dynamic `SSE: LIVE STREAM` / `SSE: CONNECTING` badge reflecting EventSource state.
  - `AmbientSimulator`: Live execution latency (`elapsed_ms`), sample count, and model diagnostics.
  - `OverviewHub`: Dynamic ingress sensor mesh status.
- [x] **Relational Social Rolodex Deduplication:** Multi-level deduplication across SQLite `social_commitments`, `social_contacts`, and Next.js React views, eliminating duplicate commitments and contact cards.
- [x] **Cross-Origin Streaming (CORS):** Full CORS support enabled on FastMCP Starlette app and `/api/events` SSE endpoint for local port 3000 / 8000 seamless connectivity.
- [x] **Ambient Simulator Multi-Key Ingestion:** Support for both `raw_transcript` and `transcript_chunk` across all endpoints and pipeline entrypoints.

### 2. Bee Wearable Hardware & Edge Ingestion (Verified with a real account via Apple Watch, 2026-10-19)
- [x] **Precompiled Standalone Binary Resolution:** Native fallback to `resources/bee-cli/dist/platforms/mac-arm64/bee` (or linux/windows) removing dependency on global `bun`/`node` on host.
- [x] **Capture real `bee stream --json` samples:** event `type` field present, `utterance.spoken_at` (ISO) present, undocumented `tagged-utterance` / `new-utterance-chunks` events, 30 s SSE pings dropped by `--json`. Full contract: [docs/10_bee_cli_reference.md](docs/10_bee_cli_reference.md).
- [ ] **Live Audio Stream Linking with the physical Bee wearable:** verified with the Apple Watch app only; re-run `scripts/bee_spike.py` with the wearable (locations, `device_type`, `update-location`).
- [x] **Bee data conformance fixes** ([docs/next_steps/07_bee_data_alignment.md](docs/next_steps/07_bee_data_alignment.md)): live location polling (C2–C4), speaker identity from `tagged-utterance` (C5, C16), raw-SSE liveness through a private `bee proxy` (C9), backfill durations and re-segmented finals (I2, I3). Under multi-user accounts ([docs/13_multi_user_accounts.md](docs/13_multi_user_accounts.md)), signing out of the dashboard preserves the background Bee stream until explicit device disconnection.
- [ ] **End-to-end verification of the fixes** with the real device and Bedrock (doc 07 §4).
- [ ] **Capture `new-conversation` / `update-conversation`:** start a capture before speaking.
- [ ] **Re-calibrate topic similarity on real lectures:** `python scripts/replay_event_scenarios.py --calibrate` after adding recorded scenarios (the Titan V2 same/different gap is narrow: 0.36 / 0.43).
- [ ] **Webhook Gateway Ingestion:** Transition from local subprocess polling to Bee Cloud webhook callback ingestion (`bee stream --webhook-endpoint <URL>`).
- [ ] **Hardware Battery & RSSI Telemetry Bridge:** not exposed by `bee-cli` or the API (verified 2026-10-19); track upstream updates.

### 3. Future Model Calls & Backend Optimizations (Deferred per Directive)
- [ ] **Multilingual Gatekeeper Prompt Refinement:** Add explicit Italian few-shot anchors (*"ho staccato il ferro"*, *"gas spento"*, *"chiuso la porta"*) to `src/ingestion/gatekeeper.py` to maximize zero-shot domestic safety recall.
- [ ] **Streaming Token Generation for Voice Recall:** Stream Bedrock Converse API token chunks directly through FastMCP SSE for instant Echo Show display updates.
- [ ] **Dynamic Multi-Tier Model Switching:** Programmatic fallback to Amazon Nova Micro for high-frequency domestic screening and Claude 3.5 Sonnet for multi-source academic research.
---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
