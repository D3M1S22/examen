# 04 — Data Model & Storage

> Part of the [Deep Topic Event Engine](00_overview.md) specification.
> All changes follow the repository rule: **backward-compatible schemas with defaults** and **non-blocking `ALTER TABLE` migrations** in `_init_db()` ([sqlite_store.py](../../../src/core/storage/sqlite_store.py)).

---

## 1. Pydantic models ([schemas.py](../../../src/core/schemas.py))

### 1.1 New models

```python
class SessionSegment(BaseModel):
    segment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    index: int                                            # 1-based order inside the event
    kind: Literal["segment", "checkpoint"] = "segment"
    start_time: str                                       # ISO, utterance time of first chunk
    end_time: Optional[str] = None                        # ISO, utterance time of last chunk
    first_chunk_id: Optional[str] = None
    last_chunk_id: Optional[str] = None
    word_count: int = 0
    title: Optional[str] = None                           # from synthesis
    status: Literal["open", "closed", "synthesizing", "synthesized", "skipped", "failed"] = "open"
    close_reason: Optional[str] = None                    # soft_timeout | explicit_cue | checkpoint | location_shift | topic_drift | manual
    briefing_id: Optional[str] = None


class TopicProfile(BaseModel):                            # see doc 02 §2
    centroid: Optional[List[float]] = None
    centroid_weight: float = 0.0
    keywords: Dict[str, float] = Field(default_factory=dict)
    segment_titles: List[str] = Field(default_factory=list)
    bee_titles: List[str] = Field(default_factory=list)
    language: Optional[str] = None
    updated_at: Optional[str] = None


class EventTransitionLog(BaseModel):                      # audit trail for UI + debugging
    at: str
    from_status: Optional[str]
    to_status: str
    rule: str                                             # R0..R9
    reason: str                                           # machine-readable reason
    detail: Optional[str] = None                          # e.g. "similarity=0.41 (<0.55)", LLM rationale
```

### 1.2 `SessionDossier` (evolved into the Event)

Existing fields are kept. Additions (all with defaults):

```python
status: Literal["active", "paused", "finalizing", "concluded"]   # "finalizing" = legacy alias of "paused"
conversation_uuids: List[str] = []           # Bee conversations spanned
segments: List[SessionSegment] = []
topic_profile: Optional[TopicProfile] = None
anchor_location: Optional[dict] = None       # median of first-segment fixes (doc 01 §4.2)
last_on_topic_at: Optional[str] = None
paused_at: Optional[str] = None
hard_close_deadline: Optional[str] = None    # set by closing cue / transit
final_status: Literal["none", "pending", "synthesizing", "ready", "failed"] = "none"   # drives rehydration + UI
pending_chunk_ids: List[str] = []            # pending window while PAUSED (doc 02 §4)
research_ledger: List[dict] = []             # [{"query": str, "sources": [url]}]
final_revision: int = 0
transitions: List[EventTransitionLog] = []
```

