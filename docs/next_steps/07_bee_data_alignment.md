# 07 — Bee Data Alignment: Fix Plan & Status

> **Status:** Phases 0–5 implemented (2026-10-19, branch `feature/historical-backfill`); phase 6 (end-to-end verification) pending
> **Why:** the 2026-10-19 device session showed that real Bee payloads differ from the documented ones. The observed contract is in [10_bee_cli_reference.md](../10_bee_cli_reference.md). This plan fixes every gap found by its conformance audit (§10, items C1–C16) and by the backfill spike ([historical_backfill/06](historical_backfill/06_phase0_device_spike.md) §5.2, items I1–I9).
> **Rules:** tests use **synthetic payloads with the real shapes**, written inline in the test files. Raw captures (`.bee-spike/`) and fixtures derived from them are never committed, and no test depends on them.

---

## 1. What was wrong (with real data, before this plan)

| Symptom | Cause | Items |
|---|---|---|
| Live chunks never carry a location | The Apple Watch emits no `update-location`; the only REST fallback (`get_location`) is unused and broken | C2, C3 |
| Wrong `semantic_zone` on real addresses | Substring matching on postal addresses ("Carlo" → transit) | C4 |
| Speaker is always `unknown` live, always `contact` in backfill | `new-utterance` has no speaker; identity arrives as `tagged-utterance`, which is ignored; REST speakers are first names, mapped with a `speaker_0` rule | C5, C6, C16 / I4, I9 |
| Speaker patches would corrupt data | `patch_utterance_speaker` writes the speaker id into `planned_tasks.session_id` and `verified_actions.matched_task_id` | (new) |
| Tags can never arrive before dispatch | The orchestrator reads the stream and processes utterances in one sequential loop | (new) |
| False coverage gaps after every pause > 5.5 min | SSE pings (every 30 s) are dropped by `bee stream --json`; a 330 s read timeout restarts the stream | C9 / I1 |
| Conversation summaries do not enrich events when EXAMEN starts mid-conversation | The uuid ↔ id map is filled only by `new-conversation` | C8 / I6 |
| Backfill utterance spans are points; re-segmented finals are re-analysed | REST `start`/`end` are relative seconds, discarded by `epoch_ms()` | I2, I3 |
| `CAPTURING` not listed as in-progress | State names differ from the docs | I7 |
| Blocking `bee status` probe | Synchronous subprocess in async handlers, 2 s timeout vs ~1.3 s real latency | C10 |

---

## 2. Decisions

| Topic | Decision |
|---|---|
| Stream transport | **Raw SSE through a private `bee proxy` on 127.0.0.1** read with `httpx` (not `--socket`: there the proxy ignores `--idle-timeout` and Bun closes the stream after 10 s idle, observed), so pings are visible: liveness timeout 90 s. Automatic fallback to `bee stream --json` (no read timeout, process-alive ticker) |
| Dashboard logout | **Unchanged by design**: `/api/auth/logout` with `disconnect_bee: true` runs `bee logout`, which disconnects Bee for the whole host and stops the live stream (C11) |
| Wearer identity | `tagged-utterance.person_first_name` (live) or REST `speaker` equal to `bee me` → `first_name` ⇒ `user`; `"Unknown"`/empty ⇒ `unknown`; any other name ⇒ `contact`. `BEE_WEARER_NAME` overrides `bee me` |
| Location source | Poll `bee locations current --json` (accept only `is_recent` fixes with a new id) in addition to SSE `update-location` |
| Verification | Unit tests + real device + real Bedrock end-to-end session |

---

## 3. Phases

| Phase | Scope | Items | Status |
|---|---|---|---|
| 0 | This document; derived fixtures moved to `.bee-spike/fixtures/` | — | ✅ Done |
| 1 | Pure stream parser; SSE proxy transport with pings; CLI fallback; real heartbeats in the orchestrator | C1, C6, C7, C9, I1 | ✅ Done; proxy transport verified on the real account (pings every 30 s, no drops over 100 s) |
| 2 | `bee_identity` (wearer); orchestrator reader/worker split with a speaker-tag wait; safe speaker patches; uuid ↔ id from `new-utterance-chunks`; backfill speaker roles | C5, C8, C16, I4, I6, I9 | ✅ Done; local replay of the real capture: 40/40 wearer tags applied before dispatch, uuid ↔ id map equal to the REST id |
| 3 | Location polling, `get_location` rewrite, whole-word semantic zones | C2, C3, C4 | ✅ Done |
| 4 | Backfill: utterance durations, live-coverage fraction for re-segmented finals, `capturing` state, ledger `duration_ms` | I2, I3, I7 | ✅ Done |
| 5 | Non-blocking `bee status` probe; C11/C12 documented; test isolation from the real Bee CLI (`tests/conftest.py`) | C10, C11, C12 | ✅ Done |
| 6 | Real-device and end-to-end verification; docs finalised | — | ⏳ Needs `bee login` and `.env` (Bedrock) |

