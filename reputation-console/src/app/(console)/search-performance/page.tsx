"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import {
  useGscSummary,
  useGscQueries,
  useGscPages,
  useGscOpportunities,
  useGscRoi,
  useGaSummary,
  useGaChannels,
  useOurContentImpact,
} from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { MetricCard } from "@/components/primitives";
import GscTrendChart from "@/components/GscTrendChart";
import GaTrendChart from "@/components/GaTrendChart";
import { GscQueryTable, GscPageTable } from "@/components/GscQueryTable";
import type { GscOpportunity, GscRoi, GaSummary, GaChannel, OurContentImpact } from "@/lib/types";

const fmtNum = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
const fmtCtr = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const fmtPos = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));
const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const fmtUsd = (v: number) =>
  v.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

// Striking-distance queries: lots of impressions, ranking just off page one. Each deep-links
// to brief generation so a small content push can win the click.
function OpportunitiesCard({ opps }: { opps: GscOpportunity[] | undefined }) {
  const rows = opps ?? [];
  return (
    <Card accent="info">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Striking-distance opportunities</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Searches where you already show up but rank just off page one — a little fresh content could win these clicks.
          </p>
        </div>
        <Link href="/content/briefs" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
          Plan content →
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No striking-distance queries yet — they appear once you have enough search history.</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-50">
          {rows.map((o) => (
            <li key={o.query} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-800">{o.query}</div>
                <div className="text-[11px] text-slate-500">
                  {fmtNum(o.impressions)} impressions · CTR {fmtCtr(o.ctr)} · avg position{" "}
                  <span className="font-semibold text-slate-700">{fmtPos(o.position)}</span>
                </div>
              </div>
              <Link
                href={`/content/briefs?q=${encodeURIComponent(o.query)}`}
                className="shrink-0 rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-slate-50"
              >
                Write a brief →
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// Equivalent-ad-value panel: the BIG number is total clicks; the smaller, distinct number is
// the subset earned by content we published. The paid-equivalent figure is an explicit ESTIMATE.
function EquivalentValueCard({ roi }: { roi: GscRoi | undefined }) {
  if (!roi || !roi.has_data) return null;
  return (
    <Card className="bg-linear-to-br from-emerald-50/50 to-white">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold tracking-tight text-slate-900">What this traffic is worth</h3>
        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700 ring-1 ring-inset ring-amber-200">
          estimate
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Roughly what it would cost to buy the same clicks through Google Ads. This is a labeled estimate, not a billed amount.
      </p>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-[32px] font-bold leading-none tracking-tight text-emerald-600">
          {fmtUsd(roi.equivalent_ads_value)}
        </span>
        <span className="text-xs font-medium text-slate-500">est. equivalent ad spend · last {roi.window_days} days</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-slate-100 pt-3">
        <div>
          <div className="text-2xl font-bold text-slate-900">{fmtNum(roi.latest_clicks)}</div>
          <div className="text-[11px] text-slate-500">total clicks earned from search</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-emerald-600">{fmtNum(roi.our_content_clicks)}</div>
          <div className="text-[11px] text-slate-500">
            clicks earned by content we published{roi.our_content_pages ? ` · ${roi.our_content_pages} page${roi.our_content_pages === 1 ? "" : "s"}` : ""}
          </div>
        </div>
      </div>
      <p className="mt-3 text-[11px] leading-snug text-slate-400">
        “Clicks earned by content we published” is a smaller, distinct subset of total clicks — the share directly
        attributable to pages produced for you.
      </p>
    </Card>
  );
}

// Clean empty state for the not-connected / still-collecting cases.
function GscEmptyState({ collecting }: { collecting: boolean }) {
  return (
    <Card accent="info">
      {collecting ? (
        <>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Collecting search data…</h3>
          <p className="mt-1 text-sm text-slate-600">
            Google Search Console is connected and we&apos;ve picked your property — we&apos;re importing your history now.
            Your clicks, impressions and rankings will appear here shortly.
          </p>
        </>
      ) : (
        <>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Connect Google Search Console</h3>
          <p className="mt-1 text-sm text-slate-600">
            Import real Google clicks, impressions and ranking data — the proof your SEO is working. It only takes a
            minute, and Search Console keeps months of history.
          </p>
          <Link
            href="/integrations"
            className="mt-3 inline-block rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
          >
            Connect Google Search Console →
          </Link>
        </>
      )}
    </Card>
  );
}

// =====================================================================================
// "Behavior & conversions" (GA4) — what visitors DO after they arrive. KPI tiles with
// prior-period deltas + a channel-mix breakdown + a sessions trend. Clean connect/collecting
// empty-state. Conversions only mean anything if the client configured GA4 conversion events,
// so we note that subtly under the conversions tile.
// =====================================================================================

// A horizontal bar list for the acquisition-channel mix (share of sessions per channel).
function ChannelMix({ channels }: { channels: GaChannel[] | undefined }) {
  const rows = (channels ?? []).filter((c) => c.sessions > 0).sort((a, b) => b.sessions - a.sessions);
  const total = rows.reduce((sum, c) => sum + c.sessions, 0);
  return (
    <Card>
      <h3 className="text-base font-semibold tracking-tight text-slate-900">Where your visitors come from</h3>
      <p className="mt-0.5 text-xs text-slate-500">
        The acquisition channels driving sessions — organic search, direct, referrals and social.
      </p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No channel data yet.</p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {rows.map((c) => {
            const share = total > 0 ? c.sessions / total : 0;
            return (
              <li key={c.channel}>
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate text-slate-700">{c.channel}</span>
                  <span className="shrink-0 text-slate-500">
                    <span className="font-semibold text-slate-900">{fmtNum(c.sessions)}</span> sessions · {fmtPct(share)}
                    {c.conversions > 0 ? ` · ${fmtNum(c.conversions)} conv.` : ""}
                  </span>
                </div>
                <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-linear-to-r from-indigo-400 to-indigo-600"
                    style={{ width: `${Math.max(2, Math.round(share * 100))}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// Connect / still-collecting empty-state for the GA behavior section.
function GaEmptyState({ collecting }: { collecting: boolean }) {
  return (
    <Card accent="info">
      {collecting ? (
        <>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Collecting analytics data…</h3>
          <p className="mt-1 text-sm text-slate-600">
            Google Analytics is connected and we&apos;ve picked your property — we&apos;re importing your sessions and
            behavior now. Your numbers will appear here shortly.
          </p>
        </>
      ) : (
        <>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Connect Google Analytics</h3>
          <p className="mt-1 text-sm text-slate-600">
            Import sessions, conversions &amp; behavior — see what visitors actually do after they arrive on your site.
          </p>
          <Link
            href="/integrations"
            className="mt-3 inline-block rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
          >
            Connect Google Analytics →
          </Link>
        </>
      )}
    </Card>
  );
}

function BehaviorSection({ businessId }: { businessId: number | null }) {
  const summary = useGaSummary(businessId);
  const channels = useGaChannels(businessId);

  const g: GaSummary | undefined = summary.data;
  const hasData = !!g?.has_data;
  const collecting = !!g?.collecting;

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-lg font-bold tracking-tight text-slate-900">Behavior &amp; conversions</h2>
        <p className="mt-0.5 text-sm text-slate-500">
          Google Analytics — what visitors do once they land: sessions, engagement and conversions.
        </p>
      </div>

      {!hasData ? (
        <GaEmptyState collecting={collecting} />
      ) : (
        <div className="space-y-6">
          {g?.as_of && (
            <p className="text-xs text-slate-400">Data through {new Date(g.as_of).toLocaleDateString()}</p>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Sessions"
              value={fmtNum(g?.sessions)}
              tone="good"
              delta={g?.sessions_delta ?? null}
              deltaSuffix="% vs prior period"
              whyItMatters="Visits to your site — how much traffic you're actually getting."
            />
            <MetricCard
              label="Users"
              value={fmtNum(g?.users)}
              tone="neutral"
              whyItMatters="Distinct people who visited — your reach in real humans."
            />
            <MetricCard
              label="Conversions"
              value={fmtNum(g?.conversions)}
              tone="good"
              delta={g?.conversions_delta ?? null}
              deltaSuffix="% vs prior period"
              whyItMatters="Key actions completed (calls, forms, bookings) — only counts events you've marked as conversions in GA4."
            />
            <MetricCard
              label="Engagement rate"
              value={fmtPct(g?.engagement_rate)}
              tone="neutral"
              whyItMatters="Share of sessions that were genuinely engaged — higher means visitors stick around."
            />
          </div>

          <ChannelMix channels={channels.data} />

          {/* Sessions trend over time */}
          <GaTrendChart businessId={businessId} />
        </div>
      )}
    </section>
  );
}

// =====================================================================================
// "Is our content working?" — the causal-proof panel. The honest framing: this is content
// WE published, a labeled subset of the whole site. We headline how many of those pages are
// earning real search traffic, show the owned-citation share, then list each page with its
// GSC clicks + GA sessions. Empty-state until something's been published.
// =====================================================================================

// A short, readable label for a published-page URL (drop the origin; keep the path).
function urlPath(url: string): string {
  try {
    const u = new URL(url);
    return u.pathname === "/" ? u.hostname : u.pathname;
  } catch {
    return url;
  }
}

function OurContentSection({ impact }: { impact: OurContentImpact | undefined }) {
  if (!impact) return null;
  const { totals, assets } = impact;
  const published = totals.assets_published;

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-lg font-bold tracking-tight text-slate-900">Is our content working?</h2>
        <p className="mt-0.5 text-sm text-slate-500">
          Pages we published for you — a labeled subset of your whole site — and the real search traffic they earn.
        </p>
      </div>

      {published === 0 ? (
        <Card accent="info">
          <h3 className="text-base font-semibold tracking-tight text-slate-900">No published pages yet</h3>
          <p className="mt-1 text-sm text-slate-600">
            Once we publish content for you and it goes live, this panel proves which of those pages are earning Google
            clicks and site visits — content impact you can actually measure.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card className="bg-linear-to-br from-emerald-50/50 to-white">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-base font-semibold tracking-tight text-slate-900">
                {totals.assets_with_traffic} of {published} page{published === 1 ? "" : "s"} we published{" "}
                {totals.assets_with_traffic === 1 ? "is" : "are"} earning search traffic
              </h3>
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 ring-1 ring-inset ring-emerald-200">
                our content
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              These are pages produced for you — a distinct subset of your full site, not the whole picture.
            </p>

            <div className="mt-4 grid grid-cols-2 gap-4 border-t border-slate-100 pt-3 sm:grid-cols-3">
              <div>
                <div className="text-2xl font-bold text-emerald-600">{fmtNum(totals.our_content_clicks)}</div>
                <div className="text-[11px] text-slate-500">Google clicks to content we published</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-900">{fmtNum(totals.our_content_sessions)}</div>
                <div className="text-[11px] text-slate-500">site sessions to those pages</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-900">{fmtPct(impact.owned_citation_share)}</div>
                <div className="text-[11px] text-slate-500">of AI citations point at content you own</div>
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Pages we published</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Each page we produced for you, with the Google clicks and site sessions it&apos;s earning.
            </p>
            {assets.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No published pages to show yet.</p>
            ) : (
              <table className="mt-3 w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    <th className="py-2 pr-3 text-left font-semibold">Page</th>
                    <th className="py-2 px-3 text-right font-semibold">Search clicks</th>
                    <th className="py-2 pl-3 text-right font-semibold">Sessions</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((a) => (
                    <tr key={a.asset_id} className="border-b border-slate-50 last:border-0">
                      <td className="py-2 pr-3 text-left">
                        <div className="flex items-center gap-2">
                          <a
                            href={a.published_url}
                            target="_blank"
                            rel="noreferrer"
                            title={a.published_url}
                            className="min-w-0 truncate text-slate-800 hover:text-indigo-600"
                          >
                            {a.title || urlPath(a.published_url)}
                          </a>
                          {!a.has_traffic && (
                            <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 ring-1 ring-inset ring-slate-200">
                              No traffic yet
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 px-3 text-right font-semibold text-slate-900">{fmtNum(a.gsc_clicks)}</td>
                      <td className="py-2 pl-3 text-right text-slate-600">{fmtNum(a.ga_sessions)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}
    </section>
  );
}

// View toggle for the page/query tables (a small reuse of the imports-tab tab pattern).
type DetailTab = "queries" | "pages";

export default function SearchPerformancePage() {
  const { businessId, businesses, loading } = useBusiness();
  const [ours, setOurs] = useState(false);
  const [tab, setTab] = useState<DetailTab>("queries");

  const summary = useGscSummary(businessId);
  const queries = useGscQueries(businessId, 25);
  const pages = useGscPages(businessId, ours, 25);
  const opps = useGscOpportunities(businessId);
  const roi = useGscRoi(businessId);
  const impact = useOurContentImpact(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Search & SEO" title="Search traffic & clicks" />
        <Card accent="info">
          <p className="text-sm text-slate-600">
            Set up a business and connect Google Search Console to see your real search traffic.
          </p>
        </Card>
      </div>
    );
  }
  if (summary.isLoading) return <Spinner />;

  const s = summary.data;
  const hasData = !!s?.has_data;
  const collecting = !!s?.collecting;

  return (
    <div>
      <PageHeader
        eyebrow="Search & SEO"
        title="Search traffic & clicks"
        subtitle="Real Google Search Console data — the clicks, impressions and rankings that prove your SEO is working."
      />

      <div className="space-y-10">
      {!hasData ? (
        <GscEmptyState collecting={collecting} />
      ) : (
        <div className="space-y-6">
          {s?.as_of && (
            <p className="text-xs text-slate-400">
              Last 28 days vs. the prior 28 days · data through {new Date(s.as_of).toLocaleDateString()}
            </p>
          )}

          {/* KPI tiles — clicks/impressions/CTR/position with prior-period deltas */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Clicks"
              value={fmtNum(s?.clicks)}
              tone="good"
              delta={s?.clicks_delta ?? null}
              deltaSuffix="% vs prior 28d"
              whyItMatters="Real visits to your site from Google search results."
            />
            <MetricCard
              label="Impressions"
              value={fmtNum(s?.impressions)}
              tone="neutral"
              delta={s?.impressions_delta ?? null}
              deltaSuffix="% vs prior 28d"
              whyItMatters="How often you appeared in Google's results — your reach."
            />
            <MetricCard
              label="CTR"
              value={fmtCtr(s?.ctr)}
              tone="neutral"
              whyItMatters="Share of impressions that became clicks. Higher means your listing is compelling."
            />
            <MetricCard
              label="Avg position"
              value={fmtPos(s?.position)}
              tone="neutral"
              goodDirection="down"
              whyItMatters="Your average ranking across all searches. Lower is better — #1 is the top of page one."
            />
          </div>

          {/* Trend (dual series + days toggle) */}
          <GscTrendChart businessId={businessId} />

          {/* Equivalent value (honest, labeled estimate) */}
          <EquivalentValueCard roi={roi.data} />

          {/* Striking-distance opportunities */}
          <OpportunitiesCard opps={opps.data} />

          {/* Queries + pages tables (toggle; pages can filter to our content) */}
          <div>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex gap-1 rounded-lg bg-slate-100 p-0.5">
                {([
                  { key: "queries", label: "Queries" },
                  { key: "pages", label: "Pages" },
                ] as { key: DetailTab; label: string }[]).map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setTab(t.key)}
                    className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                      tab === t.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {tab === "pages" && (
                <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
                  <input
                    type="checkbox"
                    checked={ours}
                    onChange={(e) => setOurs(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-slate-300"
                  />
                  Only content we published
                </label>
              )}
            </div>
            {tab === "queries" ? (
              <GscQueryTable queries={queries.data} />
            ) : (
              <GscPageTable pages={pages.data} />
            )}
          </div>
        </div>
      )}

        {/* Behavior & conversions (Google Analytics) — what visitors DO after they arrive */}
        <BehaviorSection businessId={businessId} />

        {/* Is our content working? — the causal-proof panel (our published pages vs traffic) */}
        <OurContentSection impact={impact.data} />
      </div>
    </div>
  );
}
