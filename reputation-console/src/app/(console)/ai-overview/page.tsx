"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useTimeline } from "@/lib/hooks";
import { PrimaryChallengeCard } from "@/components/PrimaryChallengeCard";
import { PerEnginePanel } from "@/components/PerEnginePanel";
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

          {/* How each assistant differs */}
          {perEngine && Object.keys(perEngine.engines).length > 0 && <PerEnginePanel data={perEngine} />}

          {/* AI reputation trend over time */}
          <Card>
            <div className="mb-3 text-base font-semibold tracking-tight text-slate-900">Your AI reputation score over time (0–100)</div>
            <ScoreTrend series={s} goal={repScore((timeline as Json | undefined)?.dominance_target as number)} />
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
