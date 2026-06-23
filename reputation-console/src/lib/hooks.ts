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
  CostBreakdown,
  AttributionRow,
  BeforeAfterPair,
  CompareResult,
  CustomPrompt,
  LocalRankings,
  OnboardingStatus,
  PromptResults,
  Report,
  VisibilityTrend,
  Competitor,
  ContentDraft,
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
  WorkOrder,
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

// ---- content / work ----
export function useWorkOrders(businessId: number | null) {
  return useApiQuery<WorkOrder[]>(["work-orders", businessId], businessId ? `/businesses/${businessId}/work-orders` : null);
}

export function useContentDrafts(businessId: number | null) {
  return useApiQuery<ContentDraft[]>(["content-drafts", businessId], businessId ? `/businesses/${businessId}/content-drafts` : null);
}

export function useProductionBriefs(businessId: number | null) {
  return useApiQuery<ProductionBrief[]>(["production-briefs", businessId], businessId ? `/businesses/${businessId}/production-briefs` : null);
}

export function useDiscoveryTargets(businessId: number | null) {
  return useApiQuery<DiscoveryTarget[]>(["discovery-targets", businessId], businessId ? `/businesses/${businessId}/discovery-targets` : null);
}

// ---- mutations ----
function useApiMutation<TVars>(
  pathFor: (vars: TVars) => string,
  bodyFor: (vars: TVars) => unknown,
  invalidate: unknown[][],
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) =>
      apiFetch(pathFor(vars), { method: "POST", body: bodyFor(vars) }),
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
  return useApiMutation<{ draftId: number }>(
    ({ draftId }) => `/businesses/${businessId}/content-drafts/${draftId}/approve`,
    () => undefined,
    [["content-drafts", businessId], ["work-orders", businessId], ["dashboard", businessId]],
  );
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
  return useApiMutation<{ woId: number; status: string; assignee?: string; notes?: string }>(
    ({ woId }) => `/businesses/${businessId}/work-orders/${woId}/status`,
    ({ status, assignee, notes }) => ({ status, assignee: assignee ?? null, notes: notes ?? null }),
    [["work-orders", businessId], ["dashboard", businessId]],
  );
}

// ---- rankings / timeline / sustain ----
const base = (businessId: number | null, suffix: string) =>
  businessId ? `/businesses/${businessId}${suffix}` : null;

export function useShareOfVoice(businessId: number | null) {
  return useApiQuery<ShareOfVoice>(["sov", businessId], base(businessId, "/citations/share-of-voice"));
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
export function useSetTargetStatus(businessId: number | null) {
  return useApiMutation<{ targetId: number; status: string }>(
    ({ targetId }) => `/businesses/${businessId}/discovery-targets/${targetId}/status`,
    ({ status }) => ({ status }),
    [["discovery-targets", businessId]],
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
  return useApiMutation<{ name: string; domain?: string; goal?: string; contested_terms?: string; geo?: string; services?: string }>(
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
