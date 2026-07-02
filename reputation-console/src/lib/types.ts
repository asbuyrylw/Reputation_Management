// Shared types mirroring the FastAPI responses (rep_engine.api).

export type Role = "admin" | "client";

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  business_ids: number[] | null; // null => admin (all businesses)
  org_id?: number | null;
  org_role?: string | null; // owner | admin | member
  is_super_admin?: boolean; // the single platform owner who can flip the billing switch
  billing_enabled?: boolean; // global billing master switch (off until the super-admin turns it on)
}

export interface LensRow {
  lens: string;
  score: number | null;
  contested_rate: number | null;
  n: number;
}
export interface AnswerLenses {
  divergence: {
    run_id: number | null;
    items: { prompt: string; spread: number; best_engine: string; best: number; worst_engine: string; worst: number; contested_engines: string[] }[];
  };
  lenses: { run_id: number | null; by_persona: LensRow[]; by_location: LensRow[] };
}

export interface ReportView {
  business: string | null;
  goal: string | null;
  score: number | null;
  biggest_gaps: string[];
  tasks_done_this_month: number;
  local_reputation: ReviewsSummary;
}

export interface MetricsTrend {
  series: { run_id: number; date: string | null; score: number | null; per_engine: Record<string, number | null> }[];
  engines: string[];
}

export interface GoogleReview {
  author: string | null;
  rating: number | null;
  body: string | null;
  sentiment: string | null;
  review_url: string | null;
  discovered_at: string | null;
}
export interface ReviewsSummary {
  current: { rating: number | null; review_count: number | null; place_name: string | null; captured_at: string | null } | null;
  rating_delta: number | null;
  new_reviews: number | null;
  history?: { date: string | null; rating: number | null; review_count: number | null }[];
  reviews: GoogleReview[];
}

export interface ActivitySummary {
  audits: number;
  drafts: number;
  published: number;
  tasks_done: number;
  mentions: number;
  outreach: number;
}

export interface TargetKeyword {
  keyword: string;
  kind: string | null;     // primary | secondary | long_tail | local | question
  source: string | null;   // llm_seed | serper_related | serper_paa | serper_autocomplete
  intent: string | null;
  priority: number | null;
  rationale: string | null;
}

// --- billing ---
export interface BillingPlan {
  code: string;
  name: string;
  price_usd_month: number;
  max_businesses: number | null;
  max_audits_per_month: number | null;
  max_engines: number | null;
  max_samples_per_prompt: number | null;
  seats: number | null;
  trial_days: number | null;
}

export interface SubscriptionSummary {
  subscription: {
    plan_code: string | null;
    status: string;
    trial_end?: string | null;
    current_period_end?: string | null;
  } | null;
  plan: BillingPlan | null;
  active: boolean;
  usage: { audits_this_month: number; businesses: number };
}

export interface Business {
  id: number;
  name: string;
  domain: string | null;
  geo: string | null; // "Areas served" in the UI
  goal: string | null;
  contested_terms: string | null;
  services?: string | null; // comma-joined service keywords (edited as tags)
  industry?: string | null;
  regulatory_profile?: RegulatoryProfile | null;
  owned_domains?: string[] | null; // extra web properties the business owns (cited -> classified "owned")
  created_at?: string;
  can_edit?: boolean; // may the current user take actions on this business?
}

export interface RegulatoryProfile {
  firm_type?: string; // ria | broker_dealer | insurance | non_financial | other
  disclosures?: string[];
  crd?: string;
  notes?: string;
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
  rationale?: { gap_source?: string; why?: string; source?: string } | null;
  gap_source?: string | null;
  gap_specifics?: { source_query?: string } | null; // ties a task to the worst AI query/topic it fixes
  why_helps_ai_rep?: string | null;
  why_helps_seo?: string | null;
  added_in_revision?: number | null;
  start_date?: string | null;
  predicted_ai_points?: number | null;
  predicted_seo_impact?: string | null;
  predicted_basis?: string | null;
  superseded?: boolean | null;
  planned?: boolean | null;
  promoted_at?: string | null;
  progress_notes?: ProgressNote[] | null;
  assignee_user_id?: number | null;
  area?: string | null; // website | blog | outreach | social | local | reviews | tracking | content | other
  platform?: string | null; // linkedin | facebook | instagram | x | youtube | tiktok | pinterest | reddit | gbp
}

export interface TeamMember {
  id: number;
  name: string;
  email: string;
}

