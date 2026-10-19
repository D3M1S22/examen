# 03 — Backfill Engine: Planning, Replay, Temporal Guards & Triggers

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> Describes **how** selected history is analysed, **when** runs start, and how they coexist with live ingestion.

---

## 0. Placement

```
                      ┌───────────────────────── FastMCP server process ─────────────────────────┐
Bee stream ─► BeeClient ─► BeeStreamOrchestrator ──► gatekeeper ─► live EventEngine ─► pipeline   │
                │              │ CoverageTracker ─────┐                                            │
                │              └ utterance ledger ────┤                                            │
                │                                     ▼                                            │
                │                           ┌──────────────────┐                                   │
REST ◄── BeeHistorySource ◄── Planner ◄─────┤  BackfillService │◄── /api/backfill/* (UI, manual)   │
                                 │          │  (queue, 1 worker)│◄── startup / reconnect triggers   │
                                 ▼          └──────────────────┘                                   │
                         ReplayExecutor ─► gatekeeper ─► isolated EventEngine(VirtualClock) ─► pipeline
                                                         (ingest_source="backfill", run_id)        │
                      └──────────────────────────────────────────────────────────────────────────┘
```

New module `src/ingestion/backfill.py`:
- `BackfillService`: process singleton (`get_backfill_service()`), FIFO run queue, one worker task, run persistence and rehydration. It is started by `OrchestratorManager` next to the orchestrator ([mcp_server.py](../../../src/serving/mcp_server.py)).
- `BackfillPlanner`: pure planning over a `BeeHistorySource` ([01](01_bee_history_sources.md) §4) and the ledger ([02](02_coverage_and_deduplication.md)). No LLM calls.
- `ReplayExecutor`: runs one plan.

The LangGraph pipeline stays **stateless**, as in the AgentCore deployment model. Backfill only adds payload fields.

---

## 1. Run lifecycle

```
planned ──► fetching ──► screening/replaying ──► synthesizing ──► completed
   │            │                 │                    │
   └────────────┴──── cancelled ◄─┴──── failed / partial (resumable) ◄┘
```

| Phase | Work | LLM cost |
|---|---|---|
| `planned` | Window validated, run row created | — |
| `fetching` | Conversation list + detail, readiness, utterance selection ([02](02_coverage_and_deduplication.md) §4) | none |
| `replaying` | Gatekeeper → isolated Event Engine → pipeline, in chronological order | gatekeeper + micro-events |
| `synthesizing` | Final timer advance, segment/final syntheses of the run's events | reasoner + web search |
| `completed` | Coverage intervals committed, summary broadcast | — |

`partial` means some utterances failed after retries. Their spans are **not** committed as coverage, so the next run picks them up again.

---

## 2. Replay on a virtual clock

All utterances are known before the run starts, so nothing waits in real time. The executor re-uses the technique already proven by [scenario_replay.py](../../../src/ingestion/scenario_replay.py):

```python
engine = EventEngine(
    store=store,
    config=EngineConfig.from_settings(ignore_demo_profile=True),  # real timings: history is real time
    clock=lambda: virtual_now,                                    # driven by utterance times
    continuity=shared_continuity,                                 # same Titan V2 / heuristic backend as live
    scope=EngineScope(ingest_source="backfill", run_id=run.id),  # NEW: isolates open-event lookup
)

for conv in plan.conversations:                       # chronological
    engine.advance_to(conv.start_ts)                  # fires R1/R3/R5 deadlines between conversations
    engine.on_location(conv.primary_location, now=conv.start_ts)
    engine.on_bee_conversation("new-conversation", conv.as_event())
    engine.on_bee_conversation("update-conversation", conv.as_event())  # title + short_summary known upfront
    for u in conv.selected_utterances:
        engine.advance_to(u.ts)
        chunk = to_chunk(u, conv)                     # chunk_id = source_key, location = primary_location
        chunk.categories = screened[u.source_key]     # §3
        outcome = engine.record_chunk(chunk)
        if qualified: await dispatch(u, outcome)      # §4
engine.advance_to(last_ts + cfg.t_soft + cfg.t_hard + 2 * cfg.tick_seconds)   # conclude everything (see §7 for the live boundary)
```

