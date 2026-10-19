# 05 — Implementation Plan, Tests & Acceptance Criteria

> Part of the [Historical Transcript Backfill](00_overview.md) specification.

---

## 0. Implementation status (2026-10-19, branch `feature/historical-backfill`)

| Phase | Status | Code | Tests |
|---|---|---|---|
| 0 Verification spike | ✅ **Done 2026-10-19** (Apple Watch capture). Results and follow-ups I1–I8: [06_phase0_device_spike.md](06_phase0_device_spike.md) §5 | [bee_spike.py](../../../scripts/bee_spike.py) | — |
| 1 Coverage & ledger | ✅ Implemented | [coverage.py](../../../src/ingestion/coverage.py), [orchestrator.py](../../../src/ingestion/orchestrator.py), [stream_convo.py](../../../src/ingestion/stream_convo.py), [sqlite_store.py](../../../src/core/storage/sqlite_store.py) | `tests/test_backfill.py` (T-COV) |
| 2 History source & planner | ✅ Implemented (CLI transport) | [bee_history.py](../../../src/ingestion/bee_history.py), [backfill.py](../../../src/ingestion/backfill.py) `BackfillPlanner` | T-DED, T-RDY |
| 3 Replay executor | ✅ Implemented | `ReplayExecutor`, [event_engine.py](../../../src/ingestion/event_engine.py) (`ingest_source`/`run_id` scope, `advance_to`, `release_open_event`, `log_transition`), [persist.py](../../../src/pipeline/nodes/persist.py), [time_utils.py](../../../src/core/time_utils.py) | T-ISO, T-IDEM, T-TMP, T-CAN |
| 4 Automatic triggers | ✅ Implemented | `BackfillService` (startup hand-over B1, reconnect debounce, deferred re-check, stitching B2, budget trim), [mcp_server.py](../../../src/serving/mcp_server.py) wiring | T-BND, T-TRG, T-BUD |
| 5 UI | ✅ Implemented | `BackfillModal`, `RecoveredBadge`, Overview *History Sync* card, Status Dock ⏪ item, SSE `backfill_*` branch in `page.tsx`, [backfill.ts](../../../src/web_ui/src/utils/backfill.ts); MCP tool `get_ingestion_coverage` ([ingestion_tools.py](../../../src/serving/tools/ingestion_tools.py)) | `tests/test_backfill_api.py`, `src/web_ui/src/utils/backfill.test.ts` |
| 6 Optimisations | ⏳ Not started | — | — |

### 0.1 Deviations from the specification

| Spec | Implementation | Reason |
|---|---|---|
| Temporal guard on `match_and_resolve_task` for every action (03 §4.1) | Applied to **backfill** actions only, plus a guard in `node_persist` on a `matched_task_id` pre-set by the action node | Live actions are spoken "now": the guard would only change live behaviour (and existing tests) without benefit |
| `occurred_at` on actions and tasks (04 §1.2) | Not added. `VerifiedAction.timestamp` already holds the spoken time; backfilled tasks get `created_at = spoken time` | Avoids a redundant column |
| Provenance on contacts and briefings | Only `verified_actions`, `planned_tasks` and `session_dossiers` carry `ingest_source`/`ingest_run_id` | Briefings belong to events (which carry it); contacts are merged by name across sources |
| `backfill_runs` with one column per field (04 §2) | Indexed columns + `payload_json` (the whole `BackfillRun`) | Schema evolution without migrations |
| `422` when the window ends after the live connection started (04 §3) | The end is **clamped** to the live start, with a warning in the plan; `422 window_covered_by_live` only if nothing remains | Presets like "last 24 h" work without the UI computing the bound |
| Matching rule "realtime utterance matched → span" (02 §4) | **One-to-one** assignment (exact hash first, then fuzzy on unused rows) and **midpoint** overlap for final utterances | Repetitive speech let one live row explain two neighbouring sentences (caught by T-DED-5) |
| `BACKFILL_ENRICH_CONTACTS_PER_RUN` cap (03 §4.1) | Setting exists, not enforced: contact web enrichment runs as on live | Enrichment lives inside the social node; contacts are rare in practice |
| `discard_events` on cancel (03 §5) | Not implemented: events of a cancelled run are always concluded | Low value for v1 |
| Live priority (03 §8) | Backfill dispatch waits while a live pipeline call is in flight; screening concurrency is not reduced | Simpler; live screening is a single call per utterance |
| System Bar badge (04 §4.1) | ⏪ item in the left **Status Dock** (where the BEE/SSE badges actually live) | Matches the current dashboard layout |

