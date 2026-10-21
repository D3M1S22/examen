# AGENTS.md — Developer & AI Agent Operational Manual

Welcome to **EXAMEN** (*Ambient Knowledge & Action Engine*), built for the **Amazon Developer Hackathon 2026** competing across both the **Bee Wearable AI** and **AWS Builder Challenge** tracks.

This document serves as the primary operational directive and knowledge index for all human developers and autonomous AI agents working within this repository.

---

## 1. Project Overview & Hackathon Targets

* **Project Name:** EXAMEN
* **Tagline:** Turning ambient spoken life into actionable intelligence and ambient ambient displays via AWS Bedrock AgentCore & Bee Wearable.
* **Target Tracks:**
  1. **Bee Wearable AI ($12,000):** Real-time audio stream processing via Bee CLI SSE, low-latency contextual enrichment, automated entity/action resolution.
  2. **AWS Builder Challenge ($5,000 + $5,000 AWS Credits):** Deployed on AWS Bedrock AgentCore Runtime, AgentCore Memory, Claude 3.5 Sonnet/Haiku, Amazon Nova, and FastMCP serving.

---

## 2. Repository Layout & Architecture

The repository is organized as a **modular monorepo**, cleanly segregating cloud deployment targets from edge ingestion and local reference resources:

```
amazon_challenge/
├── AGENTS.md                                # This operational manual
├── README.md                               # Project vision, quickstart & architecture
├── FRICTION_LOG.md                         # Log of blockers, gotchas, and resolutions
├── pyproject.toml / requirements.txt       # Python dependencies and build config
├── .env.example                            # Template of required environment variables
├── docs/                                   # Full technical & strategy documentation
│   ├── 01_architecture_flow.md             # 5-Stage end-to-end pipeline & Mermaid flow
│   ├── 02_bedrock_agentcore_pipeline.md    # LangGraph state machine & model tiering
│   ├── 03_alexa_mcp_serving.md             # FastMCP protocol, tools & Echo Show UI wireframes
│   ├── 04_hackathon_strategy_demo.md       # 3-Minute pitch script, judging rubric & roadmap
│   ├── 05_tech_stack_resources.md          # Tech stack breakdown & submodule references
│   ├── 06_aws_cloud_deployment_architecture.md # Bedrock AgentCore, Memory & AWS infrastructure
│   ├── 07_repository_structure_modules.md  # Detailed monorepo layout & deployment mapping
│   ├── 08_real_telemetry_and_bee_hardware_spec.md # Telemetry & Bee hardware integration
│   └── 10_bee_cli_reference.md             # Observed bee-cli/API contract (source of truth for Bee data)
├── resources/                              # Dedicated Git submodules (Reference Only)
│   ├── agentcore-samples/                  # Reference for Bedrock AgentCore + LangGraph
│   └── bee-cli/                            # Reference for Bee Wearable SSE streaming API
├── scripts/                                # Utility and benchmark scripts
│   └── run_live_benchmark.py               # Comprehensive live evaluation benchmark suite
├── src/                                    # Source code root
│   ├── core/                               # Shared contracts, configs & storage
│   │   ├── config.py                       # Pydantic Settings & environment config
│   │   ├── models.py                       # Centralized Dual-Provider Model Factory (Bedrock & Mantle)
│   │   ├── schemas.py                      # Pydantic V2 data contracts & LangGraph state
│   │   └── storage/                        # Storage abstraction layer (SQLite FTS5 / DynamoDB)
│   ├── pipeline/                           # LangGraph pipeline (Bedrock AgentCore Runtime)
│   │   ├── graph.py                        # StateGraph definition & conditional routing
│   │   ├── app.py                          # BedrockAgentCoreApp runtime entrypoint (@app.entrypoint)
│   │   ├── nodes/                          # Action-state, social, topic research & persist nodes
│   │   └── tools/                          # DuckDuckGo multi-tier web search tool
│   ├── serving/                            # Serving layer (FastMCP Streamable HTTP for Alexa+)
│   │   └── mcp_server.py                   # Port 8000 Streamable HTTP MCP server
│   └── ingestion/                          # Edge ingestion bridge (Local / VPS / Bee Device)
│       ├── stream_convo.py                 # Bee CLI SSE stream client (BeeClient)
│       ├── orchestrator.py                 # Sliding window buffer & edge screening orchestrator
│       └── gatekeeper.py                   # Semantic screening gatekeeper & task injection
└── tests/                                  # Pytest unit and integration test suite (66 tests, 100% pass)
    ├── test_storage.py                     # SQLite FTS5 storage contract tests
    ├── test_gatekeeper.py                  # Gatekeeper screening & active task tests
    ├── test_ingestion_orchestrator.py      # Buffer & semantic cut tests
    ├── test_model_factory.py               # Bedrock & Mantle dual-provider factory tests
    ├── test_web_search.py                  # Multi-tier web search & SSRF security tests
    ├── test_pipeline_nodes.py              # Specialized pipeline nodes & scheduled task tests
    └── test_langgraph_pipeline.py          # End-to-end LangGraph & AgentCore app tests
```

