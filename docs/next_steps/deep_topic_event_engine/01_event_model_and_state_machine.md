# 01 — Event Model & Lifecycle State Machine

> Part of the [Deep Topic Event Engine](00_overview.md) specification.

---

## 1. Hierarchy

```
Event (SessionDossier, evolved)          ← our identity: event_id
 ├── conversation_uuids[]                ← Bee conversations spanned (1..n)
 ├── topic_profile                       ← rolling "what is this about"
 ├── segments[]                          ← contiguous on-topic runs
 │     ├── chunk range (first/last chunk, start/end time)
 │     └── briefing_id (segment or checkpoint briefing)
 ├── chunks (session_chunks table)       ← every utterance while the event is open
 ├── linked_micro_events[]               ← actions / contacts / tasks / commitments
 └── final_briefing_id                   ← consolidated briefing on hard close
```

### Why the event id must be decoupled from Bee's `conversation_uuid`

Bee segments conversations with its own silence heuristics, which we do not control:

- A lecture with a 15-minute break will most likely become **two Bee conversations** → we must **merge** across uuids.
- Two lectures with no real silence in between (same room, students chatting) may stay in **one Bee conversation** → we must **split** inside a uuid.

Therefore `conversation_uuid` is treated as **one signal among others** (§4), and an event keeps a list of the uuids it spans. Today `session_id == conversation_uuid` ([orchestrator.py:153](../../../src/ingestion/orchestrator.py)); after this change, `session_id` becomes the engine-assigned `event_id` (a UUID minted when the event opens).

---

## 2. Event lifecycle

```
                     on-topic chunk (no compatible event)
     ┌──────────┐   ───────────────────────────────────►  ┌────────┐
     │  (none)  │                                           │ ACTIVE │◄──────────────┐
     └──────────┘                                           └───┬────┘               │
                                                                │                    │ R4 resume
              R1 no on-topic activity for T_soft                │                    │ (pending window
              R2 explicit pause/closing cue                     │                    │  matches profile,
              R3 checkpoint (continuous on-topic ≥ T_checkpoint)│                    │  same place,
                 → segment closed + synthesized                 ▼                    │  gap < T_hard)
                                                            ┌────────┐               │
                                                            │ PAUSED │───────────────┘
                                                            └───┬────┘
              R5 pause duration ≥ T_hard                        │
              R6 location shift (accuracy-aware)                │
              R7 pending window = different topic → new event   │
              R8 manual conclude                                │
                                                                ▼
                                                          ┌───────────┐
                                                          │ CONCLUDED │ → final synthesis
                                                          └───────────┘
```

Additional transitions directly from `ACTIVE`:

- **R6** location shift → `CONCLUDED` (the current segment is closed and synthesized first).
- **R9** sustained topic drift *without* a pause (back-to-back talks with no gap) → `CONCLUDED` + new event opened with the drifting chunks.
- **R3** checkpoint keeps the event `ACTIVE`: it closes the current segment, starts a new one and does not pause.

> The legacy `finalizing` status maps to `PAUSED` during migration (see [04](04_data_model_and_storage.md)).

### Segment lifecycle

```
open ──(R1/R2/R3/R6/R9/R8)──► closed ──► synthesizing ──► synthesized
                                   │                    └──► failed (retry ×2, then keep raw)
                                   └──(below min words)──► skipped (merged into final synthesis only)
```

---

## 3. Transition rules (normative)

All rules are evaluated by a **pure function** `decide(event_state, new_chunks, now) -> list[Transition]`. It has no I/O, uses an injectable clock and is fully unit-testable. Rules are evaluated in priority order; the first matching rule wins for each event, and every transition records a machine-readable `reason`.

| ID | From | Condition | To | Side effects |
|---|---|---|---|---|
| **R0** | none | First on-topic chunk and no compatible `ACTIVE`/`PAUSED` event | `ACTIVE` | Mint `event_id`, open segment 1, seed topic profile |
| **R1** | ACTIVE | `now − last_on_topic_at ≥ T_soft` | PAUSED | Close segment → enqueue segment synthesis |
| **R2** | ACTIVE | Explicit pause or closing cue (e.g. "facciamo una pausa", "that concludes") | PAUSED | As R1; a closing cue also sets `hard_close_deadline = now + T_hard_after_close_cue` |
| **R3** | ACTIVE | `now − segment.start ≥ T_checkpoint` **and** segment words ≥ `MIN_SEGMENT_WORDS` | ACTIVE | Close segment, open the next one, enqueue checkpoint synthesis |
| **R4** | PAUSED | Pending window resolved as **same topic** (see [02](02_topic_continuity_detection.md)) and no R6 | ACTIVE | Open new segment, attach pending chunks to it |
| **R5** | PAUSED | `now − paused_at ≥ T_hard` (or `≥ hard_close_deadline`) | CONCLUDED | Enqueue final synthesis |
| **R6** | ACTIVE/PAUSED | Location shift confirmed (§4.2) | CONCLUDED | Close the open segment (synthesize), then final synthesis |
| **R7** | PAUSED | Pending window resolved as **different topic** | CONCLUDED | Final synthesis on old event; **R0** opens a new event with the pending chunks |
| **R8** | any open | Manual `POST /api/sessions/{id}/conclude` | CONCLUDED | As R5 |
| **R9** | ACTIVE | Drift window resolved as **different topic** with stricter thresholds (§[02](02_topic_continuity_detection.md) §5) | CONCLUDED | Split at drift start: chunks before → old event; drift chunks → new event |

