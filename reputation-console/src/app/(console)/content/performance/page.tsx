"use client";

// Content Performance — the "content strategy advisor" that lives with the content, not the plan.
// It watches what your PUBLISHED content is doing between audits (which gaps it's moving, what to
// produce/publish next) so you're not flying blind until the next full audit. Same live data as the
// strategy advisor, framed around content performance.

import { useBusiness } from "@/lib/business";
import { useOurContentImpact } from "@/lib/hooks";
import { AdvisorPanel } from "@/components/AdvisorPanel";
import { CreateContentButton } from "@/components/CreateContentButton";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

function Stat({ k, value, sub, color }: { k: string; value: string; sub: string; color?: string }) {
  return (
    <div className="rounded-[12px] border border-line bg-card px-3.5 py-3">
      <div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[24px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}</div>
      <div className="mt-1 text-[11.5px] text-ink-3">{sub}</div>
    </div>
  );
}

export default function ContentPerformancePage() {
  const { businessId, businesses, loading } = useBusiness();
  const impact = useOurContentImpact(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Content · Performance" title="Content performance" />
        <EmptyState title="No data yet" why="Publish content and connect Search Console / Analytics to measure how it performs." cta={{ label: "Set up a business", href: "/onboarding" }} />
      </div>
    );
  }

  const t = impact.data?.totals;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader eyebrow="Content · Performance" title="Is our content working?"
          subtitle="Between audits, this tracks what your published content is doing — which gaps it's moving and what to produce or publish next. Your in-app content strategist." />
        <CreateContentButton className="inline-flex h-9 shrink-0 items-center rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white shadow-sm hover:bg-indigo-strong" />
      </div>

      {/* measured search/traffic proof for our own published content */}
      {t && (
        <div className="mb-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <Stat k="Published" value={String(t.assets_published)} sub="live pieces" />
          <Stat k="Earning traffic" value={String(t.assets_with_traffic)} sub="pieces with clicks/sessions" color="var(--good)" />
          <Stat k="Search clicks" value={t.our_content_clicks.toLocaleString()} sub="to our content (GSC)" />
          <Stat k="Sessions" value={t.our_content_sessions.toLocaleString()} sub="to our content (GA)" />
        </div>
      )}

      {/* the advisor, framed for content */}
      <AdvisorPanel businessId={businessId} framing="content" />

      <Card className="mt-5">
        <p className="text-[13px] text-ink-3">
          Numbers come from Search Console + Analytics for the specific pages you published. Connect
          them under <a href="/integrations" className="font-semibold text-indigo hover:underline">Integrations</a> for
          per-page click and session data; the next full audit measures AI-visibility lift.
        </p>
      </Card>
    </div>
  );
}
