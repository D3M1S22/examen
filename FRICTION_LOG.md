# 📝 EXAMEN Friction Log (+10% Hackathon Bonus)

> This document maintains a daily track of technical friction points, SDK bugs, integration hurdles, workarounds, and constructive feedback while working with official platform SDKs: **Bee CLI / beemcp**, **AWS Bedrock & AgentCore**, and **Alexa+ CLI / ext-apps**.

---

## Event Logging Template

Whenever a friction point or roadblock is encountered during development, document it using the following format:

```markdown
### [YYYY-MM-DD] - Component / SDK
* **Context:** What we were trying to achieve.
* **Friction Encountered:** Bug, crash, missing documentation, or unexpected behavior.
* **Workaround / Resolution:** How we resolved or bypassed the roadblock.
* **Platform Feedback:** How Amazon, AWS, or Bee could improve the developer experience in the future.
```

---

## Session Logs

### [2026-09-28] - Architectural Setup & Ingestion Routing Strategy
* **Context:** Defining the ingestion bridge between the continuous Bee transcript stream and the AgentCore processing harness.
* **Friction Encountered:** Sending every raw transcribed audio snippet directly to heavy reasoning models (e.g. Claude 3.5 Sonnet) would cause excessive latency (>2-3s per turn) and unsustainable token costs for the 90%+ of background chit-chat and silence.
* **Workaround / Resolution:** Designed a two-tier pattern: a high-efficiency **Semantic Gatekeeper** powered by a lightweight model (Claude 3.5 Haiku or Amazon Nova Micro) with a 30-45s sliding window that immediately drops `noop` chunks, invoking extraction and web research sub-agents only when genuine signal is detected.
* **Platform Feedback:** Having native VAD (Voice Activity Detection) flags and semantic sentence-boundary segmentation directly exposed in the Bee WebSocket/SSE stream would significantly simplify ingestion logic for developers.

### [2026-10-01] - LangChain ChatBedrockConverse with NVIDIA Models
* **Context:** Invoking `nvidia.nemotron-super-3-120b` via `ChatBedrockConverse` on AWS Bedrock.
* **Friction Encountered:** LangChain emitted recurring warnings: `"Streaming disabled for model 'nvidia.nemotron-super-3-120b': provider 'nvidia' is not verified as streaming-capable with ChatBedrockConverse, so calls will fall back to the non-streaming Converse API"`.
* **Workaround / Resolution:** Non-streaming Converse API works properly for structured output extraction. For streaming responses, explicitly pass `disable_streaming=False` or use non-streaming fallback.
* **Platform Feedback:** `langchain-aws` should maintain an updated capability registry of verified streaming models across all third-party providers on AWS Bedrock (including NVIDIA Nemotron).

### [2026-10-01] - Dual Provider: Bedrock Mantle vs Native Bedrock Model Routing
* **Context:** Implementing dual-provider support allowing developers to switch between native AWS Bedrock Converse API and Bedrock Mantle OpenAI-compatible endpoints (`/openai/v1`).
* **Friction Encountered:**
  1. Sending native Bedrock foundation model IDs (e.g. `nvidia.nemotron-super-3-120b`) to the Mantle endpoint returned `400 Bad Request: model 'nvidia.nemotron-super-3-120b' isn't supported on this route`, as Mantle routes specific OpenAI-compatible and open-weight models.
  2. `aws-bedrock-token-generator` requires AWS credentials to be present in `os.environ` or boto3 default session; however, Pydantic `BaseSettings` populates instance fields without mutating `os.environ`.
* **Workaround / Resolution:**
  1. Built a centralized model factory (`src/core/models.py`) with independent provider toggles (`GATEKEEPER_PROVIDER` and `REASONER_PROVIDER`), routing native models to `ChatBedrockConverse` and Mantle models to `ChatOpenAI`.
  2. In `get_mantle_api_key()`, explicitly propagate AWS IAM credentials to `os.environ` if missing, allowing automatic token minting without requiring manual static API keys.
* **Platform Feedback:** AWS Bedrock documentation should clearly cross-reference which foundation models are available on the Mantle OpenAI-compatible endpoint vs the native Converse API.

### [2026-10-02] - Pydantic Deprecation Warnings in bedrock-agentcore
* **Context:** Running test suite with `bedrock-agentcore`.
* **Friction Encountered:** Pydantic emitted deprecation warnings: `PydanticDeprecatedSince20: Support for class-based 'config' is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. in bedrock_agentcore/runtime/context.py:17`.
* **Workaround / Resolution:** Documented warning in test runner; internal schemas in EXAMEN strictly use Pydantic V2 `model_config = ConfigDict(...)`.
* **Platform Feedback:** Update `bedrock-agentcore` to use modern Pydantic V2 `ConfigDict` across all runtime context classes.
