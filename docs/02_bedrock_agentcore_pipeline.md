# ⚙️ Technical Pipeline: AWS Bedrock, AgentCore & LangGraph

> This document provides the engineering specifications for the **EXAMEN** agentic pipeline *(from Latin "exāmen": swarm of bees & careful examination)*, detailing **AWS Bedrock** model selection, state graph orchestration with **LangGraph / AgentCore**, Pydantic data schemas, system prompts, and autonomous web research enrichment.

---

## 🧠 Dual-Provider Model Tiering & Latency/Cost Strategy

The pipeline implements an intelligent, provider-agnostic **Dual-Provider Model Tiering** pattern on AWS Bedrock via `src/core/models.py`:
* **AWS Bedrock Native (Converse API):** High performance via SigV4 auth (`amazon.nova-*`, `anthropic.claude-*`, `nvidia.nemotron-*`).
* **AWS Bedrock Mantle (OpenAI-compatible):** Seamless OpenAI SDK compatibility (`openai.gpt-5.6-luna`, `openai.gpt-5.6-terra`, etc.) via `https://bedrock-mantle.{region}.api.aws/openai/v1` with dynamic IAM token minting.

| Pipeline Stage | Provider Selection | Primary Foundation Model | Fallback AWS Model | Temperature | Measured Avg Latency |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Stage 1: Gatekeeper / Screening** | `GATEKEEPER_PROVIDER=bedrock\|mantle` | `nvidia.nemotron-super-3-120b` / `nova-micro` | `claude-3-5-haiku` / `gpt-5.6-luna` | `0.0` | **0.95s** |
| **Stage 3A: Social Recall Extractor** | Inherits `GATEKEEPER_PROVIDER` | `nvidia.nemotron-super-3-120b` / `nova-lite` | `claude-3-5-haiku` / `gpt-5.6-luna` | `0.0` | **0.81s** |
| **Stage 3B: Action-State Verifier** | Inherits `GATEKEEPER_PROVIDER` | `nvidia.nemotron-super-3-120b` / `nova-lite` | `claude-3-5-haiku` / `gpt-5.6-luna` | `0.0` | **1.13s** |
| **Stage 3C: Deep Research & Briefing** | `REASONER_PROVIDER=bedrock\|mantle` | `nvidia.nemotron-super-3-120b` / `claude-3-5-sonnet` | `amazon.nova-pro-v1:0` | `0.2` | **23-39s** *(incl. web search)* |

* **Why Fast Tier for Screening & Extraction:** Sub-second response ($0.8\text{--}1.1\text{s}$) at ultra-low cost ($0.018\text{ cents per call}$), dropping 90%+ of irrelevant ambient chit-chat.
* **Why Deep Reasoner for Stage 3C:** Activated exclusively when technical topics, bugs, architecture questions, or academic lectures are detected to analyze multi-source search results and synthesize deep markdown dossiers.

---

## 📐 Data Schemas & Pydantic Contracts

All intra-agent state mutations are typed via **Pydantic V2** (defined in `src/core/schemas.py`):

