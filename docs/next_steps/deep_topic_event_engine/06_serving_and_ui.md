# 06 — Serving Layer, Alexa+ & Web UI

> Part of the [Deep Topic Event Engine](00_overview.md) specification.

---

## 1. REST API ([mcp_server.py](../../../src/serving/mcp_server.py))

| Method & path | Status | Description |
|---|---|---|
| `GET /api/sessions?status=&limit=` | Extend | Each item adds `segments` (summary: index, title, status, start/end, briefing_id), `conversation_uuids`, `final_briefing_id`, `last_transition` |
| `GET /api/sessions/{id}` | Extend | Full event: segments with embedded segment briefings, final briefing, linked micro-events, `transitions` audit log, `topic_profile.keywords` (top 10, no centroid) |
| `GET /api/sessions/{id}/chunks?segment_id=&since=&limit=` | New | Paginated transcript from `session_chunks` |
| `POST /api/sessions/{id}/conclude` | Keep | Manual R8. Now enqueues the final job instead of synthesizing inline (it currently blocks the request on the full synthesis) |
| `POST /api/sessions/{id}/pause` | New | Manual soft close: closes and synthesizes the current segment now (demo button "Synthesize now") |
| `POST /api/sessions/{id}/resume` | New | Forces R4 for a `PAUSED` event (overrides a wrong split decision while it is still possible) |
| `POST /api/sessions/{id}/split` `{ "at_chunk_id": "…" }` | New | Manual split: chunks from `at_chunk_id` onward move to a new event; both finals re-run (doc 03 §7) |
| `POST /api/sessions/merge` `{ "session_ids": ["a","b"] }` | New | Manual merge of **consecutive** events; segments concatenated, final re-run |
| `GET /api/topics?kind=&session_id=` | Extend | Filters by briefing `kind` and event; default unchanged |
| `POST /api/simulate` | Extend | `event_mode`, `timestamp`, `location`, `speaker_role` (doc 05 §4) |

All mutating endpoints return the updated event, and also broadcast SSE.

## 2. SSE events (`/api/events`)

Using the existing `broadcast_event` helper:

| Event | Payload | Emitted when |
|---|---|---|
| `event_opened` | event summary | R0 |
| `event_paused` | event summary + closed segment | R1/R2 |
| `event_resumed` | event summary + new segment | R4 |
| `segment_synthesizing` | `{session_id, segment_id}` | Job started |
| `segment_synthesized` | `{session_id, segment, briefing}` | Segment/checkpoint job done |
| `event_concluded` | event summary | R5–R9 (final job enqueued) |
| `event_final_ready` | `{session_id, final_briefing}` | Final job done (replaces today's `session_concluded`, which stays as an alias for one release) |
| `event_split` / `event_merged` | both event summaries | Manual operations, R9 |

---

## 3. MCP tools ([session_tools.py](../../../src/serving/tools/session_tools.py))

| Tool | Change |
|---|---|
| `get_session_dossier(session_id)` | When the final briefing is not ready yet, returns the **latest segment briefing** plus `status`, so Alexa can say "The lecture is still in progress; here is what was covered in the first part…" |
| `list_session_dossiers(status, limit)` | Adds `paused` status and a segment count |
| `get_live_event_outline()` — **new** | Current open event: title, segment titles, top keywords, elapsed time. Answers "Alexa, what is this lecture about so far?" with no LLM call |

Spoken-summary rules: segment titles are read in order ("First part: limits. Second part: derivatives."). Micro-events are summarized by count, as today.

### Echo Show `SESSION_DOSSIER_VIEWER`

The card payload gains:

```json
{
  "template": "SESSION_DOSSIER_VIEWER",
  "status": "paused",
  "segments": [
    {"index": 1, "title": "Limits and continuity", "time_range": "10:02–10:51", "status": "synthesized"},
    {"index": 2, "title": "Derivatives",            "time_range": "11:06–…",     "status": "open"}
  ],
  "explanatory_synthesis": "…final if ready, else latest segment…",
  "is_final": false
}
```

Update the static preview in `/api/cards/preview` ([mcp_server.py](../../../src/serving/mcp_server.py), `session_card`) to match.

---

## 4. Next.js Web UI ([src/web_ui/src/](../../../src/web_ui/src/))

### 4.1 Types ([types/schemas.ts](../../../src/web_ui/src/types/schemas.ts))

Add `SessionSegment`, `EventTransitionLog`, `BriefingKind`; extend `SessionDossier` / `BriefingReport` with the fields in [04](04_data_model_and_storage.md) §1.

### 4.2 `TopicDossiers.tsx` → event-centric view

```
┌ Topic Dossiers ─────────────────────────────── [Events] [All briefings] ┐
│ ● LIVE  Analysis I — limits & derivatives        Aula 7 · 10:02 → now     │
│   ├─ ① Limits and continuity      10:02–10:51  ✓ briefing  [open]          │
│   ├─ ☕ break 15 min (3 micro-events)                                       │
│   └─ ② Derivatives                11:06–…      ● recording                  │
│   [Synthesize now]  [Conclude]  [Split here…]                               │
├──────────────────────────────────────────────────────────────────────────┤
│ ✓ Database Systems — transactions                 09:00–09:55             │
│   ★ Final briefing   ① ACID basics  ② Isolation levels   [Merge with ↑]    │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Grouping:** briefings with `session_id` render inside their event card; `standalone` briefings render as today under "All briefings".
- **Status chips:** `● LIVE` (active), `⏸ PAUSED (resumes until hh:mm)` (paused, shows the hard-close deadline), `✓ CONCLUDED`, `⏳ FINAL PENDING`.
- **Segment timeline:** clicking a segment opens the existing `TopicDetailModal` with that segment's briefing; the final briefing is pinned at the top with a ★.
- **Decision audit drawer:** renders `transitions` ("10:51 paused: no on-topic speech for 4m30s"; "11:07 resumed: similarity 0.84 ≥ 0.78"). It matches the transparency style of the disambiguation audit drawer already in `ExecutiveDossierModal`.
- **Live updates:** subscribe to the SSE events in §2 via the existing `EventSource` in [page.tsx](../../../src/web_ui/src/app/page.tsx) and call `mutate()` on the sessions SWR key.

### 4.3 `AmbientSimulator.tsx`

- Add an **"Event mode"** toggle (sends `event_mode: true`) and a **virtual clock** control: "+1 min", "+5 min", "+30 min" buttons that call a small `POST /api/simulate/tick {seconds}` endpoint (demo profile only).
- Add a **scenario player** for the multi-turn scenarios of [07](07_implementation_plan_and_testing.md) (lecture with break, back-to-back lectures), with per-turn time offsets, so the whole lifecycle can be shown in the demo video.

### 4.4 `OverviewHub.tsx`

Show the live event (if any) as a compact banner: title, elapsed time, segment count, and a link to the event card.
