# 🧠 Deep Topic Event Engine — Overview

> **Document Status:** Implemented 2026-10-13 (Phase 4 completed; verification and tests in [07](07_implementation_plan_and_testing.md))
> **Supersedes / extends:** [03_session_merging_and_micro_event_splitting.md](../03_session_merging_and_micro_event_splitting.md) (Milestone 3.2)
> **Related specs:** [01_deep_topic_contextual_synthesis.md](../01_deep_topic_contextual_synthesis.md), [02_gatekeeper_context_and_multimodal_telemetry.md](../02_gatekeeper_context_and_multimodal_telemetry.md)
> **Audience:** EXAMEN engineers implementing the ingestion, pipeline, storage and UI changes

---

## 1. Why this exists

A university lecture, a 45-minute design review or a conference talk is **one continuous event** for the user, but EXAMEN receives it as hundreds of short Bee utterances. The system must decide, continuously and without user input:

1. **Which utterances belong to the same event** (aggregation).
2. **When an event pauses** (coffee break, off-topic chatter) and **when it resumes**.
3. **When an event is really over**, including the hard case of **two different lectures back-to-back in the same building**, a few minutes apart.
4. **When to spend money on web research and synthesis**: not on every utterance (too expensive, fragmented), and not only after a 2-hour timeout (too late to be useful).

Milestone 3.2 introduced the building blocks (`SessionManager`, `SessionDossier`, boundary detectors, holistic synthesis), but they are **not wired together** for `deep_topic`. This folder specifies the engine that closes that gap.

---

## 2. Current state audit (as of 2026-10-13, branch `main`)

| # | Finding | Location | Effect |
|---|---|---|---|
| 1 | `deep_topic` is routed straight to `topic_research` for **every** qualified utterance; no session awareness | [graph.py:39-40](../../../src/pipeline/graph.py), [orchestrator.py:233-235](../../../src/ingestion/orchestrator.py) | A 45-min lecture yields dozens of fragmented briefings and dozens of web searches |
| 2 | `node_persist` **concludes the session** as soon as any briefing is saved, and keeps overwriting `final_briefing_id` | [persist.py:79-80](../../../src/pipeline/nodes/persist.py) | The first `deep_topic` utterance "closes" the lecture; the final link points to the last fragment |
| 3 | Boundary detection only sets `status="finalizing"`; nobody reacts to it | [orchestrator.py:190-191](../../../src/ingestion/orchestrator.py), [session_manager.py:157-159](../../../src/ingestion/session_manager.py) | Holistic synthesis never runs automatically |
| 4 | `synthesize_session_dossier()` is only reachable via manual `POST /api/sessions/{id}/conclude` | [mcp_server.py:1140](../../../src/serving/mcp_server.py) | — |
| 5 | `check_inactivity_timeouts()` is never called | [session_manager.py:169](../../../src/ingestion/session_manager.py) | A session that goes silent never closes (inactivity is only evaluated when a *new* chunk arrives) |
| 6 | Inactivity uses processing time (`time.time()`), not utterance time | [session_manager.py:135](../../../src/ingestion/session_manager.py), [orchestrator.py:185](../../../src/ingestion/orchestrator.py) | Gaps measure pipeline latency, not real silence |
| 7 | `append_chunk_to_session` appends to `concluded` dossiers without reopening them | [sqlite_store.py:1250-1274](../../../src/core/storage/sqlite_store.py) | Status and content diverge |
| 8 | `key_discussion_points` is never written | — | No evolving outline |
| 9 | Session identity = Bee `conversation_uuid` | [orchestrator.py:153](../../../src/ingestion/orchestrator.py) | Bee's own silence-based splitting decides our event boundaries |
| 10 | Legacy 5000-char / 5-minute buffer only runs the gatekeeper and prints | [orchestrator.py:256-328](../../../src/ingestion/orchestrator.py) | Dead path, confusing |
| 11 | `/api/simulate` creates a fresh random `session_id` on every call | [app.py:118-119](../../../src/pipeline/app.py) | Multi-chunk events cannot be simulated from the UI |
| 12 | Transcript chunks are stored as a single JSON blob rewritten on every utterance | [sqlite_store.py](../../../src/core/storage/sqlite_store.py) (`transcript_chunks_json`) | O(n²) writes over a 2-hour lecture; no per-chunk metadata (time, category, speaker) |

---

## 3. Core idea in one picture

