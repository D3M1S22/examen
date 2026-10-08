/**
 * Type mappings for Python backend Pydantic models (src/core/schemas.py)
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
  updated_at: string;
}

export interface SocialEntity {
  id: string;
  name: string;
  company_or_role?: string;
  contact_info?: string;
  first_met?: string;
  key_topics: string[];
  commitments: string[];
  timestamp: string;
}

export interface BriefingReport {
  id: string;
  topic_title: string;
  context_type: "bug" | "feature_discussion" | "tech_stack" | "academic_lecture";
  executive_summary: string[];
  action_items: string[];
  web_sources: string[];
  created_at: string;
}

export interface ExamenState {
  audio_buffer: string;
  current_classification?: ChunkClassification;
  identified_actions: VerifiedAction[];
  social_observations: SocialEntity[];
  topic_briefings: BriefingReport[];
  error?: string;
}
