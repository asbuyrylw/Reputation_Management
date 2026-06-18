"use client";

import { useBusiness } from "@/lib/business";
import { useSchedules, useUpsertSchedule, useDeleteSchedule } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";

const SCHEDULABLE = [
  { job: "cycle", label: "Full reputation cycle", desc: "Re-audit all AI engines, rebuild the plan, and refresh everything.", defaultHours: 720 },
  { job: "mentions_scan", label: "Mention scan", desc: "Sweep the web for new mentions and draft replies.", defaultHours: 24 },
  { job: "incident_scan", label: "Incident triage", desc: "Flag new serious negative mentions for a response.", defaultHours: 24 },
  { job: "alert_check", label: "Alert check", desc: "Notify you of score drops, new negatives, and items needing attention.", defaultHours: 24 },
  { job: "citation_analyze", label: "Citation refresh", desc: "Recompute which sources AI is quoting about you.", defaultHours: 168 },
];
const INTERVALS = [
  { h: 24, l: "Daily" },
  { h: 72, l: "Every 3 days" },
  { h: 168, l: "Weekly" },
  { h: 336, l: "Every 2 weeks" },
  { h: 720, l: "Monthly" },
];

const fmtNext = (d: string | null) => (d ? new Date(d).toLocaleString() : "—");

export default function AutomationPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useSchedules(businessId);
  const upsert = useUpsertSchedule(businessId);
  const del = useDeleteSchedule(businessId);

  if (isLoading || !data) return <Spinner />;
  const byJob: Record<string, (typeof data)[number]> = Object.fromEntries(data.map((s) => [s.job_type, s]));

  return (
    <div>
      <PageHeader
        title="Automation"
        subtitle="Set what runs on its own and how often — so your monitoring is continuous, not something someone has to remember to click."
      />
      <div className="space-y-3">
        {SCHEDULABLE.map(({ job, label, desc, defaultHours }) => {
          const s = byJob[job];
          const on = !!s && s.enabled;
          return (
            <Card key={job}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-900">{label}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${on ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-500"}`}>
                      {on ? "On" : "Off"}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">{desc}</div>
                  {on && <div className="mt-0.5 text-xs text-gray-400">Next run: {fmtNext(s.next_run_at)}</div>}
                </div>
                {canEdit && (
                  <div className="flex items-center gap-2">
                    <select
                      value={s?.interval_hours ?? defaultHours}
                      onChange={(e) => upsert.mutate({ job_type: job, interval_hours: Number(e.target.value), enabled: true })}
                      className="rounded border border-gray-200 px-2 py-1 text-sm"
                    >
                      {INTERVALS.map((i) => <option key={i.h} value={i.h}>{i.l}</option>)}
                    </select>
                    {on ? (
                      <button onClick={() => s && del.mutate(s.id)} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100">
                        Turn off
                      </button>
                    ) : (
                      <button
                        onClick={() => upsert.mutate({ job_type: job, interval_hours: defaultHours, enabled: true })}
                        className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700"
                      >
                        Turn on
                      </button>
                    )}
                  </div>
                )}
              </div>
            </Card>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-gray-400">
        Scheduled jobs run in the background. You can also run any job on demand from Admin → Run jobs.
      </p>
    </div>
  );
}
