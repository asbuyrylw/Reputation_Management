"use client";

import { useBusiness } from "@/lib/business";
import { useLearnedLevers } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, ToneBar } from "@/components/primitives";

const LEVER_LABELS: Record<string, string> = {
  content_writing: "Publishing website content",
  schema_markup: "Adding website code (schema)",
  review_generation: "Getting genuine reviews",
  press_outreach: "PR / press coverage",
  link_building: "Earning links & citations",
  social_posting: "Social media posts",
};
const leverLabel = (k: string) => LEVER_LABELS[k] ?? k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function LeversPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useLearnedLevers(businessId);

  if (isLoading || !data) return <Spinner />;
  const levers = Object.entries(data.levers || {}).sort((a, b) => b[1] - a[1]);
  const max = levers.length ? Math.max(...levers.map(([, v]) => Math.abs(v))) || 1 : 1;

  return (
    <div>
      <PageHeader
        title="What's actually working"
        subtitle="Which of your actions are moving your score the most — learned from your own results over time."
      />
      {levers.length === 0 ? (
        <EmptyState
          title="We're still learning what works for you"
          why="To rank your tactics by real impact, we compare your score across audits and see which actions moved it."
          produces="After 2+ audits with work completed in between, this page ranks your tactics from 'do more of this' to 'deprioritize'."
          timing={
            data.baseline.monthly_gain == null
              ? "Needs another audit with work shipped in between."
              : `Early signal captured (${data.baseline.confidence ?? "low"} confidence) — it sharpens with each audit.`
          }
        />
      ) : (
        <Card>
          <div className="mb-3 text-sm text-slate-600">
            Each bar shows how much that action moves your score per effort, relative to the others.
          </div>
          <div className="space-y-3">
            {levers.map(([k, v], i) => {
              const tier = i < Math.ceil(levers.length / 3) ? "Do more" : i < Math.ceil((2 * levers.length) / 3) ? "Keep" : "Deprioritize";
              return (
                <div key={k}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-800">{leverLabel(k)}</span>
                    <span className={`text-xs ${tier === "Do more" ? "text-emerald-700" : tier === "Keep" ? "text-slate-500" : "text-slate-400"}`}>{tier}</span>
                  </div>
                  <ToneBar pct={(Math.abs(v) / max) * 100} tone={v >= 0 ? "good" : "bad"} />
                </div>
              );
            })}
          </div>
          {/* Predicted vs measured — the plan's estimate calibrating to your real results */}
          {data.predicted_levers && (
            <div className="mt-4 border-t border-slate-100 pt-3">
              <div className="text-sm font-semibold text-slate-900">Predicted vs. measured</div>
              <p className="mb-2 text-xs text-slate-500">
                What the plan estimated each action would add, vs. what we&apos;ve actually measured from your
                results. This is how the per-task “predicted points” calibrate over time.
              </p>
              <table className="w-full text-sm">
                <thead className="text-left text-[11px] uppercase tracking-wide text-slate-400">
                  <tr><th className="py-1">Action</th><th className="py-1 text-right">Predicted /unit</th><th className="py-1 text-right">Measured /unit</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {levers.map(([k, v]) => {
                    const pred = data.predicted_levers?.[k];
                    const meas = v * 100;
                    return (
                      <tr key={k}>
                        <td className="py-1">{leverLabel(k)}</td>
                        <td className="py-1 text-right text-slate-500">{pred != null ? `+${pred.toFixed(2)} pts` : "—"}</td>
                        <td className={`py-1 text-right font-medium ${pred != null && meas >= pred ? "text-emerald-700" : "text-amber-700"}`}>+{meas.toFixed(2)} pts</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-medium text-slate-400 hover:text-slate-700">▸ Show the raw numbers</summary>
            <table className="mt-2 w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {levers.map(([k, v]) => (
                  <tr key={k}><td className="py-1">{leverLabel(k)}</td><td className="py-1 text-right font-medium">{v.toFixed(4)}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </Card>
      )}
    </div>
  );
}