- **`advance_to(ts)`** (new on `EventEngine`) jumps from deadline to deadline (`EventSnapshot.effective_deadline`) instead of ticking every 15 s. A 7-hour silence costs a handful of `tick()` calls, not 1 700.
- **`EVENT_PROFILE=demo` is ignored**: compressed demo timers would split real lectures.
- **Conversation summaries are fed before the utterances**. Live only gets them later through `update-conversation`. History has them upfront, which gives the topic profile a better prior and is the main quality *gain* of backfill over live.
- **Synthesis jobs** go to a dedicated backfill worker (concurrency 1) that runs during the replay, so segment briefings do not pile up at the end. The live worker is never used.

### 2.1 Engine isolation (required store change)

Today `get_open_event()` returns the most recent active/paused event, whoever created it ([sqlite_store.py:1375](../../../src/core/storage/sqlite_store.py)). With two engines this would let the live engine adopt a backfill event on restart, or the reverse. Changes:

- `session_dossiers.ingest_source` (`live` | `backfill` | `simulator`, default `live`) and `ingest_run_id`.
- `get_open_event(ingest_source="live", run_id=None)` and `list_events_pending_final(ingest_source=…, run_id=…)`.
- `EventEngine.rehydrate()` passes its scope. The live engine is unchanged apart from the default filter.
- Backfill events are **always concluded by the end of their run**, except for the boundary case in §7. No backfill event stays open across runs.

---

## 3. Screening history

The gatekeeper (`aclassify_chunk`, [gatekeeper.py](../../../src/ingestion/gatekeeper.py)) is reused unchanged, with three differences from live:

| Input | Live | Backfill |
|---|---|---|
| `prior_context` | Ring buffer of previous utterances + `active_event_hint()` | Own `ContextRingBuffer` (same capacity), **no event hint** (see below) |
| `active_tasks` | Tasks pending *now* | Tasks pending **at `u.ts`**: `created_at ≤ ts` and (`completed_at` is null or `> ts`) |
| Concurrency | One utterance at a time | Up to `BACKFILL_SCREEN_CONCURRENCY` (default 4) calls in flight; results are consumed **in order** |

**Why no event hint:** `active_event_hint()` depends on the engine state *after* the previous utterance. Using it would force strictly sequential screening (~1 s per utterance → ~27 min for 1 600 utterances). Without it, screening parallelises 4×. The recall loss on terse lecture sentences is already compensated inside the engine by the topic-continuity micro-windows (Milestone 4.3), which keep `noop` lecture sentences on-topic. The replay calibration test ([05](05_implementation_plan_and_testing.md) §2) must confirm that the event split is identical with and without the hint on `resources/event_scenarios.json`. If it is not, set `BACKFILL_SCREEN_WITH_EVENT_HINT=true` to fall back to sequential screening.

**Later optimisation (not v1):** *window screening*. All neighbours are known, so a single gatekeeper call can label a window of ~10 utterances (and see the *following* context, which live never has). This cuts gatekeeper calls by about 10×.

---

## 4. Pipeline dispatch & temporal guards

Qualified utterances are dispatched **sequentially in chronological order** through `agent_invocation` ([app.py](../../../src/pipeline/app.py)). Order matters: a task scheduled at 10:00 and completed at 16:00 must be created before it is resolved. Payload additions:

```jsonc
{
  "timestamp": "<spoken_at ISO>",        // already honoured by app.py and the action/social nodes
  "source_key": "bee:815:2:9001",        // idempotency (02 §5)
  "ingest_source": "backfill",
  "ingest_run_id": "<run id>",
  "event_managed": true,                 // from the isolated engine, as live
  "session_id": "<backfill event id or bee conversation id>"
}
```

`ExamenState` gains `source_key`, `ingest_source` and `ingest_run_id`. All of them have defaults, so live and AgentCore invocations are unaffected.

### 4.1 Guards ("as-of" semantics)

Every side effect that reads "now" must read the utterance time when `ingest_source="backfill"`. Several of these are latent bugs for live too, because live already carries a `timestamp`:

