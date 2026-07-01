"use client";

// Results / Proof — the "did the work pay off?" surface. Two parts:
//  1. Proof of impact: a before/after delta table across the most recent action window
//     (or the reason it's not ready yet).
//  2. ROI forecast: "+X AI-score points if you finish the plan", confidence, horizon, and
//     the top capabilities still on the table.

import Link from "next/link";
import { useImpactReport, useRoiForecast } from "@/lib/hooks";
import type { ImpactMetricDelta, ImpactReport, RoiForecast } from "@/lib/types";
import { Card, CardSkeleton } from "./ui";

// The task board doesn't yet read an area filter from the query string, so every
// ROI row links to the board itself (where the work for that area lives).
const WORK_ORDERS_HREF = "/content/work-orders";

// One metric's before -> after with a tone-colored delta. `goodDirection` flips the tone
// for metrics where lower is better (contested%).
function MetricRow({
  label,
  metric,
  asPct = false,
  goodDirection = "up",
}: {
  label: string;
  metric: ImpactMetricDelta;
  asPct?: boolean;
  goodDirection?: "up" | "down";
}) {
  const fmt = (v: number | null) => {
    if (v == null) return "—";
    return asPct ? `${Math.round(v * 100)}%` : v.toFixed(1);
  };
  const delta = metric.delta;
  let tone = "text-slate-400";
  let arrow = "";
  if (delta != null && Math.abs(delta) > 1e-9) {
    const up = delta > 0;
    const good = goodDirection === "up" ? up : !up;
    tone = good ? "text-emerald-600" : "text-rose-600";
    arrow = up ? "▲" : "▼";
  }
  const deltaShown =
    delta == null
      ? "—"
      : asPct
      ? `${delta > 0 ? "+" : ""}${Math.round(delta * 100)} pts`
      : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}`;
  return (
    <tr className="border-t border-slate-100">
      <td className="py-1.5 pr-3 text-sm text-slate-700">{label}</td>
      <td className="py-1.5 px-2 text-right text-sm tabular-nums text-slate-500">{fmt(metric.before)}</td>
      <td className="py-1.5 px-2 text-right text-sm tabular-nums text-slate-900">{fmt(metric.after)}</td>
      <td className={`py-1.5 pl-2 text-right text-sm font-semibold tabular-nums ${tone}`}>
        {arrow} {deltaShown}
      </td>
    </tr>
  );
}

function ImpactPanel({ report }: { report: ImpactReport | undefined }) {
  if (!report) return null;
  if (!report.ready) {
    return (
      <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-sm text-slate-500 ring-1 ring-inset ring-slate-200">
        {report.reason || "Not enough audit history yet to prove impact. This appears after a second audit with work logged in between."}
      </div>
    );
  }
  const m = report.metrics;
  const win = report.window;
  return (
    <div>
      {report.summary && <p className="text-sm leading-relaxed text-slate-700">{report.summary}</p>}
      {(report.actions?.total ?? 0) > 0 && (
        <p className="mt-1 text-xs text-slate-500">
          {report.actions!.total} action{report.actions!.total === 1 ? "" : "s"} completed
          {win ? ` (${win.from_date} → ${win.to_date})` : ""}.
        </p>
      )}
      {m && (
        <table className="mt-3 w-full">
          <thead>
            <tr className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              <th className="pb-1 text-left font-semibold">Metric</th>
              <th className="pb-1 px-2 text-right font-semibold">Before</th>
              <th className="pb-1 px-2 text-right font-semibold">After</th>
              <th className="pb-1 pl-2 text-right font-semibold">Change</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow label="Narrative dominance" metric={m.narrative_score} />
            <MetricRow label="Owned citation share" metric={m.owned_citation_share_pct} asPct />
            <MetricRow label="Contested narrative" metric={m.contested_pct} asPct goodDirection="down" />
            <MetricRow label="Goal alignment" metric={m.avg_goal_alignment} />
          </tbody>
        </table>
      )}
    </div>
  );
}

const CAP_LABELS: Record<string, string> = {
  content: "Content",
  publish: "Publishing",
  outreach: "Outreach",
  social: "Social",
  local: "Local SEO",
  reviews: "Reviews",
  website: "Website",
  tracking: "Tracking",
};
const capLabel = (c: string) => CAP_LABELS[c] ?? c.charAt(0).toUpperCase() + c.slice(1).replace(/_/g, " ");

function RoiPanel({ forecast, currentScore }: { forecast: RoiForecast | undefined; currentScore?: number | null }) {
  if (!forecast) return null;
  const top = [...forecast.by_capability].sort((a, b) => b.predicted_points - a.predicted_points).slice(0, 5);
  // Projected score is bounded — you can't gain past 100. The backend caps predicted_points at the
  // remaining headroom; we clamp here too so the headline figure is always sane (never "+114").
  const cur = currentScore ?? null;
  const rawGain = Math.max(0, Math.round(forecast.predicted_points));
  const gain = cur != null ? Math.min(rawGain, Math.max(0, 100 - cur)) : rawGain;
  const projected = cur != null ? Math.min(100, cur + gain) : null;
  return (
    <div className="flex h-full flex-col">
      <p className="text-sm leading-relaxed text-slate-600">
        If you finish the open plan, we project your AI Reputation Score
        {cur != null ? (
          <> moves from <span className="font-semibold text-slate-900">{cur}</span> to about <span className="font-semibold text-indigo-600">{projected}/100</span></>
        ) : (
          <> rises by about <span className="font-semibold text-indigo-600">{gain} points</span></>
        )}
        {forecast.horizon_weeks != null ? <> over ~{forecast.horizon_weeks} weeks</> : null}.
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {forecast.open_tasks} open task{forecast.open_tasks === 1 ? "" : "s"} · confidence:{" "}
        <span className="font-medium text-slate-600">{forecast.confidence}</span> · a learned estimate, not a guarantee.
      </p>
      {top.length > 0 && (
        <table className="mt-3 w-full">
          <thead>
            <tr className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              <th className="pb-1 text-left font-semibold">Area</th>
              <th className="pb-1 px-2 text-right font-semibold">Open tasks</th>
              <th className="pb-1 pl-2 text-right font-semibold">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {top.map((r) => (
              <tr key={r.capability} className="border-t border-slate-100">
                <td className="py-1.5 pr-3 text-sm" title={r.basis || undefined}>
                  <Link href={WORK_ORDERS_HREF} className="font-medium text-indigo-600 hover:text-indigo-700 hover:underline">
                    {capLabel(r.capability)} →
                  </Link>
                </td>
                <td className="py-1.5 px-2 text-right text-sm tabular-nums text-slate-500">{r.open_tasks}</td>
                <td className="py-1.5 pl-2 text-right text-xs text-slate-500">{r.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {/* the highlighted projected figure, moved to the bottom of the column */}
      <div className="mt-auto pt-4">
        <div className="flex items-baseline gap-2 rounded-xl bg-indigo-50/70 px-4 py-3 ring-1 ring-inset ring-indigo-100">
          <span className="text-3xl font-bold leading-none text-indigo-600">{projected != null ? projected : `+${gain}`}</span>
          <span className="text-sm text-slate-600">{projected != null ? "projected score / 100 if you finish the plan" : "projected points if you finish the plan"}</span>
        </div>
      </div>
    </div>
  );
}

export function ResultsProofCard({ businessId, currentScore }: { businessId: number | null; currentScore?: number | null }) {
  const { data: report, isLoading: reportLoading, error: reportError } = useImpactReport(businessId);
  const { data: forecast, isLoading: forecastLoading, error: forecastError } = useRoiForecast(businessId);

  // Loading skeleton while either query is still in flight (and nothing has arrived).
  if ((reportLoading || forecastLoading) && !report && !forecast) {
    return <CardSkeleton lines={4} />;
  }

  // Graceful error line instead of silently rendering nothing.
  if (reportError && forecastError && !report && !forecast) {
    return (
      <Card accent="good">
        <h3 className="text-base font-semibold tracking-tight text-slate-900">Results &amp; Proof</h3>
        <p className="mt-2 text-sm text-slate-500">We couldn&apos;t load your results just now. Refresh in a moment.</p>
      </Card>
    );
  }

  // Pre-first-audit / no-data-yet placeholder — never render nothing.
  if (!report && !forecast) {
    return (
      <Card accent="good">
        <h3 className="text-base font-semibold tracking-tight text-slate-900">Results &amp; Proof</h3>
        <p className="mt-2 text-sm text-slate-500">
          Your before/after impact and ROI forecast appear here once an audit has run and work is logged.
        </p>
      </Card>
    );
  }

  return (
    <Card accent="good">
      <h3 className="text-base font-semibold tracking-tight text-slate-900">Results &amp; Proof</h3>
      <p className="mt-0.5 text-xs text-slate-500">
        What the work has done so far — and what completing the plan is forecast to add.
      </p>
      <div className="mt-4 grid grid-cols-1 items-stretch gap-5 lg:grid-cols-2">
        <div className="flex flex-col">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Proof of Impact</div>
          <ImpactPanel report={report} />
        </div>
        <div className="flex flex-col lg:border-l lg:border-slate-100 lg:pl-5">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">ROI Forecast</div>
          <RoiPanel forecast={forecast} currentScore={currentScore} />
        </div>
      </div>
    </Card>
  );
}
