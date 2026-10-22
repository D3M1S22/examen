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
  session_id?: string | null;
  ingest_source?: IngestSource;
  ingest_run_id?: string | null;
}

export interface PlannedTask {
  id: string;
  title: string;
  domain: "safety" | "routine" | "work_task" | "personal";
  status: "pending" | "completed" | "overdue" | "skipped" | "cancelled";
  scheduled_time?: string | null;
  recurrence: string;
  verified_action_id?: string | null;
  created_at: string;
  completed_at?: string | null;
  origin?: "manual" | "ambient_voice" | "social_commitment";
  /** Sentence the routine was scheduled from (voice) or the commitment text */
  raw_statement?: string | null;
  /** Transcript of the action that completed the routine (GET /api/routines) */
  completion_statement?: string | null;
  session_id?: string | null;
  ingest_source?: IngestSource;
  ingest_run_id?: string | null;
  recovered?: boolean;
}

// Manual curation (docs/next_steps/manual_curation/04): bodies of the PUT routes
export interface ActionChanges {
  action_type?: string;
  domain?: VerifiedAction["domain"];
}

export interface TaskChanges {
  title?: string;
  domain?: PlannedTask["domain"];
  scheduled_time?: string;
  recurrence?: "none" | "daily" | "weekdays" | "weekly";
}

export interface ContactChanges {
  person_name?: string;
  company_or_role?: string;
  contact_info?: string;
  website_url?: string;
  key_topics?: string[];
  location_encountered?: string;
}

