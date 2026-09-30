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
| **📚 Deep Meeting & Lecture Intelligence** | Discussions on complex bugs, architecture, new libraries (*AgentCore, DuckDB*), or academic lectures. | Detects salient topics, invokes autonomous web search for documentation/examples, synthesizes an **Executive Briefing**. | *"Alexa, show me the briefing on tech discussed today"* ➔ Interactive report on Echo Show with sources and action items. |

---

## 🏗️ 5-Stage System Architecture

1. **Screening (Semantic Gatekeeper):** Ultra-fast, cost-effective evaluation of incoming audio chunks via lightweight Bedrock foundation models (*GPT-5.6 Luna* or *Claude 3.5 Haiku*). If text is trivial chit-chat or background silence, it drops immediately at zero downstream computation cost.
2. **Semantic Routing:** Qualified chunks are categorized (`social`, `action`, `deep_topic`) and dynamically dispatched to specialized sub-agents.
3. **Extraction & Autonomous Enrichment:**
   - **Social:** Structured Pydantic schema for contacts, roles, and commitments.
   - **Action-State:** Strict veracity filtering to prevent false positives (completed actions only, discarding doubts or future intentions).
   - **Deep Topic Research:** Formulates search queries, retrieves documentation via web search, and synthesizes executive dossiers with Claude 3.5 Sonnet.
4. **Context Knowledge Store:** Unified persistence layer with SQLite + FTS5 for local zero-latency development, and AWS DynamoDB + AgentCore Memory for cloud scale.
5. **Serving Layer (Alexa+ MCP Server & Ext-Apps UI):** Streamable-HTTP **Model Context Protocol (MCP)** server exposing tools to Alexa+, coupled with an interactive touch UI for Echo Show via **ext-apps iframe SDK**.

---

## 💻 Tech Stack & Ecosystem Integrations

- **Wearable Ingestion:** Bee Wearable AI via [`resources/bee-cli/`](resources/bee-cli/) SSE stream (`new-utterance`) and `beemcp` bridge.
- **LLM Provider:** **AWS Bedrock**
  - *GPT-5.6 Luna / Claude 3.5 Haiku:* Low-latency screening and deterministic extraction ($<350\text{ ms}$).
  - *Claude 3.5 Sonnet / Nova Pro:* High-reasoning topic research, technical dossier synthesis, and markdown formatting.
- **Agent Harness:** **AgentCore** / LangGraph for state management, conditional edges, and serverless runtime microVM hosting.
- **Search Tooling:** DuckDuckGo Search / Tavily API for background technical research.
- **Storage:** SQLite with Full-Text Search (FTS5) for local dev; Amazon DynamoDB, S3, and Bedrock AgentCore Memory for cloud production.
- **Serving & Voice UI:** Alexa+ (Echo Show) via Model Context Protocol (Streamable HTTP JSON-RPC 2.0).
- **Frontend UI:** Ext-Apps Iframe SDK for multimodal Echo Show touch displays.

---

## 🏆 Hackathon Alignment & Target Awards

| Track / Challenge | How EXAMEN Maximizes Score |
| :--- | :--- |
| **Track 1: Bee Wearable AI ($12,000)** | Goes beyond passive audio logging by providing real-time ambient understanding, proactive web enrichment, and cross-device intelligence. |
| **Mini-Challenge: AWS Builder ($5,000 + $5,000 credits)** | Native deep integration with AWS Bedrock multi-model tiering (Haiku for screening, Sonnet for synthesis) and orchestration on Bedrock AgentCore. |
| **Cross-Device Orchestration** | Frictionless synergy: **Bee** captures context in the physical world on the go; **Alexa+ on Echo Show** synthesizes and surfaces it at home or office. |

---

## 📂 Project Documentation Structure

Detailed technical, architectural, and operational documentation is organized across the following dedicated guides:

* 📄 [01_architecture_flow.md](docs/01_architecture_flow.md): In-depth 5-stage architecture, end-to-end dataflow, and Mermaid diagrams.
* 📄 [02_bedrock_agentcore_pipeline.md](docs/02_bedrock_agentcore_pipeline.md): LangGraph state graph implementation, Pydantic V2 schemas, Bedrock prompts, and search tools.
* 📄 [03_alexa_mcp_serving.md](docs/03_alexa_mcp_serving.md): MCP Server specifications for Alexa+, JSON-RPC tool schemas, and Echo Show ext-apps wireframes.
* 📄 [04_hackathon_strategy_demo.md](docs/04_hackathon_strategy_demo.md): 3-minute video demo script, judging criteria alignment, and 4-sprint roadmap.
* 📄 [05_tech_stack_resources.md](docs/05_tech_stack_resources.md): Comprehensive tech stack, frameworks, APIs, and submodule references (`agentcore-samples`, `bee-cli`).
* 📄 [06_aws_cloud_deployment_architecture.md](docs/06_aws_cloud_deployment_architecture.md): AWS Cloud deployment architecture (AgentCore Runtime, AgentCore Memory, S3, DynamoDB, Alexa+ MCP, CloudFront).
* 📄 [07_repository_structure_modules.md](docs/07_repository_structure_modules.md): Detailed repository layout, modular monorepo mapping by deployment target, and developer quickstart.
