import re
from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ============================================================================
# 1. Gatekeeper Classifier Output (Stage 1)
# ============================================================================
class ChunkClassification(BaseModel):
    categories: List[Literal["social", "action", "deep_topic", "scheduled_task", "noop"]] = Field(
        description="Categories detected in the transcript chunk. 'noop' if irrelevant."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall classification confidence score."
    )
    summary_hint: str = Field(
        default="",
        description="Single-line concise summary of the useful signal detected."
    )


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


class SocialEntity(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique record identifier.")
    person_name: str = Field(description="Full name of person encountered.")
    company_or_role: Optional[str] = Field(default=None, description="Company, title, or professional context.")
    contact_info: Optional[str] = Field(default=None, description="Email, social handle, phone if mentioned.")
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
    # Ambient Voice Enhancements (Milestone 1.2)
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


# ============================================================================
# 5. LangGraph State Definition
# ============================================================================
class ExamenState(TypedDict, total=False):
    raw_transcript: str
    timestamp: str
    session_id: str
    categories: List[str]
    confidence: float
    summary_hint: str
    social_data: Optional[SocialEntity]
    action_data: Optional[VerifiedAction]
    scheduled_task: Optional[PlannedTask]
    topic_extracted: Optional[TopicExtraction]
    briefing_report: Optional[BriefingReport]
    error: Optional[str]
