"""Topic continuity for the Deep Topic Event Engine (Phase C).

Answers "is this new content still the same event?" by comparing a window of utterances
against the event's rolling TopicProfile.

Spec: docs/next_steps/deep_topic_event_engine/02_topic_continuity_detection.md

Backends:
  - embedding: Bedrock text embeddings (Titan Text Embeddings V2), cosine vs. an EWMA centroid.
  - heuristic: offline keyword coverage (tests, MOCK_AI, missing credentials, embedding failures).
An optional fast-model LLM judge breaks ties for undecided pause-resume windows.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from src.core.config import Settings, settings
from src.core.schemas import TopicProfile

logger = logging.getLogger("examen.ingestion.topic_continuity")

Verdict = Literal["same", "different", "undecided"]
Embedder = Callable[[str], Optional[List[float]]]

# Compact IT/EN stopword list: function words and lecture/meeting filler that carry no topic.
_STOPWORDS = {
    # Italian
    "alla", "alle", "allo", "anche", "ancora", "avere", "abbiamo", "avete", "hanno", "aveva", "come",
    "con", "cosa", "così", "cui", "dalla", "dalle", "dallo", "degli", "della", "delle", "dello",
    "dentro", "dopo", "dove", "ecco", "essere", "fare", "facciamo", "fino", "loro", "molto", "nella",
    "nelle", "nello", "noi", "nostro", "nostra", "ogni", "oggi", "ora", "perché", "perche", "però",
    "pero", "poi", "proprio", "quale", "quali", "quando", "quanto", "quella", "quelle", "quello",
    "questa", "queste", "questi", "questo", "quindi", "sempre", "sono", "stato", "stessa", "stesso",
    "sulla", "sulle", "sullo", "tutti", "tutto", "tutta", "vediamo", "vero", "volta", "allora",
    "adesso", "infatti", "invece", "magari", "qualche", "qui", "sarà", "siamo", "siete", "sapete",
    "dunque", "cioè", "cioe", "bene", "okay", "ragazzi", "diciamo", "praticamente", "esempio",
    # English
    "about", "after", "again", "also", "because", "been", "before", "being", "between", "both",
    "could", "does", "doing", "each", "from", "have", "having", "here", "into", "just", "like",
    "more", "most", "much", "only", "other", "over", "same", "should", "some", "such", "than",
    "that", "their", "them", "then", "there", "these", "they", "this", "those", "through", "very",
    "want", "were", "what", "when", "where", "which", "while", "will", "with", "would", "your",
    "okay", "right", "really", "actually", "basically", "let's", "lets", "going", "know", "think",
}

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)
_STEM_CHARS = 6  # crude prefix stemming: "derivata"/"derivate"/"derivabile" -> "deriva"


def content_terms(text: str) -> List[str]:
    """Topic-bearing terms of a text (lower-cased, stopword-free, prefix-stemmed)."""
    terms = []
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) <= 3 or token in _STOPWORDS or token.isdigit():
            continue
        terms.append(token[:_STEM_CHARS])
    return terms


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


@dataclass(frozen=True)
class ContinuityConfig:
    backend: str = "heuristic"                 # "embedding" | "heuristic"
    sim_same: float = 0.42
    sim_different: float = 0.37
    sim_same_heuristic: float = 0.20
    sim_different_heuristic: float = 0.10
    window_min_chunks: int = 3
    window_min_words: int = 120
    pending_max_age: float = 90.0
    pending_max_extensions: int = 3
    drift_windows: int = 3
    drift_min_seconds: float = 120.0
    min_profile_windows: int = 2               # a younger profile is still being built: no drift decisions
    split_refine_margin: float = 0.03          # a straddling chunk moves only if clearly closer to the new subject
    alpha: float = 0.25                        # EWMA weight of the newest window
    title_weight: float = 0.2                  # weight of segment/Bee titles blended into the centroid
    keyword_profile_size: int = 80             # top-N profile terms used by the heuristic backend
    llm_judge: bool = True
    resume_cue_bias: float = 0.05
    opening_cue_bias: float = 0.05
    bee_boundary_bias: float = 0.03

    @classmethod
    def from_settings(cls, cfg: Optional[Settings] = None) -> Optional["ContinuityConfig"]:
        """Returns None when topic continuity is disabled (Phase A behaviour)."""
        s = cfg or settings
        if s.topic_similarity_backend == "none":
            return None
        return cls(
            backend=s.topic_similarity_backend,
            sim_same=s.topic_sim_same,
            sim_different=s.topic_sim_different,
            sim_same_heuristic=s.topic_sim_same_heuristic,
            sim_different_heuristic=s.topic_sim_different_heuristic,
            window_min_chunks=s.topic_window_min_chunks,
            window_min_words=s.topic_window_min_words,
            pending_max_age=s.topic_pending_max_age_seconds,
            drift_windows=s.topic_drift_windows,
            drift_min_seconds=s.topic_drift_min_seconds,
            llm_judge=s.topic_llm_judge,
        )


@dataclass(frozen=True)
class SimilarityScore:
    value: float
    same: float
    different: float
    backend: str

    def verdict(self, resume_bias: float = 0.0, split_bias: float = 0.0) -> Verdict:
        if self.value >= self.same - resume_bias:
            return "same"
        if self.value <= self.different + split_bias:
            return "different"
        return "undecided"

    def describe(self) -> str:
        return f"{self.backend} similarity={self.value:.2f} (same>={self.same:.2f}, different<={self.different:.2f})"


class TopicContinuityVerdict(BaseModel):
    verdict: Literal["same", "different", "undecided"] = Field(
        description="'same' if the new window continues the ongoing event, 'different' if it is a new event."
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = Field(default="", description="One sentence explaining the decision.")


_JUDGE_SYSTEM_PROMPT = """You decide whether new speech captured by a wearable microphone continues an ongoing
event (lecture, meeting, talk) or starts a different one after a pause.
Answer 'same' when the new speech continues the subject of the event (including natural progression to
related sub-topics), 'different' when it is clearly another subject (e.g. a different course or talk),
and 'undecided' only if there is truly not enough information."""


class TopicSimilarity:
    """Scores windows against a TopicProfile and keeps the profile up to date."""

    def __init__(self, config: ContinuityConfig, embedder: Optional[Embedder] = None, judge_enabled: Optional[bool] = None):
        self.config = config
        self._embedder = embedder
        self._embedder_resolved = embedder is not None
        self._judge_enabled = config.llm_judge if judge_enabled is None else judge_enabled
        self._cache: Dict[str, List[float]] = {}

    # -- embeddings -----------------------------------------------------------

    def _resolve_embedder(self) -> Optional[Embedder]:
        if self._embedder_resolved:
            return self._embedder
        self._embedder_resolved = True
        if self.config.backend != "embedding":
            return None
        from src.core.models import has_active_model_credentials

        if settings.mock_ai or not has_active_model_credentials("bedrock"):
            logger.info("Topic continuity: embeddings unavailable (mock/no credentials), using heuristic backend.")
            return None
        try:
            from src.core.models import get_embedding_model

            model = get_embedding_model()
            self._embedder = model.embed_query
        except Exception as e:
            logger.warning(f"Topic continuity: embedding model init failed ({e}); using heuristic backend.")
            self._embedder = None
        return self._embedder

    def embed(self, text: str) -> Optional[List[float]]:
        embedder = self._resolve_embedder()
        if embedder is None or not text.strip():
            return None
        key = text.strip()[:4000]
        if key in self._cache:
            return self._cache[key]
        try:
            vec = embedder(key)
        except Exception as e:
            logger.warning(f"Embedding call failed, falling back to heuristic similarity: {e}")
            return None
        if vec:
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[key] = vec
        return vec

    # -- scoring ----------------------------------------------------------------

    def score(self, text: str, profile: Optional[TopicProfile]) -> Tuple[Optional[SimilarityScore], Optional[List[float]]]:
        """Returns (score, window_embedding). score is None when the profile is still empty."""
        if profile is None:
            return None, self.embed(text)
        vec = self.embed(text) if profile.centroid else None
        if vec is not None and profile.centroid:
            return SimilarityScore(_cosine(vec, profile.centroid), self.config.sim_same,
                                   self.config.sim_different, "embedding"), vec
        value = self._keyword_coverage(text, profile)
        if value is None:
            return None, vec
        return SimilarityScore(value, self.config.sim_same_heuristic,
                               self.config.sim_different_heuristic, "heuristic"), vec

    def _keyword_coverage(self, text: str, profile: TopicProfile) -> Optional[float]:
        window = set(content_terms(text))
        if not window or not profile.keywords:
            return None
        top = sorted(profile.keywords.items(), key=lambda kv: kv[1], reverse=True)[: self.config.keyword_profile_size]
        known = {term for term, _ in top}
        return len(window & known) / len(window)

    # -- profile maintenance ------------------------------------------------------

    def update(self, profile: Optional[TopicProfile], text: str, vec: Optional[List[float]] = None) -> TopicProfile:
        """Blends an on-topic window into the profile (EWMA centroid + decayed keywords)."""
        profile = profile or TopicProfile()
        alpha = self.config.alpha
        keywords = {t: w * (1.0 - alpha) for t, w in profile.keywords.items()}
        for term in set(content_terms(text)):
            keywords[term] = keywords.get(term, 0.0) + alpha
        profile.keywords = dict(sorted(keywords.items(), key=lambda kv: kv[1], reverse=True)[:200])

        if vec is None and self.config.backend == "embedding":
            vec = self.embed(text)
        if vec is not None:
            if profile.centroid and len(profile.centroid) == len(vec):
                # The second window weighs as much as the first; later windows follow the EWMA
                weight = alpha if profile.centroid_weight >= 2 else 0.5
                profile.centroid = _normalize([(1 - weight) * c + weight * v for c, v in zip(profile.centroid, vec)])
            else:
                profile.centroid = _normalize(list(vec))
        profile.centroid_weight += 1  # windows blended into the profile (both backends)
        profile.updated_at = datetime.now().isoformat()
        return profile

    def is_mature(self, profile: Optional[TopicProfile]) -> bool:
        return profile is not None and profile.centroid_weight >= self.config.min_profile_windows

    def blend_title(self, profile: TopicProfile, title: str, vec: Optional[List[float]] = None, source: str = "segment") -> TopicProfile:
        """Adds a segment/Bee title as a strong semantic anchor."""
        title = (title or "").strip()
        if not title:
            return profile
        bucket = profile.segment_titles if source == "segment" else profile.bee_titles
        if title in bucket:
            return profile
        bucket.append(title)
        del bucket[:-10]
        for term in set(content_terms(title)):
            profile.keywords[term] = profile.keywords.get(term, 0.0) + self.config.alpha
        if vec is not None and profile.centroid and len(profile.centroid) == len(vec):
            w = self.config.title_weight
            profile.centroid = _normalize([(1 - w) * c + w * v for c, v in zip(profile.centroid, vec)])
        profile.updated_at = datetime.now().isoformat()
        return profile

    # -- LLM tie-breaker ----------------------------------------------------------

    def judge(self, window_text: str, profile: Optional[TopicProfile], previous_text: str = "",
              event_title: Optional[str] = None) -> Optional[Verdict]:
        if not self._judge_enabled or profile is None:
            return None
        from src.core.models import get_fast_model, has_active_model_credentials

        if settings.mock_ai or not has_active_model_credentials(settings.gatekeeper_provider):
            return None
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            top_terms = [t for t, _ in sorted(profile.keywords.items(), key=lambda kv: kv[1], reverse=True)[:15]]
            prompt = (
                f"Ongoing event title: {event_title or 'unknown'}\n"
                f"Parts so far: {'; '.join(profile.segment_titles) or 'n/a'}\n"
                f"Bee conversation titles: {'; '.join(profile.bee_titles) or 'n/a'}\n"
                f"Frequent terms: {', '.join(top_terms)}\n\n"
                f"Last words before the pause:\n\"{' '.join(previous_text.split()[-150:])}\"\n\n"
                f"New speech after the pause:\n\"{window_text}\""
            )
            result: TopicContinuityVerdict = get_fast_model().with_structured_output(TopicContinuityVerdict).invoke([
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            logger.info(f"Topic continuity judge: {result.verdict} ({result.confidence:.2f}) {result.rationale}")
            return result.verdict if result else None
        except Exception as e:
            logger.warning(f"Topic continuity judge failed: {e}")
            return None
