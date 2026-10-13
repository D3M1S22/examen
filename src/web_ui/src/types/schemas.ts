/**
 * Type mappings for Python backend Pydantic models (src/core/schemas.py)
 * Unified for EXAMEN AgentCore, FastMCP serving, and Next.js frontend.
 */

export interface ChunkClassification {
  chunk_id: string;
  categories: ("social" | "action" | "deep_topic" | "noop")[];
  confidence: number;
  summary_hint: string;
}

export interface VerifiedAction {
  id: string;
  timestamp: string;
  action_type: string;
  domain: "safety" | "routine" | "work_task";
  raw_statement: string;
  confidence: number;
  elapsed_time_human?: string;
  matched_task_id?: string;
}

export interface PlannedTask {
  id: string;
  title: string;
  domain: "safety" | "routine" | "work_task";
  status: "pending" | "completed" | "overdue" | "skipped";
  scheduled_time?: string;
  recurrence: string;
  verified_action_id?: string;
  created_at: string;
  completed_at?: string;
}

export interface SocialCommitment {
  id: string;
  contact_id?: string;
  contact_name: string;
  debtor: "user" | "contact";
  description: string;
  due_date_raw?: string;
  normalized_deadline?: string;
  status: "open" | "fulfilled" | "cancelled";
  created_at?: string;
  fulfilled_at?: string;
}

export type SourceType = "direct_profile" | "single_aggregator" | "multi_directory" | "irrelevant";

export interface EvaluatedSource {
  index: number;
  source_type: SourceType;
  is_target_individual: boolean;
  is_redundant_of_index?: number | null;
  usable_facts_extracted: string[];
  reason: string;
}

export interface DisambiguationResult {
  primary_direct_profile_index?: number | null;
  canonical_linkedin_url?: string | null;
  canonical_github_url?: string | null;
  verified_source_indices: number[];
  rejected_source_indices: number[];
  clean_combined_facts: string[];
  confidence_score: number;
  rationale: string;
}

export interface SocialWebProfile {
  headline?: string;
  organization?: string;
  current_role?: string;
  bio_summary?: string;
  areas_of_expertise?: string[];
  linkedin_url?: string | null;
  github_url?: string | null;
  website_url?: string | null;
  confidence_score?: number;
  enriched_at: string;
  disambiguation_report?: DisambiguationResult | null;
}

export interface SocialEntity {
  id: string;
  name: string;
  person_name?: string;
  company_or_role?: string;
  contact_info?: string;
  website_url?: string | null;
  first_met?: string;
  key_topics: string[];
  commitments: (SocialCommitment | string)[];
  web_profile?: SocialWebProfile;
  location_encountered?: string;
  session_id?: string;
  timestamp: string;
}

export type BriefingKind = "standalone" | "segment" | "checkpoint" | "final";

export interface BriefingReport {
  id: string;
  topic_title: string;
  context_type: "bug" | "feature_discussion" | "tech_stack" | "academic_lecture" | "system_incident" | "general_meeting";
  explanatory_synthesis?: string;
  executive_summary: string[];
  action_items: string[];
  web_sources: string[];
  deep_dive_markdown?: string;
  created_at: string;
  kind?: BriefingKind;
  session_id?: string | null;
  segment_id?: string | null;
}

export interface MicroEventRef {
  event_type: "action" | "social_contact" | "task_scheduled" | "social_commitment";
  record_id: string;
  headline: string;
  timestamp: string;
}

// Deep Topic Event Engine (docs/next_steps/deep_topic_event_engine/)
export type EventStatus = "active" | "paused" | "finalizing" | "concluded";
export type FinalStatus = "none" | "pending" | "synthesizing" | "ready" | "failed";
export type SegmentStatus = "open" | "closed" | "synthesizing" | "synthesized" | "skipped" | "failed";

export interface SessionSegment {
  segment_id: string;
  index: number;
  kind: "segment" | "checkpoint";
  title?: string | null;
  status: SegmentStatus;
  start_time: string;
  end_time?: string | null;
  time_range: string;
  word_count: number;
  close_reason?: string | null;
  briefing_id?: string | null;
  briefing?: BriefingReport | null;
}

export interface EventTransitionLog {
  at: string;
  from_status?: string | null;
  to_status: string;
  rule: string;
  reason: string;
  detail?: string | null;
}

/** Lightweight event card returned by GET /api/sessions */
export interface EventSummary {
  session_id: string;
  title?: string | null;
  domain: string;
  status: EventStatus;
  final_status: FinalStatus;
  start_time: string;
  last_updated_at: string;
  concluded_at?: string | null;
  paused_at?: string | null;
  hard_close_deadline?: string | null;
  location_name?: string | null;
  conversation_uuids: string[];
  segments: SessionSegment[];
  final_briefing_id?: string | null;
  final_title?: string | null;
  micro_events_count: number;
  linked_micro_events: MicroEventRef[];
  last_transition?: EventTransitionLog | null;
  transitions_count: number;
  top_terms: string[];
  transcript_chunks_count: number;
}

/** Full event returned by GET /api/sessions/{id} */
export interface EventDetail {
  found: boolean;
  session_id: string;
  title: string;
  domain: string;
  status: EventStatus;
  final_status: FinalStatus;
  start_time: string;
  concluded_at?: string | null;
  briefing_report?: BriefingReport | null;
  display_briefing?: BriefingReport | null;
  is_final: boolean;
  segments: SessionSegment[];
  transitions: EventTransitionLog[];
  linked_micro_events: MicroEventRef[];
  top_terms: string[];
  research_queries: string[];
  spoken_summary: string;
  paused_at?: string | null;
  hard_close_deadline?: string | null;
}

export interface EventEngineStatus {
  enabled: boolean;
  profile: string;
  config: { t_soft_seconds: number; t_hard_seconds: number; t_checkpoint_seconds: number; min_segment_words: number };
  clock_offset_seconds: number;
  virtual_now: string;
  active_event: {
    session_id: string;
    title: string;
    status: EventStatus;
    segments: number;
    open_segment_words: number;
    last_on_topic_at?: string | null;
    paused_at?: string | null;
    pending_chunks: number;
    top_terms: string[];
  } | null;
  pending_jobs: number;
  continuity_backend?: string | null;
}

/** @deprecated kept for older components; use EventSummary / EventDetail */
export type SessionDossier = EventSummary;

export interface EchoShowCardResponse {
  card_type?: string;
  ui_card_type?: string;
  display_template?: string;
  template?: string;
  title?: string;
  topic_title?: string;
  header_badge?: string;
  timestamp?: string;
  display_data?: Record<string, any>;
  card_payload?: Record<string, any>;
  spoken_summary?: string;
  voice_summary?: string;
  suggested_prompts?: string[];
  [key: string]: any;
}

export interface ExamenStatusResponse {
  status: string;
  version: string;
  active_tasks_count: number;
  verified_actions_count: number;
  contacts_count: number;
  topic_briefings_count: number;
  active_sessions_count?: number;
  uptime_seconds?: number;
}

export interface ExamenState {
  audio_buffer: string;
  current_classification?: ChunkClassification;
  identified_actions: VerifiedAction[];
  social_observations: SocialEntity[];
  topic_briefings: BriefingReport[];
  error?: string;
}
