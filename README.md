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

## 🚀 Quickstart: Running Serving & Live Dashboard

```bash
# 1. Setup virtual environment
source .venv/bin/activate

# 2. Run complete test suite (272 unit & integration tests, 100% pass)
pytest

# 3. Build the Next.js dashboard (static export served by the MCP server) — Bun is the package manager
./scripts/build_ui.sh            # = cd src/web_ui && bun install && bun run build

# 4. Launch Unified FastMCP Server & Echo Show Web Dashboard (port = MCP_PORT, default 8000)
python -m src.serving.mcp_server

# Optional: replay the event-engine scenarios / calibrate topic similarity thresholds
python scripts/replay_event_scenarios.py --calibrate
```

> **History Sync:** if EXAMEN was offline, Bee conversations recorded meanwhile are recovered automatically on restart/reconnect (`BACKFILL_LOOKBACK_DAYS`). To analyse any past period, open *Overview → History Sync → Analyse past period…* (free preview first). Spec: [historical_backfill/](docs/next_steps/historical_backfill/00_overview.md).

> **Event engine demo:** in the dashboard open *Ambient Simulator → Deep Topic Event Engine*, pick a scenario (e.g. "Single lecture interrupted by a coffee break"), press **Play scenario**, then **Close events** and open *Topic Dossiers → Events*. `EVENT_PROFILE=demo` compresses the timers (20 s / 90 s) for live typing.

- **Web Dashboard & Echo Show Ext-App:** Open [http://localhost:8000/](http://localhost:8000/) or [http://localhost:8000/ext-app/](http://localhost:8000/ext-app/) to monitor verified Peace of Mind actions, daily routine checklists, social rolodex cards, and run ambient audio simulations.
- **Alexa+ MCP Endpoint:** Connect any MCP-compliant assistant to `http://localhost:8000/mcp`.

---

## 🏆 Hackathon Alignment & Target Awards

| Track / Challenge | How EXAMEN Maximizes Score |
| :--- | :--- |
| **Track 1: Bee Wearable AI ($12,000)** | Goes beyond passive audio logging by providing real-time ambient understanding, proactive web enrichment, and cross-device intelligence. |
| **Mini-Challenge: AWS Builder ($5,000 + $5,000 credits)** | Native deep integration with AWS Bedrock multi-model tiering (Bedrock Native & Mantle dual-provider) and orchestration on Bedrock AgentCore. |
| **Cross-Device Orchestration** | Frictionless synergy: **Bee** captures context in the physical world on the go; **Alexa+ on Echo Show** synthesizes and surfaces it at home or office. |

---

## 📂 Project Documentation Structure

Detailed technical, architectural, and operational documentation is organized across the following dedicated guides:

* 📄 [01_architecture_flow.md](docs/01_architecture_flow.md): In-depth 5-stage architecture, end-to-end dataflow, and Mermaid diagrams.
* 📄 [02_bedrock_agentcore_pipeline.md](docs/02_bedrock_agentcore_pipeline.md): LangGraph state graph implementation, dual-provider model factory, Pydantic V2 schemas, and search tools.
* 📄 [03_alexa_mcp_serving.md](docs/03_alexa_mcp_serving.md): MCP Server specifications for Alexa+, JSON-RPC tool schemas, and Echo Show ext-apps wireframes.
* 📄 [04_hackathon_strategy_demo.md](docs/04_hackathon_strategy_demo.md): 3-minute video demo script, judging criteria alignment, and 4-sprint roadmap.
* 📄 [05_tech_stack_resources.md](docs/05_tech_stack_resources.md): Comprehensive tech stack, frameworks, APIs, and submodule references (`agentcore-samples`, `bee-cli`).
* 📄 [06_aws_cloud_deployment_architecture.md](docs/06_aws_cloud_deployment_architecture.md): AWS Cloud deployment architecture (AgentCore Runtime, AgentCore Memory, S3, DynamoDB, Alexa+ MCP, CloudFront).
* 📄 [07_repository_structure_modules.md](docs/07_repository_structure_modules.md): Detailed repository layout, modular monorepo mapping by deployment target, and developer quickstart.
* 📄 [08_real_telemetry_and_bee_hardware_spec.md](docs/08_real_telemetry_and_bee_hardware_spec.md): Real hardware telemetry integration, Bee Wearable CLI capabilities, latency tracking architecture, and sector-by-sector frontend data contracts.
* 🚀 [ROADMAP.md](docs/next_steps/ROADMAP.md): Evolution Roadmap, pipeline refinements status dashboard, and execution plan for Next Steps.
* 🧠 [deep_topic_event_engine/](docs/next_steps/deep_topic_event_engine/00_overview.md): Deep Topic Event Engine specification, state machine, topic continuity calibration, synthesis scheduling, serving/UI and test plan.
* ⏪ [historical_backfill/](docs/next_steps/historical_backfill/00_overview.md): Historical Transcript Backfill specification: coverage ledger, gap detection, live/backfill de-duplication, virtual-clock replay, auto catch-up and the History Sync UI.

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

### 2. Bee Wearable Hardware & Edge Ingestion (Awaiting Physical Device Link)
- [x] **Precompiled Standalone Binary Resolution:** Native fallback to `resources/bee-cli/dist/platforms/mac-arm64/bee` (or linux/windows) removing dependency on global `bun`/`node` on host.
- [ ] **Live Audio Stream Linking:** Run `stream_convo.py` / `BeeStreamOrchestrator` when physical Bee Wearable is actively broadcasting via paired mobile companion.
- [ ] **Capture real `bee stream --json` samples:** confirm the event-type field, any utterance time field (`spoken_at`) and the `new-conversation` / `update-conversation` payloads consumed by the event engine (see FRICTION_LOG 2026-10-13).
- [ ] **Re-calibrate topic similarity on real lectures:** `python scripts/replay_event_scenarios.py --calibrate` after adding recorded scenarios (the Titan V2 same/different gap is narrow: 0.36 / 0.43).
- [ ] **Webhook Gateway Ingestion:** Transition from local subprocess polling to Bee Cloud webhook callback ingestion (`bee stream --webhook-endpoint <URL>`).
- [ ] **Hardware Battery & RSSI Telemetry Bridge:** Track upstream Bee Wearable API updates for battery level and Bluetooth RSSI exposure.

### 3. Future Model Calls & Backend Optimizations (Deferred per Directive)
- [ ] **Multilingual Gatekeeper Prompt Refinement:** Add explicit Italian few-shot anchors (*"ho staccato il ferro"*, *"gas spento"*, *"chiuso la porta"*) to `src/ingestion/gatekeeper.py` to maximize zero-shot domestic safety recall.
- [ ] **Streaming Token Generation for Voice Recall:** Stream Bedrock Converse API token chunks directly through FastMCP SSE for instant Echo Show display updates.
- [ ] **Dynamic Multi-Tier Model Switching:** Programmatic fallback to Amazon Nova Micro for high-frequency domestic screening and Claude 3.5 Sonnet for multi-source academic research.
