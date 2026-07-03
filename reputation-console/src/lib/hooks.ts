"use client";

// TanStack Query hooks. Every per-business key includes businessId so the cache is
// isolated per tenant.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";
import { useAuth } from "./auth";
import type {
  AdminUser,
  Asset,
  AuditRun,
  Answer,
  BillingPlan,
  SubscriptionSummary,
  CostBreakdown,
  AttributionRow,
  BeforeAfterPair,
  CompareResult,
  CustomPrompt,
  LocalRankings,
  LocalSeoGoal,
  OnboardingStatus,
  PromptResults,
  Report,
  VisibilityTrend,
  Competitor,
  ContentDraft,
  ContentOptimizationStatus,
  Dashboard,
  DiscoveryTarget,
  ExternalSignal,
  Keyword,
  NotificationsResponse,
  Schedule,
  GapModel,
  Incident,
  JobsResponse,
  LearnedLevers,
  Mention,
  PerEngineMetrics,
  ProductionBrief,
  ShareOfVoice,
  SiteAudit,
  TargetKeyword,
  ActivitySummary,
  ReviewsSummary,
  MetricsTrend,
  AnswerLenses,
  ReportView,
  TeamMember,
  AssetPlacement,
  ComplianceSignoff,
  ActionTaken,
  TaskImpact,
  WorkOrder,
  Roadmap,
  SocialAudit,
  ConnectionsResponse,
  ZerniaSetup,
  ZerniaConnectUrl,
  ZerniaSyncResult,
  PublishChannel,
  PublishTarget,
  ReviewReply,
  ApprovalQueueResponse,
  QueueItemKind,
  IntegrationSettings,
  IntegrationSettingsResponse,
  ReviewRequestKit,
  VisualsResponse,
  GscSummary,
  GscTrendPoint,
  GscQuery,
  GscPage,
  GscOpportunity,
  GscRoi,
  GscSite,
  GscVerifyStart,
  GscVerifyComplete,
  GaSummary,
  GaTrendPoint,
  GaPage,
  GaChannel,
  GaProperty,
  OurContentImpact,
  FreshnessQueue,
  TopicalAuthority,
  InternalLinks,
  KeywordIntent,
  DirectoryCitations,
  IndexingStatus,
  SourcesToWin,
  BacklinkProfile,
  AnswerChanges,
  ReviewSla,
  ReviewRequestSendResult,
  PublicSummary,
  QuotaUsage,
  Branding,
  ShareLink,
  LeadsResponse,
  NarrativeScore,
  ImpactReport,
  RoiForecast,
  LlmsTxt,
  SchemaVerify,
  Location,
} from "./types";

type Json = Record<string, unknown>;

function useApiQuery<T>(key: unknown[], path: string | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: key,
    queryFn: () => apiFetch<T>(path as string),
    enabled: !!user && !!path,
  });
}

export function useDashboard(businessId: number | null) {
  return useApiQuery<Dashboard>(["dashboard", businessId], businessId ? `/businesses/${businessId}/dashboard` : null);
}

// Admin-only estimated COGS for the latest audit (per engine/operation) + month total.
// Only mount the consuming component for admins, so non-admins never hit the 403.
export function useCostBreakdown(businessId: number | null) {
  return useApiQuery<CostBreakdown>(["cost-breakdown", businessId], businessId ? `/businesses/${businessId}/cost-breakdown` : null);
}

export function useAuditRuns(businessId: number | null) {
  return useApiQuery<AuditRun[]>(["audit-runs", businessId], businessId ? `/businesses/${businessId}/audit-runs` : null);
}

export function useRunAnswers(businessId: number | null, runId: number | null) {
  return useApiQuery<Answer[]>(
    ["run-answers", businessId, runId],
    businessId && runId ? `/businesses/${businessId}/audit-runs/${runId}/answers` : null,
  );
}

export function usePerEngine(businessId: number | null, runId: number | null) {
  return useApiQuery<PerEngineMetrics>(
    ["per-engine", businessId, runId],
    businessId && runId ? `/businesses/${businessId}/audit-runs/${runId}/per-engine` : null,
  );
}

export function useBeforeAfter(businessId: number | null) {
  return useApiQuery<BeforeAfterPair[]>(
    ["before-after", businessId],
    businessId ? `/businesses/${businessId}/answers/before-after` : null,
  );
}

export function useSiteAudit(businessId: number | null) {
  return useApiQuery<SiteAudit | null>(["site-audit", businessId], businessId ? `/businesses/${businessId}/site-audit` : null);
}

export function useGapModel(businessId: number | null) {
  return useApiQuery<GapModel | null>(["gap-model", businessId], businessId ? `/businesses/${businessId}/gap-model` : null);
}

export function useSocialPresence(businessId: number | null) {
  return useApiQuery<Record<string, { exists: boolean | null; profile_url: string | null; confidence: string | null }>>(
    ["social-presence", businessId],
    businessId ? `/businesses/${businessId}/social-presence` : null,
  );
}

// Per-platform social-presence audit (does each profile exist, how complete, what to do next).
export function useSocialAudit(businessId: number | null) {
  return useApiQuery<SocialAudit[]>(["social-audit", businessId], businessId ? `/businesses/${businessId}/social-audit` : null);
}

