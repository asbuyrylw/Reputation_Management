"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import {
  useDashboard, usePerEngine, useRunAnswers, useWorkOrders, useTimeline, useNotifications,
  useLocalRankings, useActivitySummary, useGscSummary, useIncidents, useMentions, useApprovalQueue,
} from "@/lib/hooks";
import { ReputationHero } from "@/components/ReputationHero";
import { ScoreTrend } from "@/components/ScoreTrend";
import { VerdictBanner } from "@/components/VerdictBanner";
import { WorstAnswers } from "@/components/WorstAnswers";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import OnboardingCard from "@/components/OnboardingCard";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import VisibilityTrendChart from "@/components/VisibilityTrendChart";
import { Card, PageHeader, SectionCard, Spinner } from "@/components/ui";
import { EmptyState, ToneLegend } from "@/components/primitives";
import { repScore } from "@/lib/repScore";
import type { SeriesPoint, WorkOrder, Business } from "@/lib/types";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string };

const pct = (v: number | null | undefined) => `${Math.round((v ?? 0) * 100)}%`;

// --- Collapsible "see more" wrapper for any object that can get tall ---
function SeeMore({ children, label = "See more", max = "max-h-64" }: { children: React.ReactNode; label?: string; max?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <div className={open ? "" : `relative ${max} overflow-hidden`}>
        {children}
        {!open && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-linear-to-t from-white to-transparent" />}
      </div>
      <button type="button" onClick={() => setOpen((o) => !o)} className="mt-2 text-sm font-medium text-indigo-600 hover:text-indigo-700">
        {open ? "Show less ▲" : `${label} ▾`}
      </button>
    </div>
  );
}

// --- Live monitor: incidents + mentions at a glance. Always visible (shows 0 / all-clear). ---
function LiveMonitorStrip({ businessId }: { businessId: number | null }) {
  const { data: incidents } = useIncidents(businessId);
  const { data: mentions } = useMentions(businessId);
  const openIncidents = (incidents ?? []).filter((i) => !i.resolved_at).length;
  const newMentions = (mentions ?? []).filter((m) => (m.status ?? "new") === "new").length;
  const pill = (n: number, label: string, href: string, emoji: string) => (
    <Link
      href={href}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
        n > 0 ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100" : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
      }`}
    >
      <span aria-hidden>{emoji}</span> <span className="font-bold">{n}</span> {label}
    </Link>
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Live monitor</span>
      {pill(openIncidents, "open incidents", "/sustain/incidents", "🚨")}
      {pill(newMentions, "new mentions", "/sustain/mentions", "💬")}
      {openIncidents === 0 && newMentions === 0 && <span className="text-xs text-emerald-600">✓ all clear</span>}
    </div>
  );
}

// "What we're tracking for you" — profile readback + setup-completeness meter.
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
  const setupPct = Math.round((filled.length / fields.length) * 100);
  return (
    <Card>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-tight text-slate-900">What we&apos;re tracking for you</h3>
        <span className="text-xs text-slate-400">{setupPct}% set up</span>
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

// --- Approval queue summary — small, lives inside the "Do this next" section ---
function ApprovalWidget({ businessId }: { businessId: number | null }) {
  const { data } = useApprovalQueue(businessId);
  const n = data?.items?.length ?? 0;
  return (
    <Link
      href="/approvals"
      className={`mt-3 flex items-center justify-between rounded-lg border px-3 py-2 text-xs font-medium transition ${
        n > 0 ? "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100" : "border-slate-100 bg-slate-50 text-slate-500 hover:bg-slate-100"
      }`}
    >
      <span>{n > 0 ? `🕒 ${n} item${n === 1 ? "" : "s"} waiting to approve & post` : "✓ Nothing waiting for your approval"}</span>
      {n > 0 && <span>Review →</span>}
    </Link>
  );
}

// --- Do this next: the top open work items + the approval summary ---
function DoThisNext({ workOrders, businessId }: { workOrders: WorkOrder[] | undefined; businessId: number | null }) {
  const open = (workOrders ?? []).filter((w) => w.status !== "done" && w.status !== "verified");
  const ranked = [...open].sort((a, b) => (a.execution === "auto" ? 1 : 0) - (b.execution === "auto" ? 1 : 0));
  const top = ranked.slice(0, 3);
  return (
    <SectionCard title="Do this next" subtitle="The highest-impact moves to raise your score." accent="info" action={{ label: "View full plan", href: "/content/work-orders" }}>
      {top.length === 0 ? (
        <p className="text-sm text-slate-500">No open tasks yet. Run an audit to generate your action plan.</p>
      ) : (
        <ol className="space-y-3.5">
          {top.map((w, i) => (
            <li key={w.id} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white shadow-sm">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-slate-900">{w.title ?? w.wo_code}</div>
                {w.instruction && (
                  <div className="mt-1 flex gap-2 text-sm leading-relaxed text-slate-600">
                    <span className="select-none text-slate-300" aria-hidden>–</span><span>{w.instruction}</span>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      {/* approval queue — what's waiting to approve & post */}
      <ApprovalWidget businessId={businessId} />
      {open.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-3 text-xs font-medium text-slate-400">
          {open.length} open task{open.length === 1 ? "" : "s"} in your plan
        </div>
      )}
    </SectionCard>
  );
}

// --- Biggest gaps: the worst questions AI gets wrong ---
function BiggestGaps({ gap }: { gap: Json | undefined }) {
  const weak = (gap?.weak_queries as WeakQuery[] | undefined) ?? [];
  const top = weak.slice(0, 3);
  return (
    <SectionCard title="Your biggest gaps" subtitle="The questions AI answers worst about you." accent="bad" action={{ label: "Close these gaps", href: "/gaps" }}>
      {top.length === 0 ? (
        <p className="text-sm text-slate-500">Run an audit to see where AI answers fall short.</p>
      ) : (
        <ol className="space-y-3.5">
          {top.map((w, i) => (
            <li key={i} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-500 text-xs font-bold text-white shadow-sm">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-slate-900">“{w.prompt}”</div>
                {w.problem && (
                  <div className="mt-1 flex gap-2 text-sm leading-relaxed text-slate-600">
                    <span className="select-none text-slate-300" aria-hidden>–</span><span>{w.problem}</span>
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

// --- Action plan & progress — merges the plan progress bar, the tasks-done/score-change strip,
// and the old "improvement tasks" block into ONE surface, with "Manage tasks" promoted up here. ---
function ActionPlanProgress({ woCounts, assetsN, series }: { woCounts: Record<string, number>; assetsN: number; series: SeriesPoint[] }) {
  const total = Object.values(woCounts).reduce((a, b) => a + b, 0);
  const done = (woCounts.done ?? 0) + (woCounts.verified ?? 0);
  const inProg = (woCounts.in_progress ?? 0) + (woCounts.in_review ?? 0) + (woCounts.review ?? 0);
  const open = Math.max(0, total - done - inProg);
  const woPct = total ? Math.round((done / total) * 100) : 0;
  const delta = series.length >= 2 ? repScore(series[series.length - 1]?.goal_alignment ?? null)! - repScore(series[0]?.goal_alignment ?? null)! : null;
  return (
    <Card accent="good">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Action plan progress</h3>
          <p className="mt-0.5 text-xs text-slate-500">Completing these work items is what moves your score.</p>
        </div>
        <Link href="/content/work-orders" className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100">Manage tasks →</Link>
      </div>
      <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-linear-to-r from-emerald-400 to-emerald-600 transition-all" style={{ width: `${woPct}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <div>
          <div className="text-2xl font-bold leading-none text-slate-900">{done}<span className="text-base font-medium text-slate-400">/{total}</span></div>
          <div className="text-xs text-slate-500">tasks done ({woPct}%)</div>
        </div>
        {delta != null && (
          <div>
            <div className={`text-2xl font-bold leading-none ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{delta >= 0 ? "+" : ""}{delta}</div>
            <div className="text-xs text-slate-500">score since first audit</div>
          </div>
        )}
        <div>
          <div className="text-2xl font-bold leading-none text-slate-900">{assetsN}</div>
          <div className="text-xs text-slate-500">published</div>
        </div>
        <div className="ml-auto flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium">
          <span className="flex items-center gap-1.5 text-slate-600"><span className="h-2 w-2 rounded-full bg-emerald-500" /> {done} done</span>
          <span className="flex items-center gap-1.5 text-slate-600"><span className="h-2 w-2 rounded-full bg-amber-500" /> {inProg} in progress</span>
          <span className="flex items-center gap-1.5 text-slate-600"><span className="h-2 w-2 rounded-full bg-slate-300" /> {open} not started</span>
        </div>
      </div>
    </Card>
  );
}

// --- Local search snapshot (grouped with organic search under "Search performance") ---
function LocalSearchCard({ businessId }: { businessId: number | null }) {
  const { data: ranks } = useLocalRankings(businessId);
  const sum = ranks?.summary ?? null;
  return (
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
  );
}

// --- Organic search traffic (real Google clicks). Self-hides to a connect hint when not linked. ---
function OrganicSearchCard({ businessId }: { businessId: number | null }) {
  const { data } = useGscSummary(businessId);
  if (!data) return null;
  const collecting = data.collecting;
  const hasData = data.has_data;
  if (!hasData && !collecting) {
    return (
      <Card className="bg-slate-50/60">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-slate-600">Want real Google clicks &amp; rankings alongside your AI score?</p>
          <Link href="/integrations" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">Connect Search Console →</Link>
        </div>
      </Card>
    );
  }
  const delta = data.clicks_delta ?? null;
  const deltaTone = delta == null ? "text-slate-400" : delta >= 0 ? "text-emerald-600" : "text-rose-600";
  return (
    <Card className="bg-linear-to-br from-sky-50/50 to-white">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-tight text-slate-900">🔍 Organic search traffic</h3>
        <Link href="/search-performance" className="text-xs font-medium text-indigo-600 hover:text-indigo-700">Search traffic →</Link>
      </div>
      {!hasData && collecting ? (
        <p className="mt-3 text-sm text-slate-500">Collecting search data…</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-2xl font-bold text-slate-900">{(data.clicks ?? 0).toLocaleString()}</span>
          <span className="text-xs text-slate-500">clicks from Google · last 28 days</span>
          {delta != null && Math.abs(delta) >= 0.5 && (
            <span className={`text-sm font-medium ${deltaTone}`}>{delta >= 0 ? "▲ +" : "▼ "}{Math.round(delta)}% vs prior 28d</span>
          )}
        </div>
      )}
    </Card>
  );
}

// --- "This month's work" — the client-facing value narrative ---
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
  if (items.every((i) => !i.n)) return null;
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

// --- When will I know it improved: projection + recheck ---
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
        <Link href="/timeline" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">See full projection →</Link>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5">
          <span className="text-2xl font-bold text-slate-900">{cur ?? "—"}</span><span className="text-xs font-medium text-slate-400">today</span>
        </div>
        <span className="text-lg text-slate-300">→</span>
        <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2 ring-1 ring-emerald-200">
          <span className="text-2xl font-bold text-emerald-600">{goal ?? "—"}</span><span className="text-xs font-medium text-emerald-700">goal</span>
        </div>
        {date && <div className="text-sm text-slate-600">on track to arrive around <span className="font-semibold text-slate-900">{date}</span></div>}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        {confidence && <>Confidence: <span className="font-medium text-slate-600">{confidence}</span> (sharpens after each audit). </>}
        Your score updates every time an audit runs — recheck after your next audit to see movement.
      </p>
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
        <Link href="/onboarding" className="mt-4 inline-block rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700">Set up a business →</Link>
      </Card>
    );
  }
  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-rose-600">Could not load the dashboard.</p>;

  const s = data.series;
  const latest: SeriesPoint | undefined = s[s.length - 1];
  const score = repScore(latest?.goal_alignment ?? null);
  const goalText = (businesses.find((b) => b.id === businessId)?.goal || "").trim();

  const engVals = perEngine ? Object.values(perEngine.engines) : [];
  const grounded = engVals.filter((e) => e.grounded_rate);
  const groundedRate = grounded.length ? grounded.reduce((a, e) => a + (e.grounded_rate!.p ?? 0), 0) / grounded.length : null;

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

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {notifs && notifs.unread > 0 && (
        <Link href="/notifications" className="mb-4 flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm hover:bg-amber-100">
          <span className="font-medium text-amber-800">⚠ {notifs.unread} thing{notifs.unread === 1 ? "" : "s"} need your attention</span>
          <span className="text-amber-700">View →</span>
        </Link>
      )}

      <div className="mb-4"><OnboardingCard businessId={businessId} /></div>

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
          {/* live monitor — incidents + mentions at a glance */}
          <LiveMonitorStrip businessId={businessId} />

          {/* A — North Star goal */}
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
                    <span className="text-2xl font-bold text-slate-900">{score}</span><span className="text-xs font-medium text-slate-400">/100 today</span>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* B — plain-English verdict */}
          <VerdictBanner businessName={data.business.name} score={score} challenge={data.challenge} />

          {/* C — consolidated AI reputation score (drivers + sentiment donut nested in) */}
          <div>
            <ReputationHero
              goalAlignment={latest.goal_alignment}
              contestedRate={latest.contested_rate}
              ownedRate={latest.owned_rate}
              groundedRate={groundedRate}
              coverage={perEngine?.coverage ?? null}
              sentiment={sentimentData}
              asOf={latest.date}
            />
            <div className="mt-1 flex justify-end px-1"><ToneLegend /></div>
          </div>

          {/* D — action plan & progress (merged) */}
          <ActionPlanProgress woCounts={data.wo_counts} assetsN={data.assets_n} series={s} />

          {/* E — do this next (+approvals) beside biggest gaps */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <DoThisNext workOrders={workOrders} businessId={businessId} />
            <BiggestGaps gap={data.gap} />
          </div>

          {/* F — search performance: local + organic together */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <LocalSearchCard businessId={businessId} />
            <OrganicSearchCard businessId={businessId} />
          </div>

          {/* G — trajectory: projection + score-over-time + visibility */}
          <ProjectionStrip timeline={timeline as Json | undefined} />
          <Card>
            <div className="mb-3 text-base font-semibold tracking-tight text-slate-900">Your score over time (0–100)</div>
            <ScoreTrend series={s} goal={repScore((timeline as Json | undefined)?.dominance_target as number)} />
          </Card>
          <VisibilityTrendChart businessId={businessId} />

          {/* H — what AI is saying now + per-engine (per-engine behind see-more) */}
          <Card accent="bad">
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Worst things AI is saying right now</h3>
            <div className="mt-3"><WorstAnswers answers={answers} runId={latestRunId} limit={3} /></div>
            <div className="mt-4 border-t border-slate-100 pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Each AI assistant&apos;s score</div>
              <SeeMore label="See every engine">
                <EngineScoreStrip perEngine={perEngine} challenge={data.challenge} />
              </SeeMore>
            </div>
          </Card>

          {/* I — this month's work (value narrative, moved to the bottom) */}
          <ThisMonthPanel businessId={businessId} />

          {/* J — housekeeping: profile setup + the AI deep-dive link */}
          <ProfileTrackingCard biz={businesses.find((b) => b.id === businessId)} />
          <Card className="bg-slate-50/60">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-slate-600">Want the why — your primary challenge and how each AI assistant differs?</p>
              <Link href="/ai-overview" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">AI overview →</Link>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
