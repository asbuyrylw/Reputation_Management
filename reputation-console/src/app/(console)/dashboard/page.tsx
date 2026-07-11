"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAuth } from "@/lib/auth";
import { OperatorHome } from "@/components/OperatorHome";
import { AdvisorPanel } from "@/components/AdvisorPanel";
import {
  useDashboard, useRunAnswers, useWorkOrders, useTimeline, useNotifications,
  useLocalRankings, useLocalSeoGoal, useActivitySummary, useGscSummary, useIncidents, useMentions, useApprovalQueue,
  useCompare, useSiteHealthTrend, useShareOfVoice, useRoadmap,
} from "@/lib/hooks";
import { GoalBanner, ScoreHero, TwoFronts, TwoGoals, DoThisNext as DoNextV2, StandingAtAGlance, SecHead } from "@/components/DashboardV2";
import type { FrontData, ActionItem } from "@/components/DashboardV2";
import { ScoreTrend } from "@/components/ScoreTrend";
import { ResultsProofCard } from "@/components/ResultsProofCard";
import OnboardingCard from "@/components/OnboardingCard";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { RunPipelineButton } from "@/components/RunPipelineButton";
import { FreshnessChip } from "@/components/FreshnessChip";
import { PipelinePrecheckBanner } from "@/components/PipelinePrecheckBanner";
import VisibilityTrendChart from "@/components/VisibilityTrendChart";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { repScore, dashboardScore } from "@/lib/repScore";
import type { SeriesPoint, Business } from "@/lib/types";

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