// Re-run the social audit (job_type "audit_socials"). The server cascades a gaps + plan refresh,
// so on success we invalidate the social audit AND the work-orders/gaps/dashboard caches.
export function useAuditSocials(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/businesses/${businessId}/jobs/audit_socials`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["social-audit", businessId] });
      qc.invalidateQueries({ queryKey: ["work-orders", businessId] });
      qc.invalidateQueries({ queryKey: ["gap-model", businessId] });
      qc.invalidateQueries({ queryKey: ["dashboard", businessId] });
      qc.invalidateQueries({ queryKey: ["jobs", businessId] });
    },
  });
}

// ---- content / work ----
export function useWorkOrders(businessId: number | null) {
  return useApiQuery<WorkOrder[]>(["work-orders", businessId], businessId ? `/businesses/${businessId}/work-orders` : null);
}

// The impact-ranked open tasks (expected_points / effort), already sorted best-first by the
// server. Powers the unified to-do hub's "Today's focus" card + "By priority" board view.
export function useRoadmap(businessId: number | null) {
  return useApiQuery<Roadmap>(["roadmap", businessId], businessId ? `/businesses/${businessId}/roadmap` : null);
}

// Team roster — people who can be assigned tasks on this business (FK-backed assignee dropdown).
export function useTeam(businessId: number | null) {
  return useApiQuery<TeamMember[]>(["team", businessId], businessId ? `/businesses/${businessId}/team` : null);
}

export function useContentDrafts(businessId: number | null) {
  return useApiQuery<ContentDraft[]>(["content-drafts", businessId], businessId ? `/businesses/${businessId}/content-drafts` : null);
}

// Is NeuronWriter content-optimization wired up for this business? `configured` means a key
// is set; `live` means it's currently reachable. When not configured the SERP-score gauge stays
// dormant (renders nothing), so the drafts UI can decide whether to surface a connect hint.
export function useContentOptimizationStatus(businessId: number | null) {
  return useApiQuery<ContentOptimizationStatus>(
    ["content-optimization-status", businessId],
    businessId ? `/businesses/${businessId}/content-optimization-status` : null,
  );
}

export function useProductionBriefs(businessId: number | null) {
  return useApiQuery<ProductionBrief[]>(["production-briefs", businessId], businessId ? `/businesses/${businessId}/production-briefs` : null);
}

// Mark a production brief produced / change its status. `produced_on` (YYYY-MM-DD, default
// today, back-datable) is recorded + logged when status is "produced". Marking produced drops
// the brief off the to-produce list (it only returns status='to_produce'), which is expected.
export function useSetBriefStatus(businessId: number | null) {
  return useApiMutation<{ briefId: number; status: "produced" | "in_production" | "to_produce" | "superseded"; produced_on?: string }>(
    ({ briefId }) => `/businesses/${businessId}/production-briefs/${briefId}/status`,
    ({ status, produced_on }) => ({ status, produced_on: produced_on ?? null }),
    [["production-briefs", businessId], ["actions-taken", businessId], ["task-impact", businessId]],
  );
}

export function useDiscoveryTargets(businessId: number | null) {
  return useApiQuery<DiscoveryTarget[]>(["discovery-targets", businessId], businessId ? `/businesses/${businessId}/discovery-targets` : null);
}

// ---- mutations ----
function useApiMutation<TVars>(
  pathFor: (vars: TVars) => string,
  bodyFor: (vars: TVars) => unknown,
  invalidate: unknown[][],
  method: "POST" | "PATCH" | "PUT" | "DELETE" = "POST",
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) =>
      apiFetch(pathFor(vars), { method, body: bodyFor(vars) }),
    onSuccess: () => {
      for (const key of invalidate) qc.invalidateQueries({ queryKey: key });
    },
  });
}

// Guided first-run setup: create a business + competitors/keywords and kick off the full
// pipeline in one POST. Returns the new business id + the queued jobs (so the UI can route
// to the new business and show progress). Invalidates the business list so the switcher updates.
export interface SetupBusinessVars {
  name: string;
  domain?: string;
  services?: string;
  industry?: string;
  goal?: string;
  contested_terms?: string;
  geo?: string;
  competitors?: { name: string; domain?: string }[];
  keywords?: string[];
  run_pipeline?: boolean;
}
export interface SetupBusinessResult {
  business_id: number;
  name: string;
  competitors_added: number;
  keywords_added: number;
  jobs: { job_type: string; job_id: number | null; already_running?: boolean; error?: string }[];
}
export function useSetupBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: SetupBusinessVars) =>
      apiFetch<SetupBusinessResult>("/onboarding/setup", { method: "POST", body: vars }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["businesses"] }),
  });
}

export function useApproveDraft(businessId: number | null) {
  return useApiMutation<{ draftId: number; override_reason?: string }>(
    ({ draftId }) => `/businesses/${businessId}/content-drafts/${draftId}/approve`,
    ({ override_reason }) => ({ override_reason: override_reason ?? null }),
    [["content-drafts", businessId], ["work-orders", businessId], ["dashboard", businessId], ["compliance-ledger", businessId]],
  );
}

// Immutable compliance sign-off record (the principal-review audit trail).
export function useComplianceLedger(businessId: number | null) {
  return useApiQuery<ComplianceSignoff[]>(["compliance-ledger", businessId], base(businessId, "/compliance-ledger"));
}

export function useEditDraft(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { draftId: number; title?: string; body?: string }) =>
      apiFetch(`/businesses/${businessId}/content-drafts/${v.draftId}`, {
        method: "PATCH",
        body: { title: v.title ?? null, body: v.body ?? null },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["content-drafts", businessId] }),
  });
}
export function useRejectDraft(businessId: number | null) {
  return useApiMutation<{ draftId: number; notes?: string }>(
    ({ draftId }) => `/businesses/${businessId}/content-drafts/${draftId}/reject`,
    ({ notes }) => ({ notes: notes ?? null }),
    [["content-drafts", businessId]],
  );
}

export function useAddWorkOrder(businessId: number | null) {
  return useApiMutation<{ title: string; instruction?: string; recommended_tool?: string; target_date?: string }>(
    () => `/businesses/${businessId}/work-orders`,
    (v) => ({
      title: v.title,
      instruction: v.instruction ?? null,
      recommended_tool: v.recommended_tool ?? null,
      target_date: v.target_date ?? null,
    }),
    [["work-orders", businessId], ["dashboard", businessId]],
  );
}
export function useSetWorkOrderStatus(businessId: number | null) {
  return useApiMutation<{ woId: number; status: string; assignee?: string; notes?: string; completed_on?: string }>(
    ({ woId }) => `/businesses/${businessId}/work-orders/${woId}/status`,
    ({ status, assignee, notes, completed_on }) => ({
      status,
      assignee: assignee ?? null,
      notes: notes ?? null,
      // Only send a completion date when one was chosen; the backend defaults to today and
      // only applies it for done/verified, so omitting it is safe.
      completed_on: completed_on ?? null,
    }),
    [["work-orders", businessId], ["dashboard", businessId], ["actions-taken", businessId], ["task-impact", businessId]],
  );
}

// Assign a task + set its start/due dates. assignee_user_id (FK) is preferred over free-text assignee.
export function useEditWorkOrder(businessId: number | null) {
  return useApiMutation<{ woId: number; assignee?: string; assignee_user_id?: number | null; start_date?: string; target_date?: string }>(
    ({ woId }) => `/businesses/${businessId}/work-orders/${woId}`,
    ({ assignee, assignee_user_id, start_date, target_date }) => ({ assignee, assignee_user_id, start_date, target_date }),
    [["work-orders", businessId]],
    "PATCH",
  );
}

// Generate an AI draft for a single content work order (background job -> shows in the
// review queue). Invalidates jobs so the progress banner picks it up.
export function useGenerateDraftForWo(businessId: number | null) {
  return useApiMutation<{ woId: number }>(
    ({ woId }) => `/businesses/${businessId}/work-orders/${woId}/generate-draft`,
    () => ({}),
    [["jobs", businessId], ["content-drafts", businessId]],
  );
}

// Promote a recommendation ("Do this next") onto the managed "Improvement tasks" board,
// capturing owner + start/due dates + an optional first progress note.
export function usePromoteWorkOrder(businessId: number | null) {
  return useApiMutation<{ woId: number; assignee?: string; assignee_user_id?: number | null; start_date?: string; target_date?: string; note?: string }>(
    ({ woId }) => `/businesses/${businessId}/work-orders/${woId}/promote`,
    ({ assignee, assignee_user_id, start_date, target_date, note }) => ({
      assignee: assignee ?? null,
      assignee_user_id: assignee_user_id ?? null,
      start_date: start_date ?? null,
      target_date: target_date ?? null,
      note: note ?? null,
    }),
    [["work-orders", businessId], ["dashboard", businessId]],
  );
}

// Append a progress note to a managed task's timeline.
export function useAddWorkOrderNote(businessId: number | null) {
  return useApiMutation<{ woId: number; text: string }>(
    ({ woId }) => `/businesses/${businessId}/work-orders/${woId}/note`,
    ({ text }) => ({ text }),
    [["work-orders", businessId]],
  );
}

// The log of completed actions (work orders marked done/verified + briefs marked produced),
// newest-first per the server. Feeds the "Work completed" readout.
export function useActionsTaken(businessId: number | null) {
  return useApiQuery<ActionTaken[]>(["actions-taken", businessId], base(businessId, "/actions-taken"));
}

// "What moved the needle" — correlation across audit windows between logged actions of each
// capability and the score change. Already sorted best-first by the server.
export function useTaskImpact(businessId: number | null) {
  return useApiQuery<TaskImpact>(["task-impact", businessId], base(businessId, "/task-impact"));
}

// ---- rankings / timeline / sustain ----
const base = (businessId: number | null, suffix: string) =>
  businessId ? `/businesses/${businessId}${suffix}` : null;

export function useShareOfVoice(businessId: number | null) {
  return useApiQuery<ShareOfVoice>(["sov", businessId], base(businessId, "/citations/share-of-voice"));
}
// Published pieces old enough to be worth a freshness refresh (read-only recommendations).
export function useFreshnessQueue(businessId: number | null) {
  return useApiQuery<FreshnessQueue>(["freshness-queue", businessId], base(businessId, "/freshness-queue"));
}
export function useMomentum(businessId: number | null) {
  return useApiQuery<Json>(["momentum", businessId], base(businessId, "/citations/momentum"));
}
export function useRootCause(businessId: number | null) {
  return useApiQuery<{ model: Json; created_at: string } | null>(["root-cause", businessId], base(businessId, "/root-cause"));
}
export function useAttribution(businessId: number | null) {
  return useApiQuery<AttributionRow[]>(["attribution", businessId], base(businessId, "/attribution"));
}
export function useTimeline(businessId: number | null) {
  return useApiQuery<Json>(["timeline", businessId], base(businessId, "/timeline"));
}
export function useAcceleration(businessId: number | null) {
  return useApiQuery<Json>(["acceleration", businessId], base(businessId, "/acceleration"));
}
export function useLearnedLevers(businessId: number | null) {
  return useApiQuery<LearnedLevers>(["levers", businessId], base(businessId, "/learned-levers"));
}
export function useIncidents(businessId: number | null) {
  return useApiQuery<Incident[]>(["incidents", businessId], base(businessId, "/incidents"));
}
export function useMentions(businessId: number | null) {
  return useApiQuery<Mention[]>(["mentions", businessId], base(businessId, "/mentions"));
}

// ---- competitor benchmarking ----
export function useCompetitors(businessId: number | null) {
  return useApiQuery<Competitor[]>(["competitors", businessId], base(businessId, "/competitors"));
}
export function useCompare(businessId: number | null) {
  return useApiQuery<CompareResult>(["compare", businessId], base(businessId, "/competitors/compare"));
}
export function useLocalRankings(businessId: number | null) {
  return useApiQuery<LocalRankings>(["local-rankings", businessId], base(businessId, "/local-rankings"));
}

export function useLocalSeoGoal(businessId: number | null) {
  return useApiQuery<LocalSeoGoal>(["local-seo-goal", businessId], base(businessId, "/local-seo-goal"));
}

// Google rating snapshot + recent reviews (from the ingest_gbp_reviews job).
export function useReviews(businessId: number | null) {
  return useApiQuery<ReviewsSummary>(["reviews", businessId], base(businessId, "/reviews"));
}

// Per-run overall + per-engine score trend (0-100) over time.
export function useMetricsTrend(businessId: number | null) {
  return useApiQuery<MetricsTrend>(["metrics-trend", businessId], base(businessId, "/metrics-trend"));
}

// Trackable site-health (AI-crawler readiness) + local-visibility trends over time (0-100),
// the same way the AI reputation score is tracked.
export type MetricTrendPoint = { date: string | null; score: number; run_id?: number };
export function useSiteHealthTrend(businessId: number | null) {
  return useApiQuery<MetricTrendPoint[]>(["site-health-trend", businessId], base(businessId, "/site-health-trend"));
}
export function useLocalRankTrend(businessId: number | null) {
  return useApiQuery<MetricTrendPoint[]>(["local-rank-trend", businessId], base(businessId, "/local-rank-trend"));
}

// Cross-engine divergence + persona/location lens.
export function useAnswerLenses(businessId: number | null) {
  return useApiQuery<AnswerLenses>(["answer-lenses", businessId], base(businessId, "/answer-lenses"));
}

// In-console viewable report bundle (score, gaps, local reputation, this-month work).
export function useReportView(businessId: number | null) {
  return useApiQuery<ReportView>(["report-view", businessId], base(businessId, "/report-view"));
}

// "This month's work" — client-facing activity counts (the retention narrative).
export function useActivitySummary(businessId: number | null) {
  return useApiQuery<ActivitySummary>(["activity-summary", businessId], base(businessId, "/activity-summary"));
}

// SEO keyword intelligence — the ranked terms to target (from the keyword_research job).
// Distinct from useKeywords (brand-monitoring keyword list).
export function useTargetKeywords(businessId: number | null) {
  return useApiQuery<TargetKeyword[]>(["seo-keywords", businessId], base(businessId, "/seo-keywords"));
}

// ---- user-managed prompts / topics ----
export function usePrompts(businessId: number | null) {
  return useApiQuery<CustomPrompt[]>(["prompts", businessId], base(businessId, "/prompts"));
}
export function useAddPrompt(businessId: number | null) {
  return useApiMutation<{ prompt: string; topic?: string; tags?: string }>(
    () => `/businesses/${businessId}/prompts`,
    (v) => ({ prompt: v.prompt, topic: v.topic ?? "", tags: v.tags ?? "" }),
    [["prompts", businessId]],
  );
}
export function useUpdatePrompt(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; enabled?: boolean; topic?: string; tags?: string }) =>
      apiFetch(`/businesses/${businessId}/prompts/${v.id}`, {
        method: "PATCH",
        body: { enabled: v.enabled ?? null, topic: v.topic ?? null, tags: v.tags ?? null },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prompts", businessId] }),
  });
}
export function useDeletePrompt(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/businesses/${businessId}/prompts/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prompts", businessId] }),
  });
}
export function usePromptResults(businessId: number | null) {
  return useApiQuery<PromptResults>(["prompt-results", businessId], base(businessId, "/prompt-results"));
}
export function useOnboarding(businessId: number | null) {
  return useApiQuery<OnboardingStatus>(["onboarding", businessId], base(businessId, "/onboarding"));
}
export function useRevokeSessions() {
  return useMutation({ mutationFn: () => apiFetch("/auth/revoke-sessions", { method: "POST" }) });
}
export function useDeleteBusiness(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/businesses/${businessId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["businesses"] }),
  });
}
export function useEmailReport(businessId: number | null) {
  return useApiMutation<{ reportId: number; to: string }>(
    ({ reportId }) => `/businesses/${businessId}/reports/${reportId}/email`,
    ({ to }) => ({ to }),
    [],
  );
}
export function useReports(businessId: number | null, poll = false) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["reports", businessId],
    queryFn: () => apiFetch<Report[]>(`/businesses/${businessId}/reports`),
    enabled: !!user && !!businessId,
    refetchInterval: poll ? 8000 : false,
  });
}
export function useVisibilityTrend(businessId: number | null) {
  return useApiQuery<VisibilityTrend>(["visibility-trend", businessId], base(businessId, "/visibility-trend"));
}
export function useAddCompetitor(businessId: number | null) {
  return useApiMutation<{ name: string; domain?: string }>(
    () => `/businesses/${businessId}/competitors`,
    (v) => ({ name: v.name, domain: v.domain ?? "" }),
    [["competitors", businessId]],
  );
}
export function useDeleteCompetitor(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/businesses/${businessId}/competitors/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["competitors", businessId] }),
  });
}

// ---- notifications / alerts ----
export function useNotifications(businessId: number | null, poll = true) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["notifications", businessId],
    queryFn: () => apiFetch<NotificationsResponse>(`/businesses/${businessId}/notifications`),
    enabled: !!user && !!businessId,
    refetchInterval: poll ? 20000 : false,
  });
}
export function useMarkNotificationRead(businessId: number | null) {
  return useApiMutation<{ id: number }>(
    ({ id }) => `/businesses/${businessId}/notifications/${id}/read`,
    () => undefined,
    [["notifications", businessId]],
  );
}
export function useMarkAllNotificationsRead(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/businesses/${businessId}/notifications/read-all`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", businessId] }),
  });
}

