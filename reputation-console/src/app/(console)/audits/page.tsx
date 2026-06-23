"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useAuditRuns, usePerEngine, useRunAnswers, useDashboard, useTriggerJob, useCostBreakdown } from "@/lib/hooks";
import type { AuditRun } from "@/lib/types";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { StatusBadge } from "@/components/SentimentBadge";
import { RepScoreBadge } from "@/components/RepScoreBadge";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import { WorstAnswers } from "@/components/WorstAnswers";
import { Sparkline } from "@/components/Sparkline";
import { EmptyState, Freshness } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { repScore, repBand, repClasses } from "@/lib/repScore";
import { Term } from "@/components/Term";

const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString() : "—");
const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

// When a run has failed answers (e.g. a provider was down/circuit-broken during the audit),
// offer a one-click "top up": re-run ONLY the failed answers + rebuild the gap model, without
// re-paying for the answers that already succeeded.
function RetryFailed({ businessId, run, canEdit }: { businessId: number | null; run: AuditRun; canEdit: boolean }) {
  const trigger = useTriggerJob(businessId);
  const qc = useQueryClient();
  if (!canEdit || !run.failed_count) return null;
  const onRetry = () =>
    trigger.mutate(
      { jobType: "refresh_failed" },
      {
        onSuccess: () => {
          // refresh_failed re-pulls failed answers + rebuilds gaps in the background; refetch
          // the affected views once it's had time to run. Progress shows in the banner above.
          for (const key of [["audit-runs", businessId], ["per-engine", businessId], ["run-answers", businessId], ["dashboard", businessId], ["gap-model", businessId]]) {
            setTimeout(() => qc.invalidateQueries({ queryKey: key }), 25000);
          }
        },
      },
    );
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50/60 px-3.5 py-2.5">
      <span className="text-sm text-amber-800">
        <span className="font-semibold">{run.failed_count}</span> answer{run.failed_count === 1 ? "" : "s"} from{" "}
        <span className="font-semibold">{run.failed_engines}</span> engine{run.failed_engines === 1 ? "" : "s"} failed in this audit
        {" "}— likely a provider was temporarily down.
      </span>
      <button
        onClick={onRetry}
        disabled={trigger.isPending}
        className="shrink-0 rounded-lg bg-amber-600 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
      >
        {trigger.isPending ? "Retrying…" : "Retry failed engines"}
      </button>
    </div>
  );
}

