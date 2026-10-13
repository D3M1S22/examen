# 02 — Topic Continuity Detection

> Part of the [Deep Topic Event Engine](00_overview.md) specification.
> Answers: *"Is this new content still the same lecture, or a different one?"*

---

## 1. Why this is the hard part

Time and GPS cannot separate **two different lectures in the same building, five minutes apart**. Topic can, but naive topic comparison fails in three ways:

| Failure mode | Example | Mitigation |
|---|---|---|
| **Break noise** | Coffee chatter during the break looks "off-topic" and would split the event | Only on-topic material feeds the profile; the break is a *pause*, not a topic change (§3) |
| **Single-chunk ambiguity** | First sentence after the break: "Allora, dove eravamo?" has no topical content | Decide on a **window** of chunks, not on one chunk (§4) |
| **Natural drift** | A lecture goes from limits → derivatives → integrals | Compare against a **rolling** profile, not the opening minutes (§2) |

---

## 2. The topic profile

Each open event keeps a `TopicProfile`:

```python
class TopicProfile(BaseModel):
    centroid: list[float] | None        # exponentially-weighted mean of on-topic window embeddings
    centroid_weight: float = 0.0        # total weight accumulated
    keywords: dict[str, float]          # term -> decayed weight (heuristic backend + UI chips)
    segment_titles: list[str]           # titles from synthesized segments (strong anchors)
    bee_titles: list[str]               # Bee update-conversation titles/short_summary, if any
    language: str | None                # "it" / "en"; detected from text
    updated_at: str
```

**Update rule** after each on-topic micro-window `w` with embedding `e_w`:

```
centroid ← normalize( (1−α)·centroid + α·e_w )      α = 0.25 (recent content matters more)
```

- α = 0.25 lets the profile follow gradual drift (limits → derivatives) within about 4 windows, while a single odd window cannot hijack it.
- Segment titles and Bee titles are embedded once and blended in with a fixed weight (0.2). They are the most "semantic" summary of the event and stabilize the profile.

---

## 3. Micro-windows and on-topic activity

Bee utterances are short, and the per-utterance gatekeeper ([gatekeeper.py](../../../src/ingestion/gatekeeper.py)) often labels individual lecture sentences as `noop` ("quindi qui sostituiamo x con h"). Relying only on `deep_topic` labels would trigger false pauses mid-lecture.

**Micro-window** = consecutive chunks of the event's chunk log grouped until `≥ TOPIC_WINDOW_MIN_CHUNKS` chunks **and** `≥ TOPIC_WINDOW_MIN_WORDS` words. Defaults: 3 chunks, 120 words, which is roughly 30–60 s of lecture speech.

A micro-window counts as **on-topic activity** (resets the `T_soft` timer, updates the profile) if:

```
any chunk in window is gatekeeper-labelled deep_topic
OR similarity(window, profile) ≥ TOPIC_SIM_SAME − 0.05
```

Otherwise it is **off-topic**. It stays in the chunk log for context and micro-events, but it does not reset the pause timer. Coffee chatter therefore lets `T_soft` expire naturally and the event pauses, which is exactly what we want.

> **Gatekeeper hint injection (recommended):** while an event is `ACTIVE`, pass a one-line hint ("An academic lecture on *<title>* is in progress") as `prior_context` to `aclassify_chunk`. This raises `deep_topic` recall for terse lecture sentences at negligible token cost. It reuses the existing `prior_context` parameter (Milestone 3.1).

---

## 4. Pending window: deciding resume vs. split after a pause

When an event is `PAUSED` and on-topic material arrives, the engine **does not decide immediately**:

```
PAUSED ── first deep_topic chunk ──► pending_chunks = [c1]
                                     (no transition yet)
          more chunks ──────────────► pending_chunks = [c1, c2, c3]
          window ready (≥ min chunks & words, or pending age ≥ 90 s)
                                     ──► similarity(pending_window, profile) = s
```

| Verdict | Condition | Transition |
|---|---|---|
| **same** | `s ≥ TOPIC_SIM_SAME` (− 0.05 if a resume cue was heard) | R4: resume, pending chunks become the start of the new segment |
| **different** | `s ≤ TOPIC_SIM_DIFFERENT` (+ 0.05 if an opening cue was heard; + 0.03 if a new Bee conversation started) | R7: conclude old event, open new one **with the pending chunks** (retroactive assignment) |
| **undecided** | in between | Grow the window by one more micro-window (max 3 extensions); then ask the **LLM judge** (§6.2); if still undecided → **resume** (merging is cheaper to undo than splitting, and the final synthesis tolerates a little extra content) |

