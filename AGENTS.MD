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
│   └── 07_repository_structure_modules.md  # Detailed monorepo layout & deployment mapping
├── resources/                              # Dedicated Git submodules (Reference Only)
│   ├── agentcore-samples/                  # Reference for Bedrock AgentCore + LangGraph
│   └── bee-cli/                            # Reference for Bee Wearable SSE streaming API
├── src/                                    # Source code root
│   ├── core/                               # Shared contracts, configs & storage
│   │   ├── config.py                       # Pydantic Settings & environment config
│   │   ├── schemas.py                      # Pydantic V2 data contracts & LangGraph state
│   │   └── storage/                        # Storage abstraction layer (SQLite FTS5 / DynamoDB)
│   ├── pipeline/                           # LangGraph pipeline (Bedrock AgentCore Runtime)
│   │   ├── graph.py                        # StateGraph definition & edge wiring
│   │   ├── app.py                          # AgentCore Runtime entrypoint
│   │   ├── nodes/                          # Gatekeeper, social, action, & topic nodes
│   │   └── tools/                          # Web search & external enrichment tools
│   ├── serving/                            # Serving layer (FastMCP Streamable HTTP)
│   │   └── mcp_server.py                   # Port 8000 Streamable HTTP MCP server
│   └── ingestion/                          # Edge ingestion bridge (Local / VPS / Bee Device)
│       ├── bee_stream_bridge.py            # Bee CLI SSE stream listener & dispatcher
│       └── mock_feeder.py                  # Synthetic conversational audio/text feeder
└── tests/                                  # Pytest unit and integration test suite
    └── test_storage.py                     # SQLite FTS5 storage contract tests
```

---

## 3. Strict Operating Rules for AI Agents

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

### F. FastMCP Version Constraint
* Always ensure `mcp>=1.10.0,<2.0.0` is respected. Version `2.0.0` introduces breaking changes to `mcp.server.fastmcp` which breaks AWS Bedrock AgentCore Runtime compatibility.

---

## 4. Key Reference Locations in Submodules

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

## 5. Development Workflows & Commands

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

### Running the Synthetic Conversational Feeder (For Demos & Testing)
```bash
.venv/bin/python -m src.ingestion.mock_feeder
```

---

## 6. Friction Log Protocol

Whenever you encounter a non-obvious bug, dependency incompatibility, or tricky API quirk (such as SDK breaking changes, Bedrock prompt formatting issues, or FastMCP quirks), **record it immediately** in `FRICTION_LOG.md`:
* **Problem:** What failed or caused unexpected friction.
* **Root Cause:** Why it happened.
* **Resolution / Workaround:** Exactly how it was solved or bypassed.

---

## 7. Current Project Roadmap & Priorities

1. **Pipeline Core (`src/pipeline/`):**
   * Implement `src/pipeline/nodes/gatekeeper.py` (GPT-5.6 Luna / Claude 3.5 Haiku).
   * Implement parallel enrichment nodes: `social.py`, `action_state.py`, and `topic_research.py`.
   * Compile the LangGraph pipeline in `src/pipeline/graph.py`.
2. **Serving Layer (`src/serving/`):**
   * Implement FastMCP server in `src/serving/mcp_server.py` exposing:
     * `get_daily_briefing`
     * `get_person_dossier`
     * `get_pending_commitments`
     * `search_ambient_memory`
3. **Ingestion & Demo Bridge (`src/ingestion/`):**
   * Build `mock_feeder.py` simulating the hackathon demo scenario (meeting with Sarah Chen).
   * Build `bee_stream_bridge.py` for live Bee Wearable hardware integration.
