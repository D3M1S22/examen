# 04 — Data Model, REST/SSE/MCP Contracts & UI

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> Follows the repository rules: Pydantic V2 contracts in [schemas.py](../../../src/core/schemas.py), backward-compatible defaults, non-blocking `ALTER TABLE` migrations in `_init_db()` ([sqlite_store.py](../../../src/core/storage/sqlite_store.py)), and storage access only through `AbstractContextStore`.

---

## 1. Pydantic models

### 1.1 New models

```python
IngestSource = Literal["live", "backfill", "simulator"]

class CoverageInterval(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: Literal["live", "backfill"]
    start: str                      # ISO
    end: str                        # ISO, advanced while open
    is_open: bool = False
    degraded: bool = False          # 02 §2.1
    run_id: Optional[str] = None    # backfill only
    utterances: int = 0
    errors: int = 0

class CoverageGap(BaseModel):
    start: str
    end: str
    seconds: float

class BackfillEstimate(BaseModel):
    gatekeeper_calls: int = 0
    expected_qualified: int = 0
    events_expected: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0

class BackfillPlan(BaseModel):             # = the preview
    window_from: str
    window_to: str
    mode: Literal["gaps_only"] = "gaps_only"   # "force" reserved (05 §4)
    retry_failed_live: bool = True
    coverage: Dict[str, float]               # live_seconds / backfill_seconds / gap_seconds
    gaps: List[CoverageGap] = []
    conversations: Dict[str, int]            # total / ready / deferred / fully_covered / to_process
    utterances: Dict[str, int]               # total / duplicate_live / selected / retry_failed
    estimate: BackfillEstimate
    warnings: List[str] = []                 # e.g. "ledger retention exceeded before 2026-10-05"

class BackfillRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trigger: Literal["startup", "reconnect", "manual", "deferred_recheck"]
    window_from: str
    window_to: str
    status: Literal["planned", "fetching", "replaying", "synthesizing",
                    "completed", "partial", "failed", "cancelled"] = "planned"
    plan: Optional[BackfillPlan] = None
    counters: Dict[str, int] = {}            # processed / qualified / skipped / failed / events / actions / contacts / tasks
    last_source_key: Optional[str] = None    # checkpoint (03 §5)
    last_ts: Optional[str] = None
    deferred_conversation_ids: List[int] = []
    error: Optional[str] = None
    requested_by: Optional[str] = None       # demo user id for manual runs
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
```

### 1.2 Changes to existing models (all defaulted)

| Model | New fields |
|---|---|
| `VerifiedAction`, `PlannedTask`, `SocialEntity`, `BriefingReport`, `SessionDossier` | `ingest_source: IngestSource = "live"`, `ingest_run_id: Optional[str] = None` |
| `VerifiedAction`, `PlannedTask` | `source_key: Optional[str] = None` (idempotency, [02](02_coverage_and_deduplication.md) §5), `occurred_at: Optional[str] = None` |
| `PlannedTask` | `recovered: bool = False` (created by backfill after its `scheduled_time` had already passed) |
| `UtteranceChunk` | `source_key: Optional[str] = None`, `bee_conversation_id: Optional[int] = None` |
| `ExamenState` | `source_key`, `ingest_source`, `ingest_run_id` |

`PlannedTask.origin` (`manual` / `ambient_voice` / `social_commitment`) keeps its meaning: it says *how* a task arose. `ingest_source` says *which ingestion path* produced it. The two are orthogonal.

---

## 2. SQLite