// Compact setup indicator for the header — replaces the old bottom "Setup & housekeeping" section
// with a small notification-style chip. Only appears when the profile is incomplete; links to the
// one place to finish it. Green check when everything's set.
function SetupBell({ biz }: { biz?: Business }) {
  if (!biz) return null;
  const fields = [biz.geo, biz.services, biz.industry, biz.goal, biz.contested_terms, biz.regulatory_profile?.firm_type];
  const filled = fields.filter((v) => (v ?? "").toString().trim()).length;
  const missing = fields.length - filled;
  const pctSet = Math.round((filled / fields.length) * 100);
  if (missing === 0) return null;
  return (
    <Link href="/account" title={`${missing} profile field${missing === 1 ? "" : "s"} missing — finish setup to unlock more accuracy`}
      className="flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-100">
      <span aria-hidden>⚙</span> {pctSet}% set up
    </Link>
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
  const { businessId, businesses, loading: bizLoading, canEdit } = useBusiness();
  const { user } = useAuth();
  const [workView, setWorkView] = useState(false);
  const { data, isLoading, error } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: answers } = useRunAnswers(businessId, latestRunId);
  const { data: workOrders } = useWorkOrders(businessId);
  const { data: roadmap } = useRoadmap(businessId);
  const { data: timeline } = useTimeline(businessId);
  const { data: localGoal } = useLocalSeoGoal(businessId);
  const { data: notifs } = useNotifications(businessId);
  // v2 "two fronts" + "standing at a glance" + "do this next" data.
  const { data: compare } = useCompare(businessId);
  const { data: localRankings } = useLocalRankings(businessId);
  const { data: approvals } = useApprovalQueue(businessId);
  const { data: gsc } = useGscSummary(businessId);
  const { data: siteHealth } = useSiteHealthTrend(businessId);
  const { data: sov } = useShareOfVoice(businessId);

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
  const { score, deltaVsLast } = dashboardScore(s);
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
  // Same server-ranked source (impact/effort ROI) the task board and Strategy overview use for
  // "Today's focus" — previously this was a THIRD independent client-side sort by predicted_ai_
  // points, which is why the same handful of tasks kept showing up reordered on every page.
  // Intersect the roadmap ranking with the actual open tasks so "Do this next" can never surface
  // something that isn't in the task list (the "making things up" fix), then take the top 3.
  const woById = new Map(openWOs.map((w) => [w.id, w]));
  const topActions: ActionItem[] = (roadmap?.items ?? [])
    .filter((item) => woById.has(item.wo_id))
    .slice(0, 3)
    .map((item, i) => {
      const w = woById.get(item.wo_id)!;
      return {
        rank: i + 1,
        impact: item.expected_points ?? null,
        title: item.title || w.title || "Untitled task",
        desc: (w.why_helps_ai_rep || w.why_helps_seo || item.why || w.instruction || "A prioritized move in your plan.").slice(0, 130),
        cat: [item.area, item.expected_points > 0 ? "AI" : item.seo_impact ? "SEO" : null].filter(Boolean).join(" · ") || "Task",
        href: `/content/work-orders#wo-${item.wo_id}`,
      };
    });
  const aiTopWO = openWOs.find((w) => w.why_helps_ai_rep) ?? openWOs[0];
  // Exclude the AI top task so the two fronts' "Do next" never show the identical task.
  const seoTopWO = openWOs.find((w) => w.id !== aiTopWO?.id && (w.why_helps_seo || (w.area && /website|seo|local|schema|blog/i.test(w.area))));
  const approvalsCount = approvals?.items?.length ?? 0;
  const openTasksCount = openWOs.length;
  const gscConnected = !!(gsc?.has_data || gsc?.collecting);
  const siteReadiness = siteHealth?.length ? siteHealth[siteHealth.length - 1].score : null;
  const siteReadinessFirst = siteHealth?.length ? siteHealth[0].score : null;
  const localSum = localRankings?.summary ?? null;

  const aiFront: FrontData = {
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></svg>,
    iconCls: "bg-indigo-050 text-indigo",
    title: "AI Visibility",
    sub: "How AI assistants answer about you",
    score,
    rows: [
      { tone: "good", k: "What's working", v: <>Owned sources cited <b>{pct(latest?.owned_rate)}</b>{latest?.contested_rate != null ? <> · contested just <b>{pct(latest.contested_rate)}</b></> : null}.</> },
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
    iconCls: "bg-sky-50 text-sky-600",
    title: "Search & SEO",
    sub: "AI-crawler readiness of your site",
    score: siteReadiness,
    rows: [
      siteReadiness != null && siteReadinessFirst != null && siteReadiness > siteReadinessFirst
        ? { tone: "good", k: "What's working", v: <>Crawler readiness <b>up +{Math.round(siteReadiness - siteReadinessFirst)}</b> since first crawl.</> }
        : { tone: "good", k: "What's working", v: "Your site is discovered and being parsed." },
      // Only flag red when page-1 rate is genuinely low; otherwise it's informational, not an alarm.
      localSum && localSum.page_one_rate >= 0.5
        ? { tone: "trend", k: "Local search", v: <>You rank page 1 for <b>{pct(localSum.page_one_rate)}</b> of local searches.</> }
        : { tone: "alert", k: "Biggest gap", v: <>You rank page 1 for <b>{localSum ? pct(localSum.page_one_rate) : "—"}</b> of local searches.</> },
      { tone: "next", k: "Do next", v: seoTopWO?.title ?? "Add LocalBusiness + Organization schema, then connect Search Console." },
    ],
    href: "/seo-overview",
    linkLabel: "Open Search & SEO",
  };

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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          eyebrow="Overview"
          title={`Dashboard — ${data.business.name}`}
          subtitle="Where you stand with AI assistants, what to do next, and when it'll improve."
        />
        {/* Always-on freshness + setup indicator + owner-safe one-click refresh (never sends owners to /admin). */}
        <div className="flex shrink-0 items-center gap-2 pt-1">
          <SetupBell biz={businesses.find((b) => b.id === businessId)} />
          <FreshnessChip asOf={latest?.date} />
          {canEdit && <RunPipelineButton key={businessId} businessId={businessId} />}
        </div>
      </div>

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {/* Connect-your-data nudge before spending on a run (self-hides once connected). */}
      {canEdit && <PipelinePrecheckBanner businessId={businessId} />}

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
          cta={{ label: "Run your first audit", href: "/runs" }}
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
            workOrders={workOrders}
            weak={data.gap?.weak_queries as WeakQuery[] | undefined}
          />

          {/* live monitor — incidents + mentions at a glance */}
          <LiveMonitorStrip businessId={businessId} />

          {/* v2 — your two fronts: AI Visibility + Search & SEO. */}
          <TwoFronts ai={aiFront} seo={seoFront} />

          {/* v2 — your two goals: AI reputation + local page-1. */}
          <TwoGoals score={score} goalScore={goalScore} aiDate={aiDate} aiMonths={aiMonths} localGoal={localGoal} />

          {/* Strategy Advisor (PDCA) — is the plan working + the single next move, live-wired. */}
          <AdvisorPanel businessId={businessId} compact />

          {/* v2 — do this next: top-3 actions + plan bar. */}
          <DoNextV2 actions={topActions} approvalsCount={approvalsCount} openTasksCount={openTasksCount} />

          {/* v2 — your standing at a glance: share of voice, rivals, local search. */}
          <StandingAtAGlance
            sov={sov}
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

          {/* This month's work — the client-facing value narrative. (The old "Full breakdown &
              detail" and the duplicate action-plan bar were removed: the score + worst answers live
              in the hero above, and the deep breakdowns live on their own hub pages — AI overview,
              Search & SEO, Gaps — so the dashboard stays a summary, not a second copy of everything.) */}
          <ThisMonthPanel businessId={businessId} />
        </div>
      )}
    </div>
  );
}