| Side effect | Current behaviour | Required behaviour |
|---|---|---|
| Action → task auto-resolution (`match_and_resolve_task`, [sqlite_store.py:504](../../../src/core/storage/sqlite_store.py)) | Matches **any** pending task by keyword, regardless of time | Only tasks with `created_at ≤ action.timestamp`. For recurring tasks, only when the action falls in the **current** occurrence (same local day for `daily`/`weekdays`, same ISO week for `weekly`). Otherwise the action is stored and linked for history but the task status is untouched |
| Relative time parsing in Stage 3D ([scheduler.py:271](../../../src/pipeline/nodes/scheduler.py)) | LLM path falls back to `parse_relative_time_expression(transcript)` **without** `ref_dt`, which means *now* | Always pass `ref_dt = state["timestamp"]` |
| Scheduled task already in the past at ingest time | n/a | Created with status `overdue` and a `recovered` flag; no reminder fires |
| Commitment deadlines (`social.py`) | Relative parsing | Same `ref_dt` rule |
| `created_at` of entities | `datetime.now()` | Keep `created_at = now` (audit truth) and add `occurred_at = state["timestamp"]` where missing; timelines sort by `occurred_at` |
| Contact web enrichment (`social_profiler.py`) | Runs on every new contact | Runs, but is rate-limited by `BACKFILL_ENRICH_CONTACTS_PER_RUN` (default 10); extra contacts can be enriched manually |
| Latency telemetry (`record_latency`) | `agentcore_pipeline` | `backfill_pipeline`, so live averages in `/api/status` are not skewed |

### 4.2 Notifications

The live UI toasts and pushes an Echo notification for **every** SSE event whose type contains `action`, `task`, `contact`, `topic`, … ([page.tsx](../../../src/web_ui/src/app/page.tsx)). A backfill of 2 days would flood it. Rules:
- Persistence in backfill mode emits **no per-entity broadcasts** and no engine `event_*` / `segment_*` broadcasts.
- `BackfillService` emits `backfill_started`, `backfill_progress` (throttled to 1 every 2 s) and `backfill_completed` / `backfill_failed`. The completion event carries the counters ([04](04_data_model_api_ui.md) §3). The UI revalidates every list once on completion.
- Backfill SSE type names must not contain the substrings matched by the UI router (`action`, `routine`, `task`, `contact`, `commitment`, `social`, `topic`, `briefing`, `pipeline`, `session`).

---

## 5. Persistence, resume and cancellation

- Each run is a `backfill_runs` row ([04](04_data_model_api_ui.md) §2) with a **checkpoint**: `last_source_key` and `last_ts` of the last utterance whose dispatch completed.
- The ledger row of an utterance is written **after** its dispatch completes. That row is the commit marker: on resume, utterances with a backfill ledger row are skipped (the idempotent keys of [02](02_coverage_and_deduplication.md) §5 make the at-least-once boundary harmless).
- **Resume after a crash:** `BackfillService` rehydrates runs in `fetching`/`replaying`/`synthesizing`. It re-plans the same window (cheap, REST only) and restores the isolated engine from the store (`get_open_event(ingest_source="backfill", run_id)`). It warms the ring buffer with the 4 utterances before the checkpoint, re-enqueues pending syntheses (`list_events_pending_final` scoped to the run) and continues.
- **Cancel:** stops after the in-flight utterance. Coverage is committed only for `[gap_start, last_ts]`. Events of the run are concluded, so their content so far gets a final briefing; this can be disabled with `discard_events=true`.
- **Commit:** at `completed`, one `backfill` coverage interval per processed gap, clipped to the processed prefix if `partial`.

---

## 6. Triggers

