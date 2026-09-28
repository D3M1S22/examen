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