// ---- automation schedules ----
export function useSchedules(businessId: number | null) {
  return useApiQuery<Schedule[]>(["schedules", businessId], base(businessId, "/schedules"));
}
export function useUpsertSchedule(businessId: number | null) {
  return useApiMutation<{ job_type: string; interval_hours: number; enabled?: boolean }>(
    () => `/businesses/${businessId}/schedules`,
    (v) => ({ job_type: v.job_type, interval_hours: v.interval_hours, enabled: v.enabled ?? true }),
    [["schedules", businessId]],
  );
}
export function useDeleteSchedule(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/businesses/${businessId}/schedules/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules", businessId] }),
  });
}

// ---- monitoring keywords ----
export function useKeywords(businessId: number | null) {
  return useApiQuery<Keyword[]>(["keywords", businessId], base(businessId, "/keywords"));
}
export function useAddKeyword(businessId: number | null) {
  return useApiMutation<{ keyword: string; negative?: boolean }>(
    () => `/businesses/${businessId}/keywords`,
    (v) => ({ keyword: v.keyword, negative: v.negative ?? false }),
    [["keywords", businessId]],
  );
}
export function useDeleteKeyword(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch(`/businesses/${businessId}/keywords/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keywords", businessId] }),
  });
}

// ---- finalized / published content (assets) ----
export function useAssets(businessId: number | null) {
  return useApiQuery<Asset[]>(["assets", businessId], base(businessId, "/assets"));
}

// ---- multi-surface distribution log (where each asset was posted) ----
export function useAssetPlacements(businessId: number | null, assetId: number | null) {
  return useApiQuery<AssetPlacement[]>(
    ["placements", businessId, assetId],
    businessId && assetId ? `/businesses/${businessId}/assets/${assetId}/placements` : null,
  );
}
export function useAddPlacement(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, channel }: { assetId: number; channel: string }) =>
      apiFetch(`/businesses/${businessId}/assets/${assetId}/placements`, { method: "POST", body: { channel } }),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ["placements", businessId, v.assetId] }),
  });
}
export function useUpdatePlacement(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ placementId, status, url }: { assetId: number; placementId: number; status?: string; url?: string }) =>
      apiFetch(`/businesses/${businessId}/placements/${placementId}`, { method: "PATCH", body: { status, url } }),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ["placements", businessId, v.assetId] }),
  });
}

// Record where a published asset went live (manual link) + flip pending -> live.
export function usePatchAsset(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, published_url, published_status }: { assetId: number; published_url?: string; published_status?: string }) =>
      apiFetch(`/businesses/${businessId}/assets/${assetId}`, {
        method: "PATCH",
        body: { published_url, published_status },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assets", businessId] }),
  });
}

// ---- outreach targets (manual add + status) ----
export function useAddDiscoveryTarget(businessId: number | null) {
  return useApiMutation<{ name: string; channel?: string; outlet?: string; url?: string; beat?: string; rationale?: string }>(
    () => `/businesses/${businessId}/discovery-targets`,
    (v) => v,
    [["discovery-targets", businessId]],
  );
}
// Push an outreach target into the client's CRM/stack via the webhook bus.
export function usePushTarget(businessId: number | null) {
  return useMutation({
    mutationFn: (targetId: number) =>
      apiFetch<{ sent: boolean }>(`/businesses/${businessId}/discovery-targets/${targetId}/push`, { method: "POST" }),
  });
}
// Draft an outreach pitch for a target (human reviews + sends).
export function useDraftPitch(businessId: number | null) {
  return useMutation({
    mutationFn: (targetId: number) =>
      apiFetch<{ pitch: string }>(`/businesses/${businessId}/discovery-targets/${targetId}/draft-pitch`, { method: "POST" }),
  });
}
export function useSetTargetStatus(businessId: number | null) {
  return useApiMutation<{ targetId: number; status: string }>(
    ({ targetId }) => `/businesses/${businessId}/discovery-targets/${targetId}/status`,
    ({ status }) => ({ status }),
    [["discovery-targets", businessId]],
  );
}
export function useUpdateTargetContact(businessId: number | null) {
  return useApiMutation<{ targetId: number; contact_name?: string; contact_email?: string; contact_phone?: string }>(
    ({ targetId }) => `/businesses/${businessId}/discovery-targets/${targetId}`,
    ({ contact_name, contact_email, contact_phone }) => ({ contact_name, contact_email, contact_phone }),
    [["discovery-targets", businessId]],
    "PATCH",
  );
}
export function useResumeIncident(businessId: number | null) {
  return useApiMutation<{ incidentId: number; approved: boolean; edited_response?: string }>(
    ({ incidentId }) => `/businesses/${businessId}/incidents/${incidentId}/resume`,
    ({ approved, edited_response }) => ({ approved, edited_response: edited_response ?? null }),
    [["incidents", businessId], ["dashboard", businessId]],
  );
}

// ---- jobs + admin ----
export function useJobs(businessId: number | null, poll = true) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["jobs", businessId],
    queryFn: () => apiFetch<JobsResponse>(`/businesses/${businessId}/jobs`),
    enabled: !!user && !!businessId,
    // Only poll while something is actually in flight — an idle dashboard shouldn't hit
    // /jobs every 3s forever. Mirrors the data-aware pattern in useExternalSignals.
    refetchInterval: (q) => {
      if (!poll) return false;
      const jobs = (q.state.data as JobsResponse | undefined)?.jobs ?? [];
      return jobs.some((j) => j.status === "running" || j.status === "queued") ? 3000 : false;
    },
  });
}

export function useTriggerJob(businessId: number | null) {
  return useApiMutation<{ jobType: string }>(
    ({ jobType }) => `/businesses/${businessId}/jobs/${jobType}`,
    () => undefined,
    [["jobs", businessId]],
  );
}

// Run the ENTIRE pipeline at once (audit → crawl → gap → plan → … → report). Expensive +
// rate-limited to once/day server-side; the UI confirms before calling this.
export function useRunEverything(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/businesses/${businessId}/jobs/run-everything`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs", businessId] }),
  });
}

