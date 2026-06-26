"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useLocalRankings, useCompare, useSiteAudit, useLocalSeoGoal, useTargetKeywords, useReviews, useReviewRequest, useOurContentImpact } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { MetricCard, EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { RunJobButton } from "@/components/RunJobButton";
import { LocalSeoGoalCard } from "@/components/LocalSeoGoalCard";
import { SearchPerformanceCard } from "@/components/SearchPerformanceCard";
import type { TargetKeyword, ReviewsSummary, ReviewRequestKit, OurContentImpact } from "@/lib/types";

function Stars({ rating }: { rating: number | null }) {
  if (rating == null) return <span className="text-slate-400">—</span>;
  const full = Math.round(rating);
  return <span className="text-amber-500">{"★".repeat(full)}<span className="text-slate-300">{"★".repeat(5 - full)}</span></span>;
}

function ReviewsCard({ businessId, canEdit, data }: { businessId: number | null; canEdit: boolean; data: ReviewsSummary | undefined }) {
  const cur = data?.current;
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Google reviews &amp; rating</h3>
          <p className="mt-0.5 text-xs text-slate-500">Your live Google star rating and review count — the biggest local-reputation signal (and what AI repeats about you).</p>
        </div>
        {canEdit && <RunJobButton businessId={businessId} jobType="ingest_gbp_reviews" label="Check reviews" variant="secondary" />}
      </div>
      {cur ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <div className="flex items-baseline gap-2"><span className="text-2xl font-bold text-slate-900">{cur.rating ?? "—"}</span><Stars rating={cur.rating} /></div>
            <div className="text-[11px] text-slate-500">{cur.review_count ?? "—"} reviews{data?.rating_delta != null && data.rating_delta !== 0 ? ` · ${data.rating_delta > 0 ? "+" : ""}${data.rating_delta} since last check` : ""}{data?.new_reviews != null && data.new_reviews > 0 ? ` · +${data.new_reviews} new` : ""}</div>
            {data?.history && data.history.length >= 2 && (
              <div className="mt-0.5 text-[11px] text-slate-400">
                Rating over time: {data.history.filter((h) => h.rating != null).map((h) => h.rating).join(" → ")}
              </div>
            )}
          </div>
          {data?.reviews && data.reviews.length > 0 && (
            <ul className="flex-1 space-y-1.5">
              {data.reviews.slice(0, 3).map((r, i) => (
                <li key={i} className="text-xs text-slate-600">
                  <Stars rating={r.rating} /> <span className="text-slate-400">{r.author || "Google user"}:</span> {(r.body || "").slice(0, 120)}{(r.body || "").length > 120 ? "…" : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No Google rating captured yet. Click “Check reviews” to pull it from Google.</p>
      )}
    </Card>
  );
}

const KW_GROUPS: { key: string; label: string }[] = [
  { key: "primary", label: "Primary" },
  { key: "local", label: "Local" },
  { key: "question", label: "Questions customers ask" },
  { key: "secondary", label: "Secondary" },
  { key: "long_tail", label: "Long-tail" },
];

function KeywordsCard({ businessId, canEdit, kws }: { businessId: number | null; canEdit: boolean; kws: TargetKeyword[] | undefined }) {
  const list = kws ?? [];
  const grouped = KW_GROUPS.map((g) => ({ ...g, items: list.filter((k) => (k.kind || "secondary") === g.key) })).filter((g) => g.items.length > 0);
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Keywords to rank for</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            The SEO terms to weave into your website, blog, social &amp; Google Business Profile — found from your site, your
            competitors, and real Google searches. These feed every draft we generate.
          </p>
        </div>
        {canEdit && <RunJobButton businessId={businessId} jobType="keyword_research" label="Find keywords" variant="secondary" />}
      </div>
      {list.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No keywords yet. Click “Find keywords” to research the terms you should target.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {grouped.map((g) => (
            <div key={g.key}>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{g.label}</div>
              <div className="flex flex-wrap gap-1.5">
                {g.items.map((k) => (
                  <span key={k.keyword} title={k.rationale || undefined}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{k.keyword}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// A small copy-to-clipboard button with transient "Copied ✓" feedback.
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

const NAP_LABELS: Record<string, string> = {
  name: "Business name",
  address: "Address",
  phone: "Phone",
  website: "Website",
  areas_served: "Areas served",
};

// "Get more reviews" — the write-review link + copy-paste SMS/email asks, plus the NAP block
// we keep consistent across directory citations (missing fields flagged in amber to fill in).
function ReviewRequestCard({ kit }: { kit: ReviewRequestKit | undefined }) {
  if (!kit) return null;
  const { link, templates, nap } = kit;
  const napRows: { key: string; label: string; value: string | null }[] = [
    { key: "name", label: NAP_LABELS.name, value: nap.name },
    { key: "address", label: NAP_LABELS.address, value: nap.address },
    { key: "phone", label: NAP_LABELS.phone, value: nap.phone },
    { key: "website", label: NAP_LABELS.website, value: nap.website },
    { key: "areas_served", label: NAP_LABELS.areas_served, value: nap.areas_served },
  ];
  const emailText = `Subject: ${templates.email_subject}\n\n${templates.email_body}`;
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Get more reviews</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            More 5-star reviews lift your local ranking — and they&apos;re what AI repeats about you. Send happy
            customers straight to your {link.source || "Google"} review page.
          </p>
        </div>
      </div>

      {/* write-review link (copyable) */}
      {link.write_review_url && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Your review link</div>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-md bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700 ring-1 ring-inset ring-slate-200">
              {link.write_review_url}
            </code>
            <CopyButton text={link.write_review_url} label="Copy link" />
            <a
              href={link.write_review_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-slate-50"
            >
              Open →
            </a>
          </div>
        </div>
      )}

      {/* copy-paste templates */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">Ask a customer:</span>
        <CopyButton text={templates.sms} label="Copy SMS" />
        <CopyButton text={emailText} label="Copy email" />
      </div>

      {/* NAP block — consistency across directory citations */}
      <div className="mt-4 border-t border-slate-100 pt-3">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Business listing details (NAP)
        </div>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
          {napRows.map((r) => {
            const missing = nap.missing_fields.includes(r.key);
            return (
              <div key={r.key} className="flex items-baseline justify-between gap-2 text-xs">
                <dt className="text-slate-500">{r.label}</dt>
                <dd className={`text-right font-medium ${missing ? "text-amber-600" : "text-slate-700"}`}>
                  {r.value || (missing ? "Missing — add this" : "—")}
                </dd>
              </div>
            );
          })}
        </dl>
        {nap.missing_fields.length > 0 && (
          <p className="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">
            {nap.consistency_note ||
              "Fill in the highlighted fields so your name, address & phone match exactly across every directory — inconsistent listings hurt local SEO."}
          </p>
        )}
      </div>
    </Card>
  );
}

const pct = (v: number | undefined | null) => `${Math.round((v ?? 0) * 100)}%`;

// One-line proof line: how many pages WE published are earning search traffic. The deep view
// (per-page clicks + sessions) lives on /search-performance. Hidden until something's published.
function OurContentImpactLine({ impact }: { impact: OurContentImpact | undefined }) {
  if (!impact || impact.totals.assets_published === 0) return null;
  const { assets_with_traffic, assets_published, our_content_clicks } = impact.totals;
  return (
    <Card accent="good">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Our content impact</h3>
          <p className="mt-0.5 text-sm text-slate-600">
            <span className="font-bold text-emerald-700">{assets_with_traffic} of {assets_published}</span> page
            {assets_published === 1 ? "" : "s"} we published {assets_with_traffic === 1 ? "is" : "are"} earning search
            traffic{our_content_clicks > 0 ? ` — ${our_content_clicks.toLocaleString()} Google clicks so far` : ""}.
          </p>
        </div>
        <Link href="/search-performance" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
          See proof →
        </Link>
      </div>
    </Card>
  );
}

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
  const { businessId, businesses, loading, canEdit } = useBusiness();
  const ranks = useLocalRankings(businessId);
  const compare = useCompare(businessId);
  const site = useSiteAudit(businessId);
  const goal = useLocalSeoGoal(businessId);
  const kws = useTargetKeywords(businessId);
  const revs = useReviews(businessId);
  const reviewKit = useReviewRequest(businessId);
  const impact = useOurContentImpact(businessId);

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
        {/* Get-to-page-1 goal (the local-SEO timeline) */}
        <LocalSeoGoalCard goal={goal.data} />

        {/* Real Google search traffic (clicks/impressions/CTR/position) — the measured proof */}
        <SearchPerformanceCard businessId={businessId} />

        {/* One-line content-impact proof (deep view lives on /search-performance) */}
        <OurContentImpactLine impact={impact.data} />

        {/* Google reviews & rating (the local-reputation signal) */}
        <ReviewsCard businessId={businessId} canEdit={canEdit} data={revs.data} />

        {/* Get more reviews — copy-paste ask + NAP consistency */}
        <ReviewRequestCard kit={reviewKit.data} />

        {/* Keywords to rank for (the SEO keyword-intelligence set) */}
        <KeywordsCard businessId={businessId} canEdit={canEdit} kws={kws.data} />

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
