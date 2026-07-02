"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAuth } from "@/lib/auth";
import { OperatorHome } from "@/components/OperatorHome";
import {
  useDashboard, usePerEngine, useRunAnswers, useWorkOrders, useTimeline, useNotifications,
  useLocalRankings, useLocalRankTrend, useLocalSeoGoal, useActivitySummary, useGscSummary, useIncidents, useMentions, useApprovalQueue,
  useCompare, useSiteHealthTrend,
} from "@/lib/hooks";
import { ReputationHero } from "@/components/ReputationHero";
import { GoalBanner, ScoreHero, TwoFronts, TwoGoals, DoThisNext as DoNextV2, StandingAtAGlance, SecHead } from "@/components/DashboardV2";
import type { FrontData, ActionItem } from "@/components/DashboardV2";
import { MetricTrend } from "@/components/MetricTrend";
import { ScoreTrend } from "@/components/ScoreTrend";
import { VerdictBanner } from "@/components/VerdictBanner";
import { ResultsProofCard } from "@/components/ResultsProofCard";
import { WorstAnswers } from "@/components/WorstAnswers";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import OnboardingCard from "@/components/OnboardingCard";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import VisibilityTrendChart from "@/components/VisibilityTrendChart";
import { Card, PageHeader, SectionCard, Spinner } from "@/components/ui";
import { EmptyState, ToneLegend, DataSection } from "@/components/primitives";
import { repScore, dashboardScore } from "@/lib/repScore";
import type { SeriesPoint, WorkOrder, Business } from "@/lib/types";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string; fix?: string; addressed_by?: string };