```sql
CREATE TABLE IF NOT EXISTS ingest_coverage (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,              -- live | backfill
    start_ts    TEXT NOT NULL,
    end_ts      TEXT NOT NULL,
    is_open     INTEGER NOT NULL DEFAULT 0,
    degraded    INTEGER NOT NULL DEFAULT 0,
    run_id      TEXT,
    utterances  INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_coverage_time ON ingest_coverage (start_ts, end_ts);

CREATE TABLE IF NOT EXISTS ingest_ledger (
    source_key            TEXT PRIMARY KEY,
    source                TEXT NOT NULL,    -- live | backfill
    bee_conversation_uuid TEXT,
    bee_conversation_id   INTEGER,
    ts                    TEXT NOT NULL,
    received_at           TEXT,
    text_norm             TEXT,
    text_hash             TEXT NOT NULL,
    status                TEXT NOT NULL,    -- screened_noop | qualified | failed | skipped_duplicate | skipped_out_of_window
    categories_json       TEXT,
    run_id                TEXT
);
CREATE INDEX IF NOT EXISTS idx_ledger_hash_time ON ingest_ledger (text_hash, received_at);
CREATE INDEX IF NOT EXISTS idx_ledger_ts        ON ingest_ledger (ts);
CREATE INDEX IF NOT EXISTS idx_ledger_status    ON ingest_ledger (status);

CREATE TABLE IF NOT EXISTS bee_conversation_map (
    uuid          TEXT PRIMARY KEY,
    id            INTEGER,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backfill_runs (
    id           TEXT PRIMARY KEY,
    trigger      TEXT NOT NULL,
    window_from  TEXT NOT NULL,
    window_to    TEXT NOT NULL,
    status       TEXT NOT NULL,
    plan_json    TEXT,
    counters_json TEXT,
    last_source_key TEXT,
    last_ts      TEXT,
    deferred_json TEXT,
    error        TEXT,
    requested_by TEXT,
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_backfill_runs_status ON backfill_runs (status, created_at DESC);

-- Provenance (non-blocking ALTERs, each in try/except like today)
ALTER TABLE verified_actions  ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';
ALTER TABLE verified_actions  ADD COLUMN ingest_run_id TEXT;
ALTER TABLE verified_actions  ADD COLUMN source_key TEXT;
ALTER TABLE verified_actions  ADD COLUMN occurred_at TEXT;
ALTER TABLE planned_tasks     ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';
ALTER TABLE planned_tasks     ADD COLUMN ingest_run_id TEXT;
ALTER TABLE planned_tasks     ADD COLUMN source_key TEXT;
ALTER TABLE planned_tasks     ADD COLUMN occurred_at TEXT;
ALTER TABLE planned_tasks     ADD COLUMN recovered INTEGER NOT NULL DEFAULT 0;
ALTER TABLE social_contacts   ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';
ALTER TABLE social_contacts   ADD COLUMN ingest_run_id TEXT;
ALTER TABLE topic_briefings   ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';
ALTER TABLE topic_briefings   ADD COLUMN ingest_run_id TEXT;
ALTER TABLE session_dossiers  ADD COLUMN ingest_source TEXT NOT NULL DEFAULT 'live';
ALTER TABLE session_dossiers  ADD COLUMN ingest_run_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_actions_source_key ON verified_actions (source_key) WHERE source_key IS NOT NULL;
```

### 2.1 Store API ([base.py](../../../src/core/storage/base.py) → [sqlite_store.py](../../../src/core/storage/sqlite_store.py))

```python
# coverage
def open_coverage_interval(self, source: str, start: str, run_id: Optional[str] = None) -> CoverageInterval
def extend_coverage_interval(self, interval_id: str, end: str, utterances: int = 0, errors: int = 0) -> None
def close_coverage_interval(self, interval_id: str, end: str, degraded: bool = False) -> None
def list_coverage(self, start: str, end: str) -> List[CoverageInterval]
def last_coverage_end(self) -> Optional[str]

# ledger
def record_ingested_utterance(self, entry: dict) -> None                   # upsert on source_key
def find_live_matches(self, text_hash: str, t_from: str, t_to: str) -> List[dict]
def find_live_fuzzy_candidates(self, t_from: str, t_to: str) -> List[dict]
def has_backfill_entry(self, source_key: str) -> bool
def purge_ingest_ledger(self, before: str) -> int
def map_bee_conversation(self, uuid: str, conv_id: int) -> None

# runs
def save_backfill_run(self, run: BackfillRun) -> None
def get_backfill_run(self, run_id: str) -> Optional[BackfillRun]
def list_backfill_runs(self, status: Optional[str] = None, limit: int = 20) -> List[BackfillRun]

# changed signatures (defaults keep current behaviour)
def get_open_event(self, ingest_source: str = "live", run_id: Optional[str] = None) -> Optional[SessionDossier]
def list_events_pending_final(self, limit: int = 20, ingest_source: Optional[str] = None,
                              run_id: Optional[str] = None) -> List[SessionDossier]
def match_and_resolve_task(self, action: VerifiedAction) -> Optional[PlannedTask]   # + temporal guard (03 §4.1)
```

[scripts/reset_db.py](../../../scripts/reset_db.py) and `POST /api/auth/gdpr-purge` must clear `ingest_coverage`, `ingest_ledger`, `bee_conversation_map` and `backfill_runs`.

---

## 3. REST endpoints ([mcp_server.py](../../../src/serving/mcp_server.py))

