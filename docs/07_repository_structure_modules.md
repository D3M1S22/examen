# 📁 Repository Structure & Module Architecture

> This document provides an exhaustive overview of the **file layout and module architecture** for **EXAMEN** *(from Latin "exāmen": swarm of bees & careful examination)*, explaining boundaries of responsibility and mapping directories to **deployment targets**.

---

## 🏛️ Design Philosophy: Modular Monorepo per Deploy Target

The repository adopts a **Modular Monorepo pattern oriented by Deployment Targets**:
1. **Unified Shared Core (`src/core/`):** All data contracts (Pydantic V2 schemas) and storage abstractions are consolidated in a single module, ensuring strict consistency between the ingestion pipeline and the serving layer.
2. **Runtime Target Isolation:**
   - The **agentic pipeline** in `src/pipeline/` is structured to be bundled and deployed directly onto AWS Graviton microVMs within **AWS Bedrock AgentCore Runtime**.
   - The **serving layer** in `src/serving/` exposes a **FastMCP** server compliant with **Alexa+**.
   - The **ingestion bridge** in `src/ingestion/` runs at the edge / companion (laptop, phone, or micro-instance).
   - The **visual UI** in `src/web_ui/` is a lightweight static web app for **Echo Show (ext-apps)** delivered via S3 + CloudFront.
3. **Zero-Friction Local Development:** Every component can be executed and tested locally offline (using SQLite with FTS5 and mock audio streams) before cloud deployment.

---

## 🌳 Repository Tree