Additional settings introduced by the implementation: `BACKFILL_LOOKBACK_MARGIN_HOURS` (list paging margin, 6 h), `BACKFILL_HISTORY_CONCURRENCY` (4), and the estimate cost model `BACKFILL_COST_PER_GATEKEEPER_CALL` / `BACKFILL_COST_PER_PIPELINE_CALL` / `BACKFILL_COST_PER_EVENT`.

---

## 1. Phased plan

Each phase ships on its own and leaves the suite green (`.venv/bin/pytest tests/ -v`).

### Phase 0: Verification spike (½ day, device required)
- Answer V1–V6 of [01](01_bee_history_sources.md) §6 with the physical Bee. Save anonymised samples to `tests/fixtures/bee_history/` (one fully live conversation, one with a mid-way outage, one with a delayed upload, one still `processing`).
- Record findings in [FRICTION_LOG.md](../../../FRICTION_LOG.md).
- **Exit:** the match window (`BACKFILL_MATCH_WINDOW_SECONDS`) and readiness rule are calibrated, and the id-mapping strategy is chosen (uuid in detail → exact; otherwise time + text).

### Phase 1: Coverage & ledger foundations (no backfill yet)
1. Schemas, migrations and store API for `ingest_coverage`, `ingest_ledger` and `bee_conversation_map` ([04](04_data_model_api_ui.md) §1–2).
2. `CoverageTracker` in `BeeStreamOrchestrator`: open/extend/close on stream lifecycle, 30 s flush ([02](02_coverage_and_deduplication.md) §2.1).
3. Ledger write in `process_incoming_utterance` for **every** utterance, `noop` included, with the gatekeeper/pipeline status.
4. Persist uuid ↔ id from `new-conversation`.
5. `GET /api/backfill/coverage` and the `coverage_gap_detected` SSE event.
6. Idempotency keys: `source_key` in the payload and `ExamenState`; deterministic action/task ids. This also fixes live duplicates on stream re-delivery.
- **Exit:** after a server restart the API reports the outage as a gap.

### Phase 2: History source & planner (preview only)
1. `BeeHistorySource` + `CliBeeHistorySource` + `FixtureBeeHistorySource` ([01](01_bee_history_sources.md) §4).
2. `BackfillPlanner`: readiness, final-vs-realtime transcription choice, selection algorithm, estimate ([02](02_coverage_and_deduplication.md) §4).
3. `POST /api/backfill/preview`.
- **Exit:** a preview on real data shows plausible duplicate/selected counts, and no LLM calls are made.

### Phase 3: Replay executor
1. `EventEngine` scope (`ingest_source`, `run_id`), `advance_to()`, `release_open_event()`, store filter changes ([03](03_backfill_engine.md) §2.1, §7).
2. `ReplayExecutor`: screening with ordered concurrency, sequential dispatch, dedicated synthesis worker.
3. Temporal guards ([03](03_backfill_engine.md) §4.1): `match_and_resolve_task` guard, `ref_dt` fix in `scheduler.py`, `overdue` + `recovered` tasks, `occurred_at`, telemetry event type.
4. Notification suppression and backfill SSE events.
5. `BackfillService`: queue, runs table, checkpoint/resume, cancel, coverage commit.
6. `POST/GET /api/backfill/runs[/{id}[/cancel]]`.
- **Exit:** a manual run over a fixture outage produces the same entities as live replay of the same transcript (§2, T-EQ), and a second run produces nothing new.

### Phase 4: Automatic triggers
1. Startup catch-up with hand-over (S1), reconnect catch-up with debounce/delay, deferred re-check ([03](03_backfill_engine.md) §6–7).
2. Boundary stitching (S2).
3. Budget guards and live-priority gating.
- **Exit:** killing the server for 20 minutes during a replayed lecture yields **one** event with a correct final briefing after restart.