| Trigger | When | Window | Defaults |
|---|---|---|---|
| **Startup catch-up** | `BACKFILL_STARTUP_DELAY_SECONDS` (60) after the first live interval opens, so live is stable first | `[max(last coverage end, now − BACKFILL_LOOKBACK_DAYS), start of the current live interval]` | `BACKFILL_AUTO_ON_STARTUP=true`, `BACKFILL_LOOKBACK_DAYS=2` |
| **First run ever** (no coverage rows) | Same | `now − BACKFILL_FIRST_RUN_DAYS` | `BACKFILL_FIRST_RUN_DAYS=0` (disabled): never analyse a whole account history by surprise |
| **Reconnect** | `CoverageTracker` closes an interval and the next opens after a hole ≥ `BACKFILL_MIN_GAP_SECONDS` (60) | `[previous end, new start]` | Debounced: holes within `BACKFILL_RECONNECT_DEBOUNCE_SECONDS` (600) are coalesced, and the run starts `BACKFILL_RECONNECT_DELAY_SECONDS` (900) later, giving Bee time to finalise transcripts |
| **Deferred re-check** | Every 15 min while deferred conversations exist | Only the deferred conversations | Give up after 24 h (`deferred_expired`, visible in the UI) |
| **Manual** | `POST /api/backfill/runs` from the UI | Any `[from, to]` with `to ≤ start of the current live interval` (or `≤ now` when live is down) | `BACKFILL_MAX_WINDOW_DAYS=14` |

- The upper bound of every window is **frozen at run creation**. Live owns everything after it, so the two never process the same time.
- Queue policy: one run at a time; manual runs jump ahead of queued automatic runs; overlapping queued automatic windows are merged.
- `BACKFILL_ENABLED=false` disables everything (REST returns 404, no triggers).

---

## 7. Boundaries with live: hand-over and stitching

Two situations put one real-world event on both sides of a gap.

**S1: the server stops in the middle of a lecture (hand-over).** On restart the live engine rehydrates the still-open live event ([event_engine.py:460](../../../src/ingestion/event_engine.py)). Its wall-clock `now()` is already past `T_hard`, so the next tick hard-closes the event on half its content, while the rest of the lecture sits in the gap.
- When startup catch-up is enabled and a gap exists, the startup sequence calls `live_engine.release_open_event(to_run=run.id)` **before** the live runtime ticks. The release sets `ingest_source="backfill"` and `ingest_run_id` on the open event. The backfill engine adopts it, replays the gap into it and concludes it normally. The live engine starts clean.
- When auto-backfill is disabled, behaviour stays as today.

**S2: the lecture continues after the gap, into live (stitching).** Before the final `advance_to` (end of §2), the executor checks the run's last event `E_b` against the first live event `E_l` after the window:
- if `E_l.start − E_b.last_on_topic_at ≤ T_hard` **and** topic similarity ≥ the resume threshold of the continuity backend, call the existing `EventEngine.merge([E_l, E_b])` on the **live** engine, keeping `E_l` (open) as the survivor. The merged event's final briefing is invalidated and regenerated when live concludes it;
- otherwise `E_b` is concluded as usual.

Both decisions are logged as `EventTransitionLog` entries (`rule="B1"` hand-over, `rule="B2"` stitch) so they appear in the Events timeline audit trail.

---

## 8. Cost and throughput

Reference numbers come from [the live benchmark](../../../README.md) (gatekeeper ~0.95 s, pipeline ~3.5 s, ~$0.04 per day of continuous wear on `nvidia.nemotron-super-3-120b`).

| Window | Utterances (≈) | Gatekeeper @4× | Qualified (~10 %) pipeline, sequential | Syntheses | Wall time (≈) |
|---|---|---|---|---|---|
| 1 h reconnect gap | 400 | ~2 min | 40 × 3.5 s ≈ 2.5 min | 0–1 event | ~5 min |
| 1 day | 4 000 | ~16 min | 400 × 3.5 s ≈ 23 min | 2–4 events | ~45 min |
| 7 days | 28 000 | ~2 h | ~2.7 h | 10–25 events | ~5 h |

Guards:
- `BACKFILL_MAX_UTTERANCES_PER_RUN` (default 20 000) and `BACKFILL_MAX_ESTIMATED_COST_USD` (default 1.00). A manual run above either limit needs `confirm_over_budget=true`. An automatic run above either limit is reduced to the most recent part of the window, and the rest is reported as an uncovered gap.
- Bedrock throttling errors use exponential back-off. After `max_job_attempts` the utterance is `failed`, and the run ends `partial`.
- Live keeps priority: while the live orchestrator is dispatching a pipeline, backfill dispatch waits (shared `asyncio.Event` "live busy"). Screening concurrency drops to 1 while a live event is `active`.
