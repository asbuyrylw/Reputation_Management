"use client";

import { useBusiness } from "@/lib/business";
import { useLearnedLevers } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, ToneBar } from "@/components/primitives";
import { SecHead } from "@/components/DashboardV2";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";

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
          <div className="mb-3 text-sm text-ink-3">
            Each bar shows how much that action moves your score per effort, relative to the others.
          </div>
          <div className="space-y-3">
            {levers.map(([k, v], i) => {
              const tier = i < Math.ceil(levers.length / 3) ? "Do more" : i < Math.ceil((2 * levers.length) / 3) ? "Keep" : "Deprioritize";
              return (
                <div key={k}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-ink-2">{leverLabel(k)}</span>
                    <span className={`text-xs ${tier === "Do more" ? "text-good" : tier === "Keep" ? "text-ink-3" : "text-ink-4"}`}>{tier}</span>
                  </div>
                  <ToneBar pct={(Math.abs(v) / max) * 100} tone={v >= 0 ? "good" : "bad"} />
                </div>
              );
            })}
          </div>
          {/* Predicted vs measured — the plan's estimate calibrating to your real results */}
          {data.predicted_levers && (
            <div className="mt-4 border-t border-line pt-3">
              <SecHead
                title="Predicted vs. measured"
                note="what the plan estimated each action would add, vs. what we've actually measured from your results — how the per-task “predicted points” calibrate over time"
              />
              <TableContainer>
                <thead>
                  <tr><Th>Action</Th><Th className="text-right">Predicted /unit</Th><Th className="text-right">Measured /unit</Th></tr>
                </thead>
                <tbody>
                  {levers.map(([k, v]) => {
                    const pred = data.predicted_levers?.[k];
                    const meas = v * 100;
                    return (
                      <tr key={k}>
                        <Td>{leverLabel(k)}</Td>
                        <Td className="text-right text-ink-3">{pred != null ? `+${pred.toFixed(2)} pts` : "—"}</Td>
                        <Td className={`text-right font-medium ${pred != null && meas >= pred ? "text-good" : "text-amber"}`}>+{meas.toFixed(2)} pts</Td>
                      </tr>
                    );
                  })}
                </tbody>
              </TableContainer>
            </div>
          )}

          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-medium text-ink-4 hover:text-ink-2">▸ Show the raw numbers</summary>
            <TableContainer className="mt-2">
              <tbody>
                {levers.map(([k, v]) => (
                  <tr key={k}><Td>{leverLabel(k)}</Td><Td className="text-right font-medium">{v.toFixed(4)}</Td></tr>
                ))}
              </tbody>
            </TableContainer>
          </details>
        </Card>
      )}
    </div>
  );
}
