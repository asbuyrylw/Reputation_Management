"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAuditRuns, usePerEngine, useRunAnswers, useDashboard } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { StatusBadge } from "@/components/SentimentBadge";
import { RepScoreBadge } from "@/components/RepScoreBadge";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import { WorstAnswers } from "@/components/WorstAnswers";
import { EmptyState, Freshness } from "@/components/primitives";
import { repScore, repBand, repClasses } from "@/lib/repScore";
import { Term } from "@/components/Term";

const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString() : "—");
const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function AuditsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading, error } = useAuditRuns(businessId);
  const latest = data && data.length ? data[0] : null;
  const prev = data && data.length > 1 ? data[1] : null;
  const { data: perEngine } = usePerEngine(businessId, latest?.id ?? null);
  const { data: answers } = useRunAnswers(businessId, latest?.id ?? null);
  const { data: dash } = useDashboard(businessId);

  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-red-600">Could not load audits.</p>;

  const score = repScore(latest?.goal_alignment ?? null);
  const prevScore = repScore(prev?.goal_alignment ?? null);
  const delta = score != null && prevScore != null ? score - prevScore : null;

  return (
    <div>
      <PageHeader
        title="What AI says about you"
        subtitle="Each audit asks ChatGPT, Claude, Perplexity, and Gemini about your business and scores their answers."
      />

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
                <h3 className="text-sm font-semibold text-gray-900">Latest audit</h3>
                <Freshness asOf={latest.finished_at || latest.started_at} cadenceDays={30} />
              </div>
              <div className="mt-2 flex flex-wrap items-end gap-3">
                <span className={`rounded-xl border px-3 py-1 text-2xl font-bold ${repClasses(score)}`}>
                  {score ?? "—"}<span className="text-sm font-normal text-gray-400"> /100</span>
                </span>
                <span className="pb-1 text-sm font-medium text-gray-600">{repBand(score).label}</span>
                {delta != null && Math.abs(delta) >= 1 && (
                  <span className={`pb-1 text-sm font-medium ${delta > 0 ? "text-green-600" : "text-rose-600"}`}>
                    {delta > 0 ? "▲ +" : "▼ −"}{Math.abs(delta)} pts since last audit
                  </span>
                )}
              </div>
              <div className="mt-4">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                  How each AI assistant answers
                </div>
                <EngineScoreStrip perEngine={perEngine} challenge={dash?.challenge} />
              </div>
              <div className="mt-4 border-t border-gray-100 pt-3">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                  Worst things AI is saying now
                </div>
                <WorstAnswers answers={answers} runId={latest.id} limit={3} />
              </div>
            </Card>
          )}

          {/* History table — now in 0-100 language */}
          <Card className="overflow-hidden p-0">
            <div className="border-b border-gray-100 px-4 py-2 text-sm font-semibold text-gray-700">
              All audits
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
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
              <tbody className="divide-y divide-gray-100">
                {data.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2">{fmtDate(r.finished_at || r.started_at)}</td>
                    <td className="px-4 py-2"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-2"><RepScoreBadge goalAlignment={r.goal_alignment} /></td>
                    <td className="px-4 py-2">{pct(r.owned_rate)}</td>
                    <td className="px-4 py-2">{pct(r.contested_rate)}</td>
                    <td className="px-4 py-2">{r.n_answers}</td>
                    <td className="px-4 py-2 text-right">
                      <Link className="text-blue-600 hover:underline" href={`/audits/${r.id}`}>
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
