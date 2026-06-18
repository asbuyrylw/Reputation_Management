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
  AttributionRow,
  BeforeAfterPair,
  CompareResult,
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

export function useApproveDraft(businessId: number | null) {
  return useApiMutation<{ draftId: number }>(
    ({ draftId }) => `/businesses/${businessId}/content-drafts/${draftId}/approve`,
    () => undefined,
    [["content-drafts", businessId], ["work-orders", businessId], ["dashboard", businessId]],
  );
}

export function useRejectDraft(businessId: number | null) {
  return useApiMutation<{ draftId: number; notes?: string }>(
    ({ draftId }) => `/businesses/${businessId}/content-drafts/${draftId}/reject`,
    ({ notes }) => ({ notes: notes ?? null }),
    [["content-drafts", businessId]],
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
    refetchInterval: poll ? 3000 : false,
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
