# 06 — Phase 0 Device Spike: Runbook & Results

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> Executes Phase 0 of [05](05_implementation_plan_and_testing.md) §1: answer the open verifications of [01](01_bee_history_sources.md) §6 with the physical Bee, calibrate the backfill settings and capture anonymised fixtures.
> **Status:** device session done on 2026-10-19 (results in §5). Implementation follow-ups in §5.2.

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
| 7 | `python scripts/bee_spike.py fixture .bee-spike/<date>/history/conv_<id>.json live_full` | local fixtures in `.bee-spike/fixtures/` (never committed: committed tests use synthetic payloads with the real shapes) | Redacts text with a random per-run salt (same word → same token inside one fixture, so realtime/final matching still works, but not reversible by dictionary), speaker names, summaries and location. `--keep-text` only for non-personal scripted speech |
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

### 3.2 Local fixture scenarios (Phase 0 exit, [05](05_implementation_plan_and_testing.md) §1; kept out of git)

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

## 5. Results (device session 2026-10-19)

Setup: Bee captured through the **Apple Watch app** (REST `device_type: "unknown"`), one live conversation of ~35 min (`11404747`, Italian speech, 279 utterances) plus two completed conversations of the previous night. Raw data in `.bee-spike/2026-10-19*/` (not committed).

| # | Question | Result | Evidence |
|---|---|---|---|
| **V0** | Does `BeeClient.stream_events` recognise `new-utterance` lines from `bee stream --json`? | ✅ **Yes.** Real `--json` lines carry `"type"` (unlike the documented payload): 184/184 utterances recognised. The feared silent drop of every utterance (documented payload has no `type`) did not materialise | `analyze` replays the capture through the production parser |
| V1 | `uuid` in `GET /v1/conversations/{id}`? | ❌ **No** (but `bee daily find <date>` pairs `id` with `conversation_uuid`, see [10](../../10_bee_cli_reference.md) §4.6). Detail keys: `id, state, start_time, end_time, created_at, updated_at, device_type, primary_location, short_summary, summary, suggested_links, transcriptions` (no `uuid`, no `title`). The uuid ↔ id map comes from the stream instead (§5.2 I6) | 3/3 conversations |
| V2 | Live utterance `id` equal to the REST realtime one? | ✅ **Yes, 184/184**, with identical `text` and `spoken_at`. Exact id-based dedup is possible **while the realtime transcription exists** (see V4) | live vs `conv_11404747.json` |
| V3 | `GET /v1/conversations` ordering | ✅ Newest first, monotonic by both `start_time` and `created_at`. List items carry `utterances_count` (= realtime + final count: 2814 for a 1407-utterance final), no transcriptions | 1 page |
| V4 | `state` values and delay until the final transcription | **`CAPTURING`** (open, `end_time: null`) → **`PROCESSING`** (`end_time` set, final transcription already there) → **`COMPLETED`** ~30 s later. Bee closes a conversation after **~6 min of silence** (`end_time` = last `spoken_at` + 377 s). From `PROCESSING` on, the detail returns **only the final transcription** (new transcription id, new utterance ids, created 2–22 s after `end_time`); the realtime one is no longer returned. `updated_at` is not bumped by new utterances. For `11404747` the final is the realtime transcription re-issued: **270/270 live texts appear verbatim in it, 268 with the same `spoken_at`** | `poll_11404747.jsonl` |
| V5 | Lag between `spoken_at` and live receipt | **1.6 s min · 12.8 s median · 44.1 s max** (n = 184). The last utterances arrived ~16 s after they were spoken; an offline backlog was not tested | `received_at` vs `utterance.spoken_at` |
| V6 | Heartbeat cadence | The server sends an SSE comment **`: ping` every 30.0 s** (19 in 10 min). **`bee stream --json` drops them**: a 231 s silence produced zero lines (§5.2 I1) | `2026-10-19-rawsse` capture |
| — | Two concurrent `/v1/stream` connections | ✅ Allowed: `bee stream --json` + raw SSE stayed connected side by side for 3 min | `2026-10-19-dual` |
| — | Location | No `update-location` event from the watch. `primary_location` is `null` while `CAPTURING`, filled on completed conversations | |

### 5.1 Real payloads (`bee stream --json`)

Event types seen: `connected`, `new-utterance` (184), `tagged-utterance` (40), `new-utterance-chunks` (7), `update-conversation-summary` (7). `new-conversation` / `update-conversation` were not seen because the conversation started before the capture. Text and names are redacted below.

```jsonc
// connected (only line with no "type"; this is the single {"timestamp"} line, not a periodic heartbeat)
{"timestamp": 1792416597207}

// new-utterance: no "speaker"; start/end are SECONDS relative to the conversation audio; spoken_at is ISO (second precision)
{"type": "new-utterance", "conversation_uuid": "e83f5848-…",
 "utterance": {"id": 3795058986, "sample_id": "5f06263c-…", "start": 22.24, "end": 32.08,
               "text": "…", "spoken_at": "2026-10-19T13:29:34.000Z"}}

// tagged-utterance (undocumented): speaker identification ~1 s after the utterance; 40/184 utterances tagged, score 0.52–0.86
{"type": "tagged-utterance", "utterance_id": 3795058986, "person_id": 12345,
 "person_first_name": "<name>", "speaker_score": 0.799, "conversation_uuid": "e83f5848-…"}

// new-utterance-chunks (undocumented): Bee's own semantic segmentation; carries the NUMERIC conversation id
{"type": "new-utterance-chunks", "conversation_id": 11404747, "transcription_id": 16973068,
 "chunks": [{"id": 346928681, "chunk_text": "<one-sentence summary>", "tags": ["CONVERSATION"],
             "utterances": [3795053053, 3795055596, 3795055978, 3795056456, 3795058986]}]}

// update-conversation-summary
{"type": "update-conversation-summary", "conversation_id": 11404747, "short_summary": "…"}
```

