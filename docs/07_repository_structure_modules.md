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
│   └── 07_repository_structure_modules.md      # This document
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
│   │   │   ├── gatekeeper.py             # Stage 1: Screening (Claude 3.5 Haiku / Nova Micro)
│   │   │   ├── social.py                 # Stage 3A: Social Recall Extractor
│   │   │   ├── action_state.py           # Stage 3B: Action-State Verifier (Peace of Mind)
│   │   │   └── topic_research.py         # Stage 3C: Deep Topic & Briefing Synthesizer
│   │   └── tools/                        # Tools invoked by agent nodes
│   │       ├── __init__.py
│   │       └── web_search.py             # Web search tool (DuckDuckGo / Tavily)
│   │
│   ├── serving/                          # 🎙️ [TARGET: Alexa+ Serving / MCP Server]
│   │   ├── __init__.py
│   │   ├── mcp_server.py                 # FastMCP server (port 8000 /mcp, streamable-http)
│   │   └── tools/                        # 4 MCP tools exposed to Alexa+
│   │       ├── __init__.py
│   │       ├── action_tools.py           # verify_action_status, get_daily_actions_recap
│   │       ├── social_tools.py           # query_social_contact
│   │       └── topic_tools.py            # get_topic_briefing
│   │
│   ├── ingestion/                        # 🐝 [TARGET: Edge / Companion Bridge]
│   │   ├── __init__.py
│   │   ├── bee_stream_bridge.py          # Live SSE client connected to bee-cli ("new-utterance")
│   │   └── mock_feeder.py                # Offline audio stream simulator for tests & video
│   │
│   └── web_ui/                           # 🖥️ [TARGET: S3 + CloudFront / Echo Show Ext-Apps]
│       ├── index.html                    # Multimodal interactive dashboard
│       ├── styles.css                    # Modern Dark Mode styling for touch displays
│       ├── app.js                        # Frontend rendering logic and cards
│       └── assets/                       # SVG icons and visual assets
│
├── deploy/                               # 🚀 Cloud Deployment & Automation Scripts
│   ├── build_agentcore_bundle.sh         # Download arm64 wheels via uv and package code.zip
│   ├── deploy_agentcore_runtime.py       # Register runtime on AWS via boto3 control-plane
│   ├── deploy_ext_apps_s3.sh             # Sync web_ui to S3 + invalidate CloudFront CDN
│   └── alexa_addon.json                  # Manifest registration for Alexa+ Developer Console
│
├── tests/                                # 🧪 Test Suite & Validation
│   ├── fixtures/                         # Mock audio transcript datasets
│   ├── test_storage.py                   # Unit tests on persistence layer (100% pass)
│   ├── test_gatekeeper.py                # Screening drop-rate test (>90% drop)
│   ├── test_langgraph_pipeline.py        # End-to-end graph test with Bedrock
│   └── test_mcp_server.py                # JSON-RPC tests for Alexa+ tools
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
* **`config.py`:** Uses `pydantic-settings` to parse environment variables with safe defaults (default: region `us-east-1`, Claude 3.5 Haiku/Sonnet models, SQLite `examen.db`, MCP port 8000).
* **`schemas.py`:** Strictly defines Pydantic V2 models:
  - `ChunkClassification`: Gatekeeper compact evaluation (`categories`, `confidence`, `summary_hint`).
  - `SocialEntity`: Contacts, corporate roles, commitments, and topic tags.
  - `VerifiedAction`: Domestic safety and routine tasks with ISO timestamps and confidence scores $\ge 0.80$.
  - `TopicExtraction` & `BriefingReport`: Technical subjects and synthesized markdown briefings with web sources.
  - `ExamenState`: `TypedDict` for the mutable LangGraph state.
* **`storage/`:**
  - `base.py`: Abstract class `AbstractContextStore` enforcing data contract operations.
  - `sqlite_store.py`: Native Python implementation with virtual FTS5 tables for sub-5ms full-text lookups.

---

### 2. `src/pipeline/` (AWS Bedrock AgentCore Runtime)
* **`app.py`:** Instantiates `BedrockAgentCoreApp` and defines the `@app.entrypoint`. Receives audio chunks via `invoke_agent_runtime` and triggers the state graph.
* **`graph.py`:** Builds the LangGraph `StateGraph`, setting Gatekeeper as the entry point and orchestrating conditional edges to specialized sub-agents.
* **`nodes/`:**
  - `gatekeeper.py`: Evaluates utterances via Claude 3.5 Haiku / Nova Micro. Drops irrelevant talk as `noop`.
  - `social.py`: Extracts contacts and bilateral promises, deduplicating known individuals.
  - `action_state.py`: Verifies completed actions, filtering out doubts or future intents.
  - `topic_research.py`: Identifies tech topics, queries `web_search.py`, and synthesizes reports with Claude 3.5 Sonnet.

---

### 3. `src/serving/` (Alexa+ Serving Layer)
* **`mcp_server.py`:** Implements an MCP server via `FastMCP` over `streamable-http` (compatible with local hosting and AgentCore native MCP runtime).
* **`tools/`:** Exposes the 4 tools callable by Alexa+:
  - `verify_action_status`: Inquires whether an action was completed (*"Did I unplug the clothes iron?"*).
  - `get_daily_actions_recap`: Returns the chronological timeline of actions performed today.
  - `query_social_contact`: Recalls professional roles and commitments made with someone.
  - `get_topic_briefing`: Fetches the executive technical briefing on recent meetings or lectures.

---

### 4. `src/ingestion/` (Edge / Companion Bridge)
* **`bee_stream_bridge.py`:** Subscribes to the `bee-cli` Server-Sent Events stream (`new-utterance`), aggregating transcribed chunks in a 30–45s sliding window with a 5s overlap.
* **`mock_feeder.py`:** Simulates realistic spoken dialogue during offline development and demo recording.

---

### 5. `src/web_ui/` (Echo Show Ext-Apps)
* Responsive web application designed for touch displays on **Echo Show (8, 10, 15)**.
* Embedded in the sandboxed Alexa Ext-Apps iframe over HTTPS via CloudFront.
* Displays verified peace-of-mind badges, social rolodex cards, and scrollable research dossiers.

---

## 🛠️ Quick Developer Commands

```bash
# 1. Setup virtual environment and dependencies
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Run test suite
pytest

# 3. Start Alexa+ MCP Server (port 8000)
python -m src.serving.mcp_server

# 4. Ingest mock audio stream
python -m src.ingestion.mock_feeder --scenario morning_routine
```
