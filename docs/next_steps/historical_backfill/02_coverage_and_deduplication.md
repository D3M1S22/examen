# 02 — Coverage Ledger, Gap Detection & De-duplication

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> Answers two questions: **"what has EXAMEN already analysed?"** and **"which Bee utterances still need analysis?"**

---

## 1. Why connection time alone is not enough

The simplest model is *"the stream was connected from 09:00 to 12:00, so everything spoken then was analysed"*. It is wrong in three common cases:

| Case | What happens | Consequence of trusting connection time |
|---|---|---|
| **Delayed upload** | The wearer's phone is offline. Bee buffers audio and uploads it later. Utterances with `spoken_at` = 10:00 may never reach the live stream, or arrive after a reconnect. | Utterances inside a "covered" interval are silently skipped |
| **Pipeline failure** | The stream delivered the utterance but the gatekeeper or Bedrock call failed (throttling, credentials, network) | Received ≠ analysed |
| **Dead connection not yet detected** | The stream stalls; the 330 s read timeout ([stream_convo.py:127](../../../src/ingestion/stream_convo.py)) eventually fires | Up to 5.5 min of false coverage per stall |

The design therefore separates:

- **Coverage intervals**: a cheap, approximate *hypothesis* of when EXAMEN was listening. Used for gap detection, auto-triggers and the UI timeline.
- **The utterance ledger**: the *evidence* of what was actually received and analysed. Used for the final, per-utterance de-duplication.

---

## 2. Coverage intervals

### 2.1 Live intervals

Maintained by a new `CoverageTracker` owned by `BeeStreamOrchestrator`:

| Stream signal | Action |
|---|---|
| `bee stream` subprocess spawned and first line read (any event, including `connected` or a heartbeat) | Open interval `[t, t]`, `source="live"` |
| Any line (utterance, heartbeat, conversation, location) | `last_alive_at = t` |
| Every `COVERAGE_FLUSH_SECONDS` (30 s) | Persist `end = last_alive_at` |
| Read timeout / EOF / cancellation / exception | Close interval at `last_alive_at` (**not** at the detection time) |
| Process crash | The interval keeps its last persisted `end`, at most 30 s short |

All times are wall-clock. Intervals are **conservative** (they end at the last proof of life), so the error always goes towards *"not covered"*. The utterance ledger (§3) then prevents the resulting overlap from producing duplicates.

A live interval is marked `degraded` (shown in amber in the UI, still counted as covered) when the gatekeeper or pipeline error rate inside it exceeds `COVERAGE_DEGRADED_ERROR_RATE` (default 20 %). Failed utterances are individually retryable (§3.3).

### 2.2 Backfill intervals

When a backfill run commits a gap (all selected utterances processed or explicitly skipped), it writes `source="backfill"` intervals with `run_id`. Re-running the same window then finds no gap.

### 2.3 Gap computation

```
gaps(window) = window − ⋃ { [i.start − M_before, i.end + M_after] | i ∈ coverage, i.source ∈ {live, backfill} }
```

- `M_before = 0`, `M_after = 0` for **gap detection** (UI, auto-triggers). Gaps are reported as-is.
- The utterance selection (§4) never relies on intervals alone. It always runs the ledger match on every candidate utterance whose time falls within `BACKFILL_MATCH_WINDOW_SECONDS` of a live interval boundary, and on every utterance inside a live interval whose conversation shows **unmatched** realtime utterances (delayed upload).

Gaps shorter than `BACKFILL_MIN_GAP_SECONDS` (default 60 s) are ignored by the **auto-triggers** only. Manual runs always consider every gap.

---

## 3. The utterance ledger

### 3.1 What is recorded

Every utterance that reaches `process_incoming_utterance` ([orchestrator.py](../../../src/ingestion/orchestrator.py)) is recorded **regardless of the gatekeeper outcome**, so `noop` utterances are recorded too. Backfill records every utterance it selects or skips.

| Field | Live | Backfill |
|---|---|---|
| `source_key` (PK) | `live:{conversation_uuid}:{chunk_id}` | `bee:{conversation_id}:{transcription_id}:{utterance_id}` |
| `source` | `live` | `backfill` |
| `bee_conversation_uuid` / `bee_conversation_id` | uuid (id once mapped via `new-conversation`) | id (uuid if V1 confirms it) |
| `ts` | best-known time (`spoken_at > received_at`) | `spoken_at ?? start` |
| `received_at` | wall clock at `BeeClient` | null |
| `text_norm` | normalised text, max 300 chars (lower-case, no punctuation, collapsed spaces) | same |
| `text_hash` | sha256 of `text_norm` | same |
| `status` | `screened_noop` · `qualified` · `failed` | same + `skipped_duplicate` · `skipped_out_of_window` |
| `run_id` | null | backfill run id |
| `categories_json` | gatekeeper categories | same |

`text_norm` is stored because fuzzy matching (§4.2) needs it. Privacy rules apply:
- Retention: rows older than `BACKFILL_LEDGER_RETENTION_DAYS` (default 14) are purged by a daily housekeeping task in `BackfillService` (the store has no retention mechanism today, so a new `purge_ingest_ledger(before)` method is needed). Beyond that horizon, backfill falls back to coverage intervals only and the UI says so.
- `POST /api/auth/gdpr-purge` also truncates the ledger and the coverage table.

### 3.2 Live conversation id mapping

> **2026-10-19:** the REST detail has no `uuid` (V1). The map can be filled from `new-utterance-chunks` (numeric `conversation_id` + utterance ids) and, for history, from `bee daily find <date>` (`conversations[].{id, conversation_uuid}`). See [10](../../10_bee_cli_reference.md) §8.

