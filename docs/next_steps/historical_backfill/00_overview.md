# ⏪ Historical Transcript Backfill — Overview

> **Document Status:** Architectural Specification (not yet implemented)
> **Related specs:** [Deep Topic Event Engine](../deep_topic_event_engine/00_overview.md), [02_gatekeeper_context_and_multimodal_telemetry.md](../02_gatekeeper_context_and_multimodal_telemetry.md), [08_real_telemetry_and_bee_hardware_spec.md](../../08_real_telemetry_and_bee_hardware_spec.md)
> **Audience:** EXAMEN engineers implementing the ingestion, storage, serving and UI changes

---

## 1. Why this exists

EXAMEN analyses **only the live Bee stream** (`bee stream --json`, consumed by [stream_convo.py](../../../src/ingestion/stream_convo.py)). The official Bee documentation describes that stream as **real-time with at-most-once delivery**: events emitted while the client is disconnected are lost, and there is no replay or `Last-Event-ID` support ([docs.bee.computer/docs/realtime](https://docs.bee.computer/docs/realtime)).

Every time EXAMEN is not listening, ambient speech is never screened. Typical causes:

- the FastMCP server process (which hosts the orchestrator) is stopped, restarted or redeployed;
- the laptop or VPS sleeps, or loses network;
- the `bee stream` subprocess dies, and the exponential reconnect back-off (up to 60 s, [stream_convo.py:204](../../../src/ingestion/stream_convo.py)) leaves a hole;
- the stream silently stalls until the 330 s read timeout fires ([stream_convo.py:127](../../../src/ingestion/stream_convo.py)).

The data is **not** lost on the Bee side. Bee keeps every conversation, with a final transcript and per-utterance `spoken_at` timestamps, and exposes it through the REST API that `bee-cli` wraps. This feature uses that history to:

1. **Detect gaps** in EXAMEN's coverage (periods nobody screened).
2. **Fill them automatically** after a restart or reconnect, within a configurable look-back window (for example the last *N* days).
3. **Analyse a period on demand** from the UI, skipping whatever was already analysed live.

All of this must produce the same kind of results as live ingestion (verified actions, contacts, commitments, scheduled tasks, event dossiers). It must do so **without** waiting in real time, **without** duplicating what live already produced, and **without** corrupting the live Event Engine state.

---

## 2. Feasibility verdict

**Feasible with the current `bee-cli`, with no upstream changes.** Details are in [01_bee_history_sources.md](01_bee_history_sources.md).

| Need | Available today | Source |
|---|---|---|
| List conversations in a period | `GET /v1/conversations?limit&cursor&from=YYYY-MM-DD` (`bee conversations list --json`) | [conversations/index.ts](../../../resources/bee-cli/sources/resources/conversations/index.ts), [sync/index.ts](../../../resources/bee-cli/sources/commands/sync/index.ts) |
| Full transcript with real utterance times | `GET /v1/conversations/{id}`: `transcriptions[].utterances[]` with `spoken_at` / `start` / `end` (epoch ms), `speaker`, `id` | same |
| Bulk hydration | `POST /v1/conversations/batch {ids}` (up to 100 ids, used by `bee sync`) | [sync/index.ts](../../../resources/bee-cli/sources/commands/sync/index.ts) |
| "What changed since X" | `GET /v1/changes?cursor=v1-<ms>` (`bee changed --json`) | [changed/index.ts](../../../resources/bee-cli/sources/commands/changed/index.ts) |
| Location per conversation | `primary_location` (lat/lon/address) | conversation detail |
| Conversation titles / summaries | `short_summary`, `summary` | conversation detail |

Three constraints shape the design:

1. **No shared utterance identity between live and history.** The live `new-utterance` payload documents only `text`, `speaker` and `conversation_uuid`. It has no utterance id or time. The REST API identifies conversations by a **numeric `id`** and returns both a `realtime` and a final (non-realtime) transcription. So de-duplication cannot rely on ids and is driven by **time coverage** ([02](02_coverage_and_deduplication.md)).
2. **History is not "live".** Replayed utterances are hours or days old. Feeding them to the live `EventEngine` would trigger its wall-clock timers immediately (`now()` = `max(clock, last_seen_ts)`, [event_engine.py:456](../../../src/ingestion/event_engine.py)). Side effects that depend on "now", such as task auto-resolution, relative-time parsing and notifications, must be anchored to the utterance time ([03](03_backfill_engine.md)).
3. **Today EXAMEN does not record what it analysed.** Chunks are persisted in `session_chunks` only while a deep-topic event is open (`EventEngine._append`, [event_engine.py:1287](../../../src/ingestion/event_engine.py)), and the `noop` majority leaves no trace. A **coverage ledger** is therefore a prerequisite.

---

## 3. Core idea in one picture

```
time ──────────────────────────────────────────────────────────────────────────►
Bee history   ██ conv 812 ██   ███ conv 813 ███      ██ 814 ██   ████ conv 815 ████
EXAMEN live   [===== live coverage =====]                          [=== live ===▶
                                         ╰────── GAP (server down) ──────╯
backfill run                             [## replay 813(tail), 814, 815(head) ##]
                                          ▲ isolated EventEngine on a virtual clock
                                          ▲ gatekeeper + pipeline with timestamp = spoken_at
                                          ▲ results tagged ingest_source="backfill"
```

1. The **live orchestrator** records *coverage intervals* (stream connected and healthy) in a ledger.
2. A **gap** is any requested time span that no live or backfill interval covers.
3. The **planner** lists Bee conversations that overlap the gaps, hydrates their final transcripts and keeps only the utterances whose `spoken_at` falls in a gap.
4. The **replay executor** feeds those utterances, in chronological order and as fast as the models allow, through the same gatekeeper → pipeline path. It uses an **isolated `EventEngine` on a virtual clock**, the same technique as [scenario_replay.py](../../../src/ingestion/scenario_replay.py). When the run ends, every timer is advanced so that each event concludes and gets its final synthesis.
5. The covered span is written back to the ledger as `backfill` coverage, so re-running the same range is a no-op.

---

## 4. Goals and non-goals

**Goals**
- Automatic catch-up of gaps on startup and on stream reconnect, bounded by `BACKFILL_LOOKBACK_DAYS`.
- UI-driven analysis of an arbitrary period with a **free preview** (coverage, conversations, utterances to process, cost estimate) before any LLM call.
- Gap-only processing by default: never re-analyse what live already analysed.
- Idempotent and resumable runs: a crash mid-run resumes from a checkpoint, and re-running produces no duplicates.
- Temporal correctness: a 3-day-old "I unplugged the iron" must not complete today's routine, and "remind me tomorrow" is anchored to the day it was said.
- Live ingestion is never blocked or altered by a running backfill.

**Non-goals (this iteration)**
- Re-processing ranges that are already covered (a "force re-analysis" mode with entity reconciliation is a later extension, [05](05_implementation_plan_and_testing.md) §4).
- Reconciling live results against Bee's later, higher-quality final transcript.
- Ingesting Bee's own derived data (facts, todos, daily summaries, journals) as EXAMEN entities.
- Multi-account backfill (the app has a single paired Bee account per server).

---

## 5. Document map

| File | Content |
|---|---|
| [01_bee_history_sources.md](01_bee_history_sources.md) | What bee-cli and the Bee API expose for history, payload shapes, limits, verified vs. inferred facts, open verifications |
| [02_coverage_and_deduplication.md](02_coverage_and_deduplication.md) | Coverage ledger, gap computation, utterance selection, dedup between live and backfill, idempotency |
| [03_backfill_engine.md](03_backfill_engine.md) | Planner, replay executor, isolated Event Engine, temporal guards, triggers (startup / reconnect / manual), concurrency with live, cost controls |
| [04_data_model_api_ui.md](04_data_model_api_ui.md) | Pydantic & SQLite changes, REST endpoints, SSE events, MCP tool, Next.js UI |
| [05_implementation_plan_and_testing.md](05_implementation_plan_and_testing.md) | Phased plan, test matrix, acceptance criteria, pre-existing issues found during analysis, open questions |
| [06_phase0_device_spike.md](06_phase0_device_spike.md) | Phase 0 runbook with the physical Bee: environment, `scripts/bee_spike.py` procedure, results table (V0–V6), settings to calibrate |

---

## 6. Glossary

| Term | Meaning |
|---|---|
| **Coverage interval** | A time span `[start, end]` during which EXAMEN reliably screened everything Bee transcribed, tagged `live` or `backfill`. |
| **Gap** | A span inside a requested window that no coverage interval covers. |
| **Backfill run** | One persisted, resumable execution that fills the gaps of a window. Triggered by `startup`, `reconnect` or `manual`. |
| **Planner** | The cost-free phase of a run: lists conversations, hydrates transcripts and selects the utterances to process. It produces the *preview*. |
| **Replay executor** | The paid phase: screens and routes the selected utterances on a virtual clock. |
| **Final transcription** | The non-`realtime` transcription Bee attaches to a processed conversation. It is preferred over the `realtime` one. |
| **Ingest source** | Provenance of an entity: `live`, `backfill` or `simulator`. |
