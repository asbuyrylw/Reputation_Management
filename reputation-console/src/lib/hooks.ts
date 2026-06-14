"use client";

// TanStack Query hooks. Every per-business key includes businessId so the cache is
// isolated per tenant.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./api";
import { useAuth } from "./auth";
import type {
  AdminUser,
  AuditRun,
  Answer,
  AttributionRow,
  BeforeAfterPair,
  ContentDraft,
  Dashboard,
  DiscoveryTarget,
  GapModel,
  Incident,
  JobsResponse,
  LearnedLevers,
  Mention,
  ProductionBrief,
  ShareOfVoice,
  SiteAudit,
  WorkOrder,
} from "./types";

type Json = Record<string, unknown>;

function useApiQuery<T>(key: unknown[], path: string | null) {
  const { token } = useAuth();
  return useQuery({
    queryKey: key,
    queryFn: () => apiFetch<T>(path as string, { token }),
    enabled: !!token && !!path,
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
  const { token } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) =>
      apiFetch(pathFor(vars), { method: "POST", body: bodyFor(vars), token }),
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
export function useResumeIncident(businessId: number | null) {
  return useApiMutation<{ incidentId: number; approved: boolean; edited_response?: string }>(
    ({ incidentId }) => `/businesses/${businessId}/incidents/${incidentId}/resume`,
    ({ approved, edited_response }) => ({ approved, edited_response: edited_response ?? null }),
    [["incidents", businessId], ["dashboard", businessId]],
  );
}

// ---- jobs + admin ----
export function useJobs(businessId: number | null, poll = true) {
  const { token } = useAuth();
  return useQuery({
    queryKey: ["jobs", businessId],
    queryFn: () => apiFetch<JobsResponse>(`/businesses/${businessId}/jobs`, { token }),
    enabled: !!token && !!businessId,
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
  const { token } = useAuth();
  return useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<AdminUser[]>("/admin/users", { token }),
    enabled: !!token,
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
