# 06 — Phase 0 Device Spike: Runbook & Results

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> Executes Phase 0 of [05](05_implementation_plan_and_testing.md) §1: answer the open verifications of [01](01_bee_history_sources.md) §6 with the physical Bee, calibrate the backfill settings and capture anonymised fixtures.
> **Status:** environment ready (2026-10-19); device session pending. Results go in §5.

---

## 1. Environment (already prepared)

| Item | State | How to reproduce |
|---|---|---|
| `resources/bee-cli` submodule | Initialised at `e67032d` (v0.7.3) | `git submodule update --init resources/bee-cli` |
| Bee binary (linux-x64) | Built into `resources/bee-cli/dist/platforms/linux-x64/bee` (git-ignored by the submodule) | `cd resources/bee-cli && bun install && bun build ./sources/main.ts --compile --target=bun-linux-x64 --outfile ./dist/platforms/linux-x64/bee` |
| `bee` on `PATH` | Symlink in `~/.local/bin/bee`; `get_bee_binary_path()` resolves it first | `ln -sf "$PWD/resources/bee-cli/dist/platforms/linux-x64/bee" ~/.local/bin/bee` |
| Python env | `.venv` via `uv sync` + `uv pip install -r requirements.txt` (pytest is only in `requirements.txt`) | 309 tests pass |
| Spike tool | [scripts/bee_spike.py](../../../scripts/bee_spike.py) | `python scripts/bee_spike.py --help` |
| Raw captures | `.bee-spike/<date>/` (git-ignored: it contains personal speech) | created by the tool |

Not needed for the spike: AWS credentials and `.env`. Every step below calls the Bee API only, no LLM. They are needed only for §4 (end-to-end test with the live server).

---

## 2. Prerequisites with the device

1. Bee paired with the companion app, latest app version, **Developer Mode** on (Settings → tap the app version 5 times).
2. `bee login` (or `bee login --qr`) and approve it in the app. The token is stored in `~/.bee/token-production`.
3. `python scripts/bee_spike.py check` prints the account and the latest conversations.

---

## 3. Procedure

All commands write into the same session directory (`.bee-spike/<today>/`, override with `--session DIR`).

| Step | Command | Answers | Notes |
|---|---|---|---|
| 1 | `python scripts/bee_spike.py check` | login OK | |
| 2 | `python scripts/bee_spike.py capture --minutes 20` while **speaking a scripted dialogue** (§3.1) | V0, V2, V5, V6, payload schemas | Runs `bee stream --json` (what EXAMEN reads) **and** the raw SSE stream through `bee proxy` (event names + comment pings) in parallel. If the server rejects two concurrent streams, rerun with `--no-raw` and note it |
| 3 | Stop speaking; note the conversation id from `bee conversations list` | | |
| 4 | `python scripts/bee_spike.py poll <id> --minutes 60 --until-final` | V4 | Records each `state` / transcription change until the final (`realtime: false`) transcription appears |
| 5 | `python scripts/bee_spike.py history --hours 2` | V1, V3 | Saves the list pages and every conversation detail of the window |
| 6 | `python scripts/bee_spike.py analyze` | V0–V6 report | Writes `analysis.md` / `analysis.json` and one payload sample per SSE event type in `samples/` |
| 7 | `python scripts/bee_spike.py fixture .bee-spike/<date>/history/conv_<id>.json live_full` | fixtures | Redacts text (same word → same token, so realtime/final matching still works), summaries and location. `--keep-text` only for non-personal scripted speech |
| 8 | Repeat 2–7 for the outage and delayed-upload scenarios (§3.2) | T-DED fixtures | |
| 9 | Fill §5, update [FRICTION_LOG.md](../../../FRICTION_LOG.md), adjust settings (§6) | exit criteria | |

V6 needs a longer capture: `capture --minutes 60` with silence is enough.

### 3.1 Scripted dialogue (covers every pipeline route)

Speak in a quiet room, ~2 s pause between sentences, mixing English and Italian:

1. *"I just unplugged the clothes iron and turned off the stove."* (action)
2. *"Nice to meet you Marco, I'm the tech lead at Acme, I'll send you the repo tomorrow."* (social + commitment)
3. *"Remind me tomorrow at three pm to call the dentist."* (scheduled task, relative time)
4. *"Ho chiuso la porta a chiave e spento il gas."* (Italian action)
5. Two minutes of a mini-lecture on one technical topic (deep_topic / event engine).
6. Small talk (noop).

