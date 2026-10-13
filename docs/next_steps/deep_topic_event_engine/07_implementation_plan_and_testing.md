# 07 — Implementation Plan, Test Scenarios & Acceptance Criteria

> Part of the [Deep Topic Event Engine](00_overview.md) specification.

---

## 1. Phased plan

Each phase is shippable on its own and leaves the test suite green.

### Phase A — Time & lifecycle foundations (time + GPS only) — ✅ IMPLEMENTED (2026-10-13)

> Code: [event_engine.py](../../../src/ingestion/event_engine.py); tests: [test_event_engine.py](../../../tests/test_event_engine.py), [test_ingestion_orchestrator.py](../../../tests/test_ingestion_orchestrator.py). Phase A already includes a minimal synthesis worker (segment and final jobs reusing `node_topic_research`, single-segment promotion, retries, rehydration) so the system stays functional; Phase B replaces it with the refactored, ledger-aware pipeline. `topic_profile`, `pending_chunk_ids` and `research_ledger` fields are deferred to Phases B/C.

Fixes audit findings #2–#7 and #10–#12. Removes fragmented briefings for the common case.

1. Timestamp capture and propagation (`received_at` / `spoken_at`) — [05](05_ingestion_and_pipeline_integration.md) §1.
2. Schema and migrations: `session_chunks`, event fields, briefing `kind`/`session_id`/`segment_id` — [04](04_data_model_and_storage.md).
3. `EventEngine` with pure `decide()` and injectable clock; rules R0, R1, R2, R3, R5, R6, R8 — [01](01_event_model_and_state_machine.md).
4. Tick loop + startup rehydration; delete the legacy buffer path — [05](05_ingestion_and_pipeline_integration.md) §2.
5. Graph routing (`event_managed`) and removal of `conclude_session_dossier` from `node_persist` — [05](05_ingestion_and_pipeline_integration.md) §3.
6. `asyncio.to_thread` around `agent_invocation` in the orchestrator.

In this phase R4 always resumes when on-topic content returns within `T_hard` (no topic split yet).

### Phase B — Progressive & consolidated synthesis
1. Refactor `node_topic_research` into `extract_topics` / `research` / `synthesize_briefing` — [03](03_synthesis_scheduling.md) §2.
2. `SynthesisJobQueue` with idempotency, retries and ordering — [03](03_synthesis_scheduling.md) §5.
3. Segment, checkpoint and final (map-reduce) synthesis; single-segment shortcut — [03](03_synthesis_scheduling.md) §3.
4. Query ledger + `web_search_cache` — [03](03_synthesis_scheduling.md) §4.

### Phase C — Topic continuity
1. `get_embedding_model()` + `TopicSimilarity` backends (`embedding`, `heuristic`, `llm` judge) — [02](02_topic_continuity_detection.md) §6.
2. Topic profile, micro-windows, on-topic activity — [02](02_topic_continuity_detection.md) §2–3.
3. Pending window with R4/R7, drift R9, cue biasing — [02](02_topic_continuity_detection.md) §4–5, [01](01_event_model_and_state_machine.md) §4.1.
4. Gatekeeper active-event hint injection — [02](02_topic_continuity_detection.md) §3.
5. Bee conversation lifecycle events forwarding — [05](05_ingestion_and_pipeline_integration.md) §2.4.
6. **Threshold calibration** on the scenarios below.

### Phase D — Serving & UI
REST/SSE/MCP extensions, Echo Show card, Next.js event view, simulator event mode + virtual clock + scenario player — [06](06_serving_and_ui.md).

### Phase E — Docs & bookkeeping
Update [ROADMAP.md](../ROADMAP.md) (new milestone), mark [03_session_merging_and_micro_event_splitting.md](../03_session_merging_and_micro_event_splitting.md) as extended by this spec, and add a `FRICTION_LOG.md` entry for the Bee stream payload findings.

---

## 2. Test strategy

### 2.1 Unit tests (pure, fast, `MOCK_AI=true`, heuristic similarity)

New file `tests/test_event_engine.py`:

| Test | Asserts |
|---|---|
| `test_open_on_first_deep_topic` | R0 mints event id ≠ conversation uuid; segment 1 open |
| `test_soft_pause_after_t_soft_without_chunks` | Tick at `t + T_soft` → PAUSED, segment closed, job enqueued |
| `test_offtopic_chatter_does_not_reset_pause_timer` | Noop chunks during break → still PAUSED at `T_soft` |
| `test_noop_lecture_sentence_counts_as_on_topic_when_similar` | Window similar to profile resets timer |
| `test_resume_same_topic_within_t_hard` | R4; new segment; pending chunks attached |
| `test_hard_close_after_t_hard` | R5 → CONCLUDED, final job enqueued after segment jobs |
| `test_closing_cue_shortens_hard_close` | "ci vediamo giovedì" → CONCLUDED at `T_hard_after_close_cue` |
| `test_location_shift_accuracy_aware` | Jitter within accuracy ignored; real shift (2 fixes) → R6 |
| `test_back_to_back_different_topic_splits` | R7; pending chunks belong to the new event |
| `test_undecided_window_defaults_to_resume` | Grows window ×3, judge undecided → resume |
| `test_drift_without_pause_requires_k_windows` | 2 drifting windows → no split; 3 → R9 with correct split point |
| `test_checkpoint_on_long_continuous_segment` | R3 at `T_checkpoint`; event stays ACTIVE |
| `test_single_active_event_invariant` | Opening a new event always concludes the previous one |
| `test_concluded_event_rejects_append` | Fix for audit finding #7 |
| `test_rehydration_reenqueues_unsynthesized_segments` | Restart safety |
| `test_spans_multiple_conversation_uuids` | Bee uuid change during PAUSED + same topic → same event, both uuids recorded |

