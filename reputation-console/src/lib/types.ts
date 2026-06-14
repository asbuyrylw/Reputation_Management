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
  persona: string | null;
  location: string | null;
  failed: boolean | null;
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
}