```
amazon_challenge/
├── docs/                                 # 📚 Technical, architectural, and strategic guides
│   ├── 01_architecture_flow.md           # 5-stage pipeline dataflow and Mermaid diagrams
│   ├── 02_bedrock_agentcore_pipeline.md  # LangGraph state graph & Bedrock models
│   ├── 03_alexa_mcp_serving.md           # MCP server specs & Echo Show ext-apps wireframes
│   ├── 04_hackathon_strategy_demo.md     # 3-min video demo script & roadmap
│   ├── 05_tech_stack_resources.md        # Tech stack, frameworks, and submodule references
│   ├── 06_aws_cloud_deployment_architecture.md # AWS cloud topology and hosting
│   ├── 07_repository_structure_modules.md      # This document
│   └── next_steps/                       # 🚀 Pipeline Refinements Roadmap (Next_steps.txt)
│       ├── 00_overview.md                # High-level architecture, roadmap, & schema evolution
│       ├── 01_deep_topic_contextual_synthesis.md # Adaptive explanatory post-meeting/lecture briefing
│       ├── 02_gatekeeper_context_and_multimodal_telemetry.md # Ring buffer context & Bee GPS/diarization
│       ├── 03_session_merging_and_micro_event_splitting.md # Session continuity & micro-event forking
│       ├── 04_ambient_scheduled_tasks.md # Spoken future task extraction & verification loop
│       ├── 05_structured_social_commitments.md # Bilateral promise tracking (debtor/deadlines)
│       └── 06_social_web_enrichment.md   # Autonomous LinkedIn/public bio enrichment
│
├── resources/                            # 📦 External Git submodules for offline reference
│   ├── agentcore-samples/                # Official AWS Labs reference architectures
│   │   └── 03-integrations/agentic-frameworks/langgraph/  # LangGraph + AgentCore sample
│   └── bee-cli/                          # Official Bee AI CLI client & native MCP server
│
├── src/                                  # 💻 Application Source Code
│   ├── core/                             # 🧱 Shared module across all components
│   │   ├── __init__.py                   # Core entity exports
│   │   ├── config.py                     # Centralized settings (Pydantic Settings & .env)
│   │   ├── schemas.py                    # Typed Pydantic V2 contracts & ExamenState
│   │   ├── models.py                     # Dual-provider LLM factory (Bedrock Converse & Mantle)
│   │   └── storage/                      # Persistence abstraction layer (Repository Pattern)
│   │       ├── __init__.py               # Factory get_storage_store()
│   │       ├── base.py                   # AbstractContextStore interface
│   │       ├── sqlite_store.py           # [Local] Thread-safe SQLite with FTS5 indexing
│   │       ├── dynamo_store.py           # [Cloud] Amazon DynamoDB for verified_actions
│   │       └── memory_store.py           # [Cloud] AWS Bedrock AgentCore Memory (facts/episodes)
│   │
│   ├── pipeline/                         # 🧠 [TARGET: AWS Bedrock AgentCore Runtime]
│   │   ├── __init__.py
│   │   ├── app.py                        # Entrypoint BedrockAgentCoreApp (@app.entrypoint)
│   │   ├── graph.py                      # LangGraph StateGraph & conditional routing
│   │   ├── nodes/                        # Specialized agent graph nodes
│   │   │   ├── __init__.py
│   │   │   ├── social.py                 # Stage 3A: Social Recall Extractor
│   │   │   ├── action_state.py           # Stage 3B: Action-State Verifier (Peace of Mind)
│   │   │   ├── topic_research.py         # Stage 3C: Deep Topic & Briefing Synthesizer
│   │   │   └── persist.py                # Context persistence node (Actions, Contacts, Briefings)
│   │   └── tools/                        # Tools invoked by agent nodes
│   │       ├── __init__.py
│   │       └── web_search.py             # Multi-tier web search tool (DuckDuckGo ddgs)
│   │
│   ├── serving/                          # 🎙️ [TARGET: Alexa+ Serving / MCP Server]
│   │   ├── __init__.py
│   │   ├── mcp_server.py                 # FastMCP server (port 8000 /mcp, streamable-http)
│   │   └── tools/                        # Exposed MCP tools for Alexa+
│   │       ├── __init__.py
│   │       ├── action_tools.py           # create_planned_task, verify_action_status, get_daily_actions_recap
│   │       ├── social_tools.py           # query_social_contact
│   │       └── topic_tools.py            # get_topic_briefing
│   │
│   ├── ingestion/                        # 🐝 [TARGET: Edge / Companion Ingestion Layer]
│   │   ├── __init__.py
│   │   ├── gatekeeper.py                 # Stage 1: Screening Gatekeeper (Fast Haiku/Luna/Nemotron + dynamic task injection)
│   │   ├── stream_convo.py               # Live SSE client connected to bee-cli (BeeClient, receive-time capture)
│   │   ├── orchestrator.py               # Per-utterance screening, event engine feeding & pipeline dispatch
│   │   ├── ring_buffer.py                # Context ring buffer for anaphora resolution (M3.1)
│   │   ├── event_engine.py               # Deep Topic Event Engine: events, segments, timers, synthesis jobs
│   │   ├── topic_continuity.py           # Topic profile & similarity (Titan V2 embeddings / heuristic / LLM judge)
│   │   ├── scenario_replay.py            # Virtual-clock replay of resources/event_scenarios.json
│   │   └── session_manager.py            # Legacy per-conversation sessions + shared boundary helpers
│   │
│   └── web_ui/                           # 🖥️ [TARGET: S3 + CloudFront / Echo Show Ext-Apps]
│       ├── index.html                    # Multimodal interactive dashboard
│       ├── styles.css                    # Modern Dark Mode styling for touch displays
│       ├── app.js                        # Frontend rendering logic and cards
│       └── assets/                       # SVG icons and visual assets
│
├── scripts/                              # 📊 Benchmarking & Telemetry Tools
│   ├── run_live_benchmark.py             # 25-scenario evaluation runner with latency/token tracking
│   └── replay_event_scenarios.py         # Event engine scenario replay & similarity threshold calibration
│
├── deploy/                               # 🚀 Cloud Deployment & Automation Scripts
│   ├── build_agentcore_bundle.sh         # Download arm64 wheels via uv and package code.zip
│   ├── deploy_agentcore_runtime.py       # Register runtime on AWS via boto3 control-plane
│   ├── deploy_ext_apps_s3.sh             # Sync web_ui to S3 + invalidate CloudFront CDN
│   └── alexa_addon.json                  # Manifest registration for Alexa+ Developer Console
│
├── tests/                                # 🧪 Test Suite & Validation (272 tests, 100% pass)
│   ├── fixtures/                         # Mock audio transcript datasets
│   ├── test_storage.py                   # Unit tests on persistence layer (SQLite & FTS5)
│   ├── test_gatekeeper.py                # Screening drop-rate (>90% drop) & task matching
│   ├── test_langgraph_pipeline.py        # End-to-end graph test with Bedrock & state persistence
│   ├── test_mcp_server.py                # 19 tests: 5 MCP tools, REST APIs & static UI
│   ├── test_model_factory.py             # Dual-provider Bedrock vs Mantle model unit tests
│   ├── test_pipeline_nodes.py            # Unit tests for social, action, and topic sub-agents
│   ├── test_ingestion_orchestrator.py    # Screening, event engine feeding & pipeline dispatch
│   ├── test_event_engine.py              # Event lifecycle state machine (rules R0-R8)
│   ├── test_event_synthesis.py           # Segment/final synthesis, search cache, query ledger
│   ├── test_topic_continuity.py          # Topic continuity, drift/split, scenario replays
│   ├── test_event_serving.py             # Manual event operations, REST endpoints, MCP tools
│   └── test_web_search.py                # Autonomous DDGS search tool tests
│
├── pyproject.toml                        # Python build config & pytest setup
├── requirements.txt                      # Unified Python dependencies
├── .env.example                          # Environment variable template
├── .gitignore                            # Excludes .venv, cache, local DBs, secrets
├── FRICTION_LOG.md                       # Developer friction diary for +10% hackathon bonus
└── README.md                             # Project overview and quickstart
```

---

## 🔍 Detailed Module Responsibilities

