"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useJobs, useRunEverything } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { RunJobButton } from "@/components/RunJobButton";
import { StatusBadge } from "@/components/content/StatusBadge";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";
import { EmptyState } from "@/components/primitives";
import { JOB_LABELS } from "@/lib/jobLabels";
import type { ApiJob } from "@/lib/types";

// The headline jobs an owner runs from Settings (the design's run cards). Deeper/internal jobs
// stay on the admin Jobs page; this surfaces the four that matter to an owner.
const FEATURED = ["audit", "site_crawl", "local_rank", "report"] as const;

const fmtWhen = (d?: string | null) => (d ? new Date(d).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—");
function duration(a: ApiJob): string {
  if (!a.started_at || !a.finished_at) return "—";
  const s = Math.max(0, Math.round((new Date(a.finished_at).getTime() - new Date(a.started_at).getTime()) / 1000));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}
const jobLabel = (t: string) => JOB_LABELS[t]?.label ?? t.replace(/_/g, " ");

export default function RunsPage() {
  const { businessId, businesses, loading, canEdit } = useBusiness();
  const { data, isLoading } = useJobs(businessId);
  const runAll = useRunEverything(businessId);
  const [confirmAll, setConfirmAll] = useState(false);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Settings · Runs & jobs" title="Run audits & reports" />
        <EmptyState title="No business yet" why="Set up a business to run audits, crawls, and reports." cta={{ label: "Set up a business", href: "/onboarding" }} />
      </div>
    );
  }

  const jobs = data?.jobs ?? [];
  const running = jobs.filter((j) => j.status === "running" || j.status === "queued");
  const past = jobs.filter((j) => j.status !== "running" && j.status !== "queued").slice(0, 25);

  return (
    <div>
      <PageHeader eyebrow="Settings · Runs & jobs" title="Run audits & reports" subtitle="Kick off the jobs that power the console — AI audits, site crawls, rank checks and reports — and watch their progress." />

      {/* run cards */}
      {canEdit ? (
        <>
          <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURED.map((key) => {
              const meta = JOB_LABELS[key];
              if (!meta) return null;
              return (
                <Card key={key} className="flex flex-col">
                  <div className="text-[14.5px] font-semibold text-ink">{meta.label}</div>
                  <div className="mb-3 mt-0.5 text-[12.5px] text-ink-4">{meta.hint}</div>
                  <div className="mt-auto">
                    <RunJobButton businessId={businessId} jobType={key} label="Run now" />
                  </div>
                </Card>
              );
            })}
          </div>

          {/* run everything */}
          <Card className="mb-6 border-indigo-100 bg-indigo-050">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-[240px] flex-1">
                <div className="text-[14px] font-semibold text-ink">Run everything</div>
                <div className="text-[12.5px] text-ink-3">Refresh every section at once — audit, crawl, gaps, plan, citations, competitors, rankings, prompts, mentions, outreach, content &amp; the report.</div>
              </div>
              <button onClick={() => setConfirmAll(true)} disabled={runAll.isPending}
                className="rounded-[10px] bg-indigo px-4 py-2 text-[13.5px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-50">
                {runAll.isPending ? "Starting…" : "▶ Run everything"}
              </button>
            </div>
            {confirmAll && !runAll.isPending && !runAll.isSuccess && (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-indigo-100 pt-3 text-[13px] text-ink-2">
                This runs the full pipeline (uses API credits).
                <button onClick={() => { runAll.mutate(); }} className="rounded-md bg-indigo px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-strong">Yes, run everything</button>
                <button onClick={() => setConfirmAll(false)} className="rounded-md border border-line-2 px-3 py-1 text-xs font-semibold text-ink-2 hover:bg-line/60">Cancel</button>
              </div>
            )}
            {runAll.isError && <div className="mt-2 text-xs text-alert">{(runAll.error as Error)?.message ?? "Couldn't start the run."}</div>}
            {runAll.isSuccess && <div className="mt-2 text-xs text-good">Pipeline queued — watch it below.</div>}
          </Card>
        </>
      ) : (
        <Card className="mb-6 text-[13px] text-ink-3">Only editors can run jobs. Ask an admin to run an audit or report.</Card>
      )}

      {/* running now */}
      {running.length > 0 && (
        <>
          <SecHead title="Running now" />
          <div className="mb-6 space-y-2">
            {running.map((j) => (
              <Card key={j.id} className="flex items-center gap-3">
                <span className="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-indigo" />
                <div className="min-w-0 flex-1">
                  <div className="text-[14px] font-semibold text-ink">{jobLabel(j.job_type)}</div>
                  <div className="font-mono text-[11px] text-ink-4">started {fmtWhen(j.started_at || j.created_at)}{JOB_LABELS[j.job_type]?.secs ? ` · ~${Math.round((JOB_LABELS[j.job_type]!.secs ?? 0) / 60) || 1}m` : ""}</div>
                </div>
                <StatusBadge status={j.status} />
              </Card>
            ))}
          </div>
        </>
      )}

      {/* past runs */}
      <SecHead title="Past runs" note="recent job history" />
      {isLoading ? (
        <Spinner />
      ) : past.length === 0 ? (
        <Card className="text-[13px] text-ink-4">No jobs have run yet.</Card>
      ) : (
        <TableContainer>
          <thead>
            <tr><Th className="w-[34%]">Job</Th><Th>When</Th><Th>Duration</Th><Th>Status</Th></tr>
          </thead>
          <tbody>
            {past.map((j) => (
              <tr key={j.id}>
                <Td><span className="font-semibold text-ink">{jobLabel(j.job_type)}</span>{j.error ? <div className="text-[11px] text-alert">{j.error.slice(0, 80)}</div> : null}</Td>
                <Td className="whitespace-nowrap font-mono text-[12px] text-ink-3">{fmtWhen(j.finished_at || j.created_at)}</Td>
                <Td className="font-mono text-[12px] text-ink-3">{duration(j)}</Td>
                <Td><StatusBadge status={j.status} /></Td>
              </tr>
            ))}
          </tbody>
        </TableContainer>
      )}
    </div>
  );
}
