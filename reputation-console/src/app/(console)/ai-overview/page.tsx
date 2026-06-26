"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useTimeline, useMetricsTrend, useAnswerLenses, useAnswerChanges } from "@/lib/hooks";
import { PrimaryChallengeCard } from "@/components/PrimaryChallengeCard";
import { PerEnginePanel } from "@/components/PerEnginePanel";
import { PerEngineTrend } from "@/components/PerEngineTrend";
import { ScoreTrend } from "@/components/ScoreTrend";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { repScore } from "@/lib/repScore";

type Json = Record<string, unknown>;

function LinkCard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-900/[0.06] transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <span className="text-sm font-bold text-slate-900 group-hover:text-indigo-600">{title} →</span>
      <span className="mt-0.5 text-xs text-slate-500">{desc}</span>
    </Link>
  );
}

// "AI Visibility" deep-dive: the analytical view the Dashboard links into. The headline score,
// verdict and worst-answers live on the Dashboard; here we explain WHY — the primary challenge,
// the per-engine breakdown, the score trend — and link to the detailed AI pages.
export default function AiOverviewPage() {
  const { businessId, businesses, loading } = useBusiness();
  const { data, isLoading } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: perEngine } = usePerEngine(businessId, latestRunId);
  const { data: timeline } = useTimeline(businessId);
  const { data: trend } = useMetricsTrend(businessId);
  const { data: lensData } = useAnswerLenses(businessId);
  const { data: answerChanges } = useAnswerChanges(businessId);

  if (loading || (businessId != null && (isLoading || !data))) return <Spinner />;
  if (businesses.length === 0 || !data) {
    return (
      <div>
        <PageHeader eyebrow="AI Visibility" title="AI overview" />
        <EmptyState
          title="No data yet"
          why="Set up a business and run an audit to see how AI assistants portray you."
          cta={{ label: "Set up a business", href: "/onboarding" }}
        />
      </div>
    );
  }

  const s = data.series;
  const latest = s[s.length - 1];

  return (
    <div>
      <PageHeader
        eyebrow="AI Visibility"
        title="AI overview"
        subtitle="The why behind your AI reputation score — your primary challenge, how each assistant differs, and the trend over time. (The headline score and worst answers are on your Dashboard.)"
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {!latest ? (
        <EmptyState
          title="No audit has run yet"
          why="An audit checks what ChatGPT, Claude, Perplexity, and Gemini say about your business."
          produces="Your primary challenge, per-engine breakdown, and score trend appear here once it finishes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-6">
          {/* Why you're scored this way */}
          <PrimaryChallengeCard challenge={data.challenge} />

          {/* What changed in AI answers since the previous audit */}
          {answerChanges?.summary?.compared && (
            <Card>
              <div className="mb-1 text-base font-semibold tracking-tight text-slate-900">What changed in AI answers</div>
              <p className="mb-3 text-xs text-slate-500">How specific answers moved since your previous audit — the wins to build on and the regressions to fix.</p>
              {answerChanges.changes.length === 0 ? (
                <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-500">No material changes since the last audit — answers held steady.</p>
              ) : (
                <ul className="space-y-3">
                  {answerChanges.changes.slice(0, 6).map((ch, i) => {
                    const beforeGA = ch.before.goal_alignment;
                    const afterGA = ch.after.goal_alignment;
                    const improved = beforeGA != null && afterGA != null ? afterGA > beforeGA : null;
                    return (
                      <li key={i} className="rounded-xl border border-slate-100 bg-white px-3.5 py-2.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-white">{ch.engine}</span>
                          <span className="min-w-0 truncate text-sm font-medium text-slate-800">“{ch.prompt}”</span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                          <span className="text-slate-400">Sentiment:</span>
                          <span className="text-slate-600">{ch.before.sentiment ?? "—"}</span>
                          <span className="text-slate-400">→</span>
                          <span className={`font-semibold ${ch.after.sentiment === "positive" ? "text-emerald-700" : ch.after.sentiment === "negative" ? "text-rose-600" : "text-slate-700"}`}>
                            {ch.after.sentiment ?? "—"}
                          </span>
                          {improved != null && (
                            <span className={`ml-1 font-semibold ${improved ? "text-emerald-700" : "text-rose-600"}`}>
                              {improved ? "▲" : "▼"} goal alignment {beforeGA} → {afterGA}
                            </span>
                          )}
                        </div>
                        {ch.reasons.length > 0 && (
                          <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
                            {ch.reasons.slice(0, 3).map((r, j) => (
                              <li key={j}>· {r}</li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          )}

          {/* How each assistant differs */}
          {perEngine && Object.keys(perEngine.engines).length > 0 && <PerEnginePanel data={perEngine} />}

          {/* AI reputation trend over time */}
          <Card>
            <div className="mb-3 text-base font-semibold tracking-tight text-slate-900">Your AI reputation score over time (0–100)</div>
            <ScoreTrend series={s} goal={repScore((timeline as Json | undefined)?.dominance_target as number)} />
          </Card>

          {/* Per-engine trend — which AI assistant is rising or drifting */}
          <Card>
            <div className="mb-1 text-base font-semibold tracking-tight text-slate-900">Each AI assistant over time</div>
            <p className="mb-3 text-xs text-slate-500">Spot a single engine drifting negative before it drags your overall score.</p>
            <PerEngineTrend data={trend} />
          </Card>

          {/* Cross-engine divergence */}
          {lensData?.divergence?.items && lensData.divergence.items.length > 0 && (
            <Card>
              <div className="mb-1 text-base font-semibold tracking-tight text-slate-900">Where AI engines disagree most</div>
              <p className="mb-3 text-xs text-slate-500">Same question, very different answers — the gap to close first.</p>
              <ul className="space-y-2">
                {lensData.divergence.items.slice(0, 5).map((d, i) => (
                  <li key={i} className="text-sm">
                    <div className="font-medium text-slate-800">“{d.prompt}”</div>
                    <div className="text-xs text-slate-500">
                      <span className="font-semibold text-emerald-700">{d.best_engine} {d.best}</span> vs{" "}
                      <span className="font-semibold text-rose-600">{d.worst_engine} {d.worst}</span>
                      <span className="ml-1 text-slate-400">({d.spread}-pt gap)</span>
                      {d.contested_engines.length > 0 && <span className="ml-1 text-amber-600">· contested on {d.contested_engines.join(", ")}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* Persona / location lens */}
          {((lensData?.lenses?.by_persona?.length ?? 0) > 0 || (lensData?.lenses?.by_location?.length ?? 0) > 0) && (
            <Card>
              <div className="mb-1 text-base font-semibold tracking-tight text-slate-900">How different audiences see you</div>
              <p className="mb-3 text-xs text-slate-500">Whether a local prospect gets a worse answer than a generic one.</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {[{ t: "By who's asking", rows: lensData!.lenses.by_persona }, { t: "By location", rows: lensData!.lenses.by_location }].map((g) =>
                  g.rows.length > 0 ? (
                    <div key={g.t}>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{g.t}</div>
                      <ul className="space-y-1">
                        {g.rows.map((r) => (
                          <li key={r.lens} className="flex items-center justify-between text-sm">
                            <span className="truncate text-slate-700">{r.lens}</span>
                            <span className={`ml-2 shrink-0 font-semibold ${(r.score ?? 50) >= 60 ? "text-emerald-700" : (r.score ?? 50) < 40 ? "text-rose-600" : "text-amber-700"}`}>{r.score ?? "—"}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null,
                )}
              </div>
            </Card>
          )}

          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Go deeper</div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <LinkCard href="/audits" title="Audits & AI answers" desc="Every answer, scored by the judge." />
              <LinkCard href="/prompts" title="Prompts & topics" desc="The questions we ask AI about you." />
              <LinkCard href="/rankings" title="AI citations" desc="Which sources AI quotes about you." />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
