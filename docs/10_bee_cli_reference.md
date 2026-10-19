# 10 — Bee CLI & API: Observed Behaviour Reference

> **EXAMEN (Ambient Knowledge & Action Engine)**
> **Status:** Reference, verified against a real account on **2026-10-19** (bee-cli `v0.7.3`, commit `e67032d`, capture through the **Apple Watch** app).
> **Purpose:** the single source of truth for how EXAMEN must call `bee` and interpret what it returns. When this document and an older spec disagree, this document wins. Older specs that relied on the documented (not observed) payloads are listed in §11.

Every statement is tagged:

| Tag | Meaning |
|---|---|
| **[obs]** | Observed on the real account (raw captures under `.bee-spike/2026-10-19*/`, not committed) |
| **[cli]** | Read from the bee-cli source in [`resources/bee-cli/`](../resources/bee-cli/) |
| **[doc]** | Official documentation ([docs.bee.computer](https://docs.bee.computer/docs)), not confirmed by observation |
| **[unverified]** | Known to exist, never observed. Treat its shape as provisional |

All examples use **synthetic values**. Real captures contain personal speech, names and addresses and must never be copied into the repository.

---

## 1. How bee-cli works

```
Bee wearable / Apple Watch ──BLE/Wi-Fi──► Bee companion app ──► Bee Cloud
                                                                   │  REST  /v1/...
                                                                   │  SSE   /v1/stream
                                                     bee-cli (Bun binary) ──► stdout (markdown | JSON)
                                                                   │
                                                     EXAMEN: subprocess per call (BeeClient)
```

- bee-cli is a thin client over the Bee developer API. `--json` prints the **raw API response body** unchanged [cli][obs]. Without `--json`, commands print markdown meant for humans and agents. EXAMEN must always pass `--json` and never parse markdown, except for `bee status`, which has no JSON mode.
- **API base URL:** `https://app-api-developer.ce.bee.amazon.dev/` (environment `production`) [obs].
- **Developer Mode** must be enabled in the companion app (Settings → tap the app version 5 times) [doc].
- **Latency:** every call is one HTTPS round trip plus process start-up. Observed: **1.2–2.2 s** for most commands, 3.3 s for `conversations transcript`, 3.8 s for neural search, 5.2 s for `now`, 7.4 s for `changed` [obs]. Never call bee synchronously on an async event loop.
- **Rate limits:** none documented. bee-cli itself caps its own concurrency at 4 (`SYNC_CONCURRENCY`) [cli]; EXAMEN does the same.

### 1.1 Authentication

| Command | Behaviour |
|---|---|
| `bee login` | Interactive: prints a link, waits for approval in the app [cli][obs] |
| `bee login --qr` | Same, shows a QR code [cli] |
| `bee login --no-wait` | Prints the link and exits (for automation); finish with `bee status` [cli] |
| `bee login --token <t>` / `--token-stdin` | Stores a token directly [cli] |
| `bee login --proxy <url\|socket>` | Uses a running `bee proxy` instead of a token [cli] |
| `bee logout` | **Deletes the stored token for the whole host** [cli] |
| `bee status` | Text only, no `--json` [obs] |

Token storage: `~/.bee/token-<env>` (plus `pairing-<env>.json`, `proxy-<env>.json`) [cli].

`bee status` output [obs]:

```
API: production (https://app-api-developer.ce.bee.amazon.dev/)
Token: eyJh...xxxx
Verified as <First> <Last> (id <n>).
```

Unauthenticated: the last lines are replaced by `Not logged in.` [obs]. `bee status` performs a network verification (~1.3 s) [obs].

### 1.2 Binary and resolution in EXAMEN

bee-cli ships `bin/bee.js`, a Node launcher that executes `dist/platforms/<os>-<arch>/bee`. That binary exists only in the npm package, not in the git submodule [cli]. Build it locally (see [AGENTS.MD](../AGENTS.MD) §7):

```bash
cd resources/bee-cli && bun install && \
  bun build ./sources/main.ts --compile --target=bun-linux-x64 --outfile ./dist/platforms/linux-x64/bee
```

`get_bee_binary_path()` ([stream_convo.py](../src/ingestion/stream_convo.py)) resolves `bee` on `PATH` first, then the platform binary, then `bin/bee.js`.

---

## 2. Global data conventions

| Topic | Rule |
|---|---|
| **REST timestamps** | Epoch **milliseconds** (integers) everywhere: `start_time`, `end_time`, `created_at`, `updated_at`, `spoken_at`, `date_time`, `alarm_at`, … [obs] |
| **Live `spoken_at`** | **ISO 8601 string in UTC with second precision** (`"2026-10-19T13:29:34.000Z"`) [obs], unlike REST |
| **Utterance `start` / `end`** | **Relative seconds (float)** with an unknown origin, not the conversation start: in a 38-minute conversation `start` only reached 446 s [obs]. Only **`end − start` (duration)** is meaningful. Never pass them to an epoch normaliser. Can be `null` [obs] |
| **Ids** | Numeric integers for conversations, transcriptions, utterances, facts, todos, dailies, locations [obs]. Search results use string ids [obs] |
| **Conversation uuid** | Exists, but appears only in the **stream** (`conversation_uuid`) and in **daily summaries** (`daily.conversations[].conversation_uuid`). It is **absent** from `conversations list/get` [obs] |
| **Time zone** | Almost every response carries a top-level `timezone` (IANA, e.g. `Europe/Rome`) [obs]. Use it to interpret days (`daily find`, `today`) |
| **Cursors** | Opaque strings. Observed formats: `v1-<epochMs>-<id>` (conversation list), `v1-<epochMs>` (changefeed). `null` when there are no more pages [obs]. Do not construct them |
| **Speaker labels** | REST: a **person's first name** or `"Unknown"`, never `speaker_N` [obs]. Live: **no speaker field**; see `tagged-utterance` (§7.3) |
| **Device type** | `"unknown"` for the Apple Watch [obs] |
| **`corrections`** | Present as `[]` on many entities (todos, insights, dailies, search results) [obs] |

---

## 3. Command reference

`(E)` = used by EXAMEN today. All commands accept `--json` unless stated otherwise.

| Command | Flags | Returns | Notes |
|---|---|---|---|
| `status` (E) | — | text (§1.1) | Account probe in `/api/status` |
| `me` | — | `{id, first_name, last_name, timezone}` | Use `first_name` to recognise the wearer in `tagged-utterance` |
| `conversations list` (E, backfill) | `--limit N`, `--cursor C` | §4.1 | Newest first by `start_time` and `created_at` [obs]. **No date filter** in the CLI (the API has `from=YYYY-MM-DD`, only reachable through `bee proxy`) [cli] |
| `conversations get <id>` (E, backfill) | — | §4.2 | |
| `conversations transcript <id>` | `--since <epochMs>` | `{conversationId, transcript: [utterance], note}` | Flattens the preferred transcription. `note` is a fixed ASR-quality disclaimer [obs]. `--since` filters on `spoken_at ?? start` client-side [cli] |
| `conversations related <id>` | `--limit N` | `{conversationId, conversations: [...]}` | Empty in the session |
| `now` | — | `{since, until, timezone, conversations: [detail]}` | Last 10 h, full details with transcriptions [cli][obs] |
| `changed` | `--cursor C` | §4.7 | Default window 24 h; hydrates every changed entity [cli][obs] |
| `activity` | `--limit N` | `{activity: [{type, at, …}]}` | `type ∈ {conversation, insight}` observed; items are the entity fields flattened with `type` and `at` [obs] |
| `today` | `--context` | §4.8 | |
| `daily list` / `get <id>` / `find <YYYY-MM-DD>` | `--limit`, `--cursor` | §4.6 | `find` returns `daily_summary: null` until the day is summarised [obs] |
| `facts list/search/get` | `--limit`, `--cursor`, `--unconfirmed`, `--query` | `{facts: [{id, text, tags[], created_at, confirmed}], next_cursor, timezone}` | Tags observed: `general, health, hobbies, politics, sports, technology` [obs]. `create/update/confirm/delete` **write** data |
| `todos list/get/suggestions` | `--limit`, `--cursor` | `{todos: [{id, text, alarm_at, completed, created_at, corrections}]}`; suggestions: `{todoSuggestions: [{id, text, emoji, details, alarm_at, created_at}]}` | `create/update/complete/delete/accept-suggestion/dismiss-suggestion` **write** data |
| `insights list/get` | `--limit` | `{insights: [{id, title, description, suggested_actions[], generated_at, timezone, corrections}]}` | |
| `journals list/search/get` | `--limit`, `--cursor`, `--query` | `{journals: [], next_cursor, timezone}` | Empty in the session |
| `search` (keyword) | `--query`, `--limit`, `--since`, `--until`, `--filter`, `--sort`, `--scope` | `{results: [{id (string), type, score, summary, snippet, title_snippet, created_at}], search_mode: "bm25", …}` | `type` observed: `daily` |
| `search --neural` | `--query`, `--limit`, `--since`, `--until` | `{results: [{id, started_at, stopped_at, link, locations[] (strings), short_summary, detailed_summary}], total, answer, timezone}` | Conversations only; `answer` is a generated natural-language answer |
| `locations current` | — | §6 | |
| `locations recent` | `--from`, `--to`, `--limit` | §6 | Default window ~24 h |
| `locations clusters` | `--limit`, `--min-visits` (default 3), `--visits` | §6 | |
| `photos list/get` | `--daily-id`, `--date`, `--limit`, `--output` | `{photos: []}` | Empty in the session |
| `external-access list` | `--limit`, `--cursor` | `{external_access: [], next_cursor, timezone}` | Audit of third parties that read the data |
| `stream` (E) | `--types`, `--json`, `--agent`, `--webhook-endpoint`, `--webhook-body` | §7 | Long-running |
| `proxy` | `--port N` \| `--socket [path]`, `--idle-timeout S` (default 120, Bun max 255) | local HTTP proxy that injects the token for `/v1/*` | Gives raw SSE (with pings) and REST endpoints the CLI does not expose |
| `sync` | `--output`, `--recent-days`, `--full`, `--since`, `--only` | markdown files | Uses batch detail + changefeed internally [cli] |
| `mcp serve` / `serve-http` / `connect` | — | MCP server | Not used by EXAMEN |

---

## 4. Data models

### 4.1 Conversation summary (`conversations list`, `activity`, `today --context`)

```jsonc
{
  "id": 11400000,
  "start_time": 1792416557798,          // epoch ms
  "end_time": 1792418854000,            // epoch ms; null while CAPTURING
  "created_at": 1792416557938,
  "updated_at": 1792418866000,          // NOT bumped by new utterances while CAPTURING [obs]
  "state": "COMPLETED",                 // §5
  "device_type": "unknown",
  "short_summary": "…", "summary": "…", // may be empty while CAPTURING
  "utterances_count": 558,              // realtime + final utterances (2 × the final count once completed) [obs]
  "primary_location": {"address": "…", "latitude": 45.07, "longitude": 7.68, "created_at": 1792416558579}  // null while CAPTURING [obs]
}
// envelope: {"conversations": [...], "next_cursor": "v1-…" | null, "timezone": "Europe/Rome"}
```

### 4.2 Conversation detail (`conversations get`, `now`, `changed`)

```jsonc
{
  "conversation": {
    /* every summary field except utterances_count */
    "suggested_links": [],
    "transcriptions": [
      {"id": 16970000, "realtime": false, "utterances": [ /* §4.3 */ ]}
    ]
  },
  "timezone": "Europe/Rome"
}
```

- **No `uuid`, no `title`** [obs], although bee-cli's formatter and the docs mention them for stream events.
- While `CAPTURING` the only transcription is `realtime: true`. From `PROCESSING` on it is **replaced** by a `realtime: false` transcription with a **new transcription id and new utterance ids** [obs] (§5).

### 4.3 Utterance (REST)

```jsonc
{
  "id": 3795000001,
  "text": "…",
  "speaker": "Unknown",          // or a person's first name
  "spoken_at": 1792416574000,    // epoch ms, second precision; can precede the conversation start_time
  "start": 22.24, "end": 32.08,  // relative seconds (unknown origin): use end − start only; start may be null
  "realtime": false,
  "created_at": 1792418860000    // when this utterance row was written
}
```

Final transcriptions usually keep realtime granularity (median 2.6–3.3 s, 9 words). They can also collapse long stretches into a few huge utterances (observed: 2 utterances of 640 and 1130 words, 250–405 s long) [obs].

### 4.4 Profile (`me`)

```json
{"id": 50000, "first_name": "Ada", "last_name": "Lovelace", "timezone": "Europe/Rome"}
```

### 4.5 Transcript (`conversations transcript`)

`{"conversationId": 11400000, "transcript": [utterance…], "note": "Transcript text is ASR output and may contain recognition errors. …"}` [obs]

### 4.6 Daily summary (`daily list`, `daily get`, `daily find`)

```jsonc
{
  "daily_summary": {
    "id": 900000, "date": "2026-10-18", "date_time": 1792274400000,
    "short_summary": "…", "summary": "…",
    "email_summary": null, "calendar_summary": null, "account_summaries": null,
    "locations": [{"id": 1, "latitude": 45.07, "longitude": 7.68, "address": "…"}],
    "photos": [], "soundtrack": [], "corrections": [], "created_at": 1792300000000,
    "conversations": [
      {"id": 11390000, "conversation_uuid": "6f0c…", "start_time": …, "end_time": …,
       "short_summary": "…", "device_type": "unknown", "state": "COMPLETED",
       "primary_location": {"address": "…", "latitude": …, "longitude": …},
       "bookmarked": false}
    ]
  },
  "timezone": "Europe/Rome"
}
```

`daily list` returns `{daily_summaries: [...], next_cursor, timezone}`, with `conversations_count` instead of `conversations`.

> **This is the only REST source that pairs `id` with `conversation_uuid`** [obs]. Equality with the live `conversation_uuid` is expected but was not checked yet, because today's daily summary did not exist at the end of the session.

### 4.7 Changefeed (`changed`)

```jsonc
{
  "meta": {"next_cursor": "v1-1792420000000", "since": …, "until": …, "updated": true, "timezone": "…"},
  "facts": [{"id", "text", "tags", "created_at", "confirmed", "timezone"}],
  "todos": [], "journals": [],
  "dailies": [ /* §4.6 objects */ ],
  "conversations": [ /* §4.2 conversation objects, without the envelope */ ]
}
```

bee-cli treats cursors older than 6 days as stale (`PROACTIVE_FULL_MS`) [cli].

### 4.8 Today (`today`, `today --context`)

- `today`: `{calendar_events: [], emails: [], timezone}` (empty without connected accounts) [obs].
- `today --context`: `{date, todayBrief: {…}, dailySummary: null | daily, activeTodos: [todo], recentNotes: [], recentConversations: [conversation summary]}` [obs].

---

## 5. Conversation lifecycle

```
CAPTURING ──(~6 min of silence)──► PROCESSING ──(~30 s)──► COMPLETED
end_time = null                    end_time set             summaries, primary_location
realtime transcription             final transcription      final transcription only
                                   (new ids, 2–22 s after end_time)
```

| Observation | Value [obs] |
|---|---|
| States seen | `CAPTURING`, `PROCESSING`, `COMPLETED` (uppercase). The docs' `processing` / `processed` (lowercase) were not seen |
| Close trigger | `end_time` = last `spoken_at` + **~377 s** (silence timeout) |
| `PROCESSING` duration | ~30 s |
| Final transcription | Appears at `PROCESSING`, created 2–22 s after `end_time` |
| Realtime transcription | **No longer returned** once the final exists |
| Final vs realtime content | Usually the same text and `spoken_at` re-issued with new ids (270/270 verbatim, 268 same `spoken_at`); sometimes re-segmented into long blocks |
| `updated_at` | Not bumped by new utterances while capturing |
| `primary_location` | `null` while capturing, filled when completed |
| Delivery after the last speech | The last utterances arrived ~16 s after they were spoken, within the normal lag (§7.4). A longer offline backlog (phone without network) was not tested |

**Readiness rule for consumers:** a conversation is final when `end_time != null` **and** `state` is not `CAPTURING`/`PROCESSING` **and** a `realtime: false` transcription exists.

---

## 6. Locations

| Source | Shape [obs] | Notes |
|---|---|---|
| `locations current` | `{location: {id, latitude, longitude, address, source_device_id, created_at, updated_at}, age_ms, is_recent, recent_threshold_ms (1 800 000), timezone}` | Returns the **last known fix**, however old: check `is_recent` / `age_ms` |
| `locations recent` | `{visits: [{visit_id, start_at, end_at, duration_ms, latitude, longitude, sample_count, address, source_device_ids}], from, to, timezone}` | Visits, not raw fixes |
| `locations clusters` | `{clusters: [{cluster_id, latitude, longitude, representative_address, visit_count, sample_count, total_dwell_ms, first_visit_at, last_visit_at, visits?}], from, to, min_visits, timezone}` | Frequent places; good input for home/work detection |
| `conversation.primary_location` | `{address, latitude, longitude, created_at}` | One fix per conversation, at its start |
| `daily.locations[]` | `{id, latitude, longitude, address}` | |
| SSE `update-location` | `{location: {latitude, longitude, name}, conversation_id}` [cli] **[unverified]** | **Never emitted** by the Apple Watch during a 35-minute conversation [obs] |

- **Address format:** a full postal address, `"<number> <street>, <district>, <city> <province>, <region>, <postcode>, <country>"` [obs]. It is not a place name such as "Home" or "Office".
- With the Apple Watch the location is sampled **at conversation start** (two samples ~24 s apart), and nothing is sent while speaking [obs].
- **Accuracy:** no accuracy field anywhere [obs].

---

## 7. Real-time stream

### 7.1 Transport

`GET /v1/stream` (`Accept: text/event-stream`), optional `?types=a,b`. Without `--types`, the server sends **every** type, including types that are not in bee-cli's `SUPPORTED_EVENT_TYPES` list [obs].

Raw SSE framing [obs] (seen through `bee proxy`):

```
retry: 4206

event: connected
data: {"timestamp":1792416597207}

event: new-utterance
data: {"type":"new-utterance","conversation_uuid":"…","utterance":{…}}

: ping            ← every 30.0 s, also during silence
```

- **Delivery is at-most-once** with no replay or `Last-Event-ID` [doc]. On connect, utterances that were not yet delivered can arrive immediately; one arrived 23 s after it was spoken [obs].
- **Concurrent connections** for the same account are accepted: two streams stayed open side by side for 3 min [obs].
- bee-cli opens a single `fetch` with **no retry**: when the connection drops, the process exits [cli]. Reconnecting is the caller's job.

### 7.2 What `bee stream --json` prints

- One line per event: the **SSE `data` field only**. The SSE `event:` name is dropped, but every payload except `connected` carries its own **`"type"`** [obs].
- **SSE comments (`: ping`) are dropped** [cli][obs]: during silence the process prints **nothing**, for minutes (231 s observed). A consumer cannot tell a quiet stream from a stalled one from stdout alone.
- The `connected` event prints `{"timestamp": <ms>}` once per connection [obs]. It is **not** a periodic heartbeat.
- `--agent` prints `Event <type>: <summary>` lines and `--webhook-endpoint` POSTs a Handlebars-rendered body per event [cli]. Neither is used by EXAMEN.

### 7.3 Event types

| Type | Payload | Source | Count in the session |
|---|---|---|---|
| `connected` | `{"timestamp": ms}` | [obs] | 1 per connection |
| `new-utterance` | `{"type", "conversation_uuid", "utterance": {"id", "sample_id" (uuid), "start", "end" (relative s), "text", "spoken_at" (ISO UTC)}}`. **No `speaker`** | [obs] | 184 |
| `tagged-utterance` | `{"type", "utterance_id", "person_id", "person_first_name", "speaker_score" (0–1), "conversation_uuid"}`, ~1 s after the utterance | [obs], undocumented | 40 (22 % of utterances), score 0.52–0.86 |
| `new-utterance-chunks` | `{"type", "conversation_id" (numeric!), "transcription_id", "chunks": [{"id", "chunk_text" (one-sentence summary), "tags": ["CONVERSATION", …], "utterances": [utterance ids]}]}` | [obs], undocumented | 7 |
| `update-conversation-summary` | `{"type", "conversation_id", "short_summary"}` | [obs][cli] | 7 |
| `new-conversation` | `{"conversation": {"id", "uuid", "state", "title"?}}` | [cli] **[unverified]** | 0 (the conversation started before the capture) |
| `update-conversation` | `{"conversation": {"id", "state", "title"?, "short_summary"?}}` | [cli] **[unverified]** | 0 |
| `delete-conversation` | `{"conversation": {"id", "title"?}}` | [cli] **[unverified]** | 0 |
| `update-location` | `{"location": {"latitude", "longitude", "name"}, "conversation_id"}` | [cli] **[unverified]** | 0 (not emitted by the watch) |
| `todo-created` / `todo-updated` / `todo-deleted` | `{"todo": {"id", "text", "completed", "alarmAt"}}` | [cli] **[unverified]** | 0 |
| `journal-created` / `journal-updated` / `journal-deleted` / `journal-text` | `{"journal": {…}}` / `{"journalId", "reason"}` / `{"journalId", "text"}` | [cli] **[unverified]** | 0 |
| ~~`update-utterance`~~ | — | **Does not exist**: not in bee-cli, not observed. Speaker identity arrives through `tagged-utterance` | — |

### 7.4 Timing

| Metric | Value [obs] |
|---|---|
| Receipt − `spoken_at` | **1.6 s min · 12.8 s median · 44.1 s max** (n = 184) |
| `tagged-utterance` after its utterance | ~1 s |
| Ping interval | 30.0 s |

---

## 8. Identity cheat-sheet

| Need | How |
|---|---|
| Live utterance ↔ REST utterance | `utterance.id` is **equal** to the REST **realtime** utterance id (184/184) [obs], but only while the conversation is `CAPTURING`. The final transcription has new ids: match on **normalised text + `spoken_at`** instead (exact for 99 % of utterances in the session) |
| `conversation_uuid` (live) ↔ `id` (REST) | (1) `new-utterance-chunks` lists utterance ids with the numeric `conversation_id`; join with the `conversation_uuid` of those `new-utterance` events. (2) `new-conversation` carries both [cli]. (3) For history: `daily find <date>` → `conversations[].{id, conversation_uuid}` |
| Who is speaking (live) | `tagged-utterance.person_first_name == me.first_name` (or a stored `person_id`) ⇒ the wearer. Untagged ⇒ unknown. There are no `speaker_0/1` labels |
| Who is speaking (REST) | `utterance.speaker` = first name or `"Unknown"` |
| Utterance time | Live: `utterance.spoken_at` (ISO). REST: `spoken_at` (ms). Duration: `end − start` in both |

---

## 9. Rules for EXAMEN code

1. Always call with `--json`; parse only the documented fields above and tolerate unknown fields and new event types.
2. Normalise time with `normalize_bee_time` (it accepts both epoch ms and ISO). **Never** feed `start`/`end` to it: compute `duration_ms = (end − start) · 1000` when both are numbers.
3. Do not infer liveness from `--json` output. Either keep the stream alive for as long as the `bee stream` process is running, or read raw SSE (`bee proxy`) and use the 30 s pings (timeout ≈ 90 s).
4. Do not assume `update-location` exists. Combine it with `bee locations current` polling (check `is_recent`) and `primary_location` of the conversation.
5. Identify the wearer through `tagged-utterance` + `bee me`, not through `speaker_0`.
6. Treat `CAPTURING` and `PROCESSING` as not final; read the final transcription only after `PROCESSING`.
7. Never run `bee logout` as a side effect of an application-level logout: it disconnects the whole host.
8. Run bee subprocesses off the event loop (`asyncio.create_subprocess_exec` **without** `text=True`, or `asyncio.to_thread`).

---

## 10. Conformance audit of the EXAMEN code (2026-10-19)

Backfill-specific findings I1–I8 are in [06_phase0_device_spike.md](next_steps/historical_backfill/06_phase0_device_spike.md) §5.2. The rest of the code, checked against §2–§9:

| # | Area | Code | Behaviour with real data | Severity | Fix |
|---|---|---|---|---|---|
| C1 | Utterance parsing | [stream_convo.py](../src/ingestion/stream_convo.py) `stream_events` | ✅ `new-utterance` recognised via `type`; `id`, `text`, `conversation_uuid`, ISO `spoken_at` parsed correctly. `start`/`end` (duration) and `sample_id` are dropped | Low | Forward `duration_ms` (needed by I2/I3) |
| C2 | **Live location** | `BeeStreamOrchestrator.update_location`, `latest_telemetry` | With the Apple Watch **no `update-location` ever arrives**, so `latest_telemetry` stays `None`: every live chunk has `location=None`. GPS rule R6, the transit `T_hard`, action location grounding (`action_state.py`) and `social.location_encountered` never fire | **High** | Poll `bee locations current --json` (every few minutes and on each new conversation), accept it only if `is_recent`, and map `address` → `place_name` |
| C3 | Location helper | `BeeClient.get_location` | Never called, and broken: `asyncio.create_subprocess_exec(..., text=True)` raises `ValueError: text must be False`. Returns only the address | Medium | Rewrite (bytes + decode) and return `LocationTelemetry` (used by C2) |
| C4 | Semantic zone | `LocationTelemetry.infer_semantic_zone` ([schemas.py](../src/core/schemas.py)) | Bee addresses are postal addresses ⇒ almost always `unknown`. Plain substring matching causes false positives on real street names (`car` in "Carlo", `casa` in "Casale", `bar` in "Barriera", `lab`, `center`) and can wrongly tag `transit`, which shortens `T_hard` in the Event Engine | Medium | Whole-word matching; derive home/work from `locations clusters` (dwell time) instead of address keywords |
| C5 | **Speaker role** | `buffer_incoming_utterance`, `patch_diarization` ([orchestrator.py](../src/ingestion/orchestrator.py)) | Live utterances have no `speaker` ⇒ `speaker_role="unknown"` for everything. The `speaker_0 → user` rule never matches real data. In `social.py` a `contact` role flips the commitment debtor, so the direction of promises cannot be told apart | **High** (social) | Handle `tagged-utterance` (I4): wearer if `person_first_name == me.first_name`, else `contact`; patch the ring buffer and the store with the existing `patch_utterance_speaker` |
| C6 | Diarization updates | `update-utterance` branches in `stream_convo.py` / `orchestrator.py` | Dead code: the event does not exist (§7.3) | Low | Replace with `tagged-utterance` |
| C7 | Unhandled events | `stream_events` | `tagged-utterance`, `new-utterance-chunks` become `stream-alive`; `connected` becomes `stream-heartbeat` | Medium | Parse them (C5, I6) |
| C8 | Conversation summaries | `update-conversation-summary` → `EventEngine.on_bee_conversation` | Payload is flat (`conversation_id`, `short_summary`) and handled. The uuid lookup uses `_bee_conv_ids`, filled only by `new-conversation`. If EXAMEN starts mid-conversation (as in the session), summaries never enrich the event topic profile | Medium | Fill the uuid ↔ id map from `new-utterance-chunks` (I6) |
| C9 | **Liveness** | 330 s read timeout in `stream_events`; `last_heartbeat_time` | Pings are invisible in `--json` (§7.2): every silence > 5.5 min kills and respawns the stream, opens a false coverage gap and schedules a reconnect backfill. `last_heartbeat_time` is set only once per connection (the `connected` line), so "LISTENING" means "connected once" | **High** (= I1) | See §9 rule 3 |
| C10 | Account probe | `_get_bee_device_telemetry` ([mcp_server.py](../src/serving/mcp_server.py)) | Regex on `bee status` matches the real output ✅. The call is a blocking `subprocess.run` (~1.3 s) inside async handlers, with a 2 s timeout close to the real latency; with `bin/bee.js` it runs the `.js` file directly (no runner) | Low | `asyncio.to_thread`, timeout 5 s, reuse `BeeClient._build_cmd` |
| C11 | **Logout side effect** | `api_auth_logout`, `api_auth_bee_disconnect`, `api_auth_gdpr_purge` → `_disconnect_bee_device` | Logging out of the dashboard runs `bee logout`, which deletes the host token: the live stream fails on its next reconnect and history becomes unreachable | **High** for `api_auth_logout`; intended for `bee_disconnect` | Only `bee_disconnect` (explicit) should call `bee logout`; GDPR purge should ask |
| C12 | Device semantics | `/api/status.telemetry.bee_device.device_paired` | Means "utterances flowing" (`is_streaming`), not BLE pairing; the CLI exposes no pairing, battery or RSSI | Low | Rename in docs/UI ("streaming"), keep the field for compatibility |
| C13 | Timestamps | `UtteranceChunk.timestamp` = `spoken_at > received_at` | ✅ Live `spoken_at` is present on every utterance [obs], so the Event Engine uses real speech time, not receipt time (lag up to 44 s) | — | — |
| C14 | Tests & helpers | `tests/test_ring_buffer.py`, `tests/test_backfill.py`, `orchestrator.py` (`horizontal_accuracy`), `UtteranceChunk.speaker_id` description | Use `speaker_0/1`, `update-utterance`, `update-location` with `horizontal_accuracy`: shapes that the real stream does not produce | Low | Keep them where they test generic logic, but add parser tests with the real shapes of §7.3 (synthetic values, inline in the tests) |
| C16 | **Backfill speaker role** | `speaker_role_for` ([backfill.py](../src/ingestion/backfill.py)) | REST speakers are first names or `"Unknown"`: any non-empty value becomes `contact`, so **the wearer and unknown speakers are both `contact`** and every backfilled commitment gets its debtor flipped in `social.py` | **High** | `"Unknown"` → `unknown`; name equal to `me.first_name` → `user`; other names → `contact` |
| C15 | Docs | [AGENTS.MD](../AGENTS.MD) §7 | Refers to `src/ingestion/mock_feeder.py`, which does not exist | Low | Remove or point to `scripts/simulate_mock_conversations.py` |

---

## 11. Specs superseded on Bee data

| Document | Statement | Reality |
|---|---|---|
| [08_real_telemetry_and_bee_hardware_spec.md](08_real_telemetry_and_bee_hardware_spec.md) §2.2, §2.4 | Speaker ids `speaker_0/1`, `update-utterance` diarization, `{"timestamp"}` heartbeats, `bee location current` | §7.2, §7.3, §3 |
| [next_steps/02_gatekeeper_context_and_multimodal_telemetry.md](next_steps/02_gatekeeper_context_and_multimodal_telemetry.md) | `update-utterance` with `speaker_N`, `update-location` with `horizontal_accuracy` | §7.3, §6 |
| [deep_topic_event_engine/05](next_steps/deep_topic_event_engine/05_ingestion_and_pipeline_integration.md) §1 | Live payload has no time field | Live `spoken_at` exists (ISO) |
| [historical_backfill/01](next_steps/historical_backfill/01_bee_history_sources.md) | `uuid` in detail, `processing`/`processed`, `speaker_N`, epoch `start`/`end` | §4, §5 |

---

## 12. Re-verifying

`python scripts/bee_spike.py check | capture | history | poll | analyze` (runbook: [06_phase0_device_spike.md](next_steps/historical_backfill/06_phase0_device_spike.md)). Re-run it when bee-cli is upgraded, when the physical Bee wearable replaces the Apple Watch (locations, `update-location`, `device_type`), and to observe `new-conversation` / `update-conversation`. A capture that starts **before** speaking is enough for the last one.
