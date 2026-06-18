// Shared types mirroring the FastAPI responses (rep_engine.api).

export type Role = "admin" | "client";

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  business_ids: number[] | null; // null => admin (all businesses)
}

export interface Business {
  id: number;
  name: string;
  domain: string | null;
  geo: string | null;
  goal: string | null;
  contested_terms: string | null;
  created_at?: string;
  can_edit?: boolean; // may the current user take actions on this business?
}

export interface WorkOrder {
  id: number;
  wo_code: string | null;
  title: string | null;
  capability: string | null;
  execution: string | null;
  phase: string | null;
  status: string;
  assignee: string | null;
  target_date: string | null;
  instruction: string | null;
  recommended_tool: string | null;
  result_notes: string | null;
}

export interface ContentDraft {
  id: number;
  work_order_id: number | null;
  asset_type: string | null;
  title: string | null;
  body: string | null;
  target_query: string | null;
  quality_score: number | null;
  compliance_pass: boolean | null;
  compliance_flags: unknown;
  status: string;
  revision_count: number | null;
  reviewer: string | null;
}

export interface ProductionBrief {
  id: number;
  channel: string;
  platform: string | null;
  title: string | null;
  target_query: string | null;
  brief: Record<string, unknown>;
  status: string;
}

export interface DiscoveryTarget {
  id: number;
  channel: string | null;
  name: string | null;
  outlet: string | null;
  url: string | null;
  beat: string | null;
  score: number | null;
  rationale: string | null;
  status: string | null;
}

export interface SeriesPoint {
  run_id: number;
  date: string;
  goal_alignment: number;
  contested_rate: number;
  owned_rate: number;
}

export interface AuditRun {
  id: number;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  goal_alignment: number | null;
  contested_rate: number | null;
  owned_rate: number | null;
  n_answers: number;
}

export interface Answer {
  id: number;
  engine: string;
  prompt: string;
  answer_text: string | null;
  sentiment: string | null;
  goal_alignment: number | null;
  cited_sources: unknown;
  mentions_contested: boolean | null;
  surfaces_owned: boolean | null;
  awareness: boolean | null; // does the engine RECOGNIZE the business (vs no-info)?
  entity_confusion: boolean | null; // is the answer about a DIFFERENT same-named entity?
  persona: string | null;
  location: string | null;
  failed: boolean | null;
}

// Primary-challenge profile: is the business's problem an awareness gap (a void to
// fill, faster) or an entrenched negative narrative (slower to crowd out)?
export type ChallengeProfile =
  | "awareness_gap"
  | "negative_narrative"
  | "mixed"
  | "established_positive"
  | "unknown";

export type ChallengeTrack = "fill_void" | "crowd_out" | "both" | "defend" | "none";

export interface ChallengeEngine {
  profile: ChallengeProfile;
  label: string;
  track: ChallengeTrack;
  n: number;
  unaware_rate: number | null;
  entity_confusion_rate: number | null;
  recognition_gap: number | null;
  negative_score: number | null;
  contested_rebutted_rate: number | null;
  avg_alignment: number | null;
}

export interface Challenge {
  business: string;
  run_id: number | null;
  profile: ChallengeProfile;
  label: string;
  track: ChallengeTrack;
  void_fill_factor: number;
  sample_size: number;
  headline: string;
  recommendation: string;
  signals: {
    unaware_rate: number | null;
    awareness_rate: number | null;
    entity_confusion_rate: number | null;
    recognition_gap: number | null;
    contested_rate: number | null;
    contested_rebutted_rate: number | null;
    negative_rate: number | null;
    negative_score: number | null;
    avg_alignment: number | null;
    awareness_known_n?: number;
  };
  by_engine?: Record<string, ChallengeEngine>;
  basis?: string;
}

// Confidence interval: `mean` for goal_alignment (normal approx), `p` for rates (Wilson).
export interface CI {
  p?: number;
  mean?: number;
  low: number | null;
  high: number | null;
  n: number;
}

export interface EngineMetrics {
  n: number;
  goal_alignment: CI | null;
  contested_rate: CI | null;
  owned_rate: CI | null;
  grounded_rate: CI | null;
}

export interface PerEngineMetrics {
  run_id: number | null;
  engines: Record<string, EngineMetrics>;
  coverage: { configured: string[]; missing: string[]; partial: boolean; expected: string[] };
}

export interface BeforeAfterPair {
  prompt: string;
  engine: string;
  before: { goal_alignment?: number; answer_text?: string } & Record<string, unknown>;
  after: { goal_alignment?: number; answer_text?: string } & Record<string, unknown>;
  improvement?: number;
}

