# 🛠️ Technology Stack, Frameworks, APIs & Reference Resources

> This document tracks all **frameworks**, **libraries**, **APIs**, **cloud platforms**, and **reference repositories** used across the **EXAMEN** project *(from Latin "exāmen": swarm of bees & careful examination)*, with relative links, paths, and integration patterns.

---

## 📁 External Resources & Submodules Directory (`resources/`)

To keep the core codebase of **EXAMEN** clean and distinguish application code from external libraries, reference templates, and SDK implementations, all Git submodules used for **consultation, references, and examples** reside in the dedicated [`resources/`](../resources/) directory.

* The root directory remains focused on application code (`src/`, `docs/`, `tests/`).
* Official samples and external CLI clients remain browseable offline inside [`resources/`](../resources/).
* Future runtime submodules can be segregated accordingly.

---

## 📦 Git Submodules in `resources/`

### 1. AWS Bedrock AgentCore Samples (`resources/agentcore-samples`)
* **Git Repository:** [awslabs/agentcore-samples](https://github.com/awslabs/agentcore-samples.git)
* **Local Submodule Path:** [`resources/agentcore-samples/`](../resources/agentcore-samples/)
* **Description:** Official collection of reference architectures, templates, and integrations for **Amazon Bedrock AgentCore**.
* **Key Reference for EXAMEN:**
  * 🎯 **Directory:** [`resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/`](../resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/)
  * **Sample Code:** [`langgraph_agent_web_search.py`](../resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/langgraph_agent_web_search.py)
  * **Dependencies:** [`requirements.txt`](../resources/agentcore-samples/03-integrations/agentic-frameworks/langgraph/requirements.txt)
  * **Architectural Pattern Adopted in EXAMEN:**
    Demonstrates wrapping a **LangGraph** `StateGraph` inside the **BedrockAgentCoreApp** runtime:
    ```python
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from langgraph.graph import StateGraph, START

    # 1. Compile LangGraph with Bedrock Converse models
    graph = graph_builder.compile()

    # 2. Initialize Bedrock AgentCore runtime app
    app = BedrockAgentCoreApp()

    # 3. MicroVM serverless entrypoint
    @app.entrypoint
    def agent_invocation(payload, context):
        prompt = payload.get("prompt", "")
        output = graph.invoke({"messages": [{"role": "user", "content": prompt}]})
        return {"result": output["messages"][-1].content}

    if __name__ == "__main__":
        app.run()
    ```
  * **Core Packages:**
    - `bedrock-agentcore`
    - `bedrock-agentcore-starter-toolkit`
    - `langchain-aws` (for `model_provider="bedrock_converse"`)
    - `langgraph`
    - `duckduckgo-search`

---

### 2. Bee AI CLI Client (`resources/bee-cli`)
* **Git Repository:** [bee-computer/bee-cli](https://github.com/bee-computer/bee-cli.git)
* **Local Submodule Path:** [`resources/bee-cli/`](../resources/bee-cli/)
* **Description:** Official CLI client and Node/TypeScript SDK for **Bee**, the ambient AI wearable.
* **Key References for EXAMEN:**
  * 🎯 **Native MCP Server:** Bee CLI includes a built-in Model Context Protocol server over stdio and local HTTP with Bearer tokens:
    ```bash
    bee mcp serve                 # stdio JSON-RPC for AI assistants
    bee mcp serve-http --port 8000 # Local HTTP with Bearer auth
    ```
    Exposes native MCP tools (`bee_search`, `bee_list_facts`, `bee_get_daily_summary`, `bee_list_todos`).
  * 🎯 **Real-time Utterance Streaming (SSE):** Supports real-time Server-Sent Events to receive transcribed speech as it happens:
    ```typescript
    import { createBeeClient } from "@beeai/cli/lib";

    const bee = createBeeClient();
    const stream = bee.sse.streamJson({ types: ["new-utterance"] });
    for await (const event of stream.events) {
      console.log(event.data); // Audio transcript payload for Gatekeeper
    }
    ```
  * **Ingestion Utility:** Enables live ingestion and offline context export to feed the sliding-window buffer of Stage 1 (Gatekeeper).

---

## 🧩 Frameworks & Libraries

| Domain | Technology / Library | Version / Package | Role in EXAMEN |
| :--- | :--- | :--- | :--- |
| **Agent Runtime** | **AWS Bedrock AgentCore** | `bedrock-agentcore`, `bedrock-agentcore-starter-toolkit` | Serverless execution harness for complex agents on AWS, state, and lifecycle. |
| **State Graph** | **LangGraph** | `langgraph` ($\ge 0.2.0$) | State orchestration: Gatekeeper $\to$ Router $\to$ Specialized Sub-Agents. |
| **LLM Provider** | **LangChain AWS** | `langchain-aws`, `boto3` | Unified interface to AWS Bedrock foundation models. |
| **Serving Layer** | **Model Context Protocol (MCP)** | `mcp>=1.10.0,<2.0.0` | FastMCP streamable-HTTP server exposing memory tools to Alexa+. |
| **Wearable Bridge** | **Bee CLI & beemcp** | `@beeai/cli`, `beemcp` | Real-time audio stream and utterance ingestion from Bee wearable. |
| **Frontend UI** | **Echo Show Ext-Apps** | HTML5, Vanilla CSS, JS | Multimodal touch UI for Echo Show (Peace of Mind, Rolodex, Briefings). |
| **Local Store** | **SQLite + FTS5** | Python native (`sqlite3`) | Zero-latency local context store with full-text search indexing. |
| **Data Validation** | **Pydantic V2** | `pydantic>=2.7` | Typed contracts for structured outputs (social entities, actions, reports). |
| **Web Research** | **DuckDuckGo / Tavily** | `duckduckgo-search`, `tavily-python` | Autonomous web research tool for technical topics and lectures. |

---

## 🤖 LLM Models (AWS Bedrock)

| Model | Model ID | Purpose / Stage | Technical Rationale |
| :--- | :--- | :--- | :--- |
| **Claude 3.5 Haiku** | `anthropic.claude-3-5-haiku-20241022-v1:0` | Stage 1 (Gatekeeper) & Stage 3A/3B | Ultra-low latency ($<350\text{ ms}$), minimal cost (~$0.25/M tokens), high accuracy in extraction. |
| **Amazon Nova Micro** | `amazon.nova-micro-v1:0` | Stage 1 Alternative (Gatekeeper) | Native AWS ultra-light model, optimal for binary `noop` vs `signal` classification. |
| **Claude 3.5 Sonnet** | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Stage 3C (Deep Research & Briefing) | Advanced reasoning, complex document synthesis, and clean markdown generation. |
| **Amazon Nova Pro** | `amazon.nova-pro-v1:0` | Stage 3C Alternative | Multimodal enterprise foundation model for deep technical analysis. |

---

## 🌐 External APIs & Cloud Services

| Service / API | Purpose | Configuration Notes |
| :--- | :--- | :--- |
| **AWS Bedrock Runtime** | Serverless foundation model inference | Requires AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1`). |
| **Bee Wearable API / WebSocket** | Real-time audio stream and transcription | Ingestion via `bee-cli` SSE stream or local `beemcp` bridge. |
| **Alexa+ Developer Preview** | MCP tool invocation and Ext-Apps rendering | Configured via `alexa_addon.json` and HTTPS endpoint (Cloudflare Tunnel). |
| **Web Search API** | Documentation lookups for Stage 3C | DuckDuckGo (zero-key local) or Tavily API (`TAVILY_API_KEY`). |

---

## 📂 Related Directory Layout

```
amazon_challenge/
├── resources/                            <-- Dedicated directory for reference submodules
│   ├── agentcore-samples/                <-- Official AWS Labs sample repository
│   │   └── 03-integrations/
│   │       └── agentic-frameworks/
│   │           └── langgraph/           <-- LangGraph + AgentCore integration reference
│   └── bee-cli/                          <-- Official Bee AI CLI Client repository
├── docs/                                 <-- Architectural specs and guides
│   ├── 01_architecture_flow.md
│   ├── 02_bedrock_agentcore_pipeline.md
│   ├── 03_alexa_mcp_serving.md
│   ├── 04_hackathon_strategy_demo.md
│   └── 05_tech_stack_resources.md       <-- This document
├── FRICTION_LOG.md                       <-- Friction log for +10% hackathon bonus
└── README.md                             <-- Project overview
```
