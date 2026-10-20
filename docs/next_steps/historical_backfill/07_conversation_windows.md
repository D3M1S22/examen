# 07 — Conversation-Level History Analysis (window screening) & Persistent Stop

> Part of the [Historical Transcript Backfill](00_overview.md) specification.
> **Status:** implemented 2026-10-20 (branch `feature/multi-user-auth`). Code: [backfill.py](../../../src/ingestion/backfill.py) (`conversation_windows`, `ReplayExecutor._replay_windows`); tests: `tests/test_backfill.py` (*Conversation windows* section).
> Implements the "window screening" optimisation of [05](05_implementation_plan_and_testing.md) Phase 6.

---

## 1. Why

Until now a backfill run treated history like the live stream: **one gatekeeper call per utterance**, each seeing only the 3 previous utterances. A 7-day run therefore meant thousands of calls, and anything that needs what comes *after* an utterance (a reply that confirms a request, a name followed by the company in the next turn) was invisible. Bee history is different from the live stream: the whole recording is available, keyed by its Bee conversation id. The conversation should be the unit.

## 2. How gaps are found (unchanged)

1. While the live stream is healthy, the orchestrator writes **coverage intervals** (`ingest_coverage`, source `live`) and an **ingest ledger** row for every utterance it screened (`ingest_ledger`: time, text hash, conversation uuid, status).
2. A **gap** is any part of the requested window not covered by a live or earlier backfill interval. Startup and reconnect runs are created for the gaps automatically (`BACKFILL_AUTO_ON_*`); manual runs come from the History Sync window.
3. Gaps only decide **which conversations to look at**. Which utterances are new is decided per utterance against the ledger (exact text hash, then fuzzy match, then live speech-time coverage for re-segmented finals), so delayed uploads inside a "covered" period are still found.

## 3. What changed

| Step | Before | Now |
|---|---|---|
| Selection | utterances inside the window only | `BACKFILL_WHOLE_CONVERSATIONS=true`: every **conversation overlapping the window is taken whole**; its un-analysed utterances are selected even if they precede the gap. Evidence (coverage, live ledger, earlier backfills) is read over the whole conversations. |
| Conversation status in the preview | `to_process` / `fully_covered` | also `missed` (never heard live) and `partial` (partly heard live) |
| Screening | 1 call per utterance, 3 lines look-back | `BACKFILL_SCREENING=window`: the conversation is cut into **windows** of `BACKFILL_WINDOW_UTTERANCES` (10) consecutive utterances, at most `BACKFILL_WINDOW_MAX_WORDS` (450) words. **Stage 1**: one call per window that holds selected speech, with Bee's title/summary, `BACKFILL_WINDOW_CONTEXT_UTTERANCES` (3) utterances before and 3 after. A *noop* window (most ambient speech) is recorded as noop with no further call. **Stage 2**: for windows with signal, each selected utterance is screened with the whole window around it (look-back and look-ahead) and dispatched to the pipeline as before. |
| Pipeline | utterance + 3 lines | utterance + the window context (so promises and introductions split across turns are readable) |
| Ids, ledger, de-duplication, temporal guards, events | — | unchanged: still one source key per utterance, so re-runs and resumed runs never duplicate entities |

Windows are cut over the **whole** transcript, never over the selection, so a resumed or repeated run sees the same windows. Utterances already analysed live stay in the window text as context but are not re-extracted.

**Cost.** With N selected utterances in W windows and a share *q* of windows with signal: `W + q·N` screening calls instead of `N`. For ambient speech (W ≈ N/10, q ≈ 0.1–0.25) that is about 3–5× fewer calls. The preview shows the estimate (`estimate.gatekeeper_calls`, `utterances.windows`).

**Trade-off.** A window classified as *noop* skips its utterances; a very short action inside long chatter could be missed. Pending task titles are still injected in the window prompt (they force `action`), and the window size is configurable. `BACKFILL_SCREENING=utterance` restores the old behaviour.

## 4. Stop is persistent

`POST /api/backfill/runs/{id}/cancel` now stores `cancel_requested` on the run. A queued run is cancelled at once; a running one stops after the step in progress. On restart, `rehydrate()` marks runs with a pending stop as `cancelled` instead of re-queuing them (before, a stop that had not finished before the process was killed was lost and the run resumed). The dashboard shows a red **Stop analysis** button in the History Sync window, on the Overview *History Sync* card and in the dock's ⏪ panel.

Note that cancelling does not stop the *automatic* catch-up: the next start or reconnect still queues a run for uncovered gaps of the last `BACKFILL_LOOKBACK_DAYS`. Set `BACKFILL_AUTO_ON_STARTUP=false` / `BACKFILL_AUTO_ON_RECONNECT=false` while testing.

## 5. Settings

| Variable | Default | Meaning |
|---|---|---|
| `BACKFILL_SCREENING` | `window` | `window` (two-stage, above) or `utterance` (legacy) |
| `BACKFILL_WINDOW_UTTERANCES` | `10` | Utterances per window |
| `BACKFILL_WINDOW_MAX_WORDS` | `450` | Word cap per window (Bee finals can be minutes long) |
| `BACKFILL_WINDOW_CONTEXT_UTTERANCES` | `3` | Utterances of look-back and of look-ahead |
| `BACKFILL_WHOLE_CONVERSATIONS` | `true` | Take every overlapping conversation whole |

## 6. Next

- Use the same windows for **live** ingestion when Bee closes a `new-utterance-chunks` chunk (the live path still screens per utterance).
- Merge near-duplicate commitments extracted from adjacent utterances of the same window.
- Pick the window boundaries from Bee's own chunks when the history API exposes them.