### 3.2 Fixture scenarios (Phase 0 exit, [05](05_implementation_plan_and_testing.md) §1)

| Fixture name | How to produce it |
|---|---|
| `live_full` | Capture running for the whole conversation |
| `live_outage_midway` | Start `capture`, stop it (Ctrl+C) halfway through the conversation, keep speaking |
| `delayed_upload` | Phone in airplane mode while speaking, then reconnect; capture running throughout |
| `processing` | `history --ids <id>` right after the conversation ends, before the final transcription |

---

## 4. Optional: end-to-end live test

Needs `.env` with AWS credentials (copy `.env.example`).

```bash
.venv/bin/python -m src.serving.mcp_server          # starts the orchestrator (bee stream) + dashboard on :8000
curl -s localhost:8000/api/orchestrator/status | jq
curl -s "localhost:8000/api/backfill/coverage" | jq '.gaps'
curl -s -X POST localhost:8000/api/backfill/preview -H 'content-type: application/json' \
     -d '{"from":"<ISO>","to":"<ISO>"}' | jq            # free preview against real history
```

Stop the server for a few minutes while speaking, restart it, and check that the startup catch-up recovers the gap (Phase 1 and Phase 4 exit criteria).

---

## 5. Results (fill in after the device session)

| # | Question | Result | Evidence |
|---|---|---|---|
| **V0** | Does `BeeClient.stream_events` recognise `new-utterance` lines from `bee stream --json`? | ✅ **Yes.** The real `--json` lines carry `"type": "new-utterance"`, unlike the documented payload. The risk below did not materialise | session 2026-10-19 |
| V1 | `uuid` in `GET /v1/conversations/{id}`? | ❌ **No.** Detail keys: `id, state, start_time, end_time, created_at, updated_at, device_type, primary_location, short_summary, summary, suggested_links, transcriptions` (no `uuid`, no `title`). Live → REST mapping must go through `new-conversation` events or utterance ids | 3/3 conversations |
| V2 | Live `new-utterance` carries an utterance `id` equal to the REST realtime one? | ⏳ Live payload has `utterance.id` (same numeric id space as REST, e.g. `3795058986`) | |
| V3 | `GET /v1/conversations` ordering (`start_time` / `created_at` desc) | ✅ Newest first, monotonic by both `start_time` and `created_at`. List items carry `utterances_count`, no transcriptions | 1 page |
| V4 | `state` values and delay until the final transcription | ⏳ | |
| V5 | Lag between `spoken_at` and live receipt | ⏳ | |
| V6 | Heartbeat cadence (SSE comments / `{"timestamp"}` lines) | ⏳ | |
| — | Two concurrent `/v1/stream` connections allowed? | ⏳ | |
| — | Payload schemas of every SSE event type | ⏳ | `samples/*.json` |

**V0 risk (added by this runbook, highest priority).** `bee stream --json` prints only the SSE `data` field ([FRICTION_LOG](../../../FRICTION_LOG.md) 2026-10-13). The documented `new-utterance` data is `{"utterance": {...}, "conversation_uuid": ...}` with no `type` field. [stream_convo.py](../../../src/ingestion/stream_convo.py) recognises `new-utterance` only through `data.get("type") or data.get("event")`, and detects conversation events, but not utterances, by their shape. With the documented payload, every utterance becomes `stream-alive` and **live ingestion screens nothing**. A synthetic run of `bee_spike.py analyze` reproduces it. If the device confirms it, add structural detection (`isinstance(data.get("utterance"), dict)` → `new-utterance`, and the same for `update-utterance`) and a regression test with the captured sample.

---

## 6. Settings to calibrate from the results

| Setting | Current default | Derived from |
|---|---|---|
| `BACKFILL_MATCH_WINDOW_SECONDS` | 300 | V5: max(received − spoken_at) + margin |
| `BACKFILL_FINAL_TRANSCRIPT_GRACE_MINUTES` | 30 | V4: observed delay until the final transcription |
| Readiness rule (`BeeConversation.readiness`) | `processing` = not ready | V4: full `state` list |
| Live read timeout (330 s in `stream_convo.py`) | 330 | V6: must exceed the max heartbeat interval |
| Live ↔ REST matching (exact vs id-based) | text hash + time | V1/V2 |