The live stream knows `conversation_uuid`. `new-conversation` events carry both `id` and `uuid`, and the Event Engine already builds this map in memory (`EventEngine._bee_conv_ids`, [event_engine.py](../../../src/ingestion/event_engine.py)). The orchestrator persists it into `bee_conversation_map(uuid, id, first_seen_at)` so the planner can tell which REST conversations live has seen at all. If V1 ([01](01_bee_history_sources.md) §6) confirms that the REST detail returns `uuid`, the map is also filled from history.

### 3.3 Failed live utterances

`status="failed"` rows are **not** considered analysed. A manual run in *gaps only* mode includes them by default (UI toggle *"Retry failed live utterances"*). Because the live row and the REST utterance are matched by §4, the retried result replaces the failure instead of adding to it.

---

## 4. Utterance selection algorithm (planner)

Input: the requested window `W`, the conversations overlapping it (from [01](01_bee_history_sources.md) §4), the coverage intervals and the ledger.

```
for conv in conversations overlapping W (ordered by start_time):
    if not ready(conv):                       → defer(conv)                 # 01 §2.2
    final   = final transcription (realtime=false) or realtime fallback
    rt      = realtime transcription (may be missing)

    # 1. Evidence: which parts of the conversation did live actually see?
    seen_spans = []
    for r in rt.utterances:
        if ledger.match_live(r):               # §4.2, exact on realtime text
            seen_spans.append([r.start, r.end])
    seen_spans = merge(seen_spans, tolerance=BACKFILL_SPAN_MERGE_SECONDS)   # default 20 s

    for u in final.utterances (sorted by spoken_at ?? start, id):
        t = u.spoken_at ?? u.start
        if t is None or t ∉ W:                 → skip (out_of_window)
        elif ledger.has_backfill(u.source_key): → skip (already backfilled)
        elif overlaps(u, seen_spans):          → skip (duplicate_live)
        elif rt is None and ledger.match_live_fuzzy(u):  → skip (duplicate_live)
        else:                                  → select(u)
```

### 4.1 Why match on the realtime transcription

The live stream emits **realtime ASR** text. The REST realtime transcription is the same ASR output, so an exact match on normalised text inside a time window is reliable and cheap. The final transcription is better for analysis, but its segmentation and wording differ, so it cannot be matched one-to-one. The matched realtime utterances are therefore turned into **time spans**, and the final utterances are selected by span overlap. This handles the cases that matter:

- **Fully live conversation** → every final utterance overlaps a seen span → skipped.
- **Conversation started live, then the server went down** → only the tail is selected.
- **Delayed upload** inside a "covered" interval → no realtime utterance matches → selected.

### 4.2 Live match rules

`match_live(r)` is true when a ledger row with `source="live"` exists such that:
1. `text_hash` equals `sha256(norm(r.text))`, **and**
2. `received_at ∈ [t(r) − 10 s, t(r) + BACKFILL_MATCH_WINDOW_SECONDS]` (default 300 s; V5 calibrates it), **and**
3. if both sides know the conversation (uuid/id mapped) they agree.

`match_live_fuzzy(u)`, used only when no realtime transcription is returned, is token Jaccard ≥ `BACKFILL_FUZZY_THRESHOLD` (default 0.6) under the same time constraint. If V2 shows that live utterance ids equal realtime utterance ids, rule 1 becomes an id equality and the fuzzy path is kept only as a fallback.

### 4.3 Planner output (the preview)

```jsonc
{
  "window": {"from": "2026-10-17T00:00:00", "to": "2026-10-19T09:00:00"},
  "coverage": {"live_seconds": 151200, "backfill_seconds": 0, "gap_seconds": 46800},
  "gaps": [{"start": "2026-10-18T13:02:11", "end": "2026-10-18T19:55:40"}],
  "conversations": {"total": 37, "ready": 34, "deferred": 3, "fully_covered": 22, "to_process": 12},
  "utterances": {"total": 5120, "duplicate_live": 3410, "selected": 1630, "retry_failed": 12},
  "estimate": {"gatekeeper_calls": 1642, "expected_qualified": 160, "events_expected": 2,
               "cost_usd": 0.019, "duration_s": 380}
}
```

The preview needs **REST calls only (no LLM)**. It is cached per `(window, mode)` for 5 minutes, so *Preview → Run* does not fetch twice.

---

## 5. Idempotency of produced entities

Re-processing must never create a second copy of the same fact.

| Entity | Idempotency key | Mechanism |
|---|---|---|
| Ledger row | `source_key` | PK, `INSERT OR IGNORE` for skips, upsert for results |
| `VerifiedAction` | `uuid5(NS, source_key + ":action")` | Deterministic id passed to `save_action`, which already does `INSERT OR REPLACE` |
| `PlannedTask` (ambient voice) | `uuid5(NS, source_key + ":task")` | Same; `save_planned_task` must not reset a status changed by the user (upsert keeps `status`, `completed_at`) |
| `SocialEntity` | name-based dedup (already in `save_social_contact`) | Unchanged |
| `SocialCommitment` | `(contact_name, debtor, description)` dedup (already in place) | Unchanged |
| Backfill events (`SessionDossier`) | `run_id` + first chunk `source_key` | The replay engine re-uses an existing event of the same run on resume (§[03](03_backfill_engine.md) §5) |
| `session_chunks` | `chunk_id = source_key` | Already `INSERT OR REPLACE` |

The pipeline payload gains `source_key`, and nodes derive their ids from it when present. Live gets the same benefit: a reconnect that re-delivers an utterance no longer duplicates actions.
