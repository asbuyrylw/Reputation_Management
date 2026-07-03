"use client";

import { useEffect, useState } from "react";
import { useJobs } from "@/lib/hooks";
import { jobMeta } from "@/lib/jobLabels";
import type { ApiJob } from "@/lib/types";

// Label + typical duration come from the shared jobLabels map so the banner, the Run-jobs grid,
// and the Automation scheduler all speak the same language. A job that overruns shows
// "finishing up…" instead of a stale ETA.
const meta = (jt: string) => jobMeta(jt);

function fmtDur(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return r ? `${m}m ${r}s` : `${m}m`;
}

// A live banner of in-flight jobs with per-job progress + ETA. Renders nothing when idle.
// Reused on the Dashboard and the Audits page so the owner always sees work in progress.
export function JobProgressBanner({ businessId, className = "" }: { businessId: number | null; className?: string }) {
  const { data } = useJobs(businessId);
  // `now` lives in state (not Date.now() during render, which is impure) and is advanced by a
  // 1s ticker while jobs are active, so the ETA countdown moves smoothly between 3s polls.
  const [now, setNow] = useState(0);
  const active = (data?.jobs ?? []).filter((j) => j.status === "running" || j.status === "queued");
  useEffect(() => {
    if (active.length === 0) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active.length]);

  if (active.length === 0) return null;
  return (
    <div className={`overflow-hidden rounded-2xl border border-indigo-200 bg-linear-to-br from-indigo-50 to-white p-4 shadow-sm ${className}`}>
      <div className="flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-indigo-500" />
        </span>
        <h3 className="text-sm font-bold tracking-tight text-slate-900">
          {active.length} job{active.length === 1 ? "" : "s"} running
        </h3>
        <span className="text-xs text-slate-500">— your dashboard updates as each finishes</span>
      </div>
      <ul className="mt-3 space-y-2.5">
        {active.map((j) => (
          <JobRow key={j.id} job={j} now={now} />
        ))}
      </ul>
    </div>
  );
}

function JobRow({ job, now }: { job: ApiJob; now: number }) {
  const m = meta(job.job_type);
  const started = job.started_at ? new Date(job.started_at).getTime() : null;
  const queued = job.status === "queued" || !started;
  const elapsed = started ? Math.max(0, (now - started) / 1000) : 0;
  const remaining = Math.max(0, m.secs - elapsed);
  const pct = queued ? 30 : Math.min(96, Math.round((elapsed / m.secs) * 100)); // never 100 until done
  return (
    <li>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="truncate font-semibold text-slate-800">{m.label}</span>
        <span className="shrink-0 text-xs font-medium text-slate-500">
          {queued ? "queued…" : remaining > 1 ? `~${fmtDur(remaining)} left` : "finishing up…"}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-indigo-100">
        <div
          className={`h-full rounded-full bg-linear-to-r from-indigo-400 to-indigo-600 transition-all duration-1000 ${queued ? "animate-pulse" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </li>
  );
}