```python
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# ----------------------------------------------------
# 1. Gatekeeper Classifier Output
# ----------------------------------------------------
class ChunkClassification(BaseModel):
    categories: List[Literal["social", "action", "deep_topic", "noop"]] = Field(
        description="Categories detected in the transcript chunk. 'noop' if irrelevant."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, 
        description="Overall classification confidence score."
    )
    summary_hint: str = Field(
        description="Single-line concise summary of detected signal."
    )

# ----------------------------------------------------
# 2. Social Recall Channel
# ----------------------------------------------------
class SocialEntity(BaseModel):
    person_name: str = Field(description="Full name of person encountered.")
    company_or_role: Optional[str] = Field(None, description="Company, title, or professional context.")
    contact_info: Optional[str] = Field(None, description="Email, social handle, phone if mentioned.")
    commitments: List[str] = Field(
        default_factory=list, 
        description="Promises made to or by the interlocutor."
    )
    key_topics: List[str] = Field(
        default_factory=list, 
        description="Salient topic tags discussed."
    )

# ----------------------------------------------------
# 3. Action-State & Routine Task Channel
# ----------------------------------------------------
class VerifiedAction(BaseModel):
    action_type: str = Field(
        description="Normalized action type: iron_unplugged, stove_off, door_locked, medication_taken, pr_merged, email_sent."
    )
    domain: Literal["safety", "routine", "work_task"] = Field(
        description="Domain of action (home safety, personal routine, work task)."
    )
    raw_statement: str = Field(
        description="Exact utterance spoken by user verifying completed action."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, 
        description="Certainty score verifying completion (filters out doubts and future intentions)."
    )

# ----------------------------------------------------
# 4. Deep Topic Research Channel
# ----------------------------------------------------
class TopicExtraction(BaseModel):
    topic_title: str = Field(description="Succinct title of topic, bug, or technology.")
    context_type: Literal["bug", "feature_discussion", "tech_stack", "academic_lecture"] = Field(
        description="Context classification."
    )
    search_queries: List[str] = Field(
        description="1-3 focused web search queries to retrieve authoritative documentation."
    )
    key_questions: List[str] = Field(
        description="Core questions or technical aspects to resolve."
    )

class BriefingReport(BaseModel):
    topic_title: str
    context_type: str
    executive_summary: List[str] = Field(description="Executive summary in 3-4 bullet points.")
    deep_dive_markdown: str = Field(description="Detailed markdown dossier with definitions, solutions, code.")
    web_sources: List[str] = Field(description="Consulted external URLs.")
    action_items: List[str] = Field(description="Concrete action items or next steps.")
```

---

## 🔄 State Definition & LangGraph Pipeline

```python
from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END
from src.core.models import get_fast_model, get_reasoner_model
from src.core.schemas import ExamenState, ChunkClassification, SocialEntity, VerifiedAction, TopicExtraction, BriefingReport

# Initializing Dynamic Dual-Provider Bedrock & Mantle Models
llm_fast = get_fast_model()       # Uses GATEKEEPER_PROVIDER (Bedrock Converse or Mantle OpenAI)
llm_reasoner = get_reasoner_model() # Uses REASONER_PROVIDER (Bedrock Converse or Mantle OpenAI)
```

### Node Implementation Details

```python
# 1. GATEKEEPER / SCREENING NODE
def node_gatekeeper(state: ExamenState) -> dict:
    prompt = (
        "You are the high-efficiency semantic screening filter for the EXAMEN wearable assistant.\n"
        "Analyze the following transcribed audio chunk and label it with detected categories:\n"
        "- 'social': introductions, names, roles, or mutual commitments;\n"
        "- 'action': explicit first-person statements confirming completed safety or work tasks;\n"
        "- 'deep_topic': discussions on engineering, libraries, bugs, features, or academic lectures;\n"
        "- 'noop': if the snippet lacks durable informative value (casual banter, pleasantries, silence).\n\n"
        f"Transcript: \"{state['raw_transcript']}\""
    )
    classifier = llm_gatekeeper.with_structured_output(ChunkClassification)
    res = classifier.invoke(prompt)
    return {"categories": res.categories, "confidence": res.confidence, "summary_hint": res.summary_hint}

# 2. SOCIAL RECALL NODE
def node_extract_social(state: ExamenState) -> dict:
    prompt = (
        "Extract details of the encountered person and bilateral commitments made.\n"
        f"Text: \"{state['raw_transcript']}\""
    )
    extractor = llm_gatekeeper.with_structured_output(SocialEntity)
    return {"social_data": extractor.invoke(prompt)}

# 3. ACTION-STATE VERIFIER NODE
def node_extract_action(state: ExamenState) -> dict:
    prompt = (
        "Analyze if the user explicitly confirmed completing a routine or safety action "
        "(e.g. 'I turned off the burner', 'door is locked', 'deployed to staging').\n"
        "IMPORTANT: Strictly ignore future intentions or doubts ('I need to remember to turn off the gas').\n"
        f"Text: \"{state['raw_transcript']}\""
    )
    extractor = llm_gatekeeper.with_structured_output(VerifiedAction)
    return {"action_data": extractor.invoke(prompt)}

# 4. TOPIC EXTRACTION & RESEARCH NODE
def node_topic_research(state: ExamenState) -> dict:
    # Step 1: Extract topic and formulate search queries
    prompt_extract = (
        "Identify the engineering topic, discussed bug, cited library, or lecture subject.\n"
        "Generate 1-3 search queries to retrieve documentation and best practices.\n"
        f"Text: \"{state['raw_transcript']}\""
    )
    topic_parser = llm_gatekeeper.with_structured_output(TopicExtraction)
    extracted: TopicExtraction = topic_parser.invoke(prompt_extract)

    # Step 2: Autonomous Web Search
    search_context = execute_web_search(extracted.search_queries)

    # Step 3: Synthesis with Claude 3.5 Sonnet
    prompt_report = (
        f"You are a technical research assistant. The user discussed: '{extracted.topic_title}'.\n"
        f"Discussion context: \"{state['raw_transcript']}\"\n"
        f"Retrieved documentation results:\n{search_context}\n\n"
        "Synthesize a thorough Executive Briefing with formatted markdown for Echo Show and engineers."
    )
    synthesizer = llm_reasoner.with_structured_output(BriefingReport)
    report = synthesizer.invoke(prompt_report)

    return {"topic_extracted": extracted, "briefing_report": report}

# 5. PERSISTENCE NODE
def node_persist(state: ExamenState) -> dict:
    from src.core.storage import get_storage_store
    store = get_storage_store()
    if state.get("social_data"):
        store.save_social_contact(state["social_data"])
    if state.get("action_data"):
        store.save_action(state["action_data"])
    if state.get("briefing_report"):
        store.save_topic_briefing(state["briefing_report"])
    return {}
```