---

## 3. Operating Mindset: Discovery, Reason, Then Act
Before proposing plans or generating code, you MUST operate as a senior software architect and frontend engineer:
1. **Discover Context**: Read and respect all architecture rules under `docs/` (`01` through `07`), active guidelines in `.agents/rules/`, and the data contracts in `src/core/schemas.py`.
2. **Reason Deeply**: Explicitly evaluate how any requested edit fits into:
   - The non-blocking ingestion stream (`BeeClient` -> `BeeStreamOrchestrator`).
   - The LangGraph pipeline and semantic screening (`Gatekeeper`).
   - The MCP serving tools and UI reactive state.
3. **Execute Cleanly**: Never make speculative changes. Build code that directly satisfies the user's design mockups and backend data models.

---

## 4. Architecture & Rule Locations
- **Project Architecture & Strategy**: Located in `docs/` (`01_architecture_flow.md` to `07_repository_structure_modules.md`).
- **Operational Rules**: Located in `.agents/rules/` (UI integration, reasoning protocols, and web standards).
- **Core Domain Models**: Located in `src/core/schemas.py`.

---

---

## 5. Web UI Redesign Protocol (For Antigravity)
- Treat the UI mockups as authoritative for layout, visual hierarchy, spacing, and component structure.
- Adhere strictly to `.agents/rules/ui-realtime-integration.md`.
- Ensure all interactive elements map 1-to-1 to endpoints in `src/serving/mcp_server.py` and tools in `src/serving/tools/`.

---

## 6. Strict Operating Rules for AI Agents

Whenever you inspect, modify, or extend this codebase, you **must adhere strictly** to the following principles:

### A. Language Standard
* **100% English:** All code, comments, docstrings, documentation files (`*.md`), git commits, and tool outputs must be written in English.

### B. Portability & Path Handling
* **NO Absolute Local Paths:** Never commit or hardcode paths containing local usernames (e.g. `/home/user/...` or `C:\...`).
* **Relative Links Only:** In documentation, reference files using portable relative paths (e.g., `docs/01_architecture_flow.md` or `resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/`).

### C. Reference Submodules Policy
* The `resources/` directory contains external Git submodules (`resources/agentcore-samples` and `resources/bee-cli`).
* **Treat `resources/` as READ-ONLY reference material:** Do not alter submodule tracking branches or commit project logic inside `resources/`. All project code lives in `src/`.

### D. Data Contracts & Typing
* All inter-module communication must use **Pydantic V2** schemas defined in `src/core/schemas.py`.
* LangGraph state is strictly typed using `ExamenState`.
* Never pass unvalidated dictionaries or ad-hoc JSON blobs across node boundaries.

### E. Storage Decoupling
* Always interact with storage via the `AbstractContextStore` interface in `src/core/storage/base.py` and obtain instances through `src/core/storage.get_storage_store()`.
* Never hardcode direct SQLite SQL queries outside `src/core/storage/sqlite_store.py`.
* Two backends implement the store (`STORAGE_BACKEND=sqlite|dynamo`, `docs/next_steps/dynamodb_storage/`). A change to a store method changes both, the domain rules shared by both live in `src/core/storage/rules.py`, and store tests use the `make_store` fixture so they run on both backends. DynamoDB requests of the per-user store must always target the tenant's own partition (`pk = user_id`, index keys `user_id#…`); never add `Scan`.