/** GET /api/contacts/{id}/cascade: what deleting a contact also deletes */
export interface ContactCascade {
  id: string;
  name: string;
  commitments: { id: string; description: string; debtor: "user" | "contact"; status: string }[];
  tasks: { id: string; title: string }[];
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

export interface DossierFolderDef {
  id: string;
  name: string;
  icon: string;
  accent: "amber" | "cyan" | "emerald" | "purple" | "blue" | "zinc";
  description: string;
  contextTypes: string[];
  isEventFolder?: boolean;
}

export const DEFAULT_DOSSIER_FOLDERS: DossierFolderDef[] = [
  {
    id: "academic",
    name: "Academic & Lectures",
    icon: "🏛️",
    accent: "amber",
    description: "University lectures, symposiums, theoretical foundations & scientific research",
    contextTypes: ["academic_lecture"],
  },
  {
    id: "tech_stack",
    name: "Tech Stack & Systems",
    icon: "💻",
    accent: "cyan",
    description: "System architecture, distributed algorithms, AI frameworks & protocols",
    contextTypes: ["tech_stack"],
  },
  {
    id: "engineering",
    name: "Product & Engineering",
    icon: "🚀",
    accent: "emerald",
    description: "Feature specs, engineering standups, bug postmortems & incident reports",
    contextTypes: ["feature_discussion", "bug", "system_incident"],
  },
  {
    id: "business",
    name: "Strategy & Business",
    icon: "💼",
    accent: "purple",
    description: "Executive debriefs, roadmap planning, stakeholder meetings & leadership syncs",
    contextTypes: ["general_meeting"],
  },
  {
    id: "event_sessions",
    name: "Event Sessions & Symposia",
    icon: "⚡",
    accent: "blue",
    description: "Deep Topic Event Engine multi-part macro recordings with live synthesis",
    contextTypes: [],
    isEventFolder: true,
  },
];

export interface DossierBreadcrumbItem {
  id: string;
  label: string;
  icon?: string;
  path?: string;
  count?: number;
  isCurrent?: boolean;
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
  ingest_source?: IngestSource;
  ingest_run_id?: string | null;
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

export interface BeePairingInfo {
  // idle | starting | pending (link/QR shown) | verifying (bee me / one-Bee-per-user check) | connected
  // | expired | failed | conflict (Bee account held by another user) | invalid (login rejected)
  status?: "idle" | "starting" | "pending" | "verifying" | "connected" | "expired" | "failed" | "conflict" | "invalid" | string;
  connected?: boolean;
  account?: string | null;
  pairing_url?: string | null;
  expires_in_seconds?: number | null;
  error?: string | null;
  message?: string;
}

// View model of the signed-in account (built from /api/auth/session by utils/auth.ts toUiUser)
export interface DemoUser {
  user_id: string;
  handle: string;
  email?: string | null;
  avatar_seed?: string;
  created_at: string;
  last_active?: string;
  gdpr_compliant: boolean;
  privacy_framework?: string;
  data_retention?: string;
  bee_connected: boolean;
  bee_account?: string | null;
  bee_pairing?: BeePairingInfo | null;
  /** Live status of the user's Bee (STREAMING, LISTENING, CAPACITY, ...) and its explanation */
  bee_status?: string | null;
  bee_detail?: string | null;
  is_admin?: boolean;
}

export interface EchoNotification {
  id: string;
  title: string;
  message: string;
  category: "action" | "routine" | "social" | "topic" | "system";
  targetTab?: string;
  timestamp: string;
}



// ============================================================================
// Historical Transcript Backfill (docs/next_steps/historical_backfill/04)
// ============================================================================

/** Ingestion path that produced an entity. */
export type IngestSource = "live" | "backfill" | "simulator";

export interface CoverageInterval {
  id: string;
  source: "live" | "backfill";
  start: string;
  end: string;
  is_open: boolean;
  degraded: boolean;
  run_id?: string | null;
  utterances: number;
  errors: number;
}

export interface CoverageGap {
  start: string;
  end: string;
  seconds: number;
}

export interface CoverageSummary {
  live_seconds: number;
  backfill_seconds: number;
  gap_seconds: number;
}

export interface CoverageBucket extends CoverageSummary {
  start: string;
  end: string;
}

/** GET /api/backfill/coverage */
export interface CoverageResponse {
  window_from: string;
  window_to: string;
  live_since?: string | null;
  summary: CoverageSummary;
  intervals: CoverageInterval[];
  gaps: CoverageGap[];
  buckets: CoverageBucket[];
}

export interface BackfillEstimate {
  gatekeeper_calls: number;
  expected_qualified: number;
  events_expected: number;
  cost_usd: number;
  duration_s: number;
}

/** POST /api/backfill/preview (cost-free plan) */
export interface BackfillPlan {
  window_from: string;
  window_to: string;
  mode: "gaps_only";
  retry_failed_live: boolean;
  coverage: CoverageSummary;
  gaps: CoverageGap[];
  conversations: Record<string, number>;
  utterances: Record<string, number>;
  estimate: BackfillEstimate;
  warnings: string[];
  deferred_conversation_ids: number[];
  over_budget?: boolean;
}

export type BackfillRunStatus =
  | "planned"
  | "fetching"
  | "replaying"
  | "synthesizing"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";

export interface BackfillRun {
  id: string;
  trigger: "startup" | "reconnect" | "manual" | "deferred_recheck";
  window_from: string;
  window_to: string;
  status: BackfillRunStatus;
  retry_failed_live: boolean;
  plan?: BackfillPlan | null;
  counters: Record<string, number>;
  last_source_key?: string | null;
  last_ts?: string | null;
  not_before?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

/** SSE backfill_* payloads and /api/status telemetry.backfill.active_run */
export interface BackfillProgress {
  run_id: string;
  trigger: BackfillRun["trigger"];
  status: BackfillRunStatus;
  window_from: string;
  window_to: string;
  processed: number;
  selected: number;
  qualified: number;
  failed: number;
  events: number;
  progress: number;
  eta_s?: number | null;
  counters?: Record<string, number>;
}

/** /api/status telemetry.coverage + telemetry.backfill */
export interface HistoryTelemetry {
  coverage?: {
    live_since?: string | null;
    last_gap?: CoverageGap | null;
    uncovered_seconds_7d?: number | null;
  };
  backfill?: {
    enabled: boolean;
    active_run: BackfillProgress | null;
    queued: number;
  };
}
