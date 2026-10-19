from enum import Enum
import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import TypedDict


# Provenance of an entity: which ingestion path produced it (docs/next_steps/historical_backfill/)
IngestSource = Literal["live", "backfill", "simulator"]


# ============================================================================
# 0. Wearable Streaming & Multimodal Telemetry (Ingestion Layer)
# ============================================================================
class LocationTelemetry(BaseModel):
    latitude: float = Field(description="GPS latitude in decimal degrees.")
    longitude: float = Field(description="GPS longitude in decimal degrees.")
    place_name: Optional[str] = Field(default=None, description="Semantic or reverse-geocoded place name, e.g. 'Market St, San Francisco'.")
    semantic_zone: Optional[Literal["home", "work_office", "transit", "public_venue", "unknown"]] = Field(
        default=None,
        description="Coarse semantic categorization of user's spatial context."
    )
    accuracy_meters: Optional[float] = Field(default=None, description="GPS horizontal accuracy in meters.")
    captured_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when telemetry was captured."
    )

    @model_validator(mode="before")
    @classmethod
    def default_semantic_zone(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("semantic_zone") and data.get("place_name"):
                data["semantic_zone"] = cls.infer_semantic_zone(data.get("place_name"))
        return data

    @classmethod
    def infer_semantic_zone(cls, place_name: Optional[str]) -> Optional[Literal["home", "work_office", "transit", "public_venue"]]:
        if not place_name:
            return None
        # Whole words only: Bee places are postal addresses, where substrings misfire
        # ("Corso Carlo" is not a car, "Casale" is not a casa, "Barriera" is not a bar).
        words = set(re.findall(r"[^\W\d_]+", place_name.lower()))
        if words & {"home", "residence", "house", "apartment", "casa", "condo"}:
            return "home"
        if words & {"office", "corp", "work", "coworking", "lab", "hq", "ufficio", "building", "campus"}:
            return "work_office"
        if words & {"transit", "highway", "train", "metro", "bus", "station", "stazione", "airport", "subway",
                    "car", "auto", "autostrada"}:
            return "transit"
        if words & {"cafe", "coffee", "starbucks", "hotel", "restaurant", "bar", "convention", "center", "shop"}:
            return "public_venue"
        return "unknown"


class UtteranceChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique utterance chunk identifier.")
    conversation_uuid: str = Field(default="default_session", description="Conversation session UUID.")
    text: str = Field(description="Transcribed spoken audio utterance.")
    speaker_id: Optional[str] = Field(
        default=None,
        description="Speaker label: Bee person first name (tagged-utterance / REST speaker), 'Unknown', or a simulator label."
    )
    speaker_role: Optional[Literal["user", "contact", "unknown"]] = Field(
        default="unknown",
        description="Role of speaker: primary user ('user'), counterparty ('contact'), or 'unknown'."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Best-known ISO timestamp when the utterance occurred (spoken_at > received_at > now)."
    )
    received_at: Optional[str] = Field(
        default=None, description="ISO wall-clock time when the utterance was read from the Bee stream."
    )
    spoken_at: Optional[str] = Field(
        default=None, description="ISO time when the utterance was spoken, if the Bee payload provides it."
    )
    categories: List[str] = Field(
        default_factory=list, description="Gatekeeper categories assigned to this utterance."
    )
    location: Optional[dict] = Field(default=None, description="LocationTelemetry dict at time of speech.")
    source_key: Optional[str] = Field(
        default=None,
        description="Stable idempotency key of the source utterance (live:<conv>:<id> or bee:<conv>:<tx>:<utt>)."
    )
    bee_conversation_id: Optional[int] = Field(
        default=None, description="Numeric Bee REST conversation id, when known (history backfill)."
    )
    duration_ms: Optional[int] = Field(
        default=None, description="Utterance duration from Bee start/end (relative seconds), when known."
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_chunk_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "utterance_id" in data and "chunk_id" not in data:
                data["chunk_id"] = data["utterance_id"]
            if "id" in data and "chunk_id" not in data:
                data["chunk_id"] = data["id"]
        return data

    @property
    def utterance_id(self) -> str:
        return self.chunk_id


# ============================================================================
# 1. Gatekeeper Classifier Output (Stage 1)
# ============================================================================
class ChunkClassification(BaseModel):
    categories: List[Literal["social", "action", "deep_topic", "scheduled_task", "noop"]] = Field(
        default_factory=lambda: ["noop"],
        description="Categories detected in the transcript chunk. 'noop' if irrelevant."
    )
    confidence: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Overall classification confidence score."
    )
    summary_hint: str = Field(
        default="",
        description="Single-line concise summary of the useful signal detected."
    )

    @model_validator(mode="before")
    @classmethod
    def handle_empty_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "categories" not in data or not data["categories"]:
                data["categories"] = ["noop"]
            if "confidence" not in data or data["confidence"] is None:
                data["confidence"] = 0.85
            if "summary_hint" not in data:
                data["summary_hint"] = ""
        return data


# ============================================================================
# 2. Social Recall Channel (Stage 3A)
# ============================================================================
class SocialCommitment(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique commitment ID.")
    contact_name: str = Field(description="Full name or identifier of the contact involved.")
    debtor: Literal["user", "contact"] = Field(
        default="user",
        description="Whether the user promised the contact ('user'), or the contact promised the user ('contact')."
    )
    description: str = Field(description="Concrete action or deliverable promised.")
    due_date_raw: Optional[str] = Field(
        default=None,
        description="Spoken deadline phrase (e.g. 'by Monday 10 AM', 'tomorrow afternoon')."
    )
    normalized_deadline: Optional[str] = Field(
        default=None,
        description="Normalized ISO-8601 UTC timestamp computed relative to current reference time."
    )
    status: Literal["open", "fulfilled", "cancelled"] = Field(
        default="open",
        description="Current commitment status."
    )
    auto_scheduled_task_id: Optional[str] = Field(
        default=None,
        description="Linked PlannedTask ID if debtor == 'user'."
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Creation ISO timestamp."
    )

    def __str__(self) -> str:
        return self.description

    def lower(self) -> str:
        return self.description.lower()

    def __contains__(self, item: str) -> bool:
        return item in self.description


class SourceType(str, Enum):
    DIRECT_PROFILE = "direct_profile"
    SINGLE_ENTITY_AGGREGATOR = "single_aggregator"
    MULTI_ENTITY_DIRECTORY = "multi_directory"
    IRRELEVANT = "irrelevant"


class EvaluatedSource(BaseModel):
    """Evaluation of an individual candidate web search snippet/URL."""
    index: int
    source_type: SourceType = Field(default=SourceType.IRRELEVANT)
    is_target_individual: bool = Field(default=False)
    is_redundant_of_index: Optional[int] = Field(
        default=None,
        description="Index of direct profile that makes this aggregator redundant."
    )
    usable_facts_extracted: List[str] = Field(
        default_factory=list,
        description="Verified facts extracted strictly from this source."
    )
    reason: str = Field(default="", description="Reason for matching, redundancy, or rejection.")


class DisambiguationResult(BaseModel):
    """Structured report produced by LLM source evaluator & deduplicator."""
    primary_direct_profile_index: Optional[int] = Field(
        default=None,
        description="Index of primary direct profile if found."
    )
    canonical_linkedin_url: Optional[str] = Field(
        default=None,
        description="Canonical verified LinkedIn profile URL."
    )
    canonical_github_url: Optional[str] = Field(
        default=None,
        description="Canonical verified GitHub profile URL."
    )
    verified_source_indices: List[int] = Field(
        default_factory=list,
        description="Indices of verified, non-redundant sources for target individual."
    )
    rejected_source_indices: List[int] = Field(
        default_factory=list,
        description="Indices of rejected homonyms, redundant directories, or noise."
    )
    clean_combined_facts: List[str] = Field(
        default_factory=list,
        description="Consolidated list of isolated facts belonging strictly to target."
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of disambiguation (0.0 to 1.0)."
    )
    rationale: str = Field(
        default="",
        description="Explanation of entity clustering and source evaluation."
    )

    @field_validator("primary_direct_profile_index", mode="before")
    @classmethod
    def coerce_empty_to_none(cls, v):
        """Prevent Pydantic crash when LLM returns [], '', 'none', or 'null' instead of null."""
        if v is None:
            return None
        if isinstance(v, list):
            if len(v) == 1 and isinstance(v[0], int):
                return v[0]
            return None
        if isinstance(v, str):
            stripped = v.strip().lower()
            if stripped in ("", "none", "null", "[]"):
                return None
            if stripped.isdigit():
                return int(stripped)
        return v

    @field_validator("canonical_linkedin_url", "canonical_github_url", mode="before")
    @classmethod
    def coerce_url_to_str(cls, v):
        """Accept LLM outputs like [], ['https://...'], '' or 'null' for single URL fields."""
        if isinstance(v, list):
            v = next((x for x in v if isinstance(x, str) and x.strip()), None)
        if isinstance(v, str) and v.strip().lower() in ("", "none", "null", "[]"):
            return None
        return v

    @field_validator("verified_source_indices", "rejected_source_indices", mode="before")
    @classmethod
    def coerce_indices_to_list(cls, v):
        """Accept LLM outputs like null, 3 or '1, 2' for index lists."""
        if v is None:
            return []
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            return [int(d) for d in re.findall(r"\d+", v)]
        return v

    @field_validator("clean_combined_facts", mode="before")
    @classmethod
    def coerce_facts_to_list(cls, v):
        """Accept a single fact string (or null) instead of a list of facts."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() and v.strip().lower() not in ("none", "null", "[]") else []
        return v


class SocialWebProfile(BaseModel):
    headline: Optional[str] = Field(default=None, description="e.g. 'VP of Infrastructure at CloudScale | ex-AWS'")
    organization: Optional[str] = Field(default=None, description="Current company, lab, or institution.")
    current_role: Optional[str] = Field(default=None, description="Specific professional title or role.")
    bio_summary: Optional[str] = Field(
        default=None,
        description="Concise 2-3 sentence authoritative executive summary of professional background."
    )
    areas_of_expertise: List[str] = Field(default_factory=list, description="Top 3-5 technical or business domains.")
    linkedin_url: Optional[str] = Field(default=None, description="Canonical public LinkedIn URL if verified.")
    website_url: Optional[str] = Field(default=None, description="Company, academic, or personal homepage URL.")
    github_url: Optional[str] = Field(default=None, description="Public GitHub URL or handle if verified.")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Verification confidence score.")
    enriched_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when the web profile was synthesized."
    )
    disambiguation_report: Optional[DisambiguationResult] = Field(
        default=None,
        description="Structured disambiguation and source evaluation audit report."
    )


class SocialEntity(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique record identifier.")
    person_name: str = Field(description="Full name of person encountered.")
    company_or_role: Optional[str] = Field(default=None, description="Company, title, or professional context.")
    contact_info: Optional[str] = Field(default=None, description="Email, social handle, phone if mentioned.")
    website_url: Optional[str] = Field(
        default=None,
        description="Personal portfolio, company website, or blog URL explicitly stated in conversation."
    )
    commitments: List[Union[SocialCommitment, str]] = Field(
        default_factory=list,
        description="Bilateral commitments made to or by the interlocutor (structured SocialCommitment or raw string)."
    )
    key_topics: List[str] = Field(
        default_factory=list,
        description="Salient topic tags discussed during interaction."
    )
    web_profile: Optional[SocialWebProfile] = Field(
        default=None,
        description="Autonomously synthesized executive web dossier."
    )
    location_encountered: Optional[str] = Field(
        default=None,
        description="Place or semantic venue where the encounter occurred (e.g. 'Starbucks on 4th', 'Moscone Center')."
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Linked conversation session or meeting identifier."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of the encounter."
    )

    def get_commitments_as_objects(self) -> List[SocialCommitment]:
        """Returns all commitments normalized as SocialCommitment models."""
        result: List[SocialCommitment] = []
        for c in self.commitments:
            if isinstance(c, SocialCommitment):
                result.append(c)
            elif isinstance(c, dict):
                result.append(SocialCommitment(**c))
            elif isinstance(c, str):
                is_user = bool(re.search(r"^(i\s|i'll\s|i\s+will\s|let\s+me\s|ti\s+mando|ti\s+invio)", c.strip(), re.I))
                result.append(SocialCommitment(
                    contact_name=self.person_name,
                    debtor="user" if is_user else "contact",
                    description=c.strip(),
                    status="open",
                ))
        return result


# ============================================================================
# 3. Action-State & Routine Task Channel (Stage 3B & Stage 3D)
# ============================================================================
class VerifiedAction(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique action identifier.")
    action_type: str = Field(
        description="Normalized action type: iron_unplugged, stove_off, door_locked, medication_taken, pr_merged, email_sent."
    )
    domain: Literal["safety", "routine", "work_task"] = Field(
        description="Domain of action (home safety, personal routine, or work task)."
    )
    raw_statement: str = Field(
        description="Exact utterance spoken by user verifying completed action."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Certainty score verifying completion (filtering out doubts and future intentions)."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when the action was confirmed."
    )
    is_revoked: bool = Field(
        default=False,
        description="True if the action was subsequently canceled or revoked."
    )
    matched_task_id: Optional[str] = Field(
        default=None,
        description="Linked PlannedTask id if this action fulfilled a scheduled task."
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Linked conversation session or meeting identifier."
    )
    location: Optional[dict] = Field(
        default=None,
        description="LocationTelemetry dict at time of action confirmation."
    )
    ingest_source: IngestSource = Field(default="live", description="Ingestion path that produced the action.")
    ingest_run_id: Optional[str] = Field(default=None, description="Backfill run that produced the action.")
    source_key: Optional[str] = Field(default=None, description="Idempotency key of the source utterance.")


class PlannedTask(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique task identifier.")
    title: str = Field(description="Task description (e.g. 'unplug clothes iron', 'Call Dr. Smith').")
    domain: Literal["safety", "routine", "work_task", "personal"] = Field(
        default="routine",
        description="Domain of action (safety, routine, work_task, personal)."
    )
    scheduled_time: Optional[str] = Field(
        default=None,
        description="Target scheduled time (HH:MM or ISO timestamp)."
    )
    recurrence: Literal["none", "daily", "weekdays", "weekly"] = Field(
        default="none",
        description="Recurrence schedule pattern."
    )
    status: Literal["pending", "completed", "overdue", "skipped", "cancelled"] = Field(
        default="pending",
        description="Current task status."
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when the task was completed."
    )
    verified_action_id: Optional[str] = Field(
        default=None,
        description="Foreign key linking to the VerifiedAction that fulfilled this task."
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Creation timestamp."
    )
    # Ambient Voice Enhancements (Milestone 1.2 & 3.1)
    origin: Literal["manual", "ambient_voice", "social_commitment"] = Field(
        default="manual",
        description="Source modality of task registration."
    )
    raw_statement: Optional[str] = Field(
        default=None,
        description="Verbatim spoken utterance indicating intention."
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Extraction confidence score."
    )
    relative_time_anchor: Optional[str] = Field(
        default=None,
        description="Exact spoken temporal anchor, e.g. 'at 3 PM tomorrow', 'in an hour'."
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Linked session/meeting ID if extracted from an ambient session."
    )
    location: Optional[dict] = Field(
        default=None,
        description="LocationTelemetry dict at time of task scheduling."
    )
    ingest_source: IngestSource = Field(default="live", description="Ingestion path that produced the task.")
    ingest_run_id: Optional[str] = Field(default=None, description="Backfill run that produced the task.")
    source_key: Optional[str] = Field(default=None, description="Idempotency key of the source utterance.")
    recovered: bool = Field(
        default=False,
        description="True when a history backfill created the task after its scheduled time had already passed."
    )


class ScheduledTaskExtraction(BaseModel):
    title: str = Field(description="Clean imperative title of task, e.g., 'Call Dr. Smith', 'Turn off irrigation valve'")
    domain: Literal["safety", "routine", "work_task", "personal"] = Field(
        default="routine",
        description="Domain of action: safety, routine, work_task, personal."
    )
    scheduled_time: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp computed relative to current reference time, or null if no specific time indicated."
    )
    relative_time_anchor: Optional[str] = Field(
        default=None,
        description="Exact phrase indicating the temporal anchor, e.g. 'at 3 PM tomorrow', 'in 20 minutes'."
    )
    recurrence: Literal["none", "daily", "weekdays", "weekly"] = Field(
        default="none",
        description="Recurrence pattern if repeating."
    )
    confidence: float = Field(
        default=0.95, ge=0.0, le=1.0,
        description="Extraction certainty score."
    )


# ============================================================================
# 4. Deep Topic Research Channel (Stage 3C)
# ============================================================================
class TopicExtraction(BaseModel):
    topic_title: str = Field(description="Succinct title of topic, bug, or technology.")
    context_type: Literal[
        "bug",
        "feature_discussion",
        "tech_stack",
        "academic_lecture",
        "system_incident",
        "general_meeting",
    ] = Field(
        description="Type of context that triggered the topic."
    )
    search_queries: List[str] = Field(
        default_factory=list,
        description="1-3 focused web search queries to retrieve authoritative documentation."
    )
    key_questions: List[str] = Field(
        default_factory=list,
        description="Core questions or technical aspects to resolve in the report."
    )


class BriefingReport(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique briefing identifier.")
    topic_title: str = Field(description="Title of explored topic.")
    context_type: str = Field(description="Context classification.")
    executive_summary: List[str] = Field(
        default_factory=list,
        description="Executive summary in 3-4 bullet points."
    )
    explanatory_synthesis: str = Field(
        default="",
        description=(
            "A cohesive, authoritative narrative (2-3 paragraphs) that explains and deep dives "
            "into the concepts discussed using findings from retrieved web documentation. "
            "Tailored to be educational, practical, and immediately usable."
        )
    )
    deep_dive_markdown: str = Field(
        default="",
        description="In-depth dossier with definitions, solutions, or documentation in Markdown."
    )
    web_sources: List[str] = Field(
        default_factory=list,
        description="Consulted external URLs and sources."
    )
    action_items: List[str] = Field(
        default_factory=list,
        description="Suggested action items or next steps."
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Creation date and time of the report."
    )
    session_id: Optional[str] = Field(
        default=None, description="Event (SessionDossier) this briefing belongs to, if any."
    )
    segment_id: Optional[str] = Field(
        default=None, description="Event segment this briefing synthesizes (segment/checkpoint kinds)."
    )
    kind: Literal["standalone", "segment", "checkpoint", "final"] = Field(
        default="standalone",
        description="standalone (single invocation), segment/checkpoint (progressive), final (consolidated event)."
    )


# ============================================================================
# 5. Macro Session & Micro-Event Decoupling (Milestone 3.2)
# ============================================================================
class MicroEventRef(BaseModel):
    event_type: Literal["action", "social_contact", "task_scheduled", "social_commitment"] = Field(
        description="Type of micro-event decoupled from the session."
    )
    record_id: str = Field(description="Database identifier of the micro-event.")
    headline: str = Field(description="Concise description or title of the micro-event.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when the micro-event occurred."
    )


class SessionSegment(BaseModel):
    """Contiguous run of on-topic activity inside an event (Deep Topic Event Engine)."""
    segment_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique segment identifier.")
    index: int = Field(default=1, description="1-based order of the segment inside the event.")
    kind: Literal["segment", "checkpoint"] = Field(
        default="segment", description="'checkpoint' when closed by the periodic checkpoint rule."
    )
    start_time: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO utterance time of the first chunk."
    )
    end_time: Optional[str] = Field(default=None, description="ISO utterance time of the last chunk.")
    word_count: int = Field(default=0, description="Words accumulated in the segment.")
    title: Optional[str] = Field(default=None, description="Segment title produced by synthesis.")
    status: Literal["open", "closed", "synthesizing", "synthesized", "skipped", "failed"] = Field(
        default="open", description="Segment lifecycle status."
    )
    close_reason: Optional[str] = Field(default=None, description="Rule reason that closed the segment.")
    briefing_id: Optional[str] = Field(default=None, description="Segment/checkpoint BriefingReport ID.")


class EventTransitionLog(BaseModel):
    """Audit trail entry for an event lifecycle transition."""
    at: str = Field(description="ISO time of the transition (engine clock).")
    from_status: Optional[str] = Field(default=None, description="Status before the transition.")
    to_status: str = Field(description="Status after the transition.")
    rule: str = Field(description="Rule identifier (R0..R9).")
    reason: str = Field(description="Machine-readable reason.")
    detail: Optional[str] = Field(default=None, description="Human-readable detail.")


class TopicProfile(BaseModel):
    """Rolling representation of what an event is about (docs/.../02_topic_continuity_detection.md)."""
    centroid: Optional[List[float]] = Field(default=None, description="EWMA of on-topic window embeddings.")
    centroid_weight: float = Field(default=0.0, description="Number of windows blended into the centroid.")
    keywords: Dict[str, float] = Field(default_factory=dict, description="Decayed content-term weights.")
    segment_titles: List[str] = Field(default_factory=list, description="Titles of synthesized segments.")
    bee_titles: List[str] = Field(default_factory=list, description="Bee conversation titles/summaries.")
    updated_at: Optional[str] = Field(default=None, description="ISO time of the last update.")


class SessionDossier(BaseModel):
    session_id: str = Field(description="Event identifier (engine-minted) or legacy Bee conversation UUID.")
    title: Optional[str] = Field(default=None, description="Evolving or finalized title of the macro session.")
    domain: Literal["meeting", "lecture", "technical_debate", "general"] = Field(
        default="meeting",
        description="Categorization of the macro session context."
    )
    start_time: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when the session began."
    )
    last_updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp when the session was last updated."
    )
    concluded_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp when the session was marked concluded."
    )
    status: Literal["active", "paused", "finalizing", "concluded"] = Field(
        default="active",
        description="Lifecycle status of the session ('finalizing' is a legacy alias of 'paused')."
    )
    location: Optional[dict] = Field(
        default=None,
        description="Spatial telemetry associated with the macro session."
    )
    transcript_chunks: List[str] = Field(
        default_factory=list,
        description="Accumulated verbatim audio transcript chunks."
    )
    key_discussion_points: List[str] = Field(
        default_factory=list,
        description="Salient discussion themes and decisions made."
    )
    linked_micro_events: List[MicroEventRef] = Field(
        default_factory=list,
        description="Decoupled micro-events (actions, tasks, contacts) linked to this session."
    )
    final_briefing_id: Optional[str] = Field(
        default=None,
        description="Linked BriefingReport ID after holistic Stage 3C synthesis."
    )
    briefing_report: Optional[BriefingReport] = Field(
        default=None,
        description="Full synthesized BriefingReport object if available."
    )
    # Deep Topic Event Engine
    conversation_uuids: List[str] = Field(
        default_factory=list, description="Bee conversation UUIDs spanned by this event."
    )
    segments: List[SessionSegment] = Field(
        default_factory=list, description="Contiguous on-topic segments of the event."
    )
    anchor_location: Optional[dict] = Field(
        default=None, description="Reference location of the event (median of first-segment fixes)."
    )
    last_on_topic_at: Optional[str] = Field(default=None, description="ISO time of the last on-topic chunk.")
    paused_at: Optional[str] = Field(default=None, description="ISO time the event was last paused.")
    hard_close_deadline: Optional[str] = Field(
        default=None, description="ISO deadline overriding the default hard-close timeout (closing cue, transit)."
    )
    final_status: Literal["none", "pending", "synthesizing", "ready", "failed"] = Field(
        default="none", description="Status of the consolidated final briefing."
    )
    final_revision: int = Field(default=0, description="Incremented whenever the final briefing is regenerated.")
    research_ledger: List[dict] = Field(
        default_factory=list,
        description="Web research already run for this event: [{'query', 'sources', 'segment_id', 'kind'}].",
    )
    topic_profile: Optional[TopicProfile] = Field(
        default=None, description="Rolling topic profile used for continuity decisions."
    )
    pending_chunk_ids: List[str] = Field(
        default_factory=list, description="Chunks awaiting the resume-vs-split decision while paused."
    )
    transitions: List[EventTransitionLog] = Field(
        default_factory=list, description="Lifecycle audit trail."
    )
    ingest_source: IngestSource = Field(default="live", description="Ingestion path that owns this event.")
    ingest_run_id: Optional[str] = Field(default=None, description="Backfill run that owns this event.")

    @property
    def open_segment(self) -> Optional[SessionSegment]:
        if self.segments and self.segments[-1].status == "open":
            return self.segments[-1]
        return None


# ============================================================================
# 6. LangGraph State Definition
# ============================================================================
class ExamenState(TypedDict, total=False):
    raw_transcript: str
    timestamp: str
    session_id: str
    event_managed: bool  # True when the Deep Topic Event Engine owns deep_topic synthesis
    categories: List[str]
    confidence: float
    summary_hint: str
    social_data: Optional[SocialEntity]
    action_data: Optional[VerifiedAction]
    scheduled_task: Optional[PlannedTask]
    topic_extracted: Optional[TopicExtraction]
    briefing_report: Optional[BriefingReport]
    session_dossier: Optional[SessionDossier]
    error: Optional[str]
    # Ingestion Stream & Multimodal Context (Milestone 3.1)
    historical_context: Optional[str]
    location: Optional[dict]
    speaker: Optional[str]
    speaker_role: Optional[str]
    utterance_id: Optional[str]
    # Historical Transcript Backfill
    source_key: Optional[str]
    ingest_source: str
    ingest_run_id: Optional[str]


# ============================================================================
# 7. Historical Transcript Backfill (docs/next_steps/historical_backfill/)
# ============================================================================
class CoverageInterval(BaseModel):
    """Time span during which an ingestion path reliably screened what Bee transcribed."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Interval identifier.")
    source: Literal["live", "backfill"] = Field(description="Ingestion path that covered the span.")
    start: str = Field(description="ISO start of the span.")
    end: str = Field(description="ISO end of the span (advanced while open).")
    is_open: bool = Field(default=False, description="True while the live stream is still connected.")
    degraded: bool = Field(default=False, description="True when the error rate inside the span was high.")
    run_id: Optional[str] = Field(default=None, description="Backfill run that produced the span.")
    utterances: int = Field(default=0, description="Utterances processed inside the span.")
    errors: int = Field(default=0, description="Utterances whose analysis failed inside the span.")


class CoverageGap(BaseModel):
    start: str = Field(description="ISO start of the uncovered span.")
    end: str = Field(description="ISO end of the uncovered span.")
    seconds: float = Field(description="Duration in seconds.")


class BackfillEstimate(BaseModel):
    gatekeeper_calls: int = 0
    expected_qualified: int = 0
    events_expected: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0


class BackfillPlan(BaseModel):
    """Cost-free preview of a backfill run (REST calls to Bee only, no LLM)."""
    window_from: str
    window_to: str
    mode: Literal["gaps_only"] = "gaps_only"
    retry_failed_live: bool = True
    coverage: Dict[str, float] = Field(default_factory=dict)
    gaps: List[CoverageGap] = Field(default_factory=list)
    conversations: Dict[str, int] = Field(default_factory=dict)
    utterances: Dict[str, int] = Field(default_factory=dict)
    estimate: BackfillEstimate = Field(default_factory=BackfillEstimate)
    warnings: List[str] = Field(default_factory=list)
    deferred_conversation_ids: List[int] = Field(default_factory=list)


BackfillRunStatus = Literal[
    "planned", "fetching", "replaying", "synthesizing", "completed", "partial", "failed", "cancelled"
]


class BackfillRun(BaseModel):
    """One persisted, resumable execution that fills the gaps of a time window."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Run identifier.")
    trigger: Literal["startup", "reconnect", "manual", "deferred_recheck"] = "manual"
    window_from: str
    window_to: str
    status: BackfillRunStatus = "planned"
    retry_failed_live: bool = True
    plan: Optional[BackfillPlan] = None
    counters: Dict[str, int] = Field(default_factory=dict)
    last_source_key: Optional[str] = Field(default=None, description="Checkpoint: last committed utterance.")
    last_ts: Optional[str] = Field(default=None, description="Checkpoint: spoken time of the last committed utterance.")
    not_before: Optional[str] = Field(default=None, description="Earliest start (startup / reconnect delays).")
    confirm_over_budget: bool = Field(default=False, description="Manual confirmation of an over-budget estimate.")
    error: Optional[str] = None
    requested_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "partial", "failed", "cancelled")