| Method & path | Body / query | Response |
|---|---|---|
| `GET /api/backfill/coverage` | `from`, `to` (ISO; default last 7 days), `bucket=hour\|day` | `{intervals: [CoverageInterval], gaps: [CoverageGap], buckets: [{start, live_s, backfill_s, gap_s, bee_conversations}]}` |
| `POST /api/backfill/preview` | `{from, to, retry_failed_live?: bool}` | `BackfillPlan` (REST calls to Bee only, cached 5 min) |
| `POST /api/backfill/runs` | `{from, to, retry_failed_live?, confirm_over_budget?, user_id?}` | `202 {run: BackfillRun}`; `409` if the window overlaps a queued or running run; `422` if `to` > start of the current live interval or the window exceeds `BACKFILL_MAX_WINDOW_DAYS`; `422 {"error": "over_budget", "estimate": …}` when a budget guard is exceeded without `confirm_over_budget` |
| `GET /api/backfill/runs` | `status?`, `limit?` | `{runs: [BackfillRun]}` |
| `GET /api/backfill/runs/{id}` | — | `BackfillRun` + `links: {events: [...], actions: n, contacts: n, tasks: n}` |
| `POST /api/backfill/runs/{id}/cancel` | `{discard_events?: bool}` | `BackfillRun` |
| `GET /api/backfill/settings` | — | Effective `BACKFILL_*` settings (read-only in v1) |

Existing endpoints:
- `GET /api/orchestrator/status` and `GET /api/status` gain `coverage: {live_since, last_gap: CoverageGap \| null, uncovered_seconds_7d}` and `backfill: {active_run: {id, status, progress} \| null, queued: n}`.
- `GET /api/actions`, `/api/routines`, `/api/contacts`, `/api/topics`, `/api/sessions` accept `ingest_source=` and `ingest_run_id=` filters and return the new fields.

### 3.1 SSE events (`/api/events`)

| Type | Payload | When |
|---|---|---|
| `backfill_queued` | `{run_id, trigger, window_from, window_to}` | Run created |
| `backfill_started` | same + `plan` summary | Leaves `planned` |
| `backfill_progress` | `{run_id, status, processed, selected, qualified, events, eta_s}` | Throttled, at most every 2 s |
| `backfill_completed` | `{run_id, status, counters, window_from, window_to}` | `completed` / `partial` |
| `backfill_failed` | `{run_id, error}` | `failed` |
| `coverage_gap_detected` | `CoverageGap` | Reconnect with a hole ≥ `BACKFILL_MIN_GAP_SECONDS` (shown even if auto-backfill is off) |

The names avoid the substrings used by the UI cache router ([03](03_backfill_engine.md) §4.2). A dedicated `eventType.startsWith("backfill_")` branch in `page.tsx` revalidates every SWR key once on `backfill_completed`.

### 3.2 MCP tool (optional, Alexa+)

`get_ingestion_coverage(day: str = "today")` → spoken summary such as *"I was offline yesterday from 1 PM to 8 PM; those conversations were recovered this morning: 2 actions, 1 new contact, 1 lecture dossier."* Uses a new `INGESTION_COVERAGE_CARD` template (timeline bar + recovered counters). It is not required for v1.

---

## 4. Web UI (`src/web_ui/`)

### 4.1 Placement

- **Overview Hub → new "History Sync" card** ([OverviewHub.tsx](../../../src/web_ui/src/components/views/OverviewHub.tsx)): a 7-day coverage strip, the last gap, and a primary button **"Analyse past period…"** that opens the modal.
- **System Bar badge** ([SystemBar.tsx](../../../src/web_ui/src/components/SystemBar.tsx)): `HISTORY: SYNCED` (green) · `HISTORY: GAP 6h 53m` (amber, clickable → modal) · `HISTORY: RECOVERING 42%` (blue, pulsing).
- **Provenance badge** `⏪ Recovered` on action, routine, contact, dossier and event cards whose `ingest_source === "backfill"`, with the original time (`occurred_at`).

### 4.2 `BackfillModal` (new, `components/ui/BackfillModal.tsx`)