export function useAdminUsers() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<AdminUser[]>("/admin/users"),
    enabled: !!user,
  });
}

export function useCreateUser() {
  return useApiMutation<{ email: string; password: string; full_name?: string; role: string }>(
    () => "/admin/users",
    (v) => v,
    [["admin-users"]],
  );
}

export function useGrantAccess() {
  return useApiMutation<{ userId: number; business_id: number; access_role: string }>(
    ({ userId }) => `/admin/users/${userId}/access`,
    ({ business_id, access_role }) => ({ business_id, access_role }),
    [["admin-users"]],
  );
}

export function useCreateBusiness() {
  return useApiMutation<{ name: string; domain?: string; goal?: string; contested_terms?: string; geo?: string; services?: string; owned_domains?: string[] }>(
    () => "/admin/businesses",
    (v) => v,
    [["businesses"]],
  );
}

// PATCH an existing business (admin only). Pass { id, ...fields-to-update }; the backend
// whitelists name/domain/services/goal/contested_terms/geo (+industry once migrated).
export function useUpdateBusiness() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number } & Record<string, unknown>) =>
      apiFetch(`/admin/businesses/${id}`, { method: "PATCH", body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["businesses"] }),
  });
}

// ---- multi-location (admin only; under /admin/businesses/{businessId}/locations) ----
// Each business can have several physical locations (storefronts/offices), one flagged primary.
export interface LocationVars {
  label?: string;
  address?: string;
  city?: string;
  state?: string;
  postal?: string;
  phone?: string;
  is_primary?: boolean;
}
export function useLocations(businessId: number | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["locations", businessId],
    queryFn: () => apiFetch<Location[]>(`/admin/businesses/${businessId}/locations`),
    enabled: !!user && !!businessId,
  });
}
export function useAddLocation(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: LocationVars) =>
      apiFetch<Location>(`/admin/businesses/${businessId}/locations`, { method: "POST", body: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["locations", businessId] }),
  });
}
export function useUpdateLocation(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ locId, ...patch }: { locId: number } & LocationVars) =>
      apiFetch<Location>(`/admin/businesses/${businessId}/locations/${locId}`, { method: "PATCH", body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["locations", businessId] }),
  });
}
export function useDeleteLocation(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (locId: number) =>
      apiFetch<{ deleted: boolean }>(`/admin/businesses/${businessId}/locations/${locId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["locations", businessId] }),
  });
}

// ---- billing (org-level; wired but dormant until the platform billing switch is on) ----
export function useBillingPlans() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["billing-plans"],
    queryFn: () => apiFetch<BillingPlan[]>("/plans"),
    enabled: !!user,
  });
}
export function useSubscription() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["subscription"],
    queryFn: () => apiFetch<SubscriptionSummary>("/orgs/me/subscription"),
    enabled: !!user && !!user.org_id,
  });
}
export function useCheckout() {
  return useMutation({
    mutationFn: (v: { plan_code: string }) =>
      apiFetch<{ url: string; id: string }>("/billing/checkout", { method: "POST", body: v }),
  });
}
export function useBillingPortal() {
  return useMutation({
    mutationFn: () => apiFetch<{ url: string }>("/billing/portal", { method: "POST", body: {} }),
  });
}

// ---- platform settings (super-admin only: the billing master switch) ----
export function usePlatformSettings() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["platform-settings"],
    queryFn: () => apiFetch<{ billing_enabled: boolean }>("/platform/settings"),
    enabled: !!user?.is_super_admin,
  });
}
export function useSetBillingEnabled() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      apiFetch<{ billing_enabled: boolean }>("/platform/settings", { method: "PATCH", body: { billing_enabled: enabled } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["platform-settings"] });
      qc.invalidateQueries({ queryKey: ["auth-me"] });
    },
  });
}

// ---- external data ingestion ----
export function useExternalSignals(businessId: number | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["external-signals", businessId],
    queryFn: () => apiFetch<ExternalSignal[]>(`/businesses/${businessId}/external-signals`),
    enabled: !!user && !!businessId,
    // poll while anything is still awaiting AI normalization
    refetchInterval: (q) =>
      (q.state.data as ExternalSignal[] | undefined)?.some((s) => s.status === "raw") ? 4000 : false,
  });
}

export function useIngestSignal(businessId: number | null) {
  return useApiMutation<{ source: string; signal_type: string; content: string }>(
    () => `/businesses/${businessId}/external-signals`,
    (v) => v,
    [["external-signals", businessId]],
  );
}

// =====================================================================================
// Integrations & Publishing
// =====================================================================================

// ---- connections vault ----
export function useConnections(businessId: number | null) {
  return useApiQuery<ConnectionsResponse>(["connections", businessId], base(businessId, "/connections"));
}

// Start an OAuth flow (GBP only) — returns the provider authorize URL the caller redirects to.
export function useAuthorizeConnection(businessId: number | null) {
  return useMutation({
    mutationFn: (kind: string) =>
      apiFetch<{ authorize_url: string; state: string }>(
        `/businesses/${businessId}/connections/${kind}/authorize`,
        { method: "POST", body: {} },
      ),
  });
}

// Directly store a credential (WordPress app-password, or an Ayrshare profile key).
export interface ConnectDirectVars {
  kind: string;
  site_url?: string;
  wp_user?: string;
  app_password?: string;
  profile_key?: string;
  display_name?: string;
  label?: string;
}
export function useConnectDirect(businessId: number | null) {
  return useApiMutation<ConnectDirectVars>(
    () => `/businesses/${businessId}/connections`,
    (v) => v,
    [["connections", businessId], ["publish-channels", businessId]],
  );
}

// Probe a stored connection (does the credential still work?). Returns the live status.
export function useTestConnection(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (connId: number) =>
      apiFetch<{ ok: boolean; status: string; detail?: string }>(
        `/businesses/${businessId}/connections/${connId}/test`,
        { method: "POST", body: {} },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections", businessId] }),
  });
}

export function useDisconnectConnection(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (connId: number) =>
      apiFetch<{ ok: true; id: number }>(`/businesses/${businessId}/connections/${connId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections", businessId] });
      qc.invalidateQueries({ queryKey: ["publish-channels", businessId] });
    },
  });
}