### Phase 5: UI
1. Types, `BackfillModal`, Overview Hub card, System Bar badge, `⏪ Recovered` badges, SSE branch in `page.tsx` ([04](04_data_model_api_ui.md) §4).
2. Optional MCP tool `get_ingestion_coverage` + Echo Show card.
- **Exit:** a user can pick *Last 3 days → Preview → Run* and watch progress without any toast flood.

### Phase 6: Optimisations (optional)
- `ProxyBeeHistorySource` (batch + `from`).
- Window screening (10 utterances per gatekeeper call, with look-ahead context).
- Changefeed-driven reconciliation of conversations that received their final transcript after a run used the realtime fallback.

---

## 2. Test matrix

| ID | File | Scenario | Expectation |
|---|---|---|---|
| T-COV-1 | `tests/test_coverage.py` | Interval open → heartbeats → timeout | Interval ends at the last heartbeat, not at the timeout |
| T-COV-2 | same | Crash without close | `end` = last flush; gap reported on next start |
| T-COV-3 | same | Gap computation with overlapping live/backfill intervals | Exact set difference; `MIN_GAP` applied to auto-triggers only |
| T-DED-1 | `tests/test_backfill_planner.py` | Fully live conversation (fixture) | 0 selected |
| T-DED-2 | same | Outage in the middle of a conversation | Only the tail is selected; boundary utterance not duplicated |
| T-DED-3 | same | Delayed upload inside a live interval | All its utterances selected |
| T-DED-4 | same | No realtime transcription | Fuzzy path; threshold respected |
| T-DED-5 | same | Failed live utterances + `retry_failed_live` | Included; result replaces the `failed` ledger row |
| T-RDY-1 | same | `state=processing`, `end_time=null` | Deferred, not selected |
| T-RDY-2 | same | Ended > grace, only realtime transcription | Realtime fallback used, warning in plan |
| T-ISO-1 | `tests/test_backfill_executor.py` | Live event open while a backfill run replays another event | Live `current_event()` unchanged; `get_open_event()` never returns the backfill event |
| T-ISO-2 | same | `EVENT_PROFILE=demo` | Backfill engine still uses real timings |
| T-EQ | same | Same scenario from `resources/event_scenarios.json` fed (a) through `replay_scenario` and (b) as a backfill fixture | Same number of events and segments |
| T-HINT | same | Event split with vs without event hint on all scenarios | Identical, otherwise the default flips ([03](03_backfill_engine.md) §3) |
| T-TMP-1 | `tests/test_backfill_temporal.py` | Historical "I unplugged the iron" (3 days ago), daily task pending today | Action stored, task **not** completed |
| T-TMP-2 | same | Historical "remind me tomorrow at 3 pm" | `scheduled_time` = spoken day + 1 at 15:00; `overdue` + `recovered` if already past |
| T-TMP-3 | same | Task created *after* the historical action | Not matched |
| T-IDEM-1 | same | Run the same window twice | Second plan selects 0; entity counts unchanged |
| T-IDEM-2 | same | Kill the executor mid-run, resume | No duplicates; events concluded once; checkpoint respected |
| T-CAN-1 | same | Cancel mid-run | Coverage committed only up to `last_ts`; next run covers the rest |
| T-BND-1 | `tests/test_backfill_triggers.py` | Startup with an open live event and a gap (S1) | Event handed over, one final briefing, `rule=B1` logged |
| T-BND-2 | same | Lecture continues from the gap into live (S2) | Merged into the live event, `rule=B2` logged |
| T-TRG-1 | same | Two reconnect holes 5 min apart | One coalesced run, delayed by `RECONNECT_DELAY` |
| T-TRG-2 | same | First run ever with `FIRST_RUN_DAYS=0` | No run |
| T-BUD-1 | same | Plan over budget, manual without confirm | `422 over_budget`; with confirm → `202` |
| T-API-1 | `tests/test_mcp_server.py` | All `/api/backfill/*` routes, SSE event names | Contracts of [04](04_data_model_api_ui.md) §3; no name contains a UI router substring |
| T-UI-1 | `src/web_ui` (bun test) | Coverage strip bucketing, preview gating, progress reducer | Pure-function unit tests, same style as `dossierExport.test.ts` |

