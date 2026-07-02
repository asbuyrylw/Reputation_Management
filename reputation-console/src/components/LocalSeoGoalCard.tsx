import { Card } from "@/components/ui";
import type { LocalSeoGoal } from "@/lib/types";

const pct = (v: number | undefined | null) => `${Math.round((v ?? 0) * 100)}%`;

function fmtGoalDate(d?: string | null): string {
  if (!d) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${m[2]}-${m[3]}-${m[1]}` : d;
}

// "Time to page 1" — the local-SEO equivalent of the AI-reputation timeline. Lives on the
// SEO overview hub (the page-1 goal projection for your local searches).
export function LocalSeoGoalCard({ goal }: { goal: LocalSeoGoal | undefined }) {
  if (!goal) return null;
  if (goal.no_data || goal.current_page_one_rate == null) {
    return (
      <Card className="border-indigo-100 bg-linear-to-br from-indigo-50 to-white">
        <div className="text-xs font-medium uppercase tracking-wide text-indigo-400">Goal — get to page 1 of Google</div>
        <p className="mt-1 text-sm text-slate-600">{goal.note || "Run a local-rank check to start this projection."}</p>
      </Card>
    );
  }
  const exp = goal.projection?.expected;
  const met = (goal.remaining_gap ?? 1) <= 0;
  return (
    <Card className="border-indigo-100 bg-linear-to-br from-indigo-50 to-white">
      <div className="text-xs font-medium uppercase tracking-wide text-indigo-400">Goal — get to page 1 of Google</div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {met ? (
          <span className="text-2xl font-bold text-emerald-700">On page 1 for most local searches 🎉</span>
        ) : (
          <>
            <span className="text-3xl font-bold text-slate-900">{fmtGoalDate(exp?.target_date)}</span>
            <span className="text-sm text-slate-500">
              (~{exp?.months ?? "—"} months) to rank on page 1 for {pct(goal.target_page_one_rate)} of your local searches
            </span>
          </>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
        <span className="text-slate-600">
          Now: <span className="font-semibold text-slate-900">{pct(goal.current_page_one_rate)}</span> on page 1 → target {pct(goal.target_page_one_rate)}
        </span>
        {goal.confidence && <span className="text-xs text-slate-500">Confidence: {goal.confidence}</span>}
      </div>
      {goal.target_searches && goal.target_searches.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Tracking: {goal.target_searches.slice(0, 4).map((q) => `“${q}”`).join(" · ")}
        </p>
      )}
      {goal.gain_basis && (
        <p className="mt-2 text-[11px] text-slate-500">Based on {goal.gain_basis}.</p>
      )}
      <p className="mt-1 text-[11px] text-slate-400">A projection that sharpens as your local-rank history grows.</p>
    </Card>
  );
}
