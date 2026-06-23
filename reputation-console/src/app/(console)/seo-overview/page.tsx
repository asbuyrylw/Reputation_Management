"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useLocalRankings, useCompare, useSiteAudit } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { MetricCard, EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";

const pct = (v: number | undefined | null) => `${Math.round((v ?? 0) * 100)}%`;

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

// Section landing page for "Search & SEO" — the traditional-search rollup: local Google
// rankings scorecard, competitor standing, and site-audit freshness, with deep links.
export default function SeoOverviewPage() {
  const { businessId, businesses, loading } = useBusiness();
  const ranks = useLocalRankings(businessId);
  const compare = useCompare(businessId);
  const site = useSiteAudit(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Search & SEO" title="SEO overview" />
        <EmptyState
          title="No data yet"
          why="Set up a business and run a local rank check to see your search visibility."
          cta={{ label: "Set up a business", href: "/onboarding" }}
        />
      </div>
    );
  }
  if (ranks.isLoading) return <Spinner />;

  const s = ranks.data?.summary ?? null;
  const c = compare.data ?? {};
  const subjectRank = c.subject_rank ?? null;
  const fieldSize = c.field_size ?? null;
  const siteAsOf = site.data?.created_at ? new Date(site.data.created_at).toLocaleDateString() : null;

  return (
    <div>
      <PageHeader
        eyebrow="Search & SEO"
        title="SEO overview"
        subtitle="Your traditional search visibility — local Google rankings, how you stack up against rivals, and your site's technical health."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      <div className="space-y-6">
        {/* Local rankings scorecard */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Local Google rankings</div>
            <Link href="/local-seo" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">Details →</Link>
          </div>
          {s ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetricCard
                label="On page one"
                value={pct(s.page_one_rate)}
                tone={s.page_one_rate >= 0.5 ? "good" : "bad"}
                whyItMatters="Share of local searches where you appear on Google's first page."
              />
              <MetricCard
                label="In the map pack"
                value={pct(s.local_pack_rate)}
                tone={s.local_pack_rate >= 0.5 ? "good" : "bad"}
                whyItMatters="Share of searches where you show in Google's local 3-pack."
              />
              <MetricCard
                label="Avg. position"
                value={s.avg_organic_rank == null ? "—" : `#${s.avg_organic_rank}`}
                tone={s.avg_organic_rank != null && s.avg_organic_rank <= 10 ? "good" : "bad"}
                whyItMatters={`Average Google rank where you appear (${s.ranked_queries} of ${s.queries} searches).`}
              />
            </div>
          ) : (
            <Card>
              <p className="text-sm text-slate-600">
                No local rank snapshot yet.{" "}
                <Link href="/local-seo" className="font-medium text-indigo-600 hover:text-indigo-700">Run a local rank check →</Link>
              </p>
            </Card>
          )}
        </div>

        {/* Competitor standing */}
        <Card accent={subjectRank != null && fieldSize != null && subjectRank <= Math.ceil(fieldSize / 2) ? "good" : "bad"}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-slate-900">Competitive standing (AI answers)</h3>
              {subjectRank != null ? (
                <p className="mt-1 text-sm text-slate-600">
                  AI surfaces you at{" "}
                  <span className="font-bold text-slate-900">rank {subjectRank} of {fieldSize}</span> for category questions.
                </p>
              ) : (
                <p className="mt-1 text-sm text-slate-600">No competitor benchmark yet.</p>
              )}
            </div>
            <Link href="/competitors" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">Compare →</Link>
          </div>
        </Card>

        {/* Site technical health */}
        <Card>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-slate-900">Site &amp; technical SEO</h3>
              <p className="mt-1 text-sm text-slate-600">
                {siteAsOf ? `Last crawled ${siteAsOf}. Review technical issues and on-page coverage.` : "No site crawl yet — run one to surface technical SEO issues."}
              </p>
            </div>
            <Link href="/seo" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">Open →</Link>
          </div>
        </Card>

        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Go deeper</div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <LinkCard href="/seo" title="Site / technical SEO" desc="On-page + technical issues." />
            <LinkCard href="/local-seo" title="Local rankings" desc="Google organic + map pack." />
            <LinkCard href="/competitors" title="Competitors" desc="Benchmark vs. your rivals." />
          </div>
        </div>
      </div>
    </div>
  );
}