REST utterance (both transcriptions): `{id, text, speaker, spoken_at (epoch ms), start, end, realtime, created_at}`. `start`/`end` are relative seconds whose origin is **not** the conversation start (they reach only 446 s in a 38-min conversation, so probably an audio segment): only `end − start` (duration) is usable. `speaker` is a **person name or `"Unknown"`**, never `speaker_N`. Final transcriptions usually have realtime-like granularity (median 3.3 s / 9 words), but can collapse into a few huge utterances (2 utterances of 640–1130 words in a 7-minute conversation).

### 5.2 Impact on the implementation

> Fix plan and status: [07_bee_data_alignment.md](../07_bee_data_alignment.md).

| # | Finding | Affected code | Recommended change |
|---|---|---|---|
| **I1** | No line reaches `--json` consumers during silence (pings dropped), but EXAMEN treats 330 s without lines as a dead stream | [stream_convo.py](../../../src/ingestion/stream_convo.py) read timeout; `CoverageTracker` closes the interval at the last line | ✅ Fixed (07 phase 1). Any pause > 5.5 min causes a needless reconnect **and a false coverage gap**, which then triggers a reconnect backfill. Either read the raw SSE through `bee proxy` (30 s pings → liveness timeout ~90 s), or with the CLI transport extend coverage while the `bee stream` process is alive instead of using a read timeout |
| **I2** | REST and live `start`/`end` are relative seconds (unknown origin): `epoch_ms()` returns `None`, so every utterance span collapses to a point at `spoken_at` | [bee_history.py](../../../src/ingestion/bee_history.py) `BeeUtterance.span_ms` | ✅ Fixed (07 phase 4). `span = [spoken_at, spoken_at + (end − start) · 1000]` |
| **I3** | Backfill runs only see **completed** conversations, which no longer expose the realtime transcription, so the planner's primary path (match live rows to REST realtime, 02 §4) never applies and it falls back to matching against the final. That works when the final re-issues the realtime text (`11404747`: 100 % verbatim, 99 % same `spoken_at`), but not when Bee re-segments it into minutes-long utterances (`11390239`) | [backfill.py](../../../src/ingestion/backfill.py) `BackfillPlanner` | ✅ Fixed (07 phase 4): live-coverage fraction. Promote **exact text + `spoken_at`** matching against the final to the primary path. For re-segmented finals, build "seen" spans **from the live ledger** (`spoken_at` + `end − start`, per conversation uuid) and select final utterances by span overlap. Keep id equality (V2) for the rare `CAPTURING` case |
| **I4** | Live utterances carry no `speaker`; identity arrives later via `tagged-utterance`. The REST speaker is a person name | `speaker_0 → user` heuristic (orchestrator, gatekeeper context) | ✅ Fixed (07 phase 2). Treat `tagged-utterance` with `person_first_name` = account `me.first_name` (or a stored `person_id`) as the user; patch the ring buffer like `update-utterance`. Untagged → unknown |
| **I5** | `tagged-utterance`, `new-utterance-chunks`, `connected` fall into `stream-alive` | `BeeClient.stream_events` | ✅ Fixed (07 phase 1). Parse them explicitly (I4, I6) |
| **I6** | uuid ↔ numeric id is not in REST (V1) | `bee_conversation_map` (filled only from `new-conversation` today) | ✅ Fixed (07 phase 2). Also fill it from `new-utterance-chunks`: the chunk's utterance ids map to the uuid of the matching `new-utterance` events |
| I7 | States are `CAPTURING` / `PROCESSING` / `COMPLETED` | `_IN_PROGRESS_STATES` in `bee_history.py` | ✅ Fixed (07 phase 4). Add `capturing` (harmless today because `end_time` is null while open); `processing` is already deferred, and lasts ~30 s |
| I8 | Bee produces its own semantic chunks with tags | gatekeeper | Follow-up (07 §5). Possible later input to window screening (Phase 6) |
| I9 | REST speaker = first name or `"Unknown"` | `speaker_role_for` in `backfill.py` | ✅ Fixed (07 phase 2). Every backfilled utterance becomes `contact` (wearer included). See [10_bee_cli_reference.md](../../10_bee_cli_reference.md) C16 |

Findings outside the backfill (location, live speaker role, logout side effect, …) are in [10_bee_cli_reference.md](../../10_bee_cli_reference.md) §10.

## 6. Settings to calibrate from the results

| Setting | Current default | Observed | Recommendation |
|---|---|---|---|
| `BACKFILL_MATCH_WINDOW_SECONDS` | 300 | lag ≤ 44 s, plus upload backlog after the watch stops; final `spoken_at` equals live `spoken_at` | Keep 300 |
| `BACKFILL_FINAL_TRANSCRIPT_GRACE_MINUTES` | 30 | final transcription 2–22 s after `end_time`, `COMPLETED` ~30 s later | Keep 30 (it only matters if a final transcription never appears) |
| `BACKFILL_RECONNECT_DELAY_SECONDS` | 900 | conversations close ~6 min after the last speech, then ~30 s of processing | 900 is enough; ≥ 420 is the floor |
| Readiness rule (`BeeConversation.readiness`) | `end_time` null or in-progress state → deferred | `CAPTURING` / `COMPLETED` | Add `capturing` to `_IN_PROGRESS_STATES` (I7) |
| Live read timeout (`stream_convo.py`) | 330 s | no `--json` line during silence; SSE pings every 30 s | See I1 |
| Live ↔ REST matching | text hash + time vs REST realtime | ids equal while `CAPTURING`; realtime gone once `COMPLETED` | Span overlap from the live ledger (I3) |