```
┌─ ANALYSE PAST PERIOD ─────────────────────────────────────────────── ✕ ┐
│ Range  [ Last 24 h ] [ Last 3 days ] [ Last 7 days ] [ Custom ▾ ]      │
│        From 2026-10-17 00:00   To 2026-10-19 09:00                     │
│                                                                        │
│ Coverage  ▕██████████░░░░░░░██████████████▒▒▒▒████████████████▏        │
│           █ analysed live   ▒ recovered   ░ gap   · no Bee data        │
│                                                                        │
│ [ ✓ Retry failed live utterances ]                                     │
│                                                    [ Preview (free) ]  │
├────────────────────────────────────────────────────────────────────────┤
│ 37 conversations · 22 already analysed · 12 to analyse · 3 not ready   │
│ 5 120 utterances · 3 410 skipped (seen live) · 1 630 to screen         │
│ Estimated: ~160 qualified · ~2 events · ≈ $0.02 · ≈ 6 min              │
│ ⚠ 3 conversations are still being processed by Bee, retried later    │
│                                          [ Cancel ]  [ Run analysis ]  │
├────────────────────────────────────────────────────────────────────────┤
│ Running ▓▓▓▓▓▓▓▓░░░░░░  replaying 812/1630 · 74 qualified · ETA 3 min  │
│                                                 [ Stop after current ] │
├────────────────────────────────────────────────────────────────────────┤
│ Recent runs                                                            │
│  ✓ 19 Oct 09:12 startup   18 Oct 13:02–19:55   2 actions · 1 dossier  │
│  ◐ 18 Oct 21:40 reconnect partial (4 failed)          [ Retry ]       │
└────────────────────────────────────────────────────────────────────────┘
```

Behaviour:
- **Preview is mandatory before Run.** *Run analysis* stays disabled until a preview exists for the current range. A changed range invalidates the preview.
- The coverage strip comes from `GET /api/backfill/coverage?bucket=hour` (≤ 7 days) or `bucket=day`. Hovering a bucket shows its exact intervals.
- Progress comes from SSE `backfill_progress`, falling back to polling `GET /api/backfill/runs/{id}` every 3 s when SSE is down. The modal can be closed; the badge keeps the progress visible.
- Over-budget previews show the estimate in amber and require ticking *"I understand this will cost about $X"*, which sends `confirm_over_budget`.
- Following the UI rules in `.agents/rules/`: no layout flicker on progress updates, scroll position preserved, optimistic *Stop* with rollback on error, and all colours through the existing theme tokens.

### 4.3 Types (`src/web_ui/src/types/schemas.ts`)

Mirror `CoverageInterval`, `CoverageGap`, `BackfillPlan`, `BackfillRun`, and add `ingest_source?`, `ingest_run_id?`, `occurred_at?`, `recovered?` to the existing entity interfaces.

---

## 5. Configuration ([config.py](../../../src/core/config.py), `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `BACKFILL_ENABLED` | `true` | Master switch |
| `BACKFILL_AUTO_ON_STARTUP` | `true` | Startup catch-up ([03](03_backfill_engine.md) §6) |
| `BACKFILL_AUTO_ON_RECONNECT` | `true` | Reconnect catch-up |
| `BACKFILL_LOOKBACK_DAYS` | `2` | Max age of automatic catch-up |
| `BACKFILL_FIRST_RUN_DAYS` | `0` | Catch-up when no coverage exists yet (0 = off) |
| `BACKFILL_STARTUP_DELAY_SECONDS` | `60` | |
| `BACKFILL_MIN_GAP_SECONDS` | `60` | Ignore smaller holes in auto-triggers |
| `BACKFILL_RECONNECT_DEBOUNCE_SECONDS` / `BACKFILL_RECONNECT_DELAY_SECONDS` | `600` / `900` | |
| `BACKFILL_MAX_WINDOW_DAYS` | `14` | Manual window cap |
| `BACKFILL_MAX_UTTERANCES_PER_RUN` / `BACKFILL_MAX_ESTIMATED_COST_USD` | `20000` / `1.00` | Budget guards |
| `BACKFILL_SCREEN_CONCURRENCY` | `4` | Parallel gatekeeper calls |
| `BACKFILL_SCREEN_WITH_EVENT_HINT` | `false` | Sequential screening with event hint ([03](03_backfill_engine.md) §3) |
| `BACKFILL_MATCH_WINDOW_SECONDS` / `BACKFILL_SPAN_MERGE_SECONDS` / `BACKFILL_FUZZY_THRESHOLD` | `300` / `20` / `0.6` | Dedup ([02](02_coverage_and_deduplication.md) §4) |
| `BACKFILL_FINAL_TRANSCRIPT_GRACE_MINUTES` | `30` | Readiness ([01](01_bee_history_sources.md) §2.2) |
| `BACKFILL_ENRICH_CONTACTS_PER_RUN` | `10` | Web profiler cap |
| `BACKFILL_LEDGER_RETENTION_DAYS` | `14` | Ledger retention |
| `BACKFILL_HISTORY_TRANSPORT` | `cli` | `cli` \| `proxy` ([01](01_bee_history_sources.md) §4) |
| `COVERAGE_FLUSH_SECONDS` / `COVERAGE_DEGRADED_ERROR_RATE` | `30` / `0.2` | Live coverage tracking |
