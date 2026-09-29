"""Data contracts and schemas for EXAMEN."""

from datetime import datetime
from typing import Annotated, List, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ============================================================================
# 1. Gatekeeper Classifier Output (Stage 1)
# ============================================================================
class ChunkClassification(BaseModel):
    categories: List[Literal["social", "action", "deep_topic", "noop"]] = Field(
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
class SocialEntity(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique record identifier.")
    person_name: str = Field(description="Full name of person encountered.")
    company_or_role: Optional[str] = Field(default=None, description="Company, title, or professional context.")
    contact_info: Optional[str] = Field(default=None, description="Email, social handle, phone if mentioned.")
    commitments: List[str] = Field(
        default_factory=list,
        description="Promises made to or by the interlocutor."
    )
    key_topics: List[str] = Field(
        default_factory=list,
        description="Salient topic tags discussed during interaction."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of the encounter."
    )


# ============================================================================
# 3. Action-State & Routine Task Channel (Stage 3B)
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
    title: str = Field(description="Task description (e.g. 'unplug clothes iron', 'take blood pressure medication').")
    domain: Literal["safety", "routine", "work_task"] = Field(
        default="routine",
        description="Domain of action (safety, routine, work_task)."
    )
    scheduled_time: Optional[str] = Field(
        default=None,
        description="Target scheduled time (HH:MM or ISO timestamp)."
    )
    recurrence: Literal["none", "daily", "weekdays", "weekly"] = Field(
        default="none",
        description="Recurrence schedule pattern."
    )
    status: Literal["pending", "completed", "overdue", "skipped"] = Field(
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


# ============================================================================
# 4. Deep Topic Research Channel (Stage 3C)
# ============================================================================
class TopicExtraction(BaseModel):
    topic_title: str = Field(description="Succinct title of topic, bug, or technology.")
    context_type: Literal["bug", "feature_discussion", "tech_stack", "academic_lecture"] = Field(
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
    topic_extracted: Optional[TopicExtraction]
    briefing_report: Optional[BriefingReport]
    error: Optional[str]
