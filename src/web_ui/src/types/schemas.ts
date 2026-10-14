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
  executive_summary?: string;
  areas_of_expertise?: string[];
  notable_work?: string[];
  shared_interests?: string[];
  linkedin_url?: string | null;
  github_url?: string | null;
  website_url?: string | null;
  confidence_score?: number;
  enrichment_source?: string;
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

export interface BeePairingInfo {
  status?: "already_connected" | "pairing_requested" | "disconnected" | string;
  connected?: boolean;
  account?: string | null;
  pairing_url?: string | null;
  request_id?: string | null;
  message?: string;
}

export interface DemoUser {
  user_id: string;
  handle: string;
  avatar_seed?: string;
  created_at: string;
  last_active?: string;
  gdpr_compliant: boolean;
  privacy_framework?: string;
  data_retention?: string;
  bee_connected: boolean;
  bee_account?: string | null;
  bee_pairing?: BeePairingInfo | null;
}

export interface EchoNotification {
  id: string;
  title: string;
  message: string;
  category: "action" | "routine" | "social" | "topic" | "system";
  targetTab?: string;
  timestamp: string;
}