### 1. `src/core/` (Shared Core)
* **`config.py`:** Uses `pydantic-settings` to parse environment variables with safe defaults (provider selection `bedrock` vs `mantle`, region `us-east-1`, Claude/Nova/Nemotron models, SQLite `examen.db`, MCP port 8000).
* **`schemas.py`:** Strictly defines Pydantic V2 models:
  - `ChunkClassification`: Gatekeeper compact evaluation (`categories`, `confidence`, `summary_hint`, `matched_scheduled_task_id`).
  - `PlannedTask`: Scheduled routine and domestic safety tasks with recurrence and tracking status.
  - `SocialEntity`: Contacts, corporate roles, commitments, and topic tags.
  - `VerifiedAction`: Domestic safety and routine tasks with ISO timestamps, confidence scores $\ge 0.80$, and task resolution links.
  - `TopicExtraction` & `BriefingReport`: Technical subjects and synthesized markdown briefings with web sources.
  - `ExamenState`: `TypedDict` for the mutable LangGraph state.
* **`models.py`:** Dual-provider LLM factory (`get_chat_model`) providing runtime model switching between:
  - **Native Bedrock Converse API (`provider="bedrock"`):** Uses `ChatBedrockConverse` with IAM SigV4 authentication.
  - **Bedrock Mantle Endpoint (`provider="mantle"`):** Uses `ChatOpenAI` routed to `bedrock-mantle.{region}.api.aws/openai/v1` with automatic bearer token generation from IAM credentials.
* **`storage/`:**
  - `base.py`: Abstract class `AbstractContextStore` enforcing data contract operations.
  - `sqlite_store.py`: Native Python implementation with virtual FTS5 tables for sub-5ms full-text lookups and thread safety.

---

### 2. `src/pipeline/` (AWS Bedrock AgentCore Runtime)
* **`app.py`:** Instantiates `BedrockAgentCoreApp` and defines the `@app.entrypoint`. Receives audio chunks via `invoke_agent_runtime` and triggers the state graph.
* **`graph.py`:** Builds the pure LangGraph `StateGraph`, setting Gatekeeper as the entry point and orchestrating conditional edges to specialized sub-agents.
* **`nodes/`:**
  - `social.py`: Extracts contacts and bilateral promises, deduplicating known individuals.
  - `action_state.py`: Verifies completed actions, resolving planned tasks and filtering out doubts.
  - `topic_research.py`: Identifies tech topics, queries `web_search.py`, and synthesizes reports with reasoning models.
  - `persist.py`: Persists extracted actions, social contacts, and topic dossiers into storage.

---

### 3. `src/serving/` (Alexa+ Serving Layer)
* **`mcp_server.py`:** Implements an MCP server via `FastMCP` over `streamable-http` (compatible with local hosting and AgentCore native MCP runtime).
* **`tools/`:** Exposes the 5 tools callable by Alexa+:
  - `create_planned_task`: Registers a planned domestic safety check or daily routine to watch for in ambient speech.
  - `verify_action_status`: Inquires whether an action was completed (*"Did I unplug the clothes iron?"*).
  - `get_daily_actions_recap`: Returns the chronological checklist of planned routines and spontaneous actions.
  - `query_social_contact`: Recalls professional roles and commitments made with someone.
  - `get_topic_briefing`: Fetches the executive technical briefing on recent meetings or lectures.

---

### 4. `src/ingestion/` (Edge / Companion Bridge)
* **`gatekeeper.py`:** Fast screening gatekeeper with dynamic planned task injection, capable of dropping >90% of ambient banter at sub-second latency.
* **`stream_convo.py`:** Subscribes to the `bee-cli` Server-Sent Events stream (`new-utterance`), aggregating transcribed chunks in a sliding window.
* **`orchestrator.py`:** Screens every utterance, feeds the Deep Topic Event Engine and dispatches qualified chunks to the pipeline (off the event loop).
* **`event_engine.py` / `topic_continuity.py`:** Group deep-topic speech into events (lectures, meetings, talks), split them into parts at breaks, decide resume vs. new event by topic similarity, and schedule part/final syntheses. Specification: [docs/next_steps/deep_topic_event_engine/](next_steps/deep_topic_event_engine/00_overview.md).

---

### 5. `src/web_ui/` (Echo Show Ext-Apps)
* Responsive web application designed for touch displays on **Echo Show (8, 10, 15)**.
* Embedded in the sandboxed Alexa Ext-Apps iframe over HTTPS via CloudFront.
* Displays verified peace-of-mind badges, daily routine checklists, social rolodex cards, and scrollable research dossiers.

---

## 🛠️ Quick Developer Commands

```bash
# 1. Setup virtual environment and dependencies
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Run test suite (85 unit & integration tests)
pytest

# 3. Run live evaluation benchmark (25 real-world scenarios)
python scripts/run_live_benchmark.py

# 4. Start Unified FastMCP Server & Web Dashboard (port 8000)
python -m src.serving.mcp_server
```