If `T_hard` expires while chunks are pending, R5 wins: the old event concludes, and the pending chunks open a new event.

---

## 5. Drift without a pause (R9)

Back-to-back conference talks may have **no silence at all**. While `ACTIVE`, the engine tracks the similarity of each new micro-window against the profile *as it was before the window*:

```
drift_confirmed  ⇔  the last K = 3 consecutive micro-windows all have
                    similarity ≤ TOPIC_SIM_DIFFERENT − 0.05
                    (and together cover ≥ 2 minutes of speech)
```

These thresholds are deliberately stricter than the post-pause split, because a false split mid-lecture is very visible to the user. On confirmation, the split point is the **first** drifting window: earlier chunks stay in the old event, drifting chunks seed the new one.

---

## 6. Similarity backends

All backends implement one interface so the engine logic is identical regardless of provider:

```python
class TopicSimilarity(Protocol):
    def embed(self, text: str) -> list[float] | None: ...
    def similarity(self, window_text: str, profile: TopicProfile) -> float: ...   # 0..1
    def judge(self, window_text: str, profile: TopicProfile, outline: str) -> Literal["same", "different", "undecided"]: ...
```

### 6.1 `embedding` (default, recommended)

- **Model candidates on Bedrock:** `amazon.titan-embed-text-v2:0` (multilingual, 256/512/1024 dims, very cheap) or `cohere.embed-multilingual-v3`. Both handle Italian and English. **Availability must be verified** in the account/region configured in `AWS_REGION`. The repo has no embedding factory yet: [models.py](../../../src/core/models.py) only builds chat models.
- Add `get_embedding_model()` to [models.py](../../../src/core/models.py) (e.g. `langchain_aws.BedrockEmbeddings`), with env `BEDROCK_EMBEDDING_MODEL`.
- **Cost order of magnitude:** a 2-hour lecture is ~15k words ≈ 20k tokens. Embedding every micro-window costs a fraction of a cent, which is negligible next to one reasoner call.
- **Calibration:** cosine values depend on the model. `TOPIC_SIM_SAME` / `TOPIC_SIM_DIFFERENT` must be calibrated on the scenarios in [07](07_implementation_plan_and_testing.md). Plot same-event vs. different-event window pairs and pick thresholds with a safety gap.
- **Latency:** embedding calls run off the hot path, inside the tick/record worker, never inside the gatekeeper call.

### 6.2 `llm` judge (tie-breaker only)

Used only for **undecided** pending windows (§4) and confirmed-drift double-checks. It is not used for every window. Fast model ([`get_fast_model()`](../../../src/core/models.py)), structured output:

```python
class TopicContinuityVerdict(BaseModel):
    verdict: Literal["same", "different", "undecided"]
    confidence: float
    rationale: str   # stored in the transition reason for the audit trail
```

Prompt inputs: event title, segment titles, top keywords, last ~150 words of the previous segment, and the pending window. These stay well under 1k tokens.

### 6.3 `heuristic` (offline / `MOCK_AI` / tests)

- Keyword-set Jaccard similarity between the window's content terms and `profile.keywords`, after stopword removal. Reuse the IT/EN stopword handling added for search-query normalization in [topic_research.py](../../../src/pipeline/nodes/topic_research.py) / [web_search.py](../../../src/pipeline/tools/web_search.py).
- It is deterministic, which makes it the backend of choice for unit tests of the state machine.
- Thresholds differ (Jaccard is much lower than cosine): `TOPIC_SIM_SAME_HEURISTIC = 0.25`, `TOPIC_SIM_DIFFERENT_HEURISTIC = 0.08` (initial).

---

## 7. Known limitations and accepted trade-offs

| Case | Behaviour | Accepted because |
|---|---|---|
| Two consecutive lectures of the **same course** | Merged into one event | They are semantically one learning unit; the user can split manually ([06](06_serving_and_ui.md)) |
| Lecture with a radical mid-course topic change and no pause | May split (R9) | Strict thresholds plus the LLM judge make it rare; manual merge is available |
| Very short on-topic bursts (a 1-minute question to a colleague) | One-segment event below `MIN_SEGMENT_WORDS` | Synthesized as a **standalone** briefing at hard close, which matches today's single-question behaviour |
| Mixed-language lecture (IT slides, EN terms) | Multilingual embeddings handle it; heuristic backend degrades | Heuristic is only for offline/tests |