- `session_id` now holds the **engine-minted event id**. Legacy rows keep their Bee uuid as id, which is harmless.
- `domain` is filled in at the first segment synthesis from `TopicExtraction.context_type` (`academic_lecture` → `lecture`, `general_meeting` → `meeting`, `feature_discussion`/`tech_stack`/`bug`/`system_incident` → `technical_debate`).
- `transcript_chunks: List[str]` is **deprecated**: kept in the model for API compatibility, but populated on read from `session_chunks` (capped, e.g. last 200 chunks) and no longer written per utterance (fixes audit finding #12).

### 1.3 `BriefingReport`

```python
session_id: Optional[str] = None
segment_id: Optional[str] = None
kind: Literal["standalone", "segment", "checkpoint", "final"] = "standalone"
```

`list_topic_briefings()` and `/api/topics` keep returning everything by default; a `kind` filter is added ([06](06_serving_and_ui.md)).

### 1.4 `UtteranceChunk` / chunk metadata

```python
timestamp: str               # existing; becomes "best known utterance time" (see doc 05 §1)
received_at: Optional[str]   # wall-clock receive time at BeeClient
spoken_at: Optional[str]     # from Bee if ever available
categories: List[str] = []   # gatekeeper result, filled after screening
```

---

## 2. SQLite migrations

```sql
-- 2.1 Per-chunk log (replaces transcript_chunks_json rewrites)
CREATE TABLE IF NOT EXISTS session_chunks (
    chunk_id        TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    segment_id      TEXT,                 -- NULL while pending / off-segment
    conversation_uuid TEXT,
    ts              TEXT NOT NULL,        -- utterance time (ISO)
    text            TEXT NOT NULL,
    word_count      INTEGER NOT NULL DEFAULT 0,
    speaker_id      TEXT,
    speaker_role    TEXT,
    categories_json TEXT,                 -- gatekeeper categories
    on_topic        INTEGER NOT NULL DEFAULT 0,
    location_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_chunks_session_ts ON session_chunks (session_id, ts);
CREATE INDEX IF NOT EXISTS idx_session_chunks_segment    ON session_chunks (segment_id);

-- 2.2 Event fields on session_dossiers (non-blocking ALTERs, each in try/except like today)
ALTER TABLE session_dossiers ADD COLUMN conversation_uuids_json TEXT;
ALTER TABLE session_dossiers ADD COLUMN segments_json TEXT;
ALTER TABLE session_dossiers ADD COLUMN topic_profile_json TEXT;
ALTER TABLE session_dossiers ADD COLUMN anchor_location_json TEXT;
ALTER TABLE session_dossiers ADD COLUMN last_on_topic_at TEXT;
ALTER TABLE session_dossiers ADD COLUMN paused_at TEXT;
ALTER TABLE session_dossiers ADD COLUMN hard_close_deadline TEXT;
ALTER TABLE session_dossiers ADD COLUMN pending_chunk_ids_json TEXT;
ALTER TABLE session_dossiers ADD COLUMN research_ledger_json TEXT;
ALTER TABLE session_dossiers ADD COLUMN final_status TEXT NOT NULL DEFAULT 'none';
ALTER TABLE session_dossiers ADD COLUMN final_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE session_dossiers ADD COLUMN transitions_json TEXT;

-- 2.3 Briefing linkage
ALTER TABLE topic_briefings ADD COLUMN session_id TEXT;
ALTER TABLE topic_briefings ADD COLUMN segment_id TEXT;
ALTER TABLE topic_briefings ADD COLUMN kind TEXT NOT NULL DEFAULT 'standalone';
CREATE INDEX IF NOT EXISTS idx_briefings_session ON topic_briefings (session_id, kind);

-- 2.4 Global search cache (doc 03 §4)
CREATE TABLE IF NOT EXISTS web_search_cache (
    query_norm   TEXT PRIMARY KEY,
    provider     TEXT,
    results_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);
```

**Why `segments_json` and not a `session_segments` table:** an event has a handful of segments, they are always read with the event, and the UI needs them together. Chunks, by contrast, are numerous and append-only, so they get their own table.

**FTS:** if the `topic_briefings` FTS5 index is maintained by triggers, no change is needed. New columns are not searchable text. `session_chunks.text` is **not** FTS-indexed in this iteration (privacy and size); search goes through briefings.

### 2.5 Legacy data migration (one-off, idempotent, at startup)

1. `status = 'finalizing'` → `'paused'` with `paused_at = last_updated_at`.
2. For rows with `transcript_chunks_json` and no `session_chunks`: insert chunks with synthetic ids (`legacy-<session>-<i>`), `ts = start_time`, `segment_id = NULL`.
3. Leave `final_briefing_id` as is. Do not try to reconstruct segments for legacy rows.

---

## 3. Store API ([base.py](../../../src/core/storage/base.py) → [sqlite_store.py](../../../src/core/storage/sqlite_store.py))

New abstract methods (the DynamoDB / AgentCore Memory backends implement them later):

```python
# chunks
def append_session_chunk(self, chunk: UtteranceChunk, session_id: str,
                         segment_id: Optional[str], on_topic: bool) -> None
def list_session_chunks(self, session_id: str, *, segment_id: Optional[str] = None,
                        since: Optional[str] = None, limit: Optional[int] = None) -> List[UtteranceChunk]
def assign_chunks_to_segment(self, chunk_ids: List[str], session_id: str, segment_id: str) -> None
def move_chunks_to_session(self, chunk_ids: List[str], target_session_id: str) -> None   # split/merge

# events
def get_open_event(self) -> Optional[SessionDossier]            # most recent active|paused
def list_events(self, status: Optional[str] = None, limit: int = 10) -> List[SessionDossier]
def append_event_transition(self, session_id: str, log: EventTransitionLog) -> None

# briefings
def list_briefings_for_session(self, session_id: str) -> List[BriefingReport]

# cache
def get_cached_search(self, query_norm: str, max_age_seconds: int) -> Optional[list]
def put_cached_search(self, query_norm: str, provider: str, results: list) -> None
```

Changed behaviour:
- `append_chunk_to_session` becomes a thin compatibility wrapper over `append_session_chunk`. It **refuses** to append to a `concluded` event: it logs a warning and returns the dossier unchanged, which fixes audit finding #7. The engine never calls it on concluded events anyway.
- `conclude_session_dossier` stays, but is only called by the engine (R5–R9) and by the manual endpoint, **never by `node_persist`**.
- `save_topic_briefing` persists `session_id`, `segment_id` and `kind`.
