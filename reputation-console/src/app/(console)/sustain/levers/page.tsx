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
          <div className="mb-3 text-sm text-gray-600">
            Each bar shows how much that action moves your score per effort, relative to the others.
          </div>
          <div className="space-y-3">
            {levers.map(([k, v], i) => {
              const tier = i < Math.ceil(levers.length / 3) ? "Do more" : i < Math.ceil((2 * levers.length) / 3) ? "Keep" : "Deprioritize";
              return (
                <div key={k}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-gray-800">{leverLabel(k)}</span>
                    <span className={`text-xs ${tier === "Do more" ? "text-green-700" : tier === "Keep" ? "text-gray-500" : "text-gray-400"}`}>{tier}</span>
                  </div>
                  <ToneBar pct={(Math.abs(v) / max) * 100} tone={v >= 0 ? "good" : "bad"} />
                </div>
              );
            })}
          </div>
          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-medium text-gray-400 hover:text-gray-700">▸ Show the raw numbers</summary>
            <table className="mt-2 w-full text-sm">
              <tbody className="divide-y divide-gray-100">
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