// =====================================================================================
// Roadmap — the impact-ranked open tasks that power the unified to-do hub's "Today's
// focus" + "By priority" view. The server returns items already sorted best-first by
// impact_score (= expected_points / effort), so the UI can render them in order.
// =====================================================================================
export interface RoadmapItem {
  wo_id: number;
  wo_code: string | null;
  title: string;
  capability: string | null;
  area: string | null;
  platform: string | null;
  status: string;
  expected_points: number; // predicted AI-score points this task earns
  effort: number; // relative effort (1 = quick win)
  impact_score: number; // expected_points / effort — the ranking key
  basis: string; // "this client" | "cross-client" | "industry baseline"
  confidence: string;
  why: string | null;
  seo_impact: string | null;
}
export interface Roadmap {
  count: number;
  items: RoadmapItem[];
}

// One logged completed action (from a work order marked done/verified or a brief marked
// produced). Powers the "Work completed" readout — what was actually done, and when.
export interface ActionTaken {
  id: number;
  source: string; // 'work_order' | 'production_brief' (kept loose — server may add sources)
  capability: string | null;
  area: string | null;
  platform: string | null;
  title: string | null;
  completed_on: string | null; // YYYY-MM-DD
  logged_at: string | null;
  logged_by: string | null;
  work_order_id: number | null;
  production_brief_id: number | null;
  notes: string | null;
}

// "What moved the needle" — correlation across audit windows between logged actions of a
// given capability and the score change in that window. NOT causal proof; a directional read.
export interface TaskImpactType {
  capability: string;
  actions: number;
  windows: number;
  gain_per_action: number;
  total_gain: number;
  confidence: string; // e.g. 'low' | 'medium' | 'high'
}
export interface TaskImpact {
  windows: number; // total audit windows analyzed
  unattributed_windows: number; // windows that moved with no logged actions
  task_types: TaskImpactType[]; // already sorted best-first by the server
}

export interface ComplianceSignoff {
  id: number;
  draft_id: number | null;
  asset_id: number | null;
  approver: string | null;
  compliance_pass: boolean | null;
  compliance_flags: unknown;
  override_reason: string | null;
  body_hash: string | null;
  signed_at: string | null;
  title: string | null;
}

export interface AssetPlacement {
  id: number;
  channel: string;
  status: string; // planned | published | skipped
  url: string | null;
  published_at: string | null;
}

export interface ProgressNote {
  text: string;
  author?: string | null;
  at?: string | null;
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
  highlighted_sections?: { type?: string; note?: string }[] | null;
  placeholders_pending?: string[] | null;
  wo_instruction?: string | null;
  quality_notes?:
    | ({
        keyword_coverage?: KeywordCoverage;
        on_page?: DraftOnPage;
        citation_ready?: DraftCitationReady;
        fact_check?: DraftFactCheck;
        neuron?: DraftNeuron;
        structure?: DraftStructure;
        keyword_density?: DraftKeywordDensity;
        readability?: DraftReadability;
        aeo?: DraftAeo;
        term_coverage?: DraftTermCoverage;
        intent_serp?: DraftIntentSerp;
      } & Record<string, unknown>)
    | null;
}

// NeuronWriter SERP content-optimization score for a draft — how well its term coverage
// matches what's already ranking for `query`. `target` is the recommended score to beat
// (null when NeuronWriter didn't supply one).
export interface DraftNeuron {
  content_score: number; // 0..100
  query: string;
  target: number | null;
}

// Whether the NeuronWriter content-optimization provider is wired up for a business.
// `configured` = a key is set; `live` = currently reachable. The SERP-score gauge is dormant
// (renders nothing) when not configured.
export interface ContentOptimizationStatus {
  configured: boolean;
  live: boolean;
  provider: string; // "neuronwriter"
}

export interface KeywordCoverage {
  covered?: string[];
  missing?: string[];
  important_missing?: string[];
  rate?: number | null;
}

export interface AmplificationPlaybook {
  primary?: string;
  post_to?: string[];
  cross_share?: string[];
  sequence?: string;
  why_helps_ai_rep?: string;
  why_helps_seo?: string;
}
export interface ProductionBrief {
  id: number;
  channel: string;
  platform: string | null;
  title: string | null;
  target_query: string | null;
  brief: Record<string, unknown>;
  status: string;
  amplification_playbook?: AmplificationPlaybook | null;
  why_helps_ai_rep?: string | null;
  why_helps_seo?: string | null;
}