All executor tests use `FixtureBeeHistorySource`, the heuristic similarity backend and a fake synthesizer (as in `tests/test_event_synthesis.py`). No network, no Bedrock.

---

## 3. Acceptance criteria

1. After any outage of ≥ 1 minute within `BACKFILL_LOOKBACK_DAYS`, the uncovered time reported by `/api/backfill/coverage` drops to **0** within `RECONNECT_DELAY + run duration`, except for deferred conversations, which are listed.
2. No entity (action, task, contact, commitment, briefing) is produced twice for the same spoken sentence across live and backfill.
3. Backfilled micro-events carry `occurred_at` = spoken time, `ingest_source="backfill"`, and never change the *current* status of recurring routines.
4. Live ingestion latency (`/api/status` rolling average) is unaffected by a running backfill (±10 %).
5. A manual 3-day preview completes in < 30 s on the CLI transport and performs no LLM call.
6. The UI shows a single progress indicator and one completion toast per run.

---

## 4. Future extension: "force re-analysis" mode

Re-processing already covered ranges (for example after a prompt upgrade) needs entity reconciliation: retract or supersede the old live actions, contacts and briefings derived from the same sentences. The ledger (`source_key` ↔ entity ids) is designed to make this possible later. The planner and API reserve `mode="force"`, which v1 rejects with `422`.

---

## 5. Pre-existing issues found during the analysis

Each of these affects live ingestion today and is worth fixing independently. Items 1–3 are prerequisites of Phase 3.

| # | Location | Issue | Fix |
|---|---|---|---|
| 1 | [scheduler.py:271](../../../src/pipeline/nodes/scheduler.py) | LLM-path fallback calls `parse_relative_time_expression(transcript)` without `ref_dt`, so the utterance time is ignored | Pass `ref_dt` parsed from `state["timestamp"]` |
| 2 | [sqlite_store.py:504](../../../src/core/storage/sqlite_store.py) | `match_and_resolve_task` matches by keyword overlap with no time constraint | Temporal guard ([03](03_backfill_engine.md) §4.1) |
| 3 | [persist.py](../../../src/pipeline/nodes/persist.py) / `save_action` | Random ids: the same utterance processed twice creates two actions | Deterministic ids from `source_key` ([02](02_coverage_and_deduplication.md) §5) |
| 4 | [orchestrator.py:138](../../../src/ingestion/orchestrator.py) | `chunk_id` falls back to `time.time()` when the payload has no id, so ids are not stable across re-deliveries | Fall back to `sha1(conversation_uuid + received_at + text)` |
| 5 | [stream_convo.py:84](../../../src/ingestion/stream_convo.py) | `get_location` runs `bee location current`, but the CLI command is `locations current` ([locations/index.ts](../../../resources/bee-cli/sources/resources/locations/index.ts)) | Use `['locations', 'current', '--json']` |
| 6 | [event_engine.py:1287](../../../src/ingestion/event_engine.py) | Utterances outside events, including all `noop`, leave no persistent trace | Addressed by the ledger (Phase 1) |

---

## 6. Open questions

1. **Default look-back.** Is `BACKFILL_LOOKBACK_DAYS=2` the right balance between completeness and surprise cost after a long holiday? The alternative is `7` with the budget guard trimming to the most recent part.
2. **Ledger text retention.** Is storing `text_norm` for 14 days acceptable under the project's GDPR stance, or should fuzzy matching use a token MinHash sketch instead (no plaintext)?
3. **Realtime fallback reconciliation.** When a run used the realtime transcription and the final one arrives later, should EXAMEN re-analyse that conversation (Phase 6 changefeed), or accept the lower-quality result?
4. **AgentCore deployment.** In the cloud split, should the executor call AgentCore per utterance (as live does) or invoke a single "batch" entrypoint per run to amortise cold starts?
