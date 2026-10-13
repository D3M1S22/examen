# 05 — Ingestion & Pipeline Integration

> Part of the [Deep Topic Event Engine](00_overview.md) specification.
> Describes **where** the engine lives and **what changes** in the existing ingestion bridge and LangGraph pipeline.

---

## 0. Placement

```
Bee stream ─► BeeClient (stream_convo.py) ─► BeeStreamOrchestrator (orchestrator.py)
                                                 │
                                                 ├─ ring buffer + gatekeeper (unchanged)
                                                 ├─ EventEngine  ◄── NEW (evolves SessionManager)
                                                 │     ├─ decide() state machine        (doc 01)
                                                 │     ├─ TopicSimilarity backend       (doc 02)
                                                 │     └─ SynthesisJobQueue             (doc 03)
                                                 └─ pipeline dispatch (micro-events only when event-managed)
/api/simulate ─────────────────────────────────────► same EventEngine singleton
```

- The engine is **stateful** and lives in the ingestion bridge. Locally that is the FastMCP server process, because `OrchestratorManager` runs the orchestrator as a background task in [mcp_server.py](../../../src/serving/mcp_server.py). The LangGraph pipeline stays **stateless**, so the AgentCore deployment model is preserved.
- `SessionManager` ([session_manager.py](../../../src/ingestion/session_manager.py)) is evolved into `EventEngine`. The boundary helpers (`is_closing_phrase`, `calculate_haversine_distance`, `check_location_shift`) are kept and extended. A module-level `get_event_engine()` singleton is shared by the orchestrator **and** `/api/simulate`. Today they do not share anything (audit finding #11).

---

## 1. Timestamps: use utterance time, not processing time

Every time-based rule (R1, R3, R5) is meaningless if it measures pipeline latency (audit finding #6).

**Best-known utterance time**, in priority order:

1. `spoken_at` from the Bee payload, **if present**. The documented `new-utterance` payload has no time fields ([Bee realtime docs](https://docs.bee.computer/docs/realtime)), but the REST transcript API exposes `spoken_at` / `start` in epoch ms ([conversations/index.ts](../../../resources/bee-cli/sources/resources/conversations/index.ts)). Parse it defensively in case the live stream carries it.
2. `received_at`: wall-clock time captured **in `BeeClient.stream_events`** at the moment the line is read from the `bee stream --json` subprocess. This is before the gatekeeper and before any queueing.
3. `datetime.now()` as a last resort (simulate API without an explicit timestamp).

Propagation changes:

| Step | File | Change |
|---|---|---|
| Capture | [stream_convo.py:129-139](../../../src/ingestion/stream_convo.py) | Add `received_at` (and `spoken_at` if found in `utt`/`data`) to the yielded `data` |
| Chunk | [orchestrator.py:163](../../../src/ingestion/orchestrator.py) | `UtteranceChunk(timestamp=best_time, received_at=..., spoken_at=...)` |
| Engine | `record_chunk(...)` | Receives `chunk.timestamp`, never `time.time()` |
| Pipeline | [orchestrator.py:220-231](../../../src/ingestion/orchestrator.py) | Add `"timestamp": chunk.timestamp` to the payload; [app.py:144](../../../src/pipeline/app.py) already honours it, and `action_state.py` / `social.py` already ground on `state["timestamp"]` |
| Tick | `EventEngine.tick(now)` | `now` = max(last chunk time, wall clock), so a silent stream still advances time |

**Optional backfill (later):** for completed Bee conversations, `bee conversations transcript <id> --since <epochMs>` returns authoritative `spoken_at` values that can correct chunk times after the fact. It is not required for the engine to work.

---

## 2. Orchestrator changes ([orchestrator.py](../../../src/ingestion/orchestrator.py))

### 2.1 Per-utterance flow (new)

```
process_incoming_utterance(utt):
    chunk = buffer_incoming_utterance(utt)                       # unchanged + timestamps
    classification = await aclassify_chunk(chunk.text,
                         prior_context=rolling_hint + engine.active_event_hint())   # doc 02 §3
    chunk.categories = classification.categories
    transitions = await engine.record_chunk(chunk)               # appends to session_chunks, runs decide()
    event_id = engine.current_event_id()                         # may be None

    if is_noop(classification):
        return
    payload = {..., "session_id": event_id or chunk.conversation_uuid,
               "timestamp": chunk.timestamp,
               "event_managed": event_id is not None}
    await asyncio.to_thread(agent_invocation, payload)           # NOTE: currently called synchronously
```

- **Blocking call fix:** `agent_invocation` is synchronous and is currently called directly inside an `async def` ([orchestrator.py:233-235](../../../src/ingestion/orchestrator.py)). Inside the server process this blocks the event loop, including SSE and REST, for the whole pipeline run. Wrap it in `asyncio.to_thread`.
- **Ordering:** `record_chunk` runs **before** the pipeline so that a chunk that opens an event (R0) is already event-managed when the pipeline persists its micro-events.

### 2.2 Tick loop

Replace the legacy `timeout_monitor` (which only flushes the dead 5000-char buffer) with:

```python
async def event_tick_loop(self):
    while True:
        await asyncio.sleep(settings.event_tick_seconds)
        await self.engine.tick(now=self.engine.clock())
```

- `tick` evaluates R1/R3/R5 for the open event and drains nothing itself; synthesis jobs go to the `SynthesisJobQueue` worker.
- On startup, the engine **rehydrates** from the store: it loads the open event (`get_open_event()`) and re-enqueues `closed`-but-not-synthesized segments (doc 03 §5).

### 2.3 Remove the legacy buffer path

`text_buffer`, `flush_to_model`, `_evaluate_buffer_limit`, `analyze_text_model`, `response_worker` and the 5-minute `timeout_monitor` ([orchestrator.py:256-328](../../../src/ingestion/orchestrator.py)) only send concatenated text to the gatekeeper and print the result. They are superseded by the engine and should be deleted, together with their tests in `tests/test_ingestion_orchestrator.py`, after confirming that no other caller depends on them.

### 2.4 Bee conversation lifecycle events

[stream_convo.py](../../../src/ingestion/stream_convo.py) currently drops `new-conversation`, `update-conversation` and `update-conversation-summary`. Forward them:

| Event | Engine use |
|---|---|
| `new-conversation` | Record uuid; if the event is `PAUSED`, apply the weak split bias (doc 02 §4) |
| `update-conversation` (`title`, `short_summary`) | Append to `topic_profile.bee_titles`; candidate event title |
| `update-conversation-summary` | Same as above |

> **Open verification:** with `bee stream --json` the CLI prints only the raw SSE `data` without the event name ([stream/index.ts:349-351](../../../resources/bee-cli/sources/commands/stream/index.ts)), while `stream_convo.py` dispatches on `data["type"] or data["event"]`. A teammate confirmed that utterances arrive, so the live payload evidently carries a type field. Capture real samples of the conversation events before relying on them, and fall back to structural detection (`"utterance" in data`, `"conversation" in data`) if needed.

---

## 3. LangGraph pipeline changes

### 3.1 Routing ([graph.py](../../../src/pipeline/graph.py))

```python
if "deep_topic" in categories and not state.get("event_managed"):
    targets.append("topic_research")          # standalone behaviour, unchanged
```

- When `event_managed` is true, `deep_topic` **does not** trigger research. Its content already lives in the event's chunk log, and the engine schedules synthesis.
- `action`, `social` and `scheduled_task` still fan out immediately (micro-events are instantaneous by design, doc 03 of Milestone 3.2).
- If a chunk is *only* `deep_topic` and event-managed, `route_categories` returns `[END]`, so no pipeline cost is spent.
- Add `event_managed: bool` to `ExamenState` ([schemas.py](../../../src/core/schemas.py)) and map it from the payload in [app.py](../../../src/pipeline/app.py).

### 3.2 Persistence ([persist.py](../../../src/pipeline/nodes/persist.py))

- **Remove** the `conclude_session_dossier` call after saving a briefing ([persist.py:79-80](../../../src/pipeline/nodes/persist.py)). Concluding is the engine's job (audit finding #2).
- Standalone briefings are saved with `kind="standalone"` and `session_id` (if any).
- Micro-event linking is unchanged; `session_id` now refers to the event id.

### 3.3 Synthesis entry point

Add a second invocation mode to `agent_invocation` ([app.py](../../../src/pipeline/app.py)):

```python
if payload.get("mode") == "synthesis":
    return run_synthesis_job(kind=payload["kind"], session_id=payload["session_id"],
                             segment_id=payload.get("segment_id"))
```

Locally the `SynthesisJobQueue` can call `run_synthesis_job` directly; in AgentCore mode it sends this payload. This keeps the cloud split described in doc 03 §5.

---

## 4. `/api/simulate` ([mcp_server.py:1154](../../../src/serving/mcp_server.py))

Extended request body (all optional, backward compatible):

```json
{
  "transcript_chunk": "…",
  "actor_id": "user_web_sim",
  "event_mode": true,                 // route through the EventEngine (default: true when the UI simulator sends it)
  "timestamp": "2026-10-13T10:05:00", // virtual time for demos / replays
  "location": {"latitude": 45.06, "longitude": 7.66, "place_name": "Politecnico, Aula 7"},
  "speaker_role": "contact"
}
```

- With `event_mode` the endpoint calls `engine.record_chunk` on the shared singleton, then the pipeline with `event_managed`. The response includes `{"event": {id, status, segment_index, last_transition}}` so the simulator can show what happened.
- Without `event_mode`, today's behaviour is preserved (standalone briefing, fresh session).
- A **virtual clock** (`engine.clock = VirtualClock()`) is enabled when `EVENT_PROFILE=demo` or when requests carry `timestamp`. Ticks then use the latest virtual time, so a whole lecture with a break can be replayed in seconds (doc 07).

---

## 5. Other entry points

| Entry point | Behaviour |
|---|---|
| `scripts/live_tester.py` | Add `--event-mode` flag and `/tick <seconds>` / `/conclude` commands that drive the shared engine with a virtual clock |
| `scripts/simulate_mock_conversations.py` | Replace its direct `session_manager.record_chunk` usage with the engine; honour per-turn `offset_seconds` (doc 07) |
| AgentCore direct invocation / Alexa | Unchanged: no engine, standalone briefings |