// Per-platform social-presence audit. `source` says how the profile was found:
// "website"=confirmed-owned (linked from the site), "serper"=Google Business Profile,
// "search"=inferred from a web search, "none"=not found. `completeness` is 0..1.
export interface SocialAudit {
  platform: string;
  exists: boolean;
  profile_url: string | null;
  source: string | null; // "website" | "search" | "serper" | "none"
  confidence: string | null;
  completeness: number | null; // 0..1
  audit: {
    findings?: string[];
    recommendations?: string[];
    signals?: Record<string, unknown>;
  } | null;
  last_checked_at: string | null;
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
  target_type?: string | null;
  capabilities?: string[] | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  contact_verified?: boolean | null;
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
  failed_count: number;
  failed_engines: number;
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
  by_source_type: Record<string, { cites: number; share: number }>;
  top_domains: { domain: string; cite_count: number; share: number; classification: string; source_type: string }[];
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
  predicted_levers?: Record<string, number>;
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
  result: Record<string, unknown> | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CostItem {
  provider: string;
  operation: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}
export interface CostBreakdown {
  run_id: number | null;
  items: CostItem[];
  run_total: number;
  month_total: number;
  estimated: boolean;
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
  // the actual questions behind each bucket (added by compare(); optional for back-compat)
  prompts_subject_only?: string[];
  prompts_competitor_only?: string[];
  prompts_both?: string[];
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

// ---- deliverable reports ----
export interface Report {
  id: number;
  filename: string;
  kind: string;
  created_at: string;
  has_pdf?: boolean;
}

// ---- getting-started onboarding ----
export interface OnboardingStep {
  key: string;
  label: string;
  href: string;
  done: boolean;
}
export interface OnboardingStatus {
  steps: OnboardingStep[];
  done: number;
  total: number;
  complete: boolean;
}

// ---- visibility over time (subject vs competitors across benchmark runs) ----
export interface TrendPoint {
  run_id: number;
  date: string;
  subject_rate: number;
  competitors: Record<string, number>;
}
export interface VisibilityTrend {
  business: string | null;
  competitors: string[];
  points: TrendPoint[];
}

// ---- per-prompt visibility (how each tracked question performs in the latest audit) ----
export interface PromptEngineResult {
  n: number;
  visibility: number | null;
  goal_alignment: number | null;
  sentiment: string;
}
export interface PromptResult {
  prompt: string;
  persona: string;
  location: string;
  n: number;
  visibility: number | null;
  goal_alignment: { mean: number; low: number | null; high: number | null; n: number } | null;
  sentiment: { positive: number; neutral: number; negative: number; mixed: number };
  owned_rate: { p: number; low: number; high: number; n: number } | null;
  contested_rate: { p: number; low: number; high: number; n: number } | null;
  engines: Record<string, PromptEngineResult>;
}
export interface PromptResults {
  run_id: number | null;
  prompts: PromptResult[];
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

export interface ProjWindow {
  months: number;
  weeks: number;
  target_date: string;
}
export interface LocalSeoGoal {
  business?: string;
  current_page_one_rate: number | null;
  target_page_one_rate: number;
  remaining_gap?: number;
  avg_organic_rank?: number | null;
  monthly_gain_estimate?: number;
  gain_basis?: string; // plain-English basis for the estimate (grounded cold-start / measured velocity)
  confidence?: string;
  no_data?: boolean;
  note?: string;
  status?: string;
  target_searches?: string[];
  projection?: { optimistic: ProjWindow; expected: ProjWindow; conservative: ProjWindow };
  disclaimer?: string;
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  severity: string;
  read: boolean;
  created_at: string | null;
  user_id?: number | null; // scoped to the current user server-side (e.g. task-assignment alerts)
}
export interface NotificationsResponse {
  items: Notification[];
  unread: number;
}

// =====================================================================================
// Narrative crowding-out score — the headline metric. How much the DESIRED narrative
// dominates AI answers vs the CONTESTED one (0-100). `latest`/`series` are the trend
// shape; `latest_detail` adds the neutral split + a per-engine breakdown.
// =====================================================================================
export interface NarrativePoint {
  run_id: number;
  date: string;
  score: number; // 0-100 narrative dominance
  desired_pct: number; // share of answers carrying the desired narrative
  contested_pct: number; // share carrying the contested narrative
}
export interface NarrativeEngineDetail {
  score: number;
  desired: number;
  contested: number;
  neutral: number;
}
export interface NarrativeDetail {
  score: number;
  desired_pct: number;
  contested_pct: number;
  neutral_pct: number;
  by_engine: Record<string, NarrativeEngineDetail>;
}
export interface NarrativeScore {
  latest: NarrativePoint | null;
  delta: number | null; // change vs the prior audit (in score points)
  series: NarrativePoint[];
  latest_detail: NarrativeDetail | null;
}

// =====================================================================================
// Proof of impact + ROI forecast — the "did the work pay off?" surfaces. The impact
// report compares before/after across the most recent action window (ready=false when
// there isn't enough history yet). The ROI forecast predicts the AI-score points still
// on the table if the remaining plan is finished.
// =====================================================================================
export interface ImpactMetricDelta {
  before: number | null;
  after: number | null;
  delta: number | null;
}
export interface ImpactReport {
  ready: boolean;
  reason?: string; // why it's not ready yet (shown when ready=false)
  window?: { from_date: string; to_date: string };
  actions?: { total: number; by_area: Record<string, number> };
  metrics?: {
    narrative_score: ImpactMetricDelta;
    owned_citation_share_pct: ImpactMetricDelta;
    contested_pct: ImpactMetricDelta;
    avg_goal_alignment: ImpactMetricDelta;
  };
  summary?: string;
}

export interface RoiCapabilityRow {
  capability: string;
  open_tasks: number;
  gain_per_task: number;
  predicted_points: number;
  basis: string;
  confidence: string;
}
export interface RoiForecast {
  predicted_points: number; // total AI-score points if the whole plan is finished
  open_tasks: number;
  by_capability: RoiCapabilityRow[];
  confidence: string;
  horizon_weeks: number | null;
  note: string;
}

// =====================================================================================
// AI-crawler readiness — llms.txt content + schema.org coverage verification. The
// llms.txt block is copy/downloadable; schema-verify lists deployed vs recommended-missing.
// =====================================================================================
export interface LlmsTxt {
  content: string;
  page_count: number;
  note: string;
}
export interface SchemaVerify {
  checked_pages: number;
  deployed_schema: string[];
  recommended_missing: string[];
  // per-page schema detail; the server shape may vary, so keep it loose (only the
  // aggregate deployed/recommended_missing chips + verdict are rendered).
  per_page: Record<string, unknown>[];
  verdict: string;
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
  published_url?: string | null;
  published_status?: string | null; // 'pending' | 'live'
  summary?: string | null;
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
  narrative?: NarrativeScore | null; // headline narrative crowding-out score + trend
}

// =====================================================================================
// Integrations & Publishing — connections vault, publishing, review replies, the unified
// approval queue, and per-business integration/automation settings.
// =====================================================================================

// A stored credential/connection to an external surface we can publish to (or reply on).
// `kind` is the provider; `status` is the live health of the credential.
export type ConnectionKind = "wordpress_org" | "google_business_profile" | "ayrshare_profile" | "google_search_console" | "google_analytics" | "zernia";
export type ConnectionStatus = "pending" | "active" | "error" | "revoked" | "expired" | "needs_reconnect";

// =====================================================================================
// Zernio (Zernia) social publishing — connect the client's social accounts so approved
// posts can be published. The owner (1) sets up a profile container, (2) authorizes each
// platform in a Zernio OAuth popup, (3) syncs to pull the connected accounts back. Auth is
// a server-side account key, so there's nothing for the owner to paste.
// =====================================================================================

// Result of setting up (or reusing) the Zernio profile. `accounts` maps platform -> account
// id for already-connected platforms; `platforms` is the list of connectable platform slugs.
export interface ZerniaSetup {
  ok: boolean;
  profile_id: string;
  accounts: Record<string, string>;
  platforms: string[];
}

// The OAuth URL to open (in a new tab) so the owner can authorize one platform on Zernio.
export interface ZerniaConnectUrl {
  authUrl: string;
  platform: string;
}

// One social account pulled back by a sync (after the owner authorizes it in the popup).
export interface ZerniaAccount {
  account_id: string;
  platform: string;
  username: string | null;
  display_name: string | null;
  is_active: boolean;
}

// Result of a sync — the confirmed connected accounts + the list of connected platform slugs.
export interface ZerniaSyncResult {
  ok: boolean;
  accounts: ZerniaAccount[];
  connected_platforms: string[];
}

export interface Connection {
  id: number;
  business_id: number;
  kind: string; // ConnectionKind, but the API may return others — keep it loose like other types
  label: string | null;
  status: string; // ConnectionStatus
  token_type: string | null;
  expires_at: string | null;
  account_ref: string | null;
  profile_ref: string | null;
  gbp_access: string | null; // GBP review-reply approval state ('approved' once Google grants it)
  meta: Record<string, unknown>;
  last_error: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  has_token: boolean;
}

export interface ConnectionsResponse {
  vault_ready: boolean; // false when TOKEN_ENC_KEY isn't configured on the server
  connections: Connection[];
}

// A channel we can publish an asset to. `connected` is false when no live connection backs it.
export interface PublishChannel {
  channel: string;
  label: string;
  kind: string | null;
  connected: boolean;
}

// One publish attempt of an asset to a channel/network, with its live external URL + status.
export interface PublishTarget {
  id: number;
  channel: string;
  network: string;
  status: string; // pending | scheduled | published | failed | skipped
  external_url: string | null;
  external_id: string | null;
  scheduled_for: string | null;
  published_at: string | null;
  attempts: number;
  last_error: string | null;
  updated_at: string;
}

// A drafted reply to a Google/third-party review (compliance-screened, human-approved).
export interface ReviewReply {
  id: number;
  review_id: number;
  draft: string | null;
  compliance_pass: boolean | null;
  compliance_flags: string[];
  status: string; // pending | approved | rejected | posted
  reviewer: string | null;
  reviewed_at: string | null;
  posted_at: string | null;
  external_url: string | null;
  created_at: string;
  // denormalized review context (so the card can render the review it answers)
  author: string | null;
  rating: number | null;
  review_title: string | null;
  review_body: string | null;
  sentiment: string | null;
  review_url: string | null;
}

// The unified approval inbox: mention replies, review replies, and scheduled posts in one feed.
export type QueueItemKind = "mention_reply" | "review_reply" | "scheduled_post";

export interface QueueItem {
  kind: QueueItemKind;
  id: number;
  draft: string | null;
  compliance: { pass: boolean | null; flags: string[] };
  surface: "owned" | "third_party";
  capability: "publish" | "publish_costed" | "review_reply" | "alert_only";
  source: string | null;
  url?: string | null;
  title: string | null;
  sentiment: string | null;
  rating?: number | null;
  status?: string;
  scheduled_for?: string | null;
  can_auto_post: boolean;
  editable: boolean;
}

export interface ApprovalQueueResponse {
  items: QueueItem[];
}

// Per-business automation/integration settings. Auto-post fields are org-manager-gated server-side.
export interface IntegrationSettings {
  business_timezone: string;
  require_approval: boolean;
  allow_owned_autopost: boolean;
  auto_reply_reviews: boolean;
  auto_reply_mentions: boolean;
  auto_reply_min_stars: number;
  auto_reply_max_len: number;
  auto_platforms: string[];
  never_auto_sentiments: string[];
  daily_autopost_cap: number;
  hourly_auto_cap: number;
  warmup_manual_count: number;
  quiet_hours: Record<string, number>;
  banned_phrases: string[];
  allowed_channels: string[];
  blocked_channels: string[];
  disclosure_text: string | null;
  notify_email: boolean;
  notify_on_auto: boolean;
}

export interface IntegrationSettingsResponse {
  settings: IntegrationSettings;
  can_manage_autopost: boolean; // is the current user an org manager (may change auto-post fields)?
  autopost_globally_enabled: boolean; // platform-wide kill-switch state (read-only)
}

// =====================================================================================
// Review-request kit — the copy-paste assets that ask happy customers for a Google
// review, plus the NAP block we keep consistent across directory citations.
// =====================================================================================

// Name/Address/Phone (+ web/areas) the way it should appear in every directory listing.
// `missing_fields` flags anything blank so the owner fills it in (citation consistency).
export interface Nap {
  name: string | null;
  address: string | null;
  phone: string | null;
  website: string | null;
  areas_served: string | null;
  missing_fields: string[];
  consistency_note: string;
}

export interface ReviewRequestKit {
  link: {
    write_review_url: string;
    listing_url: string;
    source: string;
    place_name: string;
  };
  templates: {
    sms: string;
    email_subject: string;
    email_body: string;
    link: string;
  };
  nap: Nap;
}

// =====================================================================================
// Visual content (CI-4) — generated images / quote cards / video briefs for a work order.
// Files live server-side; the console shows kind + status and gates approval by canEdit.
// =====================================================================================

export interface VisualAsset {
  id: number;
  work_order_id: number | null;
  draft_id: number | null;
  kind: string; // image | quote_card | video_brief
  provider: string | null;
  model: string | null;
  prompt: string | null;
  file_path: string | null;
  url: string | null;
  width: number | null;
  height: number | null;
  status: string; // pending | approved | rejected
  compliance_note: string | null;
  reviewer: string | null;
  reviewed_at: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface VisualsResponse {
  image_configured: boolean; // is an AI-image provider key set in .env?
  video_configured: boolean; // is a video provider key set (else briefs are shootable only)?
  visuals: VisualAsset[];
}

// =====================================================================================
// Google Search Console — real Google "Search traffic": clicks, impressions, CTR, average
// position. The honest, measured counterpart to the AI-visibility story. Nullable metrics
// stay `T | null` (Search Console reports null position/CTR for rows with no rank data).
// =====================================================================================

// Top-line search-traffic summary for the current 28-day window vs the prior 28 days.
// When `has_data` is false the API returns ONLY { has_data:false, collecting } — every
// numeric field below is absent, so guard on has_data before reading them.
export interface GscSummary {
  has_data: boolean;
  collecting: boolean; // connected + property set, but no rows imported yet (history is backfilling)
  as_of?: string;
  clicks?: number;
  impressions?: number;
  ctr?: number | null;
  position?: number | null;
  clicks_delta?: number; // % change vs the prior 28 days
  impressions_delta?: number; // % change vs the prior 28 days
  clicks_prev?: number;
}

// One day on the clicks/impressions trend.
export interface GscTrendPoint {
  date: string;
  clicks: number;
  impressions: number;
  ctr: number | null;
  position: number | null;
}

// A search query (the words people typed) with its performance.
export interface GscQuery {
  query: string;
  clicks: number;
  impressions: number;
  ctr: number | null;
  position: number | null;
}

// A landing page with its performance + whether it's content we published.
export interface GscPage {
  page: string;
  clicks: number;
  impressions: number;
  ctr: number | null;
  position: number | null;
  is_our_content: boolean;
  asset_id: number | null;
}

// A "striking-distance" query — lots of impressions but a position that's just off page one,
// so a small content push could win the click. Deep-links to brief generation.
export interface GscOpportunity {
  query: string;
  impressions: number;
  clicks: number;
  position: number | null;
  ctr: number | null;
}

// Equivalent-ad-value framing: total clicks vs the smaller subset earned by content we
// published, with a labeled paid-search-equivalent estimate.
export interface GscRoi {
  has_data: boolean;
  collecting: boolean;
  baseline_clicks: number;
  latest_clicks: number;
  our_content_clicks: number; // the smaller, distinct subset earned by content we published
  our_content_pages: number;
  equivalent_ads_value: number; // a LABELED estimate, not a billed amount
  window_days: number;
}

// A verified property the connected Google account can read (per-connection picker).
export interface GscSite {
  property: string; // e.g. "https://example.com/" or "sc-domain:example.com"
  permission: string;
}

// Guided verification (onboarding assist) for a site not yet verified in Search Console.
// start() returns the token to place; complete() verifies ownership + registers the property.
export interface GscVerifyStart {
  ok: boolean;
  method: string; // "META" (a URL) | "DNS_TXT" (a whole domain)
  identifier: string; // the URL or domain being verified
  property: string; // the resulting GSC property string
  token: string; // the exact <meta> tag or DNS TXT value to place
  instructions: string;
}

export interface GscVerifyComplete {
  ok: boolean;
  verified: boolean;
  property?: string;
  added?: boolean; // false when ownership verified but sites.add failed (reconnect needed)
  add_error?: string | null;
  ingest_started?: boolean;
  error?: string;
}

// =====================================================================================
// Google Analytics (GA4) — what visitors DO after they arrive: sessions, users, pageviews,
// conversions, engagement. The behavior-side counterpart to Search Console's traffic story.
// Conversions are only meaningful if the client has configured GA4 conversion events, so the
// UI notes that subtly. When `has_data` is false the API returns ONLY { has_data, collecting }.
// =====================================================================================

// Top-line behavior summary for the current window vs the prior period.
export interface GaSummary {
  has_data: boolean;
  collecting: boolean; // connected + property set, but no rows imported yet
  as_of?: string;
  sessions: number;
  users: number;
  pageviews: number;
  conversions: number;
  engagement_rate: number | null; // 0..1; null if GA4 doesn't report it
  sessions_delta: number; // % change vs the prior period
  conversions_delta: number; // % change vs the prior period
}

// One day on the GA sessions/users/pageviews/conversions trend.
export interface GaTrendPoint {
  date: string;
  sessions: number;
  users: number;
  pageviews: number;
  conversions: number;
}

// A landing page with its GA performance + whether it's content we published.
export interface GaPage {
  page: string;
  sessions: number;
  conversions: number;
  is_our_content: boolean;
  asset_id: number | null;
}

// Acquisition channel (Organic Search, Direct, Referral, Social, …) with its session/conversion split.
export interface GaChannel {
  channel: string;
  sessions: number;
  conversions: number;
}

// A GA4 property the connected Google account can read (per-connection picker).
export interface GaProperty {
  property: string; // e.g. "properties/123456789"
  display_name: string;
  account: string;
}

// =====================================================================================
// "Is our content working?" — the causal-proof panel. Each row is a page WE published
// (a labeled subset of the whole site) with the real search clicks + GA sessions it earns,
// so the value of the content we produce is provable rather than asserted.
// =====================================================================================

export interface OurContentAsset {
  asset_id: number;
  title: string | null;
  published_url: string;
  published_at: string | null;
  gsc_clicks: number;
  ga_sessions: number;
  has_traffic: boolean;
}

export interface OurContentImpact {
  assets: OurContentAsset[];
  owned_citation_share: number; // 0..1 — share of citations pointing at content we own/published
  totals: {
    assets_published: number;
    assets_with_traffic: number;
    our_content_clicks: number;
    our_content_sessions: number;
  };
}

// =====================================================================================
// Wave 2 — draft-quality scorecards (carried on ContentDraft.quality_notes), topical
// authority, internal linking, and keyword-intent coverage.
// =====================================================================================

// On-page SEO self-check for a draft (word count, headings, images/alt, links, schema).
export interface DraftOnPage {
  score: number; // 0..100
  word_count: number;
  h1: number;
  h2: number;
  images: number;
  images_with_alt: number;
  links: number;
  avg_sentence_len: number;
  suggested_schema: string;
  issues: { label: string; fix: string }[];
}

// "Will an AI quote this?" readiness — FAQ-shaped headings + tips to make it citable.
export interface DraftCitationReady {
  score: number; // 0..100
  faq_headings: number;
  tips: { label: string; fix: string }[];
}

// Best-effort fact-check of the claims in a draft. `status` is the verification verdict;
// unverified claims may still be true — they just need a human to confirm.
export interface DraftFactCheck {
  claims: { claim: string; status: string; note: string }[];
  unverified: number;
}

// Phase-1 draft grades (from content_quality.analyze_draft) — a NeuronWriter-style scorecard.
export interface DraftStructure {
  score: number; // 0..100 heading hierarchy + layout for AI extraction
  hierarchy_valid: boolean;
  structure_map: { level: number; text: string }[];
  issues: { label: string; fix: string }[];
}
export interface DraftKeywordDensity {
  keyword_densities: { keyword: string; count: number; density_pct: number; band: "missing" | "low" | "ok" | "high" }[];
  issues: { label: string; fix: string }[];
}
export interface DraftReadability {
  grade: number | null; // Flesch-Kincaid grade level
  avg_sentence_len: number;
  passive_hits: number;
  target?: string;
  issues: { label: string; fix: string }[];
}
export interface DraftAeo {
  score: number; // 0..100 across pillars
  suggested_schema: string;
  pillars: { name: string; score: number; max: number; ok: boolean }[];
  tips: { label: string; fix: string }[];
}
export interface DraftTermCoverage {
  terms_total: number;
  terms_covered: string[];
  terms_missing: string[];
  covered_pct: number | null;
}
export interface DraftIntentSerp {
  intent: string;
  recommended_shape: string;
}

// Topic-authority clusters — pillar + spoke keywords grouped into the topics to own.
export interface TopicalCluster {
  topic: string;
  pillar: string;
  spokes: string[];
  keyword_count: number;
  total_search_volume: number | null;
  owned_pieces: number;
  needs_content: boolean;
  priority: number;
}
export interface TopicalAuthority {
  clusters: TopicalCluster[];
  summary: { keywords: number; topics: number; uncovered: number };
  next_to_write: { topic: string; covers_keywords: number; spokes: string[]; why: string }[];
}

// Internal-linking opportunities — under-linked owned pages + concrete link suggestions.
export interface InternalLinks {
  under_linked: { url: string; title: string; internal_links: number }[];
  suggestions: { from: string; to: string; anchor: string; why: string }[];
  summary: { pages: number; owned_pieces: number; under_linked: number; suggestions: number };
}

// Keyword coverage grouped by search intent (informational / commercial / …).
export interface KeywordIntent {
  by_intent: { intent: string; keywords: number; examples: string[]; owned_pieces: number; needs_content: boolean }[];
  summary: { intents: number; uncovered: number };
}

// =====================================================================================
// Wave 3 — directory citations, indexing status, sources-to-win, backlink profile.
// =====================================================================================

// Curated directory/citation submission list, with the NAP block to keep consistent.
export interface DirectoryCitations {
  nap: Nap;
  directories: { key: string; name: string; submit_url: string; authority: string; category: string; financial: boolean }[];
  note: string;
  summary: { total: number; essential: number };
}

// Which of our owned pages Google has indexed vs. needs a manual "request indexing" in GSC.
// When GSC isn't connected the API returns the `skipped` shape instead.
export interface IndexingStatus {
  indexed?: { url: string; title: string | null; coverage: string | null }[];
  not_indexed?: { url: string; title: string | null; coverage: string | null }[];
  summary?: { checked: number; indexed: number; needs_request: number };
  skipped?: true;
  reason?: string;
  urls?: number;
}

// Non-owned domains AI cites about us, ranked, with the suggested action per source.
export interface SourcesToWin {
  run_id: number | null;
  sources: { domain: string; cite_count: number; share: number; classification: string; action: string; capability: string }[];
  summary: { total: number; contested: number };
}

// Backlink profile snapshot (present only when a backlink data source is configured).
export interface BacklinkProfile {
  has_data: boolean;
  source?: string;
  as_of?: string;
  profile?: Record<string, unknown>;
  lost_domains?: string[];
}

// =====================================================================================
// Wave 4 — answer changes (what moved between audits) + review-reply SLA / requests.
// =====================================================================================

// What materially changed in AI answers between the last two audits, per prompt/engine.
export interface AnswerChanges {
  changes: {
    engine: string;
    prompt: string;
    reasons: string[];
    before: { goal_alignment: number | null; sentiment: string | null };
    after: { goal_alignment: number | null; sentiment: string | null };
  }[];
  summary: { compared: boolean; changed: number };
}

// Negative reviews still awaiting a reply, with how long they've waited vs. the SLA.
export interface ReviewSla {
  sla_hours: number;
  pending: { review_id: number; rating: number | null; hours_waiting: number; sla_breached: boolean; snippet: string }[];
  summary: { awaiting: number; sla_breached: number };
}

// Result of POSTing review requests. When email isn't configured the API returns the
// keyless `skipped` shape with a preview of what WOULD have been sent.
export type ReviewRequestSendResult =
  | { sent: number; failed?: number }
  | { sent: 0; skipped: true; reason: string; preview: { subject: string; body: string } };

// =====================================================================================
// Wave 5 — shareable public summary + platform quota usage (super-admin).
// =====================================================================================

// The data behind a public lead-magnet page — score, band, top gaps, teaser line.
export interface PublicSummary {
  found: boolean;
  business: string;
  area: string | null;
  score: number | null;
  band: string;
  top_gaps: string[];
  teaser: string;
  has_audit: boolean;
}

// One provider's quota line — `unlimited` when uncapped (then used/cap may be null).
export interface QuotaLine {
  within: boolean;
  used: number | null;
  cap: number | null;
  unlimited: boolean;
}
// Platform-wide publishing/quota usage across the shared provider accounts (super-admin).
export interface QuotaUsage {
  ayrshare: QuotaLine;
  x: QuotaLine;
  gbp: QuotaLine;
}

// =====================================================================================
// White-label & sharing — agency branding, shareable lead-magnet links, captured leads.
// =====================================================================================

// The agency/business branding applied to the public lead-magnet page. `accent` is a hex
// color (e.g. "#4f46e5"); `logo_url` and `accent` may be null until the owner sets them.
export interface Branding {
  brand_name: string;
  logo_url: string | null;
  accent: string | null;
}

// A freshly minted public share link for the lead-magnet page (token + the full URL).
export interface ShareLink {
  token: string;
  url: string;
}

// One email captured from the public lead-magnet page.
export interface Lead {
  id: number;
  email: string;
  name: string | null;
  source: string | null;
  captured_at: string;
}

export interface LeadsResponse {
  leads: Lead[];
}

// The PUBLIC (unauthenticated) lead-magnet payload behind a share token. Mirrors the
// authed PublicSummary but adds branding + a `found` flag (404 when the token is invalid).
// The public page fetches this with a raw `fetch("/api/public/audit/{token}")` — no auth.
export interface PublicAudit {
  found: boolean;
  business: string;
  area: string | null;
  score: number | null;
  band: string;
  top_gaps: string[];
  teaser: string;
  has_audit: boolean;
  branding: Branding;
}

// A physical location for a multi-location business (admin-managed). Each row is one
// storefront/office with its own NAP details; one row can be flagged the primary.
export interface Location {
  id: number;
  label: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  postal: string | null;
  phone: string | null;
  is_primary: boolean;
  created_at: string;
}