// ---- Zernio (Zernia) social publishing --------------------------------------------------
// The connect-your-accounts flow: set up a profile, authorize each platform in a Zernio OAuth
// popup, then sync to pull the connected accounts back. Auth is a server-side account key.

// Create (or reuse) the Zernio profile for this business. Invalidates connections so the
// new zernia connection (with its meta.accounts) shows up.
export function useZerniaSetup(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ZerniaSetup>(`/businesses/${businessId}/connections/zernia/setup`, { method: "POST", body: {} }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections", businessId] }),
  });
}

// Get the Zernio OAuth URL for one platform. Does NOT navigate — the caller opens authUrl
// in a new tab so the owner can authorize that account on the platform.
export function useZerniaConnect(businessId: number | null) {
  return useMutation({
    mutationFn: (platform: string) =>
      apiFetch<ZerniaConnectUrl>(`/businesses/${businessId}/connections/zernia/connect/${platform}`, { method: "GET" }),
  });
}

// Pull the connected accounts back from Zernio (after the owner finishes authorizing in the
// popup). Invalidates connections so the connected handles refresh on the card.
export function useZerniaSync(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ZerniaSyncResult>(`/businesses/${businessId}/connections/zernia/sync`, { method: "POST", body: {} }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections", businessId] }),
  });
}