export interface SiteAudit {
  summary: Record<string, unknown>;
  created_at: string;
}

export interface GapModel {
  model: Record<string, unknown>;
  created_at: string;
}

export interface ShareOfVoice {
  run_id: number | null;
  by_classification: Record<string, { cites: number; share: number }>;
  top_domains: { domain: string; cite_count: number; share: number; classification: string }[];
}

export interface AttributionRow {
  metric: string;
  delta: number | null;
  assets_in_window: unknown;
  created_at: string;
}

export interface Incident {
  id: number;
  mention_url: string | null;
  sentiment: string | null;
  severity: string | null;
  severity_score: number | null;
  delay_impact: unknown;
  draft_response: string | null;
  sla_hours: number | null;
  status: string;
  created_at: string | null;
  resolved_at: string | null;
}

export interface Mention {
  id: number;
  source: string | null;
  source_url: string | null;
  author: string | null;
  title: string | null;
  body: string | null;
  matched_keyword: string | null;
  sentiment: string | null;
  relevance: number | null;
  status: string | null;
  discovered_at: string | null;
}

export interface LearnedLevers {
  baseline: { monthly_gain: number | null; confidence: string | null };
  levers: Record<string, number>;
}

export interface AdminUser {
  id: number;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  created_at?: string;
  last_login_at?: string | null;
  access: { business_id: number; access_role: string }[];
}

export interface ApiJob {
  id: number;
  job_type: string;
  status: string;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PipelineStep {
  step_key: string;
  status: string;
  error: string | null;
}

export interface PipelineRun {
  id: number;
  kind: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  steps: PipelineStep[];
}

export interface JobsResponse {
  jobs: ApiJob[];
  pipeline_runs: PipelineRun[];
}

export interface Competitor {
  id: number;
  name: string;
  domain: string | null;
  created_at?: string;
}
export interface Standing {
  name: string;
  is_subject: boolean;
  appears_in: number;
  appearance_rate: number;
}
export interface HeadToHead {
  competitor: string;
  subject_only_prompts: number;
  competitor_only_prompts: number;
}
export interface CompareResult {
  business?: string;
  run_id?: number | null;
  prompts_compared?: number;
  subject_rank?: number | null;
  field_size?: number;
  standings?: Standing[];
  head_to_head?: HeadToHead[];
  method?: string;
}

// ---- user-managed prompts / topics ----
export interface CustomPrompt {
  id: number;
  prompt: string;
  topic: string;
  tags: string;
  enabled: boolean;
  source: "user" | "ai_suggested";
  created_at?: string;
}

// ---- local SEO rank tracking (Google organic + map/local pack) ----
export interface LocalRankEntry {
  name: string;
  organic_rank: number | null;
  local_pack_rank: number | null;
  on_page_one: boolean;
  url: string;
  title: string;
  found: boolean;
}
export interface LocalRankQuery {
  query: string;
  location: string;
  subject: LocalRankEntry | null;
  competitors: LocalRankEntry[];
}
export interface LocalRankSummary {
  queries: number;
  page_one_rate: number;
  local_pack_rate: number;
  avg_organic_rank: number | null;
  ranked_queries: number;
  note: string;
}
export interface LocalRankings {
  business?: string;
  run_id: number | null;
  queries: LocalRankQuery[];
  summary: LocalRankSummary | null;
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  severity: string;
  read: boolean;
  created_at: string | null;
}
export interface NotificationsResponse {
  items: Notification[];
  unread: number;
}

export interface Schedule {
  id: number;
  job_type: string;
  interval_hours: number;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
}

export interface Keyword {
  id: number;
  keyword: string;
  negative: boolean;
  active: boolean;
  created_at?: string;
}

export interface Asset {
  id: number;
  asset_type: string | null;
  title: string | null;
  url: string | null;
  surface: string | null;
  published_at: string | null;
  work_order_id: number | null;
  body: string | null;
  target_query: string | null;
}

export interface ExternalSignal {
  id: number;
  source: string | null;
  signal_type: string | null;
  raw: Record<string, unknown>;
  normalized: Record<string, unknown> | null;
  status: string;
  created_at: string | null;
}

export interface Dashboard {
  business: Business & Record<string, unknown>;
  gap: Record<string, unknown>;
  plan: Record<string, unknown>;
  series: SeriesPoint[];
  before_after: unknown[];
  wo_counts: Record<string, number>;
  assets_n: number;
  month_cost?: number; // present for admins only
  attribution: { metric: string; delta: number; assets_in_window: unknown }[];
  challenge?: Challenge | null; // primary-challenge profile (awareness gap vs negatives)
}