**Invariant:** at most **one** event is `ACTIVE` at any time for a single wearer. Opening a new event (R0 via R7/R9) always concludes the previous `ACTIVE`/`PAUSED` one. A `PAUSED` event can only be resumed while it is the **most recent** event, so we never jump back over an intervening event.

**Non-deep-topic chunks while an event is open** (`noop`, `social`, `action`, `scheduled_task`):
- are appended to the event's chunk log with their categories (useful context for the final synthesis);
- micro-events extracted from them are linked to the event (current [persist.py](../../../src/pipeline/nodes/persist.py) behaviour, kept);
- they **do not** update the topic profile and **do not** reset the pause timer, unless their micro-window is similar enough to the profile to count as on-topic activity (see [02](02_topic_continuity_detection.md) §3). This is how a lecture survives utterances that the per-utterance gatekeeper misclassifies as `noop`.

---

## 4. Signal fusion

The engine uses **ordered, explainable rules**, not a weighted score. A score is harder to debug and to explain to a judge; rules give each decision a human-readable `reason` that is shown in the UI audit trail.

| Signal | Source | Strength | Role |
|---|---|---|---|
| **Utterance time gap** | `chunk.timestamp` (receive time or `spoken_at`, see [05](05_ingestion_and_pipeline_integration.md)) | Strong | Drives R1/R5. |
| **GPS displacement** | `update-location` → `LocationTelemetry` | Strong, **one-directional** | Moving away ⇒ close (R6). Staying put proves nothing: rooms in the same building are below GPS resolution. |
| **Topic similarity** | Topic profile vs. micro-window | Strong when the window is sufficient, weak on a single chunk | The only signal separating back-to-back events in the same place (R7/R9). Decides resume vs. split (R4/R7). |
| **Explicit cues** | Regex + gatekeeper hint | Medium | Pause/close cues (R2); resume cues lower the resume threshold; opening cues lower the split threshold. |
| **Bee conversation boundary** | `new-conversation` / `update-conversation` events | Weak–medium | A new Bee conversation while `PAUSED` slightly biases toward split. Bee `title`/`short_summary` enriches the topic profile. |
| **Semantic zone change** | `LocationTelemetry.semantic_zone` (`home`, `work_office`, `transit`, …) | Medium | `→ transit` while PAUSED accelerates the hard close (`T_hard_transit`). |

### 4.1 Cue lexicon (initial)

Extends `CLOSING_PHRASE_PATTERNS` in [session_manager.py](../../../src/ingestion/session_manager.py). Patterns are bilingual (IT/EN):

| Cue type | Examples | Effect |
|---|---|---|
| Pause | "facciamo una pausa", "dieci minuti di pausa", "short break", "let's take five" | R2 (pause only) |
| Closing | "per oggi è tutto", "ci vediamo giovedì", "concludiamo", "that concludes", "see you next week" | R2 + shortened hard-close deadline |
| Resume | "riprendiamo", "dove eravamo rimasti", "torniamo a", "let's get back", "where were we" | Resume threshold −0.05 (§[02](02_topic_continuity_detection.md)) |
| Opening | "oggi parliamo di", "benvenuti al corso di", "il prossimo relatore", "today's topic is", "next speaker" | Split threshold +0.05 |

Cues are evaluated on the chunk text **and** optionally on the gatekeeper `summary_hint`. They bias decisions; they never override GPS (R6).

### 4.2 Accuracy-aware location shift

Indoor GPS jitter easily exceeds 50–100 m. A shift is confirmed only when:

```
distance(prev, new) − (prev.accuracy_m + new.accuracy_m) ≥ LOCATION_SHIFT_METERS
AND the condition holds for 2 consecutive fixes (or 1 fix with semantic_zone change)
```

`calculate_haversine_distance` in [session_manager.py](../../../src/ingestion/session_manager.py) is reused. The reference point is the **event's anchor location**, i.e. the median of fixes during the first segment, not the last fix. This avoids slow drift being accumulated.