// ---- publishing ----
export function usePublishChannels(businessId: number | null) {
  return useApiQuery<PublishChannel[]>(["publish-channels", businessId], base(businessId, "/publish-channels"));
}

export function usePublishTargets(businessId: number | null, assetId: number | null) {
  return useApiQuery<PublishTarget[]>(
    ["publish-targets", businessId, assetId],
    businessId && assetId ? `/businesses/${businessId}/assets/${assetId}/publish-targets` : null,
  );
}

// Publish an asset to one or more channels (optionally scheduled). Invalidates that asset's targets.
export function usePublishAsset(businessId: number | null, assetId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { channels: string[]; scheduled_for?: string | null }) =>
      apiFetch<{ ok: true; created: number[]; skipped: string[] }>(
        `/businesses/${businessId}/assets/${assetId}/publish`,
        { method: "POST", body: { channels: v.channels, scheduled_for: v.scheduled_for ?? null } },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publish-targets", businessId, assetId] }),
  });
}

// Retry a failed publish target. Invalidates the asset's targets (caller passes assetId for the key).
export function useRetryPublishTarget(businessId: number | null, assetId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetId: number) =>
      apiFetch<{ ok: true; id: number }>(`/businesses/${businessId}/publish-targets/${targetId}/retry`, { method: "POST", body: {} }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publish-targets", businessId, assetId] }),
  });
}

// ---- review replies ----
export function useReviewReplies(businessId: number | null, status?: string) {
  return useApiQuery<ReviewReply[]>(
    ["review-replies", businessId, status ?? "all"],
    businessId ? `/businesses/${businessId}/review-replies${status ? `?status=${encodeURIComponent(status)}` : ""}` : null,
  );
}

// Approve a review reply — may 422 with a compliance message (the caller surfaces err.message).
export function useApproveReviewReply(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/businesses/${businessId}/review-replies/${id}/approve`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-replies", businessId] });
      qc.invalidateQueries({ queryKey: ["approval-queue", businessId] });
    },
  });
}
export function useRejectReviewReply(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/businesses/${businessId}/review-replies/${id}/reject`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-replies", businessId] });
      qc.invalidateQueries({ queryKey: ["approval-queue", businessId] });
    },
  });
}
export function useEditReviewReply(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; draft: string }) =>
      apiFetch(`/businesses/${businessId}/review-replies/${v.id}`, { method: "PATCH", body: { draft: v.draft } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-replies", businessId] });
      qc.invalidateQueries({ queryKey: ["approval-queue", businessId] });
    },
  });
}

// ---- unified approval queue ----
export function useApprovalQueue(businessId: number | null, surface?: string, kind?: string) {
  const params = new URLSearchParams();
  if (surface) params.set("surface", surface);
  if (kind) params.set("kind", kind);
  const qs = params.toString();
  return useApiQuery<ApprovalQueueResponse>(
    ["approval-queue", businessId, surface ?? "all", kind ?? "all"],
    businessId ? `/businesses/${businessId}/approval-queue${qs ? `?${qs}` : ""}` : null,
  );
}

// Approve/reject any queue item (kind ∈ mention_reply | review_reply). approve may 422 (compliance).
export function useApproveQueueItem(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { kind: QueueItemKind; itemId: number }) =>
      apiFetch(`/businesses/${businessId}/approval-queue/${v.kind}/${v.itemId}/approve`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval-queue", businessId] });
      qc.invalidateQueries({ queryKey: ["review-replies", businessId] });
    },
  });
}
export function useRejectQueueItem(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { kind: QueueItemKind; itemId: number }) =>
      apiFetch(`/businesses/${businessId}/approval-queue/${v.kind}/${v.itemId}/reject`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval-queue", businessId] });
      qc.invalidateQueries({ queryKey: ["review-replies", businessId] });
    },
  });
}

// ---- integration / automation settings ----
export function useIntegrationSettings(businessId: number | null) {
  return useApiQuery<IntegrationSettingsResponse>(
    ["integration-settings", businessId],
    base(businessId, "/integration-settings"),
  );
}

// PUT a partial settings patch. Auto-post fields 403 unless the user is an org manager
// (the caller disables those inputs based on can_manage_autopost + surfaces the error).
export function useUpdateIntegrationSettings(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<IntegrationSettings>) =>
      apiFetch<{ ok: true; settings: IntegrationSettings }>(`/businesses/${businessId}/integration-settings`, {
        method: "PUT",
        body: patch,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integration-settings", businessId] }),
  });
}

// =====================================================================================
// Review-request kit + visual content
// =====================================================================================

// Copy-paste "ask for a review" assets (write-review link + SMS/email templates) and the
// NAP block we keep consistent across directory citations.
export function useReviewRequest(businessId: number | null) {
  return useApiQuery<ReviewRequestKit>(["review-request", businessId], base(businessId, "/review-request"));
}

// Generated visuals for the business (optionally filtered by status). `poll` refetches
// while anything is still pending, so a freshly-queued visual appears when its job finishes.
export function useVisuals(businessId: number | null, status?: string, poll = false) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["visuals", businessId, status ?? "all"],
    queryFn: () =>
      apiFetch<VisualsResponse>(
        `/businesses/${businessId}/visuals${status ? `?status=${encodeURIComponent(status)}` : ""}`,
      ),
    enabled: !!user && !!businessId,
    refetchInterval: (q) => {
      if (!poll) return false;
      const visuals = (q.state.data as VisualsResponse | undefined)?.visuals ?? [];
      return visuals.some((v) => v.status === "pending") ? 4000 : false;
    },
  });
}

// Generated visuals for a single draft (from its ![alt](IMAGE:…) markers). Polls while any is
// pending so a freshly-queued image appears when its job finishes.
export function useDraftVisuals(businessId: number | null, draftId: number | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["draft-visuals", businessId, draftId],
    queryFn: () => apiFetch<VisualsResponse>(`/businesses/${businessId}/visuals?draft_id=${draftId}`),
    enabled: !!user && !!businessId && !!draftId,
    refetchInterval: (q) => {
      const visuals = (q.state.data as VisualsResponse | undefined)?.visuals ?? [];
      return visuals.some((v) => v.status === "pending") ? 4000 : false;
    },
  });
}