Update existing tests: `tests/test_session_manager.py` (API evolves), `tests/test_ingestion_orchestrator.py` (legacy buffer removed), `tests/test_langgraph_pipeline.py` (routing with `event_managed`), `tests/test_storage.py` (migrations, chunk table, cache), `tests/test_mcp_server.py` (new endpoints, SSE).

### 2.2 Scenario replays (integration, virtual clock)

Extend [resources/mock_conversations.json](../../../resources/mock_conversations.json) with per-turn `offset_seconds` and `expected_event` labels. Existing scenarios (e.g. `macro_session_continuous_meeting`, `deep_topic_synthesis`) are kept.

```json
{
  "id": "lecture_with_break",
  "title": "Single lecture interrupted by a 15-minute break",
  "turns": [
    {"offset_seconds": 0,    "text": "Oggi parliamo di limiti di funzioni e continuità…",       "expected_event": "E1"},
    {"offset_seconds": 40,   "text": "Il limite per x che tende a zero di sin x su x vale uno…", "expected_event": "E1"},
    "… ~40 turns over 50 minutes …",
    {"offset_seconds": 3000, "text": "Facciamo dieci minuti di pausa.",                          "expected_event": "E1", "expected_transition": "paused"},
    {"offset_seconds": 3100, "text": "Prendi un caffè? Sì, al bar del secondo piano.",           "expected_event": "E1"},
    {"offset_seconds": 3900, "text": "Riprendiamo: dove eravamo rimasti con la continuità…",     "expected_event": "E1", "expected_transition": "resumed"},
    "…"
  ],
  "expect": {"events": 1, "segments_per_event": [2], "final_briefings": 1}
}
```

| Scenario id | What it proves | Expected outcome |
|---|---|---|
| `lecture_with_break` | Pause + resume | 1 event, 2 segments, 1 final |
| `back_to_back_lectures_same_room` | Topic split with same GPS, 5-min gap | 2 events, each with its own final |
| `lecture_topic_drift` | Rolling profile tolerates subtopics | 1 event (limits → derivatives) |
| `conference_talks_no_gap` | R9 drift split without silence | 2 events, split at the right turn (±1 window) |
| `walk_away_after_meeting` | GPS hard close | Final within `T_hard_transit` |
| `isolated_question` | Single short burst | 1 event, `standalone`-like final, no extra research |
| `lecture_with_micro_events` | Micro-events during lecture and break are linked | Action/contact/task linked to the event; no extra deep_topic research |
| `long_lecture_no_break` | Checkpoint | ≥ 2 checkpoint briefings + 1 final |

Runner: `scripts/simulate_mock_conversations.py --event-mode --virtual-clock` prints the transition log and checks `expect`. The same scenarios feed `pytest -m scenarios` (heuristic backend, offline) and a manual calibration run with real embeddings.

### 2.3 Calibration procedure (Phase C)

1. Run all scenarios with `TOPIC_SIMILARITY_BACKEND=embedding`, logging every window-vs-profile similarity with its ground-truth label (same / different event).
2. Plot the two distributions; choose `TOPIC_SIM_SAME` / `TOPIC_SIM_DIFFERENT` with a gap of ≥ 0.1 between them; record the values and the plot in this folder.
3. Re-run; target **0 wrong splits** and **≤ 1 wrong merge** across the scenario set (wrong merges are cheaper; see [02](02_topic_continuity_detection.md) §4).

---

## 3. Acceptance criteria

- [ ] A 2-hour lecture replay with one break produces **exactly 1 event, 2 segment briefings and 1 final briefing**. Today it produces dozens of briefings.
- [ ] Back-to-back different lectures in the same location produce **2 events**.
- [ ] The first segment briefing is available ≤ `T_soft` + 90 s after the break starts (mock-AI timing excluded).
- [ ] The final briefing is available ≤ `T_hard` + 120 s after the last on-topic chunk, or ≤ `T_hard_after_close_cue` + 120 s after a closing cue.
- [ ] Web searches per 2-hour lecture are ≤ 12.
- [ ] No synchronous pipeline call blocks the server event loop: SSE heartbeats keep flowing during synthesis.
- [ ] Standalone mode (no engine) behaves as today: `tests/test_pipeline_nodes.py` passes unchanged.
- [ ] Every transition has a rule id and a human-readable reason visible in the UI audit drawer.
- [ ] Full test suite green; new tests cover every rule R0–R9.

---

## 4. Open questions

| # | Question | Owner / how to resolve |
|---|---|---|
| 1 | ~~Which Bedrock embedding models are enabled?~~ **Resolved 2026-10-13:** Titan Text Embeddings V2, Cohere Embed Multilingual / v4, Nova Multimodal and others are active on-demand in `us-east-1` | — |
| 2 | Does the live `bee stream` payload carry any time field (`spoken_at`, `created_at`)? What exactly do `new-conversation` / `update-conversation` look like in `--json` mode? | Capture samples with a real device |
| 3 | How does Bee split a lecture with a break into conversations (silence threshold)? | Same capture session; informs the weight of the Bee-boundary signal |
| 4 | ~~Final `T_soft` / `T_hard` defaults?~~ **Decided 2026-10-13:** `T_soft = 5 min`, `T_hard = 30 min` (revisit after real-device tests) | — |
| 5 | Privacy: retention of raw `session_chunks` after the final briefing exists (keep / truncate after N days)? | Team decision; add `EVENT_CHUNK_RETENTION_DAYS` |
| 6 | Should the final briefing be regenerated if a concluded event is manually merged days later? | Default yes (doc 03 §7); confirm UX |
