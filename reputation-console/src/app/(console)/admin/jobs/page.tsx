"use client";

import { useBusiness } from "@/lib/business";
import { useJobs, useTriggerJob } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";

const JOBS = [
  // core pipeline
  { type: "audit", label: "Run audit" },
  { type: "site_crawl", label: "Crawl website" },
  { type: "gap_model", label: "Rebuild gap model" },
  { type: "plan", label: "Regenerate plan" },
  { type: "sync_plan", label: "Sync tasks" },
  { type: "generate_drafts", label: "Generate content drafts" },
  { type: "report", label: "Build report" },
  { type: "cycle", label: "Run full monthly cycle" },
  // monitoring + outreach + learning
  { type: "mentions_scan", label: "Scan mentions" },
  { type: "incident_scan", label: "Scan for incidents" },
  { type: "alert_check", label: "Check for alerts" },
  { type: "discovery", label: "Find outreach targets" },
  { type: "benchmark", label: "Benchmark vs competitors" },
  { type: "local_rank", label: "Track local Google rankings" },
  { type: "citation_analyze", label: "Refresh citation analytics" },
  { type: "learn", label: "Recompute what's working" },
  { type: "production_briefs", label: "Generate production briefs" },
];

function StepDot({ status }: { status: string }) {
  const c =
    status === "done" ? "bg-green-500" : status === "failed" ? "bg-red-500" : status === "pending" ? "bg-amber-400" : "bg-gray-300";
  return <span className={`inline-block h-2 w-2 rounded-full ${c}`} />;
}

function JobStatus({ status }: { status: string }) {
  const c: Record<string, string> = {
    complete: "text-green-700",
    failed: "text-red-700",
    running: "text-blue-700",
    queued: "text-amber-700",
  };
  return <span className={`text-xs font-medium ${c[status] || "text-gray-600"}`}>{status}</span>;
}

export default function JobsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useJobs(businessId);
  const trigger = useTriggerJob(businessId);

  if (isLoading || !data) return <Spinner />;
  const latest = data.pipeline_runs[0];

  return (
    <div>
      <PageHeader
        title="Run jobs"
        subtitle="Trigger an audit or the monthly cycle, then watch it progress. Long jobs run in the background — you can leave this page."
      />
      {canEdit && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-gray-700">Trigger</div>
          <div className="flex flex-wrap gap-2">
            {JOBS.map((j) => (
              <button
                key={j.type}
                disabled={trigger.isPending}
                onClick={() => trigger.mutate({ jobType: j.type })}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
              >
                {j.label}
              </button>
            ))}
          </div>
          {trigger.isError && <p className="mt-2 text-xs text-amber-700">Could not start — it may already be running.</p>}
        </Card>
      )}

      {latest && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-gray-700">
            Latest pipeline ({latest.kind}) — {latest.status}
          </div>
          <ol className="space-y-1 text-sm">
            {latest.steps.map((s) => (
              <li key={s.step_key} className="flex items-center gap-2">
                <StepDot status={s.status} />
                <span className="text-gray-700">{s.step_key.replace(/_/g, " ")}</span>
                {s.error && <span className="text-xs text-red-600">{s.error}</span>}
              </li>
            ))}
          </ol>
        </Card>
      )}

      <Card className="overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2">Job</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">Finished</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {data.jobs.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-3 text-gray-400">
                  No jobs yet.
                </td>
              </tr>
            ) : (
              data.jobs.map((j) => (
                <tr key={j.id}>
                  <td className="px-4 py-2">{j.job_type}</td>
                  <td className="px-4 py-2">
                    <JobStatus status={j.status} />
                    {j.error && <span className="ml-2 text-xs text-red-600">{j.error.slice(0, 80)}</span>}
                  </td>
                  <td className="px-4 py-2">{j.started_at ? new Date(j.started_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-2">{j.finished_at ? new Date(j.finished_at).toLocaleString() : "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