// Enqueue a visual-generation job (quote card / AI image / video brief). Invalidates jobs
// so the progress banner picks it up + the visuals lists so it shows once the job finishes.
export function useGenerateVisual(businessId: number | null) {
  return useApiMutation<{
    kind: "image" | "quote_card" | "video_brief";
    prompt?: string;
    text?: string;
    attribution?: string;
    topic?: string;
    work_order_id?: number;
    draft_id?: number;
  }>(
    () => `/businesses/${businessId}/visuals/generate`,
    (v) => ({
      kind: v.kind,
      prompt: v.prompt ?? null,
      text: v.text ?? null,
      attribution: v.attribution ?? null,
      topic: v.topic ?? null,
      work_order_id: v.work_order_id ?? null,
      draft_id: v.draft_id ?? null,
    }),
    [["visuals", businessId], ["draft-visuals", businessId], ["jobs", businessId]],
  );
}

export function useApproveVisual(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (visualId: number) =>
      apiFetch<{ ok: true }>(`/businesses/${businessId}/visuals/${visualId}/approve`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["visuals", businessId] });
      qc.invalidateQueries({ queryKey: ["draft-visuals", businessId] });
    },
  });
}

export function useRejectVisual(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (visualId: number) =>
      apiFetch<{ ok: true }>(`/businesses/${businessId}/visuals/${visualId}/reject`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["visuals", businessId] });
      qc.invalidateQueries({ queryKey: ["draft-visuals", businessId] });
    },
  });
}

// =====================================================================================
// Google Search Console — real Google "Search traffic": clicks, impressions, CTR, position.
// The measured counterpart to the AI-visibility story. Every key includes businessId so the
// cache is tenant-isolated; the site/property hooks key by connId since they're per-connection.
// =====================================================================================

// Top-line clicks/impressions/CTR/position for the current 28d window vs the prior 28d.
export function useGscSummary(businessId: number | null) {
  return useApiQuery<GscSummary>(["gsc-summary", businessId], base(businessId, "/gsc-summary"));
}

// Daily clicks + impressions over the requested window (28 / 90 / 365 days).
export function useGscTrend(businessId: number | null, days = 28) {
  return useApiQuery<GscTrendPoint[]>(
    ["gsc-trend", businessId, days],
    businessId ? `/businesses/${businessId}/gsc-trend?days=${days}` : null,
  );
}

// Top search queries (the words people typed to find the business).
export function useGscQueries(businessId: number | null, limit = 25) {
  return useApiQuery<GscQuery[]>(
    ["gsc-queries", businessId, limit],
    businessId ? `/businesses/${businessId}/gsc-queries?limit=${limit}` : null,
  );
}

// Top landing pages. `oursOnly` filters to content we published (is_our_content) server-side.
export function useGscPages(businessId: number | null, oursOnly = false, limit = 25) {
  return useApiQuery<GscPage[]>(
    ["gsc-pages", businessId, oursOnly, limit],
    businessId ? `/businesses/${businessId}/gsc-pages?limit=${limit}&ours_only=${oursOnly ? "true" : "false"}` : null,
  );
}

// Striking-distance queries — high-impression terms ranking just off page one.
export function useGscOpportunities(businessId: number | null) {
  return useApiQuery<GscOpportunity[]>(["gsc-opportunities", businessId], base(businessId, "/gsc-opportunities"));
}

// Equivalent-ad-value framing (total clicks vs the subset earned by content we published).
export function useGscRoi(businessId: number | null) {
  return useApiQuery<GscRoi>(["gsc-roi", businessId], base(businessId, "/gsc-roi"));
}

// Verified Search Console properties the connected Google account can read. GET, but keyed by
// connId because it's per-connection (only enabled once a connection id exists).
export function useGscSites(businessId: number | null, connId: number | null) {
  return useApiQuery<{ sites: GscSite[] }>(
    ["gsc-sites", businessId, connId],
    businessId && connId ? `/businesses/${businessId}/connections/${connId}/gsc/sites` : null,
  );
}

// Save which property this connection should pull. Invalidates connections (the picker reads
// the saved value off connection.meta) and every GSC query so the new property's data loads.
export function useSetGscProperty(businessId: number | null, connId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (property: string) =>
      apiFetch<{ ok: true; property: string }>(
        `/businesses/${businessId}/connections/${connId}/gsc/property`,
        { method: "PUT", body: { property } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-summary", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-trend", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-queries", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-pages", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-opportunities", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-roi", businessId] });
    },
  });
}

// Guided verification (for a site not yet in Search Console). Step 1 mints a token to place.
export function useStartGscVerification(businessId: number | null, connId: number | null) {
  return useMutation({
    mutationFn: (vars: { site_url: string; method: string }) =>
      apiFetch<GscVerifyStart>(
        `/businesses/${businessId}/connections/${connId}/gsc/verify/start`,
        { method: "POST", body: vars },
      ),
  });
}

// Step 2: verify ownership + register the property. On success the picker (gsc-sites) refreshes
// so the new property is selectable; if it auto-selected, the GSC summary refreshes too.
export function useCompleteGscVerification(businessId: number | null, connId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { site_url: string; method: string }) =>
      apiFetch<GscVerifyComplete>(
        `/businesses/${businessId}/connections/${connId}/gsc/verify/complete`,
        { method: "POST", body: vars },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["gsc-sites", businessId, connId] });
      qc.invalidateQueries({ queryKey: ["connections", businessId] });
      qc.invalidateQueries({ queryKey: ["gsc-summary", businessId] });
    },
  });
}

// =====================================================================================
// Google Analytics (GA4) — behavior & conversions: what visitors DO after they arrive.
// Mirrors the GSC hooks: every key includes businessId for tenant isolation; the property
// hooks key by connId since they're per-connection.
// =====================================================================================

// Top-line sessions/users/pageviews/conversions/engagement for the current window vs prior.
export function useGaSummary(businessId: number | null) {
  return useApiQuery<GaSummary>(["ga-summary", businessId], base(businessId, "/ga-summary"));
}

// Daily sessions/users/pageviews/conversions over the requested window.
export function useGaTrend(businessId: number | null, days = 28) {
  return useApiQuery<GaTrendPoint[]>(
    ["ga-trend", businessId, days],
    businessId ? `/businesses/${businessId}/ga-trend?days=${days}` : null,
  );
}

// Top landing pages by GA sessions. `oursOnly` filters to content we published (is_our_content).
export function useGaPages(businessId: number | null, oursOnly = false, limit = 25) {
  return useApiQuery<GaPage[]>(
    ["ga-pages", businessId, oursOnly, limit],
    businessId ? `/businesses/${businessId}/ga-pages?limit=${limit}&ours_only=${oursOnly ? "true" : "false"}` : null,
  );
}

// Acquisition channel mix (Organic Search / Direct / Referral / Social / …).
export function useGaChannels(businessId: number | null) {
  return useApiQuery<GaChannel[]>(["ga-channels", businessId], base(businessId, "/ga-channels"));
}

// GA4 properties the connected Google account can read (per-connection picker). Keyed by connId.
export function useGaProperties(businessId: number | null, connId: number | null) {
  return useApiQuery<{ properties: GaProperty[] }>(
    ["ga-properties", businessId, connId],
    businessId && connId ? `/businesses/${businessId}/connections/${connId}/ga/properties` : null,
  );
}

