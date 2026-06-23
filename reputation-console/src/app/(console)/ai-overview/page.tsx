"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useRunAnswers } from "@/lib/hooks";
import { ReputationHero } from "@/components/ReputationHero";
import { VerdictBanner } from "@/components/VerdictBanner";
import { WorstAnswers } from "@/components/WorstAnswers";
import { EngineScoreStrip } from "@/components/EngineScoreStrip";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { repScore } from "@/lib/repScore";

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

// Section landing page for "AI Visibility" — the AI-only rollup that the main Dashboard
// links into. Reuses the reputation hero + worst-answers + per-engine, then deep-links to
// the detailed AI pages.
export default function AiOverviewPage() {
  const { businessId, businesses, loading } = useBusiness();
  const { data, isLoading } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: perEngine } = usePerEngine(businessId, latestRunId);
  const { data: answers } = useRunAnswers(businessId, latestRunId);

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
  const score = repScore(latest?.goal_alignment ?? null);
  const engVals = perEngine ? Object.values(perEngine.engines) : [];
  const grounded = engVals.filter((e) => e.grounded_rate);
  const groundedRate = grounded.length
    ? grounded.reduce((a, e) => a + (e.grounded_rate!.p ?? 0), 0) / grounded.length
    : null;

  return (
    <div>
      <PageHeader
        eyebrow="AI Visibility"
        title="AI overview"
        subtitle="How AI assistants portray you — your reputation score, the drivers behind it, and what they're saying right now."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {!latest ? (
        <EmptyState
          title="No audit has run yet"
          why="An audit checks what ChatGPT, Claude, Perplexity, and Gemini say about your business."
          produces="Your reputation score, drivers, and the worst answers appear here once it finishes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-6">
          <VerdictBanner businessName={data.business.name} score={score} challenge={data.challenge} />

          <ReputationHero
            goalAlignment={latest.goal_alignment}
            contestedRate={latest.contested_rate}
            ownedRate={latest.owned_rate}
            groundedRate={groundedRate}
            coverage={perEngine?.coverage ?? null}
            woCounts={data.wo_counts}
            assetsN={data.assets_n}
          />

          <Card accent="bad">
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Worst things AI is saying right now</h3>
            <div className="mt-3">
              <WorstAnswers answers={answers} runId={latestRunId} limit={3} />
            </div>
            <div className="mt-4 border-t border-slate-100 pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Each AI assistant&apos;s score</div>
              <EngineScoreStrip perEngine={perEngine} challenge={data.challenge} />
            </div>
          </Card>

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