### 3.1 New settings

| Variable | Default | Meaning |
|---|---|---|
| `BEE_STREAM_TRANSPORT` | `proxy` | `proxy` (raw SSE via `bee proxy`) or `cli` (`bee stream --json`) |
| `BEE_PROXY_PORT` | `0` | Port of the private `bee proxy` on 127.0.0.1 (`0` = first free port from 8787) |
| `BEE_STREAM_PING_TIMEOUT_SECONDS` | `90` | No SSE frame for this long ⇒ reconnect (pings arrive every 30 s) |
| `BEE_SPEAKER_TAG_WAIT_SECONDS` | `1.5` | Max wait after receipt for a `tagged-utterance` before dispatch |
| `BEE_WEARER_NAME` | — | Overrides the wearer first name read from `bee me` |
| `BEE_LOCATION_POLL_SECONDS` | `120` | `bee locations current` polling period (0 disables) |
| `BACKFILL_LIVE_COVERAGE_FRACTION` | `0.5` | A final utterance whose span is covered at least this much by live speech of the same conversation is a live duplicate |

---

### 3.2 Implementation notes

| Area | Where | Notes |
|---|---|---|
| Stream parser | `parse_bee_payload`, `SseFrameParser` in [stream_convo.py](../../src/ingestion/stream_convo.py) | Pure functions; unknown types → `stream-alive` |
| Private proxy | `BeeProxy` (same file) | `bee proxy --idle-timeout 255` on TCP; `--socket` drops idle streams after 10 s (observed). Restarted with back-off; after 3 consecutive failures the stream falls back to `bee stream --json` |
| Reader / worker | `BeeStreamOrchestrator.run` ([orchestrator.py](../../src/ingestion/orchestrator.py)) | The reader applies tags, pings, chunks, conversations and locations immediately; utterances go through an ordered queue |
| Speaker tags | `on_tagged_utterance`, `_await_speaker_tag` | Bounded wait (`BEE_SPEAKER_TAG_WAIT_SECONDS`) only when the reader runs concurrently; late tags patch the ring buffer and `utterance_diarization` only (the old patch overwrote `planned_tasks.session_id` and `verified_actions.matched_task_id`) |
| Wearer | [bee_identity.py](../../src/ingestion/bee_identity.py) | `bee me` once per process (retried every 10 min on failure); without a known wearer, named speakers stay `unknown` |
| Location | `poll_location` | Only `is_recent` fixes with a new id; `captured_at` = fix `created_at` |
| Backfill dedup | `_LiveEvidence.covered_fraction` ([backfill.py](../../src/ingestion/backfill.py)) | Live spans `[spoken_at, spoken_at + duration]` merged with `BACKFILL_SPAN_MERGE_SECONDS`; applied after the hash/fuzzy match |
| Ledger | `ingest_ledger.duration_ms` | Non-blocking `ALTER TABLE` |

## 4. Verification

1. `.venv/bin/pytest tests/ -q` green after every phase.
2. Real device, ingestion only: a capture started **before** speaking (to observe `new-conversation` / `update-conversation`), replayed locally through the new parser.
3. End-to-end with Bedrock on the homelab test instance ([11_homelab_test_deployment.md](../11_homelab_test_deployment.md)): the scripted dialogue of [historical_backfill/06](historical_backfill/06_phase0_device_spike.md) §3.1 through `python -m src.serving.mcp_server`:
   - `STREAMING` status, heartbeat advancing every ~30 s, `has_location: true`;
   - the wearer's sentences tagged `speaker_role=user`, commitments with the right debtor;
   - a ~7-minute silence opens **no** coverage gap and the stream survives the proxy idle timeout;
   - a 3-minute server outage while speaking is recovered by the backfill without duplicates.
4. Next day: `bee daily find` confirms that `conversation_uuid` equals the live uuid ([10](../10_bee_cli_reference.md) §4.6).

---

## 5. Follow-ups (out of scope)

- Home / work detection from `bee locations clusters` (dwell time) instead of address keywords.
- `ProxyBeeHistorySource` (batch detail, `from` filter) on top of the new private proxy.
- Window screening using Bee's own `new-utterance-chunks` segmentation.
