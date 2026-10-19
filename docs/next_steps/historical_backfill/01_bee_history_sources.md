# 01 — Bee History Sources (bee-cli & Bee API)

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> Sources audited: `resources/bee-cli` at commit `e67032d` (2026-08-17) and the official docs at [docs.bee.computer](https://docs.bee.computer/docs) (pages *Realtime Sync*, *Agentic Sync*, *Full Sync*, *API*), read on 2026-10-19.
> Each fact is marked **[doc]** (official docs), **[code]** (bee-cli source) or **[inferred]** (deduced from code behaviour, must be verified, see §6).

---

## 1. Live stream vs. history

| Aspect | Live stream (`bee stream --json`) | History (REST via bee-cli) |
|---|---|---|
| Delivery | Real-time, **at-most-once**; nothing is delivered for disconnected periods **[doc]** | Durable; any past conversation can be fetched **[doc]** |
| Replay / resume | None (no `Last-Event-ID`, no reconnect replay) **[doc]**; the CLI opens a single `fetch` with no retry **[code]** ([stream/index.ts](../../../resources/bee-cli/sources/commands/stream/index.ts)) | Pagination cursors and changefeed cursors **[doc][code]** |
| Utterance fields | `utterance.text`, `utterance.speaker`, `conversation_uuid` **[doc]** | `id`, `text`, `speaker`, `spoken_at`, `start`, `end`, `realtime`, `created_at` **[code]** |
| Conversation identity | `conversation_uuid` (string) **[doc]** | numeric `id`; `new-conversation` events carry both `id` and `uuid` **[doc]** |
| Timing | No time field; EXAMEN stamps `received_at` **[doc]**, see [FRICTION_LOG](../../../FRICTION_LOG.md) 2026-10-13 | Epoch-ms `spoken_at` per utterance, `start_time` / `end_time` per conversation **[code]** |
| Transcript quality | Realtime ASR | Final, non-realtime transcription when processing is done (`pickTranscription` prefers `realtime: false`, [conversations/index.ts:541-547](../../../resources/bee-cli/sources/resources/conversations/index.ts)) **[code]** |

---

## 2. Endpoints and CLI commands relevant to backfill

| Purpose | CLI | HTTP (through `bee proxy` or the public base URL) | Notes |
|---|---|---|---|
| List conversations | `bee conversations list --limit N --cursor C --json` | `GET /v1/conversations?limit=&cursor=&from=YYYY-MM-DD` | `from` is a **date** filter used by `bee sync --recent-days` (`recentDaysFrom`, [sync/index.ts](../../../resources/bee-cli/sources/commands/sync/index.ts)) **[code]**; the CLI `list` subcommand does **not** expose `from` **[code]**; no `to` parameter is known; ordering is newest first **[inferred]** from `bee now`, which stops paging once `created_at < since` ([now/index.ts](../../../resources/bee-cli/sources/commands/now/index.ts)) |
| Conversation detail | `bee conversations get <id> --json` | `GET /v1/conversations/{id}` | Returns all transcriptions with utterances, `state`, `start_time`, `end_time`, `short_summary`, `summary`, `primary_location`, `device_type` **[code]** |
| Bulk detail | — (only used internally by `bee sync`) | `POST /v1/conversations/batch` `{"ids": [...]}` | Chunks of 100 (`BATCH_DETAIL_SIZE`); ids can be **missing** from the response (replication lag) and must be retried one by one **[code]** |
| Transcript only | `bee conversations transcript <id> --since <epochMs> --json` | (client-side filter over the detail) | `--since` keeps utterances with `spoken_at ?? start >= since`; utterances without any timestamp are dropped **[code]** |
| Last 10 hours | `bee now --json` | list + detail | Conversations of the last 10 h (`WINDOW_HOURS = 10`) with utterances, **all transcriptions flattened** (realtime and final mixed) **[code]** |
| Changefeed | `bee changed --cursor C --json` | `GET /v1/changes?cursor=v1-<ms>` | Returns changed ids per type plus `since`, `until` and `next_cursor`; `bee changed` also hydrates each changed entity **[doc][code]**; cursors look like `v1-<epochMs>` but the docs say to treat them as opaque **[doc]** |
| Keyword / neural search | `bee search --query … --since --until` | `POST /v1/search/conversations[/neural]` | Not needed for backfill; useful for a later "find in history" feature |

### 2.1 Changefeed limits (inferred from `bee sync`)

`bee sync` treats any cursor older than **6 days** as stale (`PROACTIVE_FULL_MS`) and handles the server errors `cursor_too_old` / `invalid_cursor` by falling back to a full crawl ([sync/index.ts:28-31](../../../resources/bee-cli/sources/commands/sync/index.ts)). This points to a **~7-day server-side floor** on changefeed cursors **[inferred]**. `bee sync` also re-scans a **10-minute overlap** (`CHANGES_OVERLAP_MS`) to absorb commit-after-snapshot races and clock skew **[code]**.

**Consequence for EXAMEN:** the changefeed is fine for short catch-ups and for "did a conversation get its final transcript yet?" polling. It is not a primary source for multi-day windows. The **conversation list + detail** path has no such floor and is the primary source.

### 2.2 Conversation states

Conversations carry a `state` string. Observed values are `processing` and `processed` in the SSE examples, and `COMPLETED` in the Agentic Sync example **[doc]**. The docs do not list the full set. The backfill treats a conversation as **ready** only when:
- `end_time` is not null, **and**
- `state` is not a known in-progress value (`processing`, case-insensitive), **and**
- a final transcription (`realtime: false`) exists, **or** the conversation ended more than `BACKFILL_FINAL_TRANSCRIPT_GRACE_MINUTES` ago (default 30). After the grace period the realtime transcription is used as a fallback.

Non-ready conversations are **deferred** (see [03](03_backfill_engine.md) §6).

---

## 3. Payload shapes used by the backfill

Conversation detail (fields consumed; types from [conversations/index.ts](../../../resources/bee-cli/sources/resources/conversations/index.ts)):

```jsonc
{
  "conversation": {
    "id": 815,                       // numeric id (REST identity)
    "uuid": "…",                     // [inferred] present in detail: verify (daily detail exposes conversation_uuid)
    "start_time": 1760860800000,     // epoch ms
    "end_time":   1760864400000,     // null while open
    "state": "processed",
    "short_summary": "Lecture on limits and derivatives",
    "summary": "…",
    "primary_location": { "address": "…", "latitude": 45.06, "longitude": 7.66, "created_at": 1760860900000 },
    "transcriptions": [
      { "id": 1, "realtime": true,  "utterances": [ /* realtime ASR */ ] },
      { "id": 2, "realtime": false, "utterances": [
          { "id": 9001, "text": "Today we talk about limits.", "speaker": "speaker_1",
            "spoken_at": 1760860812000, "start": 1760860812000, "end": 1760860815000,
            "realtime": false, "created_at": 1760864500000 }
      ] }
    ]
  },
  "timezone": "Europe/Rome"
}
```

Timestamps can be epoch seconds or epoch milliseconds. bee-cli normalises them with `> 1e12 → ms`, `> 1e9 → s` ([now/index.ts](../../../resources/bee-cli/sources/commands/now/index.ts)). EXAMEN's `normalize_bee_time` ([stream_convo.py](../../../src/ingestion/stream_convo.py)) applies the same rule and is reused.

---

## 4. Access strategy: CLI subprocess first, HTTP later

EXAMEN already shells out to the bee binary (`BeeClient._build_cmd`), so authentication, proxy and token storage stay inside bee-cli. The backfill keeps that model:

| Option | Pros | Cons | Decision |
|---|---|---|---|
| **A. CLI subprocess** (`conversations list/get --json`) | Zero new auth code, same binary resolution as live, honours `bee login --proxy` | One process per call (~100–300 ms overhead), no batch endpoint, no `from` filter on `list` | **v1** |
| **B. `bee proxy` + `httpx`** (`httpx` is already a dependency) | Batch endpoint, `from` filter, connection reuse, ~10× fewer round trips on multi-day windows | EXAMEN must start/supervise a proxy (`bee proxy --socket`) or a token | **v2 optimisation**, behind the same `BeeHistorySource` interface |

`BeeHistorySource` (new, `src/ingestion/bee_history.py`):

```python
class BeeHistorySource(Protocol):
    async def list_conversations(self, since_ms: int, until_ms: int) -> List[BeeConversationSummary]: ...
    async def get_conversations(self, ids: List[int]) -> List[BeeConversationDetail]: ...

class CliBeeHistorySource:   # v1: pages `conversations list` until start_time < since_ms, then `get` each id (concurrency 4)
class ProxyBeeHistorySource: # v2: GET /v1/conversations?from=… + POST /v1/conversations/batch, per-id fallback
class FixtureBeeHistorySource:  # tests: JSON fixtures under tests/fixtures/bee_history/
```

Paging stops once a page's oldest `start_time ?? created_at` is older than `since_ms - BACKFILL_LOOKBACK_MARGIN` (default 6 h). The margin keeps long conversations that started before the window but overlap it. Concurrency is capped at **4**, matching `SYNC_CONCURRENCY` in bee-cli, to stay polite towards the Bee API, which documents no rate limits.

---

## 5. What the history does **not** give us

- **No per-utterance location.** Only `primary_location` per conversation. Every replayed utterance inherits it, which is coarser than live `update-location` fixes. The Event Engine's GPS rule R6 therefore fires only between conversations.
- **No diarization updates.** The final transcription already contains the settled speaker labels, which is an improvement over live.
- **No "user is speaker_0" guarantee.** Same heuristic as live (`speaker_0` → user).
- **No deletion signal in the list.** `delete-conversation` exists only on the stream. A conversation deleted on Bee after a backfill keeps its EXAMEN-derived entities (same limitation as `bee sync`, [doc]).

---

## 6. Open verifications (Phase 0 spike)

These must be captured with the physical device before Phase 3 and recorded in [FRICTION_LOG.md](../../../FRICTION_LOG.md):

| # | Question | Why it matters | How |
|---|---|---|---|
| V1 | Does `GET /v1/conversations/{id}` return the conversation `uuid`? | Maps live `conversation_uuid` to REST `id` for conversation-level coverage | `bee conversations get <id> --json \| jq '.conversation \| keys'` |
| V2 | Does the live `new-utterance` payload carry an utterance `id`, and does it equal the id of the matching utterance in the **realtime** transcription? | Would allow exact (id-based) dedup on the realtime transcription | Run `bee stream --json` and `bee conversations get` on the same conversation |
| V3 | Exact ordering of `GET /v1/conversations` and the behaviour of `from` (inclusive? `start_time` or `created_at`? which time zone?) | Planner paging stop condition | Compare `list` pages against known conversations |
| V4 | Full list of `state` values and when the final transcription appears | Readiness rule (§2.2) | Poll `get` on a fresh conversation every minute after it ends |
| V5 | Lag between speech and the realtime utterance appearing in REST | Margin between live coverage and backfill selection | Compare `received_at` (live) with `spoken_at` (REST) for the same sentence |
| V6 | Heartbeat cadence on the stream (`{"timestamp": …}` lines) | Coverage interval extension without speech | Log heartbeat intervals for 1 h |
