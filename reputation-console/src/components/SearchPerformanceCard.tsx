"use client";

import Link from "next/link";
import { Card } from "./ui";
import { Sparkline } from "./Sparkline";
import { useGscSummary, useGscTrend, useGscQueries } from "@/lib/hooks";

const fmtNum = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
const fmtCtr = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const fmtPos = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));

// SEO-overview summary of real Google search traffic: clicks/impressions sparklines + CTR +
// avg position + the top queries, with a deep-dive link. Honest framing throughout — this is
// MEASURED Google data, distinct from the AI-visibility story elsewhere on the page.
export function SearchPerformanceCard({ businessId }: { businessId: number | null }) {
  const { data: summary } = useGscSummary(businessId);
  const { data: trend } = useGscTrend(businessId, 28);
  const { data: queries } = useGscQueries(businessId, 3);

  const hasData = !!summary?.has_data;
  const collecting = !!summary?.collecting;

  // Not connected and not collecting → connect CTA.
  if (!hasData && !collecting) {
    return (
      <Card>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Search traffic &amp; clicks</h3>
            <p className="mt-1 text-sm text-slate-600">
              Connect Google Search Console to import real Google clicks, impressions and rankings — the proof your SEO is
              actually working.
            </p>
          </div>
        </div>
        <Link
          href="/integrations"
          className="mt-3 inline-block rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          Connect Google Search Console →
        </Link>
      </Card>
    );
  }

  // Connected, property set, but still backfilling history.
  if (!hasData && collecting) {
    return (
      <Card>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Search traffic &amp; clicks</h3>
            <p className="mt-1 text-sm text-slate-600">Collecting search data from Google… your first numbers will appear shortly.</p>
          </div>
          <Link href="/search-performance" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
            Deep dive →
          </Link>
        </div>
      </Card>
    );
  }

  const clicksSeries = (trend ?? []).map((p) => p.clicks);
  const imprSeries = (trend ?? []).map((p) => p.impressions);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Search traffic &amp; clicks</h3>
          <p className="mt-0.5 text-xs text-slate-500">Real Google clicks &amp; impressions — last 28 days.</p>
        </div>
        <Link href="/search-performance" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
          Deep dive →
        </Link>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Clicks</div>
          <div className="text-xl font-bold text-slate-900">{fmtNum(summary?.clicks)}</div>
          {clicksSeries.length >= 2 && <Sparkline values={clicksSeries} />}
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Impressions</div>
          <div className="text-xl font-bold text-slate-900">{fmtNum(summary?.impressions)}</div>
          {imprSeries.length >= 2 && <Sparkline values={imprSeries} />}
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">CTR</div>
          <div className="text-xl font-bold text-slate-900">{fmtCtr(summary?.ctr)}</div>
          <div className="text-[11px] text-slate-400">clicks ÷ impressions</div>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Avg position</div>
          <div className="text-xl font-bold text-slate-900">{fmtPos(summary?.position)}</div>
          <div className="text-[11px] text-slate-400">lower is better</div>
        </div>
      </div>

      {queries && queries.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Top queries</div>
          <ul className="space-y-1">
            {queries.map((q) => (
              <li key={q.query} className="flex items-baseline justify-between gap-3 text-sm">
                <span className="min-w-0 truncate text-slate-700">{q.query}</span>
                <span className="shrink-0 font-semibold text-slate-900">{fmtNum(q.clicks)} clicks</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
