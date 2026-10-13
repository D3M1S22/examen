# 03 — Synthesis Scheduling: Segment, Checkpoint & Final Briefings

> Part of the [Deep Topic Event Engine](00_overview.md) specification.
> Answers: *"When do we spend money on web research and synthesis, and on what?"*

---

## 1. Principle: progressive, then consolidated

| Briefing kind | Produced when | Input | Purpose |
|---|---|---|---|
| `segment` | Soft close (R1/R2), or R6/R9 closing an open segment | On-topic chunks of the segment + event outline so far | Useful **minutes after a break starts**: the user can review the first half during the coffee |
| `checkpoint` | R3 (continuous on-topic ≥ `T_checkpoint`) | Same as `segment` | Long lectures without breaks still get progressive briefings |
| `final` | Hard close (R5/R6/R7/R8/R9) | Segment briefings + micro-events + gap research | The one consolidated event dossier |
| `standalone` | Hard close of a single-segment event below `MIN_SEGMENT_WORDS`; or invocation without the engine (AgentCore console, Alexa, sessionless simulate) | Raw transcript | Preserves today's single-question behaviour |

Nothing is synthesized per utterance any more when the engine is active (fixes audit finding #1).

---

## 2. Refactor `node_topic_research` into reusable steps

Today [topic_research.py](../../../src/pipeline/nodes/topic_research.py) runs extract → search (with retry) → synthesize as one LangGraph node. Split it into pure-ish functions so that the engine and the graph node share them:

```python
def extract_topics(text: str, *, context: EventOutline | None, max_queries: int) -> TopicExtraction
def research(queries: list[str], *, ledger: QueryLedger, cache: SearchCache) -> WebSearchBatchResult
def synthesize_briefing(text: str, topic: TopicExtraction, search: WebSearchBatchResult,
                        *, kind: BriefingKind, context: EventOutline | None) -> BriefingReport

def node_topic_research(state):        # unchanged contract, now a thin wrapper → kind="standalone"
```

As implemented, the engine talks to a `Synthesizer` protocol with two methods: `segment(text, session_id, outline, kind)` and `final(parts, extra_text, session_id, outline, micro_events)`, both returning a `SynthesisOutcome(briefing, research)`. The default `PipelineEventSynthesizer` chains the three steps above. Tests inject fakes.

- `EventOutline` = event title, previous segment titles, accumulated `key_discussion_points`, and queries already run. It is passed to the extractor so a segment **does not re-research** what an earlier segment already covered, and to the synthesizer so the narrative continues instead of restarting.
- `TopicExtraction.search_queries` allows up to 3 for segments and up to 2 *gap* queries for the final.
- The heuristic paths (`_heuristic_extract_topic`, `_heuristic_synthesize_report`) remain the offline fallback for every step.

### 2.1 Long transcripts

A 50-minute segment is ~7k words (~10k tokens). That is acceptable for the reasoner, but to keep latency and cost bounded:

- If the segment exceeds `SEGMENT_MAX_WORDS` (default 6000), **condense first**: the fast model summarizes consecutive blocks of ~1500 words into dense notes, and the synthesizer receives the notes plus the last block verbatim.
- Off-topic chunks inside the segment boundaries (micro-windows that did not count as on-topic) are **excluded** from the synthesis text, but their micro-events are listed separately.

---

## 3. Final synthesis (map-reduce)

The final synthesis **does not re-read the whole raw transcript**. It reduces:

```
inputs:
  - every segment/checkpoint BriefingReport of the event (summaries, syntheses, sources)
  - accumulated key_discussion_points
  - linked micro-events (actions, contacts, tasks, commitments)
  - text of `skipped` segments (too short for their own briefing)
  - Bee conversation titles/summaries (if any)

steps:
  1. gap analysis (fast model): which important concepts are NOT covered by existing sources? → ≤ 2 gap queries
  2. research(gap queries)  — with ledger/cache, usually 0–2 new searches
  3. synthesize_briefing(kind="final")  — consolidated executive summary, cross-segment narrative,
     merged + deduplicated web_sources, action items, "during this event" micro-event section
```

**Single-segment shortcut:** if the event has exactly one synthesized segment and no new gap is found, the final briefing is the segment briefing **promoted** (copied with `kind="final"` and the micro-events section added), with no extra reasoner call.

**Output linkage:** `SessionDossier.final_briefing_id` → the final briefing; segment briefings stay linked through `segments[].briefing_id`. The UI shows both ([06](06_serving_and_ui.md)).

---

## 4. Research reuse: query ledger & search cache

| Mechanism | Scope | Storage | Behaviour |
|---|---|---|---|
| **Query ledger** | Per event | `SessionDossier.research_ledger` (`[{query, sources, segment_id, kind}]`) | The extractor sees it (via `EventOutline`) and is told not to repeat it; `research()` passes ledger queries as `cache_only`: they are served from the cache (context preserved) and never re-hit the network |
| **Search cache** | Global | Table `web_search_cache` (see [04](04_data_model_and_storage.md)) | Key `cache_key()` = lower-cased `normalize_search_query()`; TTL `WEB_SEARCH_CACHE_TTL_SECONDS` (default 24 h, `0` disables); empty results are never cached; used by event syntheses only (standalone briefings keep the uncached path) |

---

## 5. Job execution model

Synthesis is slow (seconds to tens of seconds) and synchronous (LangChain `.invoke`). It must never block ingestion.

```
SessionManager.decide() ──► Transition(..., enqueue=SynthesisJob(kind, event_id, segment_id))
                                   │
                                   ▼
                     SynthesisJobQueue (asyncio, in the orchestrator process)
                       - idempotency key: (event_id, segment_id or "final", kind)
                       - concurrency limit: SYNTHESIS_MAX_CONCURRENCY = 1 (Bedrock + DDG rate limits)
                       - execution: await asyncio.to_thread(run_job, job)
                       - retries: 2 with exponential backoff; then segment.status = "failed"
                       - ordering: a "final" job waits until all segment jobs of its event are done
                       - on completion: persist briefing → update segment/event → broadcast SSE
```

- **Restart safety:** job state is derived from persisted segment statuses (`closed` but not `synthesized` ⇒ re-enqueue on startup). No separate job table is needed.
- **AgentCore deployment:** in cloud mode the job's `run_job` sends an AgentCore invocation with `{"mode": "synthesis", "kind": ..., "event_id": ...}` instead of calling the functions in-process. The ingestion bridge stays the stateful component; the pipeline stays stateless. See [06_aws_cloud_deployment_architecture.md](../../06_aws_cloud_deployment_architecture.md).

---

## 6. Cost & latency model (order of magnitude)

Scenario: 2-hour lecture with one 15-minute break; gatekeeper flags ~60 utterances as `deep_topic`.

| | Today | With the engine |
|---|---|---|
| Topic extraction calls (fast model) | ~60 | 3–4 (2 segments + 1 checkpoint + gap analysis) |
| Reasoner synthesis calls | ~60 | 3–4 |
| Web searches | ~60–180 | ~6–10 (ledger + cache) |
| Embedding calls | 0 | ~60–120 micro-windows (negligible cost) |
| Briefings visible to the user | ~60 fragments | 2–3 progressive + 1 consolidated |
| First useful briefing | Immediately, but fragmentary | ≈ `T_soft` + synthesis time (~5–6 min after the break starts) |
| Final consolidated briefing | Never | ≈ `T_hard` after the end (≈ 5 min if a closing cue is heard) |

---

## 7. Revisions after manual edits

Manual **split** or **merge** ([06](06_serving_and_ui.md)) marks the affected events' final briefings as stale (`final_revision += 1`) and re-enqueues a `final` job. Segment briefings are kept and reattached to the right event; only the reduce step is re-run.