### F2. Tenancy (multi-user)
* Every user is a tenant (`src/core/tenancy.py`, `docs/13_multi_user_accounts.md`). Request handlers and MCP tools already run inside the caller's tenant; background work for a user must be started inside `tenant_scope(user_id)`.
* Never cache per-user objects in module globals: follow the pattern of `get_event_engine()` / `get_backfill_service()` (one instance per tenant via `resolve_tenant()`; legacy singleton only with `AUTH_ENABLED=false`). With accounts enabled, code that touches user data without a tenant raises `MissingTenant` (fail-closed): fix the missing `tenant_scope`, never catch it to fall back.
* Pipeline payloads carry `user_id` (`agent_invocation` checks it); LLM calls go through `llm_slot()` (`src/core/limits.py`), shared by every user.
* Dev scripts touching user data run as an account: wrap `main()` in `cli_tenant()` (`src/core/cli.py`, `EXAMEN_CLI_USER=<email>`).
* Account, Bee and admin routes are session-only (`SESSION_ONLY_PREFIXES` in `auth_middleware.py`); admin routes manage accounts and must never return a user's data.

### F3. Logging, service log and runtime settings (`docs/next_steps/admin_console/`)
* Use `logging.getLogger("examen.<area>.<module>")` (never `__name__` outside `examen.*`): only the `examen` hierarchy reaches journald and the admin service log.
* **Never put user content in a log message** (names, titles, summaries, transcripts, places): log ids. `tests/test_admin_console.py` greps for it. Use `Debug.debug(..., log=False)` for debug prints that carry speech.
* Problems worth the admin's attention: `logger.warning(msg, extra={"event_code": "<catalogue code>", "ctx": {...}})` or `report_event(code, …)` (`src/core/service_log.py`, catalogue in doc 03 §4.5); model fallbacks go through `model_fallback()`. Background tasks: `watch_task()`.
* Build every model through `src/core/models.py` (`get_chat_model(..., role=…)`, `get_fast_model(role=…)`, `get_embedding_model`): it attaches the token usage counter of the admin console; a model built elsewhere is not counted.
* New tunables that admins may change at runtime: add a `SettingSpec` to `REGISTRY` in `src/core/runtime_settings.py` (type, limits, apply mode). Read settings at use time, or mark the key `runtime` if a component copies it at construction.
* Every `bee` subprocess must pass `env=bee_subprocess_env()` (per-user `BEE_CONFIG_DIR` + file store). Never call `bee logout` for the host.
* `broadcast_event` targets the current tenant; pass `tenant=` explicitly from callbacks that may run elsewhere.

### F. FastMCP Version Constraint
* Always ensure `mcp>=1.10.0,<2.0.0` is respected. Version `2.0.0` introduces breaking changes to `mcp.server.fastmcp` which breaks AWS Bedrock AgentCore Runtime compatibility.

---

## 6. Key Reference Locations in Submodules

When implementing or debugging specific features, refer to these canonical implementations in `resources/`:

1. **AWS Bedrock AgentCore + LangGraph Integration:**
   * Path: `resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/`
   * Key pattern: How to wrap a LangGraph compiled graph with Bedrock AgentCore decorators and host it inside AgentCore Runtime.

2. **Bee Wearable SSE Audio Stream Bridge:**
   * Path: `resources/bee-cli/`
   * Key pattern: Subscribing to the real-time utterance stream:
     ```typescript
     bee.sse.streamJson({ types: ["new-utterance"] })
     ```

---

## 7. Development Workflows & Commands

### Virtual Environment Setup
The project uses `uv` for fast, deterministic Python environment management:
```bash
# Sync dependencies
uv sync

# Or with pip in active venv
pip install -r requirements.txt
```

### Running Test Suite
Always verify that test suites pass before concluding any task:
```bash
.venv/bin/pytest tests/ -v
```

### Running the FastMCP Server Locally
```bash
.venv/bin/python -m src.serving.mcp_server
# Listens on http://0.0.0.0:8000/mcp (Streamable HTTP transport)
```

