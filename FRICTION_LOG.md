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

### [2026-10-05] - FastMCP Tool Schema Inspection on Python Dependency Injection Types
* **Context:** Exposing MCP tools using `@mcp.tool()` in FastMCP.
* **Friction Encountered:** FastMCP inspects Python type hints on decorated tool functions to automatically generate JSON schema definitions for LLMs via Pydantic. When optional internal dependency objects (such as `store: Optional[AbstractContextStore] = None`) were present in the function signature, Pydantic raised `PydanticInvalidForJsonSchema: Cannot generate a JsonSchema for core_schema.IsInstanceSchema (<class 'AbstractContextStore'>)`, crashing tool registration.
* **Workaround / Resolution:** Decoupled internal logic functions (`execute_create_planned_task`, `execute_verify_action_status`) from public tool signatures (`create_planned_task`, `verify_action_status`). Public signatures only expose client parameters (strings, ints, optional scalars) suitable for Alexa+ and LLM function calling, resolving internal services via singleton factories.
* **Platform Feedback:** `FastMCP` should provide an option or parameter marker (e.g. `Depends()` or `exclude_from_schema=True`) to allow internal dependency injection without exposing internal service classes in the generated MCP JSON schema.

### [2026-10-13] - Bee CLI / `bee stream --json` Event Envelope & Utterance Timing
* **Context:** Grouping the live utterance stream into lectures/meetings (Deep Topic Event Engine) requires knowing *when* each utterance was spoken (pause and end-of-lecture detection) and which events are conversation boundaries.
* **Friction Encountered:**
  1. With `--json`, the CLI prints only the raw SSE `data` payload (`console.log(event.data)` in `sources/commands/stream/index.ts`), dropping the SSE `event:` name, so consumers cannot tell `new-utterance` from `update-location` or `new-conversation` without guessing from the payload shape.
  2. The documented `new-utterance` payload (`{"utterance": {"text", "speaker"}, "conversation_uuid"}`) carries no time field, while the REST transcript API exposes `spoken_at` / `start` (epoch ms). Timing must therefore be approximated with the local receive time, which drifts under reconnects or backlogs.
  3. The real device could not be paired yet (the CLI requires the companion app, which requires the physical device / watch), so the live payload could not be verified first-hand.
* **Workaround / Resolution:** `stream_convo.py` stamps `received_at` when each line is read (before any screening/queueing), parses `spoken_at` defensively if present, and detects conversation events structurally (`"conversation" in data`, `conversation_id` + `short_summary`) when no type field is present. The event engine uses `spoken_at > received_at > now`.
* **Platform Feedback:** Emit `{"event": "<type>", "data": {...}}` envelopes in `--json` mode (or add a `--json-envelope` flag), include `spoken_at` (and the conversation id) in `new-utterance`, and document the full SSE schema for every event type, including `update-utterance` diarization updates.

### [2026-10-13] - AWS Bedrock / `langchain_aws.BedrockEmbeddings` Credentials
* **Context:** Adding Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) for topic-continuity similarity, next to the existing `ChatBedrockConverse` models configured from Pydantic `Settings`.
* **Friction Encountered:** `BedrockEmbeddings(model_id=..., region_name=...)` raised `botocore.exceptions.NoCredentialsError` although the chat models worked: the credentials live in `.env` and are read by Pydantic Settings, not exported to `os.environ`, and the embeddings client only resolves the default boto3 chain unless keys are passed explicitly.
* **Workaround / Resolution:** `get_embedding_model()` in `src/core/models.py` passes `aws_access_key_id`, `aws_secret_access_key` and `aws_session_token` explicitly (same pattern as the chat factory), plus Titan V2 `model_kwargs={"dimensions": 512, "normalize": True}`.
* **Platform Feedback:** Align credential handling and parameter names across `ChatBedrockConverse` and `BedrockEmbeddings`, and surface the resolved credential source in the error message.

### [2026-10-13] - AWS Bedrock / Titan Text Embeddings V2 Similarity Scale (Italian & English)
* **Context:** Choosing cosine thresholds to decide whether speech after a pause continues the same lecture or starts a new one.
* **Friction Encountered:** Typical "semantic similarity" thresholds (0.75–0.8) are far off for Titan V2 on spoken Italian: single sentences of the same subject score ~0.5, unrelated subjects ~0.2; ~120-word windows score 0.43–0.68 (same event) vs. 0.23–0.36 (different event). The usable gap is only ~0.07, and there is no published guidance on score distributions per language or dimension setting.
* **Workaround / Resolution:** Built a replay & calibration tool (`scripts/replay_event_scenarios.py --calibrate`) over labelled scenarios; chose `TOPIC_SIM_SAME=0.42` / `TOPIC_SIM_DIFFERENT=0.37`, plus hysteresis (multi-window decisions, LLM tie-breaker, profile maturity) so the narrow gap does not cause flapping.
* **Platform Feedback:** Publish reference similarity distributions for Titan Text Embeddings V2 (per language and per `dimensions` setting) or a small calibration notebook in the Bedrock documentation.

### [2026-10-19] - Bee CLI / At-most-once stream & history de-duplication
* **Context:** Recovering Bee conversations spoken while EXAMEN was offline (Historical Transcript Backfill, `docs/next_steps/historical_backfill/`).
* **Friction Encountered:**
  1. `bee stream` is real-time with **at-most-once** delivery: nothing is replayed after a disconnect, and there is no `Last-Event-ID`.
  2. Live `new-utterance` payloads carry neither an utterance id nor a time, while the REST history identifies conversations by a numeric `id` (the stream uses `conversation_uuid`) and exposes two transcriptions (`realtime` and final). There is no shared key between what live analysed and what history returns.
  3. A first token-similarity de-duplication let one live sentence "explain" two neighbouring REST sentences in repetitive speech (e.g. lecture enumerations).
  4. `BeeClient.get_location` called `bee location current`, but the CLI command is `bee locations current`.
* **Workaround / Resolution:** EXAMEN now keeps a per-utterance ingest ledger (noop included) and live coverage intervals. Live rows are matched **one-to-one** against the REST *realtime* transcription (exact hash first, fuzzy second), turned into "seen" time spans, and only final-transcription utterances outside those spans are replayed, on an isolated virtual-clock Event Engine. The CLI command was fixed.
* **Platform Feedback:** Emit the REST utterance `id`, `spoken_at` and numeric `conversation_id` in `new-utterance`, support `Last-Event-ID` resume on `/v1/stream`, expose a `from`/`to` filter on `bee conversations list`, and document the conversation `state` values and when the final transcription replaces the realtime one.
