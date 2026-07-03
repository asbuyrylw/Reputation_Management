"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAuth } from "@/lib/auth";
import { useJobs, useRunEverything, usePlatformQuotaUsage } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { RunJobButton } from "@/components/RunJobButton";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { JOB_LABELS, JOB_GROUP_ORDER, jobLabel, jobMeta } from "@/lib/jobLabels";
import type { QuotaLine } from "@/lib/types";

// "Platform quota usage" — the shared publishing-provider accounts' usage vs. their caps,
// across all tenants. Super-admin / admin only. Shows "unlimited" when a provider has no cap.
function QuotaUsageCard({ enabled }: { enabled: boolean }) {
  const { data } = usePlatformQuotaUsage(enabled);
  if (!enabled || !data) return null;
  const providers: { key: string; label: string; line: QuotaLine }[] = [
    { key: "ayrshare", label: "Ayrshare (social)", line: data.ayrshare },
    { key: "x", label: "X / Twitter", line: data.x },
    { key: "gbp", label: "Google Business Profile", line: data.gbp },
  ];
  return (
    <Card className="mb-4">
      <div className="text-sm font-semibold text-slate-900">Platform quota usage</div>
      <p className="mt-0.5 text-xs text-slate-500">Shared publishing-provider accounts across all tenants. &ldquo;Unlimited&rdquo; means the provider has no cap.</p>
      <ul className="mt-3 space-y-2">
        {providers.map(({ key, label, line }) => {
          const pct = line.unlimited || line.cap == null || !line.cap ? null : Math.min(100, Math.round(((line.used ?? 0) / line.cap) * 100));
          return (
            <li key={key} className="text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-700">{label}</span>
                <span className={`text-xs font-semibold ${line.within ? "text-slate-500" : "text-rose-600"}`}>
                  {line.unlimited ? "Unlimited" : line.cap == null ? `${line.used ?? 0} used` : `${line.used ?? 0} / ${line.cap}`}
                </span>
              </div>
              {pct != null && (
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${line.within ? "bg-indigo-500" : "bg-rose-500"}`} style={{ width: `${pct}%` }} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// Trigger buttons grouped the way the sidebar is, so "what runs" lines up with "where the
// result shows up." Derived from the shared jobLabels map (the single source of truth).
const JOB_GROUPS = JOB_GROUP_ORDER.map((group) => ({
  group,
  jobs: Object.values(JOB_LABELS).filter((m) => m.navGroup === group),
})).filter((g) => g.jobs.length > 0);

function StepDot({ status }: { status: string }) {
  const c =
    status === "done" ? "bg-emerald-500" : status === "failed" ? "bg-rose-500" : status === "pending" ? "bg-amber-400" : "bg-slate-300";
  return <span className={`inline-block h-2 w-2 rounded-full ${c}`} />;
}

function JobStatus({ status }: { status: string }) {
  const c: Record<string, string> = {
    complete: "text-emerald-700",
    failed: "text-rose-700",
    running: "text-indigo-700",
    queued: "text-amber-700",
  };
  return <span className={`text-xs font-medium ${c[status] || "text-slate-600"}`}>{status}</span>;
}

// Turn a job's structured result into a one-line human note, so a "complete" job that
// actually skipped or produced nothing tells the owner why instead of looking successful.
function resultNote(result: Record<string, unknown> | null): string | null {
  if (!result || typeof result !== "object") return null;
  const r = result as Record<string, unknown>;
  if (r.budget_exhausted) return `budget reached — $${r.spent} of $${r.cap} this month (resets next month)`;
  if (r.skipped) return `skipped — ${(r.reason as string) ?? "nothing to do"}`;
  if (typeof r.rows === "number") {
    const q = typeof r.queries === "number" ? ` across ${r.queries} quer${r.queries === 1 ? "y" : "ies"}` : "";
    return `recorded ${r.rows} row${r.rows === 1 ? "" : "s"}${q}`;
  }
  if (Array.isArray(r.keywords)) return `proposed ${r.keywords.length} keyword${r.keywords.length === 1 ? "" : "s"}`;
  if (typeof r.added === "number") return `added ${r.added}`;
  return null;
}

export default function JobsPage() {
  const { businessId, canEdit } = useBusiness();
  const { user } = useAuth();
  const isPlatformAdmin = !!user?.is_super_admin || user?.role === "admin";
  const { data, isLoading } = useJobs(businessId);
  const runAll = useRunEverything(businessId);
  const [confirmAll, setConfirmAll] = useState(false);

  if (isLoading || !data) return <Spinner />;
  const latest = data.pipeline_runs[0];

  return (
    <div>
      <PageHeader
        title="Run jobs"
        subtitle="Trigger an audit or the monthly cycle, then watch it progress. Long jobs run in the background — you can leave this page. Some jobs auto-chain (e.g. regenerating the plan also syncs tasks and content to produce)."
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />

      <QuotaUsageCard enabled={isPlatformAdmin} />

      {canEdit && (
        <Card className="mb-4 border-indigo-100 bg-indigo-50/40">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-900">Run everything</div>
              <div className="text-xs text-slate-600">
                Refresh every section at once — audit, site crawl, gap analysis, plan, AI citations,
                competitor benchmark, local rankings, prompts, mentions, outreach, content &amp; the report.
              </div>
            </div>
            <button
              onClick={() => setConfirmAll(true)}
              disabled={runAll.isPending}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {runAll.isPending ? "Starting…" : "▶ Run everything"}
            </button>
          </div>
          {runAll.isError && (
            <div className="mt-2 text-xs text-rose-600">{(runAll.error as Error)?.message ?? "Couldn't start the run."}</div>
          )}
          {runAll.isSuccess && (
            <div className="mt-2 text-xs text-emerald-700">Pipeline queued — watch it progress above.</div>
          )}
        </Card>
      )}

      {canEdit && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-slate-700">Trigger a job</div>
          <div className="space-y-3">
            {JOB_GROUPS.map(({ group, jobs }) => (
              <div key={group}>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{group}</div>
                <div className="flex flex-wrap gap-2">
                  {jobs.map((j) => (
                    <RunJobButton
                      key={j.type}
                      businessId={businessId}
                      jobType={j.type}
                      label={j.label}
                      title={j.hint}
                      variant="secondary"
                      className={j.internal ? "opacity-70" : ""}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {latest && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-slate-700">
            Latest pipeline ({latest.kind}) — {latest.status}
          </div>
          <ol className="space-y-1 text-sm">
            {latest.steps.map((s) => (
              <li key={s.step_key} className="flex items-center gap-2">
                <StepDot status={s.status} />
                <span className="text-slate-700">{s.step_key.replace(/_/g, " ")}</span>
                {s.error && <span className="text-xs text-rose-600">{s.error}</span>}
              </li>
            ))}
          </ol>
        </Card>
      )}

      <Card className="overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Job</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">Finished</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.jobs.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-3 text-slate-400">
                  No jobs yet.
                </td>
              </tr>
            ) : (
              data.jobs.map((j) => (
                <tr key={j.id}>
                  <td className="px-4 py-2" title={jobMeta(j.job_type).hint}>{jobLabel(j.job_type)}</td>
                  <td className="px-4 py-2">
                    <JobStatus status={j.status} />
                    {j.error && <span className="ml-2 text-xs text-rose-600">{j.error.slice(0, 80)}</span>}
                    {!j.error && resultNote(j.result) && (
                      <span className="ml-2 text-xs text-slate-500">· {resultNote(j.result)}</span>
                    )}
                  </td>
                  <td className="px-4 py-2">{j.started_at ? new Date(j.started_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-2">{j.finished_at ? new Date(j.finished_at).toLocaleString() : "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>

      {confirmAll && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setConfirmAll(false)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold text-slate-900">Run the entire pipeline?</h3>
            <p className="mt-2 text-sm text-slate-600">
              This runs <span className="font-semibold">audit → site crawl → gap analysis → plan → sync → AI citations →
              competitor benchmark → local rankings → prompts → mentions → outreach → content briefs → report</span>,
              in order.
            </p>
            <p className="mt-2 text-sm text-slate-600">
              It costs roughly <span className="font-semibold">$8–12</span> in AI &amp; search usage and takes about
              <span className="font-semibold"> 30–50 minutes</span>. You can only start it once a day.
            </p>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button onClick={() => setConfirmAll(false)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
                Cancel
              </button>
              <button
                onClick={() => runAll.mutate(undefined, { onSettled: () => setConfirmAll(false) })}
                disabled={runAll.isPending}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {runAll.isPending ? "Starting…" : "Yes, run everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