### Conditional State Graph Construction (`src/pipeline/graph.py`)

The pipeline receives pre-screened, qualified chunks from Ingestion and uses conditional edges from `START` to dispatch to specialized nodes in parallel:

```python
def route_categories(state: ExamenState) -> List[str]:
    """Conditional router: maps categorized signal to specialized nodes."""
    categories = state.get("categories", [])
    if not categories or "noop" in categories:
        return [END]

    targets = []
    if "action" in categories:
        targets.append("action_node")
    if "social" in categories:
        targets.append("social_node")
    if "deep_topic" in categories:
        targets.append("topic_node")

    return targets if targets else [END]

builder = StateGraph(ExamenState)
builder.add_node("action_node", node_extract_action)
builder.add_node("social_node", node_extract_social)
builder.add_node("topic_node", node_topic_research)
builder.add_node("persist_node", node_persist)

# Route conditionally from START
builder.add_conditional_edges(
    START,
    route_categories,
    {
        "action_node": "action_node",
        "social_node": "social_node",
        "topic_node": "topic_node",
        END: END,
    },
)

# All specialized branches converge at the persistence layer
builder.add_edge("action_node", "persist_node")
builder.add_edge("social_node", "persist_node")
builder.add_edge("topic_node", "persist_node")
builder.add_edge("persist_node", END)

pipeline_graph = builder.compile()
```

### AWS Bedrock AgentCore Runtime Entrypoint (`src/pipeline/app.py`)

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from src.pipeline.graph import pipeline_graph

app = BedrockAgentCoreApp()

@app.entrypoint
def agent_invocation(payload: dict, context: Any = None) -> dict:
    # Handles raw prompt fallback or pre-categorized ingestion chunks
    ...
    return pipeline_graph.invoke(state)

if __name__ == "__main__":
    app.run()
```

---

## 🌐 Autonomous Web Search Tooling

When `topic_research` is invoked, the harness executes autonomous web research via DuckDuckGo Search (`ddgs`) or Bedrock Agent Action Groups:

```python
from duckduckgo_search import DDGS

def execute_web_search(queries: List[str]) -> str:
    results_text = []
    with DDGS() as ddgs:
        for q in queries[:2]:
            res = list(ddgs.text(q, max_results=3))
            formatted = "\n".join([f"- [{r['title']}]({r['href']}): {r['body']}" for r in res])
            results_text.append(f"Query: {q}\nResults:\n{formatted}")
    return "\n\n".join(results_text)
```

---

## 🚀 AWS Bedrock AgentCore Runtime Packaging

To deploy to **AWS Bedrock AgentCore Runtime**:
* **Packaging:** Pre-compile arm64 dependencies using `uv`:
  ```bash
  uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 --target bundle -r requirements.txt
  cd bundle && zip -r ../code.zip . && cd ..
  zip code.zip -r src/
  ```
* **Hosting:** Upload `code.zip` to S3 and register via `bedrock-agentcore-control.create_agent_runtime(...)`.
