"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useRunAnswers, useWorkOrders, useTimeline, useNotifications } from "@/lib/hooks";
import { ReputationHero } from "@/components/ReputationHero";
import { PrimaryChallengeCard } from "@/components/PrimaryChallengeCard";
import { ScoreDonut } from "@/components/ScoreDonut";
import { ScoreTrend } from "@/components/ScoreTrend";
import { PerEnginePanel } from "@/components/PerEnginePanel";
import { VerdictBanner } from "@/components/VerdictBanner";
import { WorstAnswers } from "@/components/WorstAnswers";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import OnboardingCard from "@/components/OnboardingCard";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import VisibilityTrendChart from "@/components/VisibilityTrendChart";
import { Card, PageHeader, SectionCard, Spinner } from "@/components/ui";
import { EmptyState, Freshness, ToneLegend } from "@/components/primitives";
import { repScore } from "@/lib/repScore";
import type { SeriesPoint, WorkOrder } from "@/lib/types";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string };

// --- Do this next: the top open work items, framed as the owner's action list ---
function DoThisNext({ workOrders }: { workOrders: WorkOrder[] | undefined }) {
  const open = (workOrders ?? []).filter((w) => w.status !== "done" && w.status !== "verified");
  // prefer human/team tasks over engine-automated baseline steps, but never end up empty
  const ranked = [...open].sort((a, b) => (a.execution === "auto" ? 1 : 0) - (b.execution === "auto" ? 1 : 0));
  const top = ranked.slice(0, 3);
  return (
    <SectionCard
      title="Do this next"
      subtitle="The highest-impact moves to raise your score."
      accent="info"
      action={{ label: "View full plan", href: "/content/work-orders" }}
    >
      {top.length === 0 ? (
        <p className="text-sm text-slate-500">No open tasks yet. Run an audit to generate your action plan.</p>
      ) : (
        <ol className="space-y-3.5">
          {top.map((w, i) => (
            <li key={w.id} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white shadow-sm">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-slate-900">{w.title ?? w.wo_code}</div>
                {w.instruction && (
                  <div className="mt-1 flex gap-2 text-sm leading-relaxed text-slate-600">
                    <span className="select-none text-slate-300" aria-hidden>–</span>
                    <span>{w.instruction}</span>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      {open.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3 text-xs font-medium text-slate-400">
          {open.length} open task{open.length === 1 ? "" : "s"} in your plan
        </div>
      )}
    </SectionCard>
  );
}

// --- Biggest gaps: the worst questions AI gets wrong, in plain English ---
function BiggestGaps({ gap }: { gap: Json | undefined }) {
  const weak = (gap?.weak_queries as WeakQuery[] | undefined) ?? [];
  const top = weak.slice(0, 3);
  return (
    <SectionCard
      title="Your biggest gaps"
      subtitle="The questions AI answers worst about you."
      accent="bad"
      action={{ label: "Close these gaps", href: "/gaps" }}
    >
      {top.length === 0 ? (
        <p className="text-sm text-slate-500">Run an audit to see where AI answers fall short.</p>
      ) : (
        <ol className="space-y-3.5">
          {top.map((w, i) => (
            <li key={i} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-500 text-xs font-bold text-white shadow-sm">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-slate-900">“{w.prompt}”</div>
                {w.problem && (
                  <div className="mt-1 flex gap-2 text-sm leading-relaxed text-slate-600">
                    <span className="select-none text-slate-300" aria-hidden>–</span>
                    <span>{w.problem}</span>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </SectionCard>
  );
}

// --- When will I know it improved: projection + recheck, in 0-100 language ---
function ProjectionStrip({ timeline }: { timeline: Json | undefined }) {
  if (!timeline) return null;
  const cur = repScore((timeline.current_alignment as number) ?? null);
  const goal = repScore((timeline.dominance_target as number) ?? null);
  const proj = (timeline.projection as Json | undefined)?.expected as Json | undefined;
  const date = proj?.target_date as string | undefined;
  const confidence = timeline.confidence as string | undefined;
  return (
    <Card accent="info" className="bg-linear-to-br from-indigo-50/60 to-white">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold tracking-tight text-slate-900">When will I know it improved?</h3>
        <Link href="/timeline" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
          See full projection →
        </Link>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5">
          <span className="text-2xl font-bold text-slate-900">{cur ?? "—"}</span>
          <span className="text-xs font-medium text-slate-400">today</span>
        </div>
        <span className="text-lg text-slate-300">→</span>
        <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2 ring-1 ring-emerald-200">
          <span className="text-2xl font-bold text-emerald-600">{goal ?? "—"}</span>
          <span className="text-xs font-medium text-emerald-700">goal</span>
        </div>
        {date && (
          <div className="text-sm text-slate-600">
            on track to arrive around <span className="font-semibold text-slate-900">{date}</span>
          </div>
        )}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        {confidence && <>Confidence: <span className="font-medium text-slate-600">{confidence}</span> (sharpens after each audit). </>}
        Your score updates every time an audit runs — recheck after your next audit to see movement.
      </p>
    </Card>
  );
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function DashboardPage() {
  const { businessId, businesses, loading: bizLoading } = useBusiness();
  const { data, isLoading, error } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: perEngine } = usePerEngine(businessId, latestRunId);
  const { data: answers } = useRunAnswers(businessId, latestRunId);
  const { data: workOrders } = useWorkOrders(businessId);
  const { data: timeline } = useTimeline(businessId);
  const { data: notifs } = useNotifications(businessId);

  if (bizLoading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <Card accent="info" className="text-center">
        <h2 className="text-lg font-bold tracking-tight text-slate-900">Let&apos;s get you set up</h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
          No businesses yet. The guided setup captures your goals, competitors, locations and keywords, then runs the
          full audit, prompts, SEO, gaps and rankings for you.
        </p>
        <Link
          href="/onboarding"
          className="mt-4 inline-block rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
        >
          Set up a business →
        </Link>
      </Card>
    );
  }
  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-rose-600">Could not load the dashboard.</p>;

  const s = data.series;
  const latest: SeriesPoint | undefined = s[s.length - 1];
  const score = repScore(latest?.goal_alignment ?? null);

  // grounded rate across engines (from the latest run's per-engine metrics)
  const engVals = perEngine ? Object.values(perEngine.engines) : [];
  const grounded = engVals.filter((e) => e.grounded_rate);
  const groundedRate = grounded.length
    ? grounded.reduce((a, e) => a + (e.grounded_rate!.p ?? 0), 0) / grounded.length
    : null;

  // sentiment distribution of the latest run's answers
  const counts: Record<string, number> = { positive: 0, neutral: 0, mixed: 0, negative: 0 };
  for (const a of answers ?? []) if (a.sentiment && a.sentiment in counts) counts[a.sentiment]++;
  const sentimentData = [
    { name: "positive", value: counts.positive, color: "#16a34a" },
    { name: "neutral", value: counts.neutral, color: "#9ca3af" },
    { name: "mixed", value: counts.mixed, color: "#f59e0b" },
    { name: "negative", value: counts.negative, color: "#dc2626" },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title={`Dashboard — ${data.business.name}`}
        subtitle="Where you stand with AI assistants, what to do next, and when it'll improve."
      />

      {/* Live progress for any audit/benchmark/etc. running in the background. */}
      <JobProgressBanner businessId={businessId} className="mb-4" />

      {notifs && notifs.unread > 0 && (
        <Link
          href="/notifications"
          className="mb-4 flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm hover:bg-amber-100"
        >
          <span className="font-medium text-amber-800">
            ⚠ {notifs.unread} thing{notifs.unread === 1 ? "" : "s"} need your attention
          </span>
          <span className="text-amber-700">View →</span>
        </Link>
      )}

      {/* Getting-started checklist — guides a new owner; collapses to a confirmation when done. */}
      <div className="mb-4">
        <OnboardingCard businessId={businessId} />
      </div>

      {!latest ? (
        <EmptyState
          title="No audit has run yet"
          why="An audit checks what ChatGPT, Claude, Perplexity, and Gemini say about your business."
          produces="Once it finishes, your reputation score, your biggest gaps, and your action plan appear here."
          timing="An audit takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-6">
          {/* 1. plain-English verdict */}
          <VerdictBanner businessName={data.business.name} score={score} challenge={data.challenge} />

          {/* 2. hero score + recheck */}
          <div>
            <ReputationHero
              goalAlignment={latest.goal_alignment}
              contestedRate={latest.contested_rate}
              ownedRate={latest.owned_rate}
              groundedRate={groundedRate}
              coverage={perEngine?.coverage ?? null}
              woCounts={data.wo_counts}
              assetsN={data.assets_n}
            />
            <div className="mt-1 flex items-center justify-between px-1">
              <Freshness asOf={latest.date} cadenceDays={30} />
              <ToneLegend />
            </div>
          </div>

          {/* 3. problem beside action */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <DoThisNext workOrders={workOrders} />
            <BiggestGaps gap={data.gap} />
          </div>

          {/* 4. when will I know it improved */}
          <ProjectionStrip timeline={timeline as Json | undefined} />

          {/* 4b. visibility over time vs competitors (self-hides until 2+ benchmark runs) */}
          <VisibilityTrendChart businessId={businessId} />

          {/* 5. what AI is saying now + per-engine */}
          <Card accent="bad">
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Worst things AI is saying right now</h3>
            <div className="mt-3">
              <WorstAnswers answers={answers} runId={latestRunId} limit={3} />
            </div>
            <div className="mt-4 border-t border-slate-100 pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Each AI assistant&apos;s score
              </div>
              <EngineScoreStrip perEngine={perEngine} challenge={data.challenge} />
            </div>
          </Card>

          {/* 6. trend (0-100) + sentiment */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <div className="mb-3 text-base font-semibold tracking-tight text-slate-900">Your score over time (0–100)</div>
              <ScoreTrend series={s} goal={repScore((timeline as Json | undefined)?.dominance_target as number)} />
            </Card>
            <ScoreDonut
              title="How AI answers lean"
              subtitle="Sentiment of the latest run's answers"
              data={sentimentData}
              centerLabel="answers"
            />
          </div>

          {/* 7. details on demand */}
          <details className="group">
            <summary className="cursor-pointer text-sm font-semibold text-indigo-600 hover:text-indigo-700">
              ▸ More detail: why this challenge, and what each engine says ({pct(latest.contested_rate)} raise concerns)
            </summary>
            <div className="mt-3 space-y-6">
              <PrimaryChallengeCard challenge={data.challenge} />
              {perEngine && Object.keys(perEngine.engines).length > 0 && <PerEnginePanel data={perEngine} />}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
