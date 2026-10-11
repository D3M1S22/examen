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

export interface SocialWebProfile {
  executive_summary: string;
  linkedin_url?: string;
  github_url?: string;
  current_role?: string;
  organization?: string;
  notable_work: string[];
  shared_interests: string[];
  enrichment_source: string;
  enriched_at: string;
}

export interface SocialEntity {
  id: string;
  name: string;
  person_name?: string;
  company_or_role?: string;
  contact_info?: string;
  first_met?: string;
  key_topics: string[];
  commitments: (SocialCommitment | string)[];
  web_profile?: SocialWebProfile;
  location_encountered?: string;
  session_id?: string;
  timestamp: string;
}

export interface BriefingReport {
  id: string;
  topic_title: string;
  context_type: "bug" | "feature_discussion" | "tech_stack" | "academic_lecture";
  explanatory_synthesis?: string;
  executive_summary: string[];
  action_items: string[];
  web_sources: string[];
  deep_dive_markdown?: string;
  created_at: string;
}

export interface MicroEventRef {
  event_type: "action" | "social" | "topic";
  event_id: string;
  summary: string;
  timestamp: string;
}

export interface SessionDossier {
  id: string;
  session_name: string;
  start_time: string;
  end_time?: string;
  status: "active" | "concluded";
  participants: string[];
  summary?: string;
  micro_events: MicroEventRef[];
}

export interface EchoShowCardResponse {
  card_type: string;
  template: string;
  title: string;
  header_badge?: string;
  timestamp: string;
  display_data: Record<string, any>;
  voice_summary: string;
  suggested_prompts?: string[];
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