```
EVENT  "Analysis I lecture — limits & derivatives"   (10:02 → 11:58)
 ├─ Segment 1   10:02–10:51  ──► segment briefing (research + synthesis)
 │      (break 10:51–11:06: chatter, coffee → ignored for topic, micro-events still linked)
 ├─ Segment 2   11:06–11:58  ──► segment briefing
 └─ Final close (hard)        ──► consolidated event briefing (merges segments, reuses research)
 + linked micro-events: actions, contacts, scheduled tasks, commitments
```

Two different closing decisions:

| Decision | Trigger (summary) | Consequence | Reversible? |
|---|---|---|---|
| **Soft close → `PAUSED`** | No on-topic content for `T_soft` (≈4–5 min), explicit pause cue, or periodic checkpoint | Synthesize the **segment** now | ✅ Yes: event can **resume** |
| **Hard close → `CONCLUDED`** | Pause lasts `T_hard` (≈30 min), GPS displacement, or a **different-topic** event starts | Synthesize the **whole event** | ❌ No (manual merge only) |

Signals are combined with distinct roles:

- **Time**: the main driver of soft/hard closing.
- **GPS**: a one-directional veto. Moving away closes the event; staying put proves nothing.
- **Topic similarity**: the only signal that can split two consecutive lectures in the same place.
- **Explicit cues & Bee conversation events**: additional evidence that shifts the decision.

---

## 4. Goals and non-goals

**Goals**
- One coherent event dossier per lecture/meeting, with progressive (segment) briefings available within minutes of a break.
- Correct split between consecutive, different-topic events in the same location.
- Correct merge of an event interrupted by a break.
- Bounded cost: research runs per segment/checkpoint/final, not per utterance.
- Deterministic, unit-testable decision logic with an injectable clock.
- Backward compatibility: standalone invocations (AgentCore console, Alexa, single `/api/simulate` calls without a session) keep working.

**Non-goals (for this iteration)**
- Speaker-identity–based event detection (Bee speaker labels are per-conversation and unreliable for this).
- Multi-user / shared events.
- Fully automatic retroactive re-segmentation of long-concluded events (manual split/merge is provided instead).

---

## 5. Document map

| File | Content |
|---|---|
| [01_event_model_and_state_machine.md](01_event_model_and_state_machine.md) | Event / Segment / Chunk hierarchy, lifecycle states, transition rules, signal fusion, configuration |
| [02_topic_continuity_detection.md](02_topic_continuity_detection.md) | Topic profile, micro-windows, pending-window hysteresis, similarity backends (embeddings / LLM judge / heuristic) |
| [03_synthesis_scheduling.md](03_synthesis_scheduling.md) | Segment, checkpoint and final synthesis; research reuse and caching; cost model |
| [04_data_model_and_storage.md](04_data_model_and_storage.md) | Pydantic schema changes, SQLite migrations, store API |
| [05_ingestion_and_pipeline_integration.md](05_ingestion_and_pipeline_integration.md) | Timestamps, orchestrator tick loop, graph routing, persist changes, Bee conversation events, simulate API |
| [06_serving_and_ui.md](06_serving_and_ui.md) | REST, SSE, MCP tools, Echo Show card, Next.js views |
| [07_implementation_plan_and_testing.md](07_implementation_plan_and_testing.md) | Phased plan, test scenarios, acceptance criteria, open questions |

---

## 6. Glossary

| Term | Meaning |
|---|---|
| **Utterance** | One Bee `new-utterance` payload (typically a sentence). Unit of ingestion. |
| **Chunk** | An utterance after enrichment (timestamp, speaker, location, gatekeeper categories). Stored per row. |
| **Micro-window** | A small group of consecutive chunks (≈3 chunks / ≈60–150 words) used as the unit of topic comparison. |
| **Segment** | A contiguous run of on-topic activity inside an event, delimited by pauses or checkpoints. Gets its own briefing. |
| **Event** | The macro unit (lecture, meeting, talk). Persisted as an evolved `SessionDossier`. Spans one or more Bee conversations. |
| **Topic profile** | Rolling representation of what the event is about (embedding centroid + keywords + segment titles). |
| **On-topic activity** | A chunk that is `deep_topic` *or* sufficiently similar to the active topic profile. Resets the pause timer. |
| **Soft close / Hard close** | Pause (segment synthesis, resumable) vs. conclusion (final synthesis). |