// Save which GA4 property this connection should pull. Invalidates connections (the picker reads
// the saved value off connection.meta.ga_property) and every GA query so the new data loads.
export function useSetGaProperty(businessId: number | null, connId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (property: string) =>
      apiFetch<{ ok: true; property: string }>(
        `/businesses/${businessId}/connections/${connId}/ga/property`,
        { method: "PUT", body: { property } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections", businessId] });
      qc.invalidateQueries({ queryKey: ["ga-summary", businessId] });
      qc.invalidateQueries({ queryKey: ["ga-trend", businessId] });
      qc.invalidateQueries({ queryKey: ["ga-pages", businessId] });
      qc.invalidateQueries({ queryKey: ["ga-channels", businessId] });
      qc.invalidateQueries({ queryKey: ["our-content-impact", businessId] });
    },
  });
}

// =====================================================================================
// "Is our content working?" — the causal-proof panel. Each row is a page WE published
// (a labeled subset of the whole site) with the real GSC clicks + GA sessions it earns.
// =====================================================================================
export function useOurContentImpact(businessId: number | null) {
  return useApiQuery<OurContentImpact>(["our-content-impact", businessId], base(businessId, "/our-content-impact"));
}

// =====================================================================================
// Content intelligence + SEO depth (waves 2–5). Topic authority, internal linking,
// keyword intent, directory citations, indexing, sources-to-win, backlinks, answer
// changes, review SLA / requests, public summary, and platform quota usage.
// =====================================================================================

// Topic-authority clusters (pillar/spoke keyword groups + what to write next).
export function useTopicalAuthority(businessId: number | null) {
  return useApiQuery<TopicalAuthority>(["topical-authority", businessId], base(businessId, "/topical-authority"));
}

// Keyword coverage grouped by search intent.
export function useKeywordIntent(businessId: number | null) {
  return useApiQuery<KeywordIntent>(["keyword-intent", businessId], base(businessId, "/keyword-intent"));
}

// Internal-linking opportunities (under-linked owned pages + link suggestions).
export function useInternalLinks(businessId: number | null) {
  return useApiQuery<InternalLinks>(["internal-links", businessId], base(businessId, "/internal-links"));
}

// Indexing status of our owned pages (or a skipped shape when GSC isn't connected).
export function useIndexingStatus(businessId: number | null) {
  return useApiQuery<IndexingStatus>(["indexing-status", businessId], base(businessId, "/indexing-status"));
}

// Backlink profile snapshot (has_data is false until a backlink source is configured).
export function useBacklinkProfile(businessId: number | null) {
  return useApiQuery<BacklinkProfile>(["backlink-profile", businessId], base(businessId, "/backlink-profile"));
}

// Curated directory/citation submission list + the NAP block to keep consistent.
export function useDirectoryCitations(businessId: number | null) {
  return useApiQuery<DirectoryCitations>(["directory-citations", businessId], base(businessId, "/directory-citations"));
}

// Non-owned domains AI cites about us, with the suggested action to win each.
export function useSourcesToWin(businessId: number | null) {
  return useApiQuery<SourcesToWin>(["sources-to-win", businessId], base(businessId, "/sources-to-win"));
}

// What materially changed in AI answers between the last two audits.
export function useAnswerChanges(businessId: number | null) {
  return useApiQuery<AnswerChanges>(["answer-changes", businessId], base(businessId, "/answer-changes"));
}

// Negative reviews awaiting a reply, with hours-waited vs. the SLA.
export function useReviewSla(businessId: number | null) {
  return useApiQuery<ReviewSla>(["review-sla", businessId], base(businessId, "/review-sla"));
}

// Send review-request emails to one or more recipients. Returns { sent } or a keyless
// `skipped` shape with a preview when email isn't configured on the server.
export function useSendReviewRequests(businessId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (recipients: { email: string; first_name?: string }[]) =>
      apiFetch<ReviewRequestSendResult>(`/businesses/${businessId}/review-requests/send`, {
        method: "POST",
        body: { recipients },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-sla", businessId] }),
  });
}

// The data behind a public lead-magnet page (score + band + top gaps + teaser).
export function usePublicSummary(businessId: number | null) {
  return useApiQuery<PublicSummary>(["public-summary", businessId], base(businessId, "/public-summary"));
}

// Platform-wide provider quota usage (super-admin; absolute path, no businessId).
export function usePlatformQuotaUsage(enabled: boolean) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["platform-quota-usage"],
    queryFn: () => apiFetch<QuotaUsage>("/platform/quota-usage"),
    enabled: !!user && enabled,
  });
}

// =====================================================================================
// White-label & sharing — agency branding, the public lead-magnet share link, and the
// emails captured from that page. (The PUBLIC page itself does NOT use these hooks — it's
// unauthenticated and fetches /api/public/audit/{token} with a raw fetch.)
// =====================================================================================

// Current white-label branding for the business (brand name / logo / accent hex).
export function useBranding(businessId: number | null) {
  return useApiQuery<Branding>(["branding", businessId], base(businessId, "/branding"));
}

// PATCH a partial branding update; invalidates branding so the form reflects the saved values.
export function useSetBranding(businessId: number | null) {
  return useApiMutation<Partial<Branding>>(
    () => `/businesses/${businessId}/branding`,
    (v) => v,
    [["branding", businessId]],
    "PATCH",
  );
}

// Mint (or rotate to) a public share link for the lead-magnet page. POST returns { token, url }.
export function useShareLink(businessId: number | null) {
  return useMutation({
    mutationFn: () => apiFetch<ShareLink>(`/businesses/${businessId}/share-link`, { method: "POST", body: {} }),
  });
}

// Emails captured from the public lead-magnet page (newest-first ordering is up to the caller).
export function useLeads(businessId: number | null) {
  return useApiQuery<LeadsResponse>(["leads", businessId], base(businessId, "/leads"));
}

// =====================================================================================
// Headline metric + proof — narrative crowding-out score, proof-of-impact report, and the
// ROI forecast. The dashboard bundle already embeds `narrative`, but the dedicated trend
// hook is here for any page that wants the standalone series.
// =====================================================================================

// Narrative crowding-out score (0-100) — desired vs contested narrative dominance + trend.
export function useNarrativeScore(businessId: number | null) {
  return useApiQuery<NarrativeScore>(["narrative-score", businessId], base(businessId, "/narrative-score"));
}

// Before/after proof across the most recent action window (ready=false until enough history).
export function useImpactReport(businessId: number | null) {
  return useApiQuery<ImpactReport>(["impact-report", businessId], base(businessId, "/impact-report"));
}

// Predicted AI-score points still on the table if the remaining plan is finished.
export function useRoiForecast(businessId: number | null) {
  return useApiQuery<RoiForecast>(["roi-forecast", businessId], base(businessId, "/roi-forecast"));
}

// =====================================================================================
// AI-crawler readiness (SEO) — generated llms.txt + schema.org coverage verification.
// =====================================================================================
export function useLlmsTxt(businessId: number | null) {
  return useApiQuery<LlmsTxt>(["llms-txt", businessId], base(businessId, "/llms-txt"));
}
export function useSchemaVerify(businessId: number | null) {
  return useApiQuery<SchemaVerify>(["schema-verify", businessId], base(businessId, "/schema-verify"));
}
