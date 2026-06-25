"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useRunAnswers, useWorkOrders, useTimeline, useNotifications, useLocalRankings, useActivitySummary } from "@/lib/hooks";
import { ReputationHero } from "@/components/ReputationHero";
import { ScoreDonut } from "@/components/ScoreDonut";
import { ScoreTrend } from "@/components/ScoreTrend";
import { VerdictBanner } from "@/components/VerdictBanner";
import { WorstAnswers } from "@/components/WorstAnswers";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import OnboardingCard from "@/components/OnboardingCard";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import VisibilityTrendChart from "@/components/VisibilityTrendChart";
import { Card, PageHeader, SectionCard, Spinner } from "@/components/ui";
import { EmptyState, Freshness, ToneLegend } from "@/components/primitives";
import { repScore } from "@/lib/repScore";
import type { SeriesPoint, WorkOrder, Business } from "@/lib/types";

// "What we're tracking for you" — profile readback + setup-completeness meter. Each empty field
// shows the capability it unlocks, so onboarding gaps are visible and fixable.
function ProfileTrackingCard({ biz }: { biz?: Business }) {
  if (!biz) return null;
  const fields = [
    { label: "Areas served", value: biz.geo, enables: "local rankings & Google reviews" },
    { label: "Services", value: biz.services, enables: "keyword targeting & category prompts" },
    { label: "Industry", value: biz.industry, enables: "sharper benchmarking" },
    { label: "Goal", value: biz.goal, enables: "your North-Star score framing" },
    { label: "Contested terms", value: biz.contested_terms, enables: "narrative defense" },
    { label: "Firm type", value: biz.regulatory_profile?.firm_type, enables: "correct compliance checks" },
  ];
  const filled = fields.filter((f) => (f.value ?? "").toString().trim());
  const empty = fields.filter((f) => !(f.value ?? "").toString().trim());
  const pct = Math.round((filled.length / fields.length) * 100);
  return (
    <Card>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-tight text-slate-900">What we&apos;re tracking for you</h3>
        <span className="text-xs text-slate-400">{pct}% set up</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {filled.map((f) => <span key={f.label} className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">✓ {f.label}</span>)}
      </div>
      {empty.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
          {empty.map((f) => (
            <li key={f.label}>⚠ Add <Link href="/admin/businesses" className="font-medium text-indigo-600 hover:underline">{f.label}</Link> to enable {f.enables}.</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

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

const pct = (v: number | null | undefined) => `${Math.round((v ?? 0) * 100)}%`;

// --- Cross-cutting snapshot: a small SEO summary + tasks summary, so the Dashboard spans
// AI *and* search *and* execution — not just the AI rollup (which is what AI overview is for). ---
function CrossCutStrip({ businessId, workOrders }: { businessId: number | null; workOrders: WorkOrder[] | undefined }) {
  const { data: ranks } = useLocalRankings(businessId);
  const sum = ranks?.summary ?? null;
  const wos = workOrders ?? [];
  const open = wos.filter((w) => w.status !== "done" && w.status !== "verified" && !w.superseded).length;
  const inProgress = wos.filter((w) => w.status === "in_progress").length;
  const done = wos.filter((w) => w.status === "done" || w.status === "verified").length;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Local search snapshot */}
      <Card>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold tracking-tight text-slate-900">📍 Local search</h3>
          <Link href="/seo-overview" className="text-xs font-medium text-indigo-600 hover:text-indigo-700">SEO overview →</Link>
        </div>
        {sum ? (
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div><div className="text-xl font-bold text-slate-900">{pct(sum.page_one_rate)}</div><div className="text-[11px] text-slate-500">on page 1</div></div>
            <div><div className="text-xl font-bold text-slate-900">{pct(sum.local_pack_rate)}</div><div className="text-[11px] text-slate-500">in map pack</div></div>
            <div><div className="text-xl font-bold text-slate-900">{sum.avg_organic_rank == null ? "—" : `#${sum.avg_organic_rank}`}</div><div className="text-[11px] text-slate-500">avg rank</div></div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No local-rank snapshot yet. <Link href="/local-seo" className="font-medium text-indigo-600 hover:text-indigo-700">Run a check →</Link></p>
        )}
      </Card>

      {/* Tasks snapshot */}
      <Card>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold tracking-tight text-slate-900">✅ Improvement tasks</h3>
          <Link href="/content/work-orders" className="text-xs font-medium text-indigo-600 hover:text-indigo-700">Manage tasks →</Link>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div><div className="text-xl font-bold text-slate-900">{open}</div><div className="text-[11px] text-slate-500">open</div></div>
          <div><div className="text-xl font-bold text-indigo-600">{inProgress}</div><div className="text-[11px] text-slate-500">in progress</div></div>
          <div><div className="text-xl font-bold text-emerald-600">{done}</div><div className="text-[11px] text-slate-500">done</div></div>
        </div>
      </Card>
    </div>
  );
}

// --- "This month's work" — the client-facing value narrative (what the service did) ---
function ThisMonthPanel({ businessId }: { businessId: number | null }) {
  const { data } = useActivitySummary(businessId);
  if (!data) return null;
  const items = [
    { n: data.audits, label: "audits run" },
    { n: data.drafts, label: "drafts created" },
    { n: data.published, label: "published" },
    { n: data.tasks_done, label: "tasks done" },
    { n: data.mentions, label: "mentions found" },
    { n: data.outreach, label: "outreach targets" },
  ];
  if (items.every((i) => !i.n)) return null; // nothing yet this month — don't show an empty panel
  return (
    <Card className="bg-linear-to-br from-indigo-50/50 to-white">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-tight text-slate-900">This month&apos;s work</h3>
        <span className="text-[11px] text-slate-400">your reputation team, this month</span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-6">
        {items.map((i) => (
          <div key={i.label} className="text-center">
            <div className="text-2xl font-bold text-slate-900">{i.n}</div>
            <div className="text-[11px] leading-tight text-slate-500">{i.label}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// --- B2: progress narrative — what you've done and how the score moved ---
function ProgressStrip({ workOrders, series }: { workOrders: WorkOrder[] | undefined; series: SeriesPoint[] }) {
  const wos = workOrders ?? [];
  const done = wos.filter((w) => w.status === "done" || w.status === "verified").length;
  const total = wos.length;
  if (total === 0 && series.length < 2) return null;
  const first = series[0];
  const last = series[series.length - 1];
  const delta = series.length >= 2 ? repScore(last?.goal_alignment ?? null)! - repScore(first?.goal_alignment ?? null)! : null;
  const donePct = total ? Math.round((done / total) * 100) : 0;
  return (
    <Card className="bg-linear-to-br from-emerald-50/50 to-white">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div>
          <div className="text-2xl font-bold text-slate-900">{done}<span className="text-base font-medium text-slate-400">/{total}</span></div>
          <div className="text-xs text-slate-500">tasks done ({donePct}% of your plan)</div>
        </div>
        {delta != null && (
          <div>
            <div className={`text-2xl font-bold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{delta >= 0 ? "+" : ""}{delta}</div>
            <div className="text-xs text-slate-500">score change since your first audit</div>
          </div>
        )}
        <div className="ml-auto text-xs text-slate-500">
          {delta != null && delta > 0
            ? "It's working — keep shipping tasks and re-run an audit to measure the next move."
            : "Complete tasks, then re-run an audit to measure the impact."}
        </div>
      </div>
    </Card>
  );
}

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
  // North Star: the owner's stated positioning goal — what we want AI to say about them.
  const goalText = (businesses.find((b) => b.id === businessId)?.goal || "").trim();

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
          {/* 0. North Star — the stated goal, with the score framed as progress toward it */}
          {goalText && (
            <Card accent="info" className="bg-linear-to-br from-indigo-50/70 to-white">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">Your goal</div>
                  <p className="mt-0.5 text-base font-semibold tracking-tight text-slate-900">{goalText}</p>
                  <p className="mt-0.5 text-xs text-slate-500">Your score is how close AI is to saying this about you today.</p>
                </div>
                {score != null && (
                  <div className="flex shrink-0 items-baseline gap-1 rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5">
                    <span className="text-2xl font-bold text-slate-900">{score}</span>
                    <span className="text-xs font-medium text-slate-400">/100 today</span>
                  </div>
                )}
              </div>
            </Card>
          )}

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

          {/* 2b. your progress — tasks done + score movement */}
          <ProgressStrip workOrders={workOrders} series={s} />

          {/* 2c. cross-cutting: local search + tasks (the Dashboard spans AI + SEO + execution) */}
          <CrossCutStrip businessId={businessId} workOrders={workOrders} />

          {/* 2d. this month's work — the value narrative (self-hides when nothing yet) */}
          <ThisMonthPanel businessId={businessId} />

          {/* 2e. profile readback + setup completeness */}
          <ProfileTrackingCard biz={businesses.find((b) => b.id === businessId)} />

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

          {/* 7. why this challenge + per-engine detail now lives on the AI overview */}
          <Card className="bg-slate-50/60">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-slate-600">
                Want the why — your primary challenge and how each AI assistant differs?
              </p>
              <Link href="/ai-overview" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">AI overview →</Link>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