### Bee CLI & Physical Device Testing
```bash
git submodule update --init resources/bee-cli
cd resources/bee-cli && bun install && \
  bun build ./sources/main.ts --compile --target=bun-linux-x64 --outfile ./dist/platforms/linux-x64/bee
ln -sf "$PWD/dist/platforms/linux-x64/bee" ~/.local/bin/bee   # optional: `bee` on PATH
bee login                                                     # approve in the Bee app (Developer Mode)
python scripts/bee_spike.py check                             # Phase 0 spike tool, raw data in .bee-spike/
```
Runbook and results: `docs/next_steps/historical_backfill/06_phase0_device_spike.md`.
The live stream uses a private `bee proxy` on 127.0.0.1 (`BEE_STREAM_TRANSPORT=proxy`, fallback `cli`); see `.env.example` for the `BEE_*` settings. Tests must never run the real `bee` binary: `tests/conftest.py` stubs it (some endpoints call `bee logout`).
**Before touching any code that reads Bee data, read `docs/10_bee_cli_reference.md`**: real payloads differ from the official docs (no speaker in `new-utterance`, ISO `spoken_at`, relative `start`/`end`, no `update-utterance`, no `update-location` from the Apple Watch).

### Running the Synthetic Conversation Scenarios (For Demos & Testing)
```bash
.venv/bin/python scripts/simulate_mock_conversations.py --help   # scenarios from resources/mock_conversations.json
```

---

## 8. Friction Log Protocol

Whenever you encounter a non-obvious bug, dependency incompatibility, or tricky API quirk (such as SDK breaking changes, Bedrock prompt formatting issues, or FastMCP quirks), **record it immediately** in `FRICTION_LOG.md`:
* **Problem:** What failed or caused unexpected friction.
* **Root Cause:** Why it happened.
* **Resolution / Workaround:** Exactly how it was solved or bypassed.

---

## 9. Current Project Roadmap & Priorities

1. **Pipeline Core (`src/pipeline/`) — [COMPLETED & VERIFIED]:**
   * ✅ Implemented `src/ingestion/gatekeeper.py` with dynamic active task injection.
   * ✅ Implemented parallel enrichment nodes: `social.py`, `action_state.py`, and `topic_research.py`.
   * ✅ Compiled pure LangGraph `StateGraph` in `src/pipeline/graph.py` with multi-label fan-out and conditional routing.
   * ✅ Integrated Bedrock AgentCore Runtime entrypoint in `src/pipeline/app.py` (`@app.entrypoint`).
   * ✅ Dual-Provider Engine: Native Bedrock Converse API + Bedrock Mantle OpenAI-compatible API (`src/core/models.py`).
   * ✅ Comprehensive Live Evaluation Benchmark (`scripts/run_live_benchmark.py`): 25/25 scenarios passed (100%), average 3.5s latency, sub-1-cent cost on `nvidia.nemotron-super-3-120b`.
2. **Serving Layer (`src/serving/`) — [COMPLETED & VERIFIED]:**
   * ✅ Implemented FastMCP server in `src/serving/mcp_server.py` with Starlette ASGI support.
   * ✅ Implemented 5 exposed MCP tools in `src/serving/tools/`:
     * `create_planned_task` (for scheduling domestic/routine checks)
     * `verify_action_status` (for peace of mind queries like "did I unplug the iron?")
     * `get_daily_actions_recap`
     * `query_social_contact`
     * `get_topic_briefing`
   * ✅ Exposes REST telemetry endpoints (`/api/status`, `/api/actions`, `/api/routines`, `/api/contacts`, `/api/topics`, `/api/simulate`).
3. **Frontend UI & Alexa+ Add-On (`src/web_ui/` & `deploy/`) — [COMPLETED & VERIFIED]:**
   * ✅ Built modern multimodal touch dashboard for Echo Show (ext-apps) and desktop/mobile in `src/web_ui/` (`index.html`, `styles.css`, `app.js`).
   * ✅ Implemented Peace of Mind Hero banner, Daily Routines Checklist with live scheduling, Social Rolodex cards, Topic Dossiers viewer, and Ambient Audio Stream Simulator.
   * ✅ 85 unit & integration tests passing (100% test suite).
4. **Ingestion & Demo Bridge (`src/ingestion/`):**
   * ✅ Demo scenarios via `scripts/simulate_mock_conversations.py` and `scripts/replay_event_scenarios.py`.
   * ✅ Live stream verified with a real account (2026-10-19, Apple Watch): `docs/10_bee_cli_reference.md`.
   * Conformance fixes pending: `docs/10_bee_cli_reference.md` §10 (C1–C16) and backfill items I1–I9.