---

## 5. Reference pseudo-code

```python
def decide(ev: EventState | None, window: list[Chunk], now: float, cfg: EngineConfig) -> list[Transition]:
    t: list[Transition] = []

    # Location veto first (R6)
    if ev and ev.status in ("active", "paused") and location_shift_confirmed(ev, window, cfg):
        t.append(Transition(ev.id, to="concluded", reason="location_shift"))
        ev = None

    if ev and ev.status == "active":
        if any_closing_or_pause_cue(window):
            t.append(Transition(ev.id, to="paused", reason="explicit_cue"))
        elif now - ev.last_on_topic_at >= cfg.t_soft:
            t.append(Transition(ev.id, to="paused", reason="soft_timeout"))
        elif drift_confirmed(ev, cfg):                         # R9, see doc 02
            t += split_on_drift(ev, reason="topic_drift")
        elif checkpoint_due(ev, now, cfg):
            t.append(Transition(ev.id, to="active", reason="checkpoint", new_segment=True))

    elif ev and ev.status == "paused":
        if now - ev.paused_at >= ev.effective_t_hard(cfg):
            t.append(Transition(ev.id, to="concluded", reason="hard_timeout"))
        elif ev.pending_window_ready(cfg):
            verdict = ev.pending_verdict                       # same | different | undecided
            if verdict == "same":
                t.append(Transition(ev.id, to="active", reason="resume_same_topic"))
            elif verdict == "different":
                t.append(Transition(ev.id, to="concluded", reason="new_topic_after_pause"))
                t.append(Transition(None, to="active", reason="open_from_pending"))

    elif ev is None and has_on_topic(window):
        t.append(Transition(None, to="active", reason="open"))

    return t
```

`decide` is called from two places:
1. **On every chunk** (`SessionManager.record_chunk`): evaluates cue, drift, pending window and location rules.
2. **On every tick** (`SessionManager.tick(now)`, every `TICK_SECONDS`): evaluates the time-based rules R1, R3 and R5, which must fire even when no audio arrives. Today they are missing (audit finding #5).

---

## 6. Configuration

All values live in `Settings` ([config.py](../../../src/core/config.py)) with env aliases, so they can be tuned without code changes. The values below are **initial guesses to be calibrated** with the scenarios in [07](07_implementation_plan_and_testing.md).

| Setting | Env | Default | Rationale |
|---|---|---|---|
| `event_t_soft_seconds` | `EVENT_T_SOFT_SECONDS` | `270` (4.5 min) | Longer than a typical lecturer's pause or Q&A silence, shorter than a break |
| `event_t_hard_seconds` | `EVENT_T_HARD_SECONDS` | `1800` (30 min) | Covers the usual 10–15 min university break with margin |
| `event_t_hard_after_close_cue_seconds` | `EVENT_T_HARD_AFTER_CLOSE_CUE_SECONDS` | `300` | "Ci vediamo giovedì" → don't wait 30 min |
| `event_t_hard_transit_seconds` | `EVENT_T_HARD_TRANSIT_SECONDS` | `120` | User is clearly leaving |
| `event_t_checkpoint_seconds` | `EVENT_T_CHECKPOINT_SECONDS` | `1200` (20 min) | Progressive briefings for long lectures without breaks |
| `event_min_segment_words` | `EVENT_MIN_SEGMENT_WORDS` | `300` | Below this, a segment is not worth an independent research pass |
| `event_location_shift_meters` | `EVENT_LOCATION_SHIFT_METERS` | `400` | Above campus-building jitter, below "went somewhere else" |
| `event_tick_seconds` | `EVENT_TICK_SECONDS` | `15` | Timer resolution |
| `topic_window_min_chunks` | `TOPIC_WINDOW_MIN_CHUNKS` | `3` | See [02](02_topic_continuity_detection.md) |
| `topic_window_min_words` | `TOPIC_WINDOW_MIN_WORDS` | `120` | See [02](02_topic_continuity_detection.md) |
| `topic_similarity_backend` | `TOPIC_SIMILARITY_BACKEND` | `embedding` | `embedding` \| `llm` \| `heuristic` |
| `topic_sim_same` / `topic_sim_different` | `TOPIC_SIM_SAME` / `TOPIC_SIM_DIFFERENT` | `0.78` / `0.55` | Backend-specific, calibrate (see [02](02_topic_continuity_detection.md)) |

For **demo mode**, a profile (`EVENT_PROFILE=demo`) scales all time thresholds down, e.g. `T_soft=20s` and `T_hard=90s`, so the full lifecycle is visible in a 3-minute video.