const pct = (v: number | null | undefined) => `${Math.round((v ?? 0) * 100)}%`;

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
                {w.fix && (
                  <div className="mt-1.5 text-sm leading-relaxed text-emerald-700">
                    <span className="font-semibold">Fix:</span> {w.fix}
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
function ActionPlanProgress({ woCounts, assetsN, delta }: { woCounts: Record<string, number>; assetsN: number; delta: number | null }) {
  const total = Object.values(woCounts).reduce((a, b) => a + b, 0);
  const done = (woCounts.done ?? 0) + (woCounts.verified ?? 0);
  const inProg = (woCounts.in_progress ?? 0) + (woCounts.in_review ?? 0) + (woCounts.review ?? 0);
  const open = Math.max(0, total - done - inProg);
  const woPct = total ? Math.round((done / total) * 100) : 0;
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
            <div className="text-xs text-slate-500">score since you started</div>
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
  const { data: trend } = useLocalRankTrend(businessId);
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
      {trend && trend.length >= 2 && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <MetricTrend data={trend} label="Local visibility over time" suffix="%" hint="Share of your tracked local searches ranking on page 1, per check." />
        </div>
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

export default function DashboardPage() {
  const { businessId, businesses, loading: bizLoading } = useBusiness();
  const { user } = useAuth();
  const [workView, setWorkView] = useState(false);
  const { data, isLoading, error } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: perEngine } = usePerEngine(businessId, latestRunId);
  const { data: answers } = useRunAnswers(businessId, latestRunId);
  const { data: workOrders } = useWorkOrders(businessId);
  const { data: timeline } = useTimeline(businessId);
  const { data: localGoal } = useLocalSeoGoal(businessId);
  const { data: notifs } = useNotifications(businessId);
  // v2 "two fronts" + "standing at a glance" + "do this next" data.
  const { data: compare } = useCompare(businessId);
  const { data: localRankings } = useLocalRankings(businessId);
  const { data: approvals } = useApprovalQueue(businessId);
  const { data: gsc } = useGscSummary(businessId);
  const { data: siteHealth } = useSiteHealthTrend(businessId);

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
  // Admins/operators land on the OWNER dashboard by default; the work queue is opt-in
  // (a link in the header switches to it).
  const isOperator = user?.role === "admin";
  if (isOperator && workView) {
    return <OperatorHome businessId={businessId} onViewOwner={() => setWorkView(false)} />;
  }

  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-rose-600">Could not load the dashboard.</p>;

  const s = data.series;
  const latest: SeriesPoint | undefined = s[s.length - 1];
  const { score, deltaVsLast, deltaSinceStart } = dashboardScore(s);
  const goalScore = repScore((timeline as Json | undefined)?.dominance_target as number);
  const goalText = (businesses.find((b) => b.id === businessId)?.goal || "").trim();

  // v2 dashboard props — AI projection ETA, local goal ETA, and the worst-scoring answers.
  const aiExp = ((timeline as Json | undefined)?.projection as Json | undefined)?.expected as Json | undefined;
  const aiDate = aiExp?.target_date as string | undefined;
  const aiMonths = (aiExp?.months as number | undefined) ?? null;
  const localExpDate = localGoal?.projection?.expected?.target_date;
  const worstAnswers = (answers ?? [])
    .filter((a) => !a.failed && a.goal_alignment != null)
    .sort((a, b) => (a.goal_alignment ?? 0) - (b.goal_alignment ?? 0))
    .slice(0, 2);

  // Open tasks ranked by predicted AI-score points — powers "Do this next" + each front's "Do next".
  const openWOs = (workOrders ?? [])
    .filter((w) => w.status !== "done" && w.status !== "verified" && w.status !== "cancelled" && !w.superseded)
    .sort((a, b) => (b.predicted_ai_points ?? 0) - (a.predicted_ai_points ?? 0));
  const topActions: ActionItem[] = openWOs.slice(0, 3).map((w, i) => ({
    rank: i + 1,
    impact: w.predicted_ai_points ?? null,
    title: w.title ?? "Untitled task",
    desc: (w.why_helps_ai_rep || w.why_helps_seo || w.instruction || "A prioritized move in your plan.").slice(0, 130),
    cat: [w.area, w.why_helps_ai_rep ? "AI" : w.why_helps_seo ? "SEO" : null].filter(Boolean).join(" · ") || "Task",
  }));
  const aiTopWO = openWOs.find((w) => w.why_helps_ai_rep) ?? openWOs[0];
  const seoTopWO = openWOs.find((w) => w.why_helps_seo || (w.area && /website|seo|local|schema|blog/i.test(w.area)));
  const approvalsCount = approvals?.items?.length ?? 0;
  const openTasksCount = openWOs.length;
  const gscConnected = !!(gsc?.has_data || gsc?.collecting);
  const siteReadiness = siteHealth?.length ? siteHealth[siteHealth.length - 1].score : null;
  const siteReadinessFirst = siteHealth?.length ? siteHealth[0].score : null;
  const localSum = localRankings?.summary ?? null;

  const aiFront: FrontData = {
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></svg>,
    title: "AI Visibility",
    sub: "How AI assistants answer about you",
    score,
    rows: [
      { tone: "good", k: "What's working", v: <>Owned sources cited <b>{pct(latest.owned_rate)}</b>{latest.contested_rate != null ? <> · contested just <b>{pct(latest.contested_rate)}</b></> : null}.</> },
      deltaVsLast != null && Math.abs(deltaVsLast) >= 0.5
        ? { tone: deltaVsLast >= 0 ? "trend" : "alert", k: "Trending", v: <><b>{deltaVsLast >= 0 ? "Up" : "Down"} {Math.abs(deltaVsLast)} pts</b> at the last audit.</> }
        : { tone: "trend", k: "Trending", v: "Holding steady since the last audit." },
      { tone: "next", k: "Do next", v: aiTopWO?.title ?? "Run an audit to generate your plan." },
    ],
    href: "/ai-overview",
    linkLabel: "Open AI Visibility",
  };
  const seoFront: FrontData = {
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>,
    title: "Search & SEO",
    sub: "AI-crawler readiness of your site",
    score: siteReadiness,
    rows: [
      siteReadiness != null && siteReadinessFirst != null && siteReadiness > siteReadinessFirst
        ? { tone: "good", k: "What's working", v: <>Crawler readiness <b>up +{Math.round(siteReadiness - siteReadinessFirst)}</b> since first crawl.</> }
        : { tone: "good", k: "What's working", v: "Your site is discovered and being parsed." },
      { tone: "alert", k: "Biggest gap", v: <>You rank page 1 for <b>{localSum ? pct(localSum.page_one_rate) : "—"}</b> of local searches.</> },
      { tone: "next", k: "Do next", v: seoTopWO?.title ?? "Add LocalBusiness + Organization schema, then connect Search Console." },
    ],
    href: "/seo-overview",
    linkLabel: "Open Search & SEO",
  };

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
      {isOperator && (
        <button
          onClick={() => setWorkView(true)}
          className="mb-3 text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          Open your work queue →
        </button>
      )}
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
          {/* v2 HERO — dark org-goal banner, then the score gauge + worst answers side by side. */}
          <GoalBanner goalText={goalText || undefined} aiTarget={goalScore} aiDate={aiDate} localDate={localExpDate} />
          <ScoreHero
            score={score}
            delta={deltaVsLast}
            goalScore={goalScore}
            aiDate={aiDate}
            aiMonths={aiMonths}
            worst={worstAnswers}
          />

          {/* live monitor — incidents + mentions at a glance */}
          <LiveMonitorStrip businessId={businessId} />

          {/* v2 — your two fronts: AI Visibility + Search & SEO. */}
          <TwoFronts ai={aiFront} seo={seoFront} />

          {/* v2 — your two goals: AI reputation + local page-1. */}
          <TwoGoals score={score} goalScore={goalScore} aiDate={aiDate} aiMonths={aiMonths} localGoal={localGoal} />

          {/* v2 — do this next: top-3 actions + plan bar. */}
          <DoNextV2 actions={topActions} approvalsCount={approvalsCount} openTasksCount={openTasksCount} />

          {/* v2 — your standing at a glance: share of voice, rivals, local search. */}
          <StandingAtAGlance
            ownedRate={latest.owned_rate}
            contestedRate={latest.contested_rate}
            compare={compare}
            local={localSum}
            gscConnected={gscConnected}
          />

          {/* v2 — how you're trending. */}
          <div>
            <SecHead title="How you're trending" note="your score & visibility over time" />
            <div className="space-y-5">
              <Card>
                <div className="mb-3 text-base font-semibold tracking-tight text-ink">Your score over time (0–100)</div>
                <ScoreTrend series={s} goal={goalScore} projected={goalScore} />
              </Card>
              <VisibilityTrendChart businessId={businessId} />
            </div>
          </div>

          {/* Results & Proof — tactic impact */}
          <ResultsProofCard businessId={businessId} currentScore={score} />

          {/* Deeper detail — drivers, sentiment, search performance, worst answers, task & gap detail, per-engine. */}
          <DataSection title="Full breakdown & detail" headline="Drivers, sentiment, search performance, the worst answers with their fixes, your task & gap detail, and per-engine scores." detailsLabel="Show full breakdown">
            <div className="space-y-6">
              {/* drivers + sentiment + verdict */}
              <div className="space-y-3">
                <ReputationHero
                  goalAlignment={latest.goal_alignment}
                  contestedRate={latest.contested_rate}
                  ownedRate={latest.owned_rate}
                  groundedRate={groundedRate}
                  coverage={perEngine?.coverage ?? null}
                  sentiment={sentimentData}
                  asOf={latest.date}
                  delta={deltaVsLast}
                />
                <VerdictBanner businessName={data.business.name} score={score} challenge={data.challenge} compact />
                <div className="flex justify-end px-1"><ToneLegend /></div>
              </div>

              {/* search performance */}
              <section>
                <h2 className="mb-3 text-sm font-semibold tracking-tight text-slate-900">
                  Search performance <span className="font-normal text-slate-400">— your Google visibility</span>
                </h2>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <LocalSearchCard businessId={businessId} />
                  <OrganicSearchCard businessId={businessId} />
                </div>
              </section>

              {/* fix the worst things — actionable, with fixes */}
              {answers && answers.some((a) => !a.failed && a.goal_alignment != null) && (
                <section>
                  <h2 className="mb-1 text-sm font-semibold tracking-tight text-slate-900">
                    Fix the worst things AI is saying <span className="font-normal text-slate-400">— your highest-ROI moves</span>
                  </h2>
                  <p className="mb-3 text-xs text-slate-500">
                    The lowest-scoring answers from your latest audit — each paired with the specific action that fixes it.
                  </p>
                  <Card accent="bad">
                    <WorstAnswers
                      answers={answers}
                      runId={latestRunId}
                      limit={4}
                      weakQueries={data.gap?.weak_queries as WeakQuery[] | undefined}
                      workOrders={workOrders}
                      showFix
                    />
                    <div className="mt-3 border-t border-slate-100 pt-3 text-right">
                      <Link href="/next-steps" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
                        See your full prioritized plan →
                      </Link>
                    </div>
                  </Card>
                </section>
              )}

              {/* task detail beside biggest gaps */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <DoThisNext workOrders={workOrders} businessId={businessId} />
                <BiggestGaps gap={data.gap} />
              </div>

              {/* per-engine AI scores */}
              <section className="space-y-2">
                <h2 className="text-sm font-semibold tracking-tight text-slate-900">Per-engine AI scores</h2>
                <Card>
                  <EngineScoreStrip perEngine={perEngine} challenge={data.challenge} />
                </Card>
              </section>
            </div>
          </DataSection>

          {/* 7) Your progress — action plan + this month's work, combined, at the bottom */}
          <section className="space-y-4">
            <h2 className="text-sm font-semibold tracking-tight text-slate-900">Your progress</h2>
            <ActionPlanProgress woCounts={data.wo_counts} assetsN={data.assets_n} delta={deltaSinceStart} />
            <ThisMonthPanel businessId={businessId} />
          </section>

          {/* 8) Setup & housekeeping — collapsed at the very bottom */}
          <DataSection title="Setup & housekeeping" headline="What we're tracking for you, and the deeper AI breakdown." detailsLabel="Show setup & housekeeping">
            <div className="space-y-6">
              <ProfileTrackingCard biz={businesses.find((b) => b.id === businessId)} />
              <Card className="bg-slate-50/60">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm text-slate-600">Want the why — your primary challenge and how each AI assistant differs?</p>
                  <Link href="/ai-overview" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">AI overview →</Link>
                </div>
              </Card>
            </div>
          </DataSection>
        </div>
      )}
    </div>
  );
}