// Admin-only estimated-COGS panel: what the latest audit cost us, per engine + operation.
// Surfaces where the money goes (the answer engines + grounding dominate) so cost levers are
// obvious. Estimates, not invoiced amounts.
function CostPanel({ businessId }: { businessId: number | null }) {
  const { data } = useCostBreakdown(businessId);
  if (!data || !data.run_id || data.items.length === 0) return null;
  const max = Math.max(...data.items.map((i) => i.cost), 0.0001);
  const fmt = (n: number) => `$${n.toFixed(2)}`;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Audit cost (estimated)</h3>
          <p className="mt-0.5 max-w-md text-xs text-slate-500">
            Our provider COGS for the latest audit — estimated from token counts × list prices, not invoiced amounts.
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold leading-none text-slate-900">{fmt(data.run_total)}</div>
          <div className="mt-0.5 text-xs text-slate-500">this audit · {fmt(data.month_total)} this month</div>
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {data.items.map((i) => (
          <div key={i.provider + i.operation}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-700">
                {i.provider} · {i.operation} <span className="text-slate-400">({i.calls} calls)</span>
              </span>
              <span className="font-semibold tabular-nums text-slate-900">{fmt(i.cost)}</span>
            </div>
            <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.round((i.cost / max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function AuditsPage() {
  const { businessId, canEdit, isAdmin } = useBusiness();
  const { data, isLoading, error } = useAuditRuns(businessId);
  const latest = data && data.length ? data[0] : null;
  const prev = data && data.length > 1 ? data[1] : null;
  const { data: perEngine } = usePerEngine(businessId, latest?.id ?? null);
  const { data: answers } = useRunAnswers(businessId, latest?.id ?? null);
  const { data: dash } = useDashboard(businessId);

  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-rose-600">Could not load audits.</p>;

  const score = repScore(latest?.goal_alignment ?? null);
  const prevScore = repScore(prev?.goal_alignment ?? null);
  const delta = score != null && prevScore != null ? score - prevScore : null;
  // scores oldest -> newest for the sparkline
  const scoreSeries = [...data]
    .reverse()
    .map((r) => repScore(r.goal_alignment))
    .filter((v): v is number => v != null);

  return (
    <div>
      <PageHeader
        eyebrow="Audits"
        title="What AI says about you"
        subtitle="Each audit asks ChatGPT, Claude, Perplexity, and Gemini about your business and scores their answers."
      />

      {/* Live progress while an audit (or other job) runs in the background. */}
      <JobProgressBanner businessId={businessId} className="mb-4" />

      {data.length === 0 ? (
        <EmptyState
          title="No audits have run yet"
          why="An audit checks what the AI assistants say about your business and turns it into a 0–100 score."
          produces="You'll see your latest score, the worst answers, and how each engine answers — right here."
          timing="An audit takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-6">
          {/* Latest audit hero — the answer up top, no drill-in needed */}
          {latest && (
            <Card>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Latest audit</h3>
                <Freshness asOf={latest.finished_at || latest.started_at} cadenceDays={30} />
              </div>
              <div className="mt-2 flex flex-wrap items-end gap-3">
                <span className={`rounded-xl border px-3 py-1 text-2xl font-bold ${repClasses(score)}`}>
                  {score ?? "—"}<span className="text-sm font-normal text-slate-400"> /100</span>
                </span>
                <span className="pb-1 text-sm font-medium text-slate-600">{repBand(score).label}</span>
                {delta != null && Math.abs(delta) >= 1 && (
                  <span className={`pb-1 text-sm font-medium ${delta > 0 ? "text-emerald-600" : "text-rose-600"}`}>
                    {delta > 0 ? "▲ +" : "▼ −"}{Math.abs(delta)} pts since last audit
                  </span>
                )}
                {scoreSeries.length >= 2 && (
                  <span className="ml-auto pb-1" title="Your score across audits">
                    <Sparkline values={scoreSeries} />
                  </span>
                )}
              </div>
              <div className="mt-4">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                  How each AI assistant answers
                </div>
                <EngineScoreStrip perEngine={perEngine} challenge={dash?.challenge} />
              </div>
              <div className="mt-4 border-t border-slate-100 pt-3">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                  Worst things AI is saying now
                </div>
                <WorstAnswers answers={answers} runId={latest.id} limit={3} />
              </div>
              <RetryFailed businessId={businessId} run={latest} canEdit={canEdit} />
            </Card>
          )}

          {/* Estimated COGS for this audit (admin-only) — shows where the spend goes. */}
          {isAdmin && <CostPanel businessId={businessId} />}

          {/* History table — now in 0-100 language */}
          <Card className="overflow-hidden p-0">
            <div className="border-b border-slate-100 px-4 py-2 text-sm font-semibold text-slate-700">
              All audits
            </div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">Score</th>
                  <th className="px-4 py-2"><Term name="owned content">Owned</Term></th>
                  <th className="px-4 py-2"><Term name="contested">Concerns</Term></th>
                  <th className="px-4 py-2">Answers</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2">{fmtDate(r.finished_at || r.started_at)}</td>
                    <td className="px-4 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-2"><RepScoreBadge goalAlignment={r.goal_alignment} /></td>
                    <td className="px-4 py-2">{pct(r.owned_rate)}</td>
                    <td className="px-4 py-2">{pct(r.contested_rate)}</td>
                    <td className="px-4 py-2">{r.n_answers}</td>
                    <td className="px-4 py-2 text-right">
                      <Link className="text-indigo-600 hover:underline" href={`/audits/${r.id}`}>
                        Read answers →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
}
