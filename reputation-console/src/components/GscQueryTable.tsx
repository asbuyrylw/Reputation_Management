"use client";

import { Card } from "./ui";
import type { GscQuery, GscPage } from "@/lib/types";

// Shared formatters — Search Console reports null CTR/position for rows with no rank data.
const fmtCtr = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const fmtPos = (v: number | null) => (v == null ? "—" : v.toFixed(1));
const fmtNum = (v: number) => v.toLocaleString();

// A short, readable label for a landing-page URL (drop the origin; keep the path).
function pagePath(url: string): string {
  try {
    const u = new URL(url);
    return u.pathname === "/" ? u.hostname : u.pathname;
  } catch {
    return url;
  }
}

function HeadRow() {
  return (
    <tr className="border-b border-slate-100 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
      <th className="py-2 pr-3 text-left font-semibold">&nbsp;</th>
      <th className="py-2 px-3 text-right font-semibold">Clicks</th>
      <th className="py-2 px-3 text-right font-semibold">Impr.</th>
      <th className="py-2 px-3 text-right font-semibold">CTR</th>
      <th className="py-2 pl-3 text-right font-semibold">Avg pos</th>
    </tr>
  );
}

function Metrics({ row }: { row: GscQuery | GscPage }) {
  return (
    <>
      <td className="py-2 px-3 text-right font-semibold text-slate-900">{fmtNum(row.clicks)}</td>
      <td className="py-2 px-3 text-right text-slate-600">{fmtNum(row.impressions)}</td>
      <td className="py-2 px-3 text-right text-slate-600">{fmtCtr(row.ctr)}</td>
      <td className="py-2 pl-3 text-right text-slate-600">{fmtPos(row.position)}</td>
    </>
  );
}

// Top search queries — the words people typed to find the business.
export function GscQueryTable({ queries }: { queries: GscQuery[] | undefined }) {
  const rows = queries ?? [];
  return (
    <Card>
      <h3 className="text-base font-semibold tracking-tight text-slate-900">Top search queries</h3>
      <p className="mt-0.5 text-xs text-slate-500">The actual words people typed into Google to find you.</p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No query data yet.</p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead><HeadRow /></thead>
          <tbody>
            {rows.map((q) => (
              <tr key={q.query} className="border-b border-slate-50 last:border-0">
                <td className="py-2 pr-3 text-left text-slate-800">{q.query}</td>
                <Metrics row={q} />
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// Top landing pages — with an "Our content" badge when the page is something we published.
export function GscPageTable({ pages }: { pages: GscPage[] | undefined }) {
  const rows = pages ?? [];
  return (
    <Card>
      <h3 className="text-base font-semibold tracking-tight text-slate-900">Top landing pages</h3>
      <p className="mt-0.5 text-xs text-slate-500">
        The pages people land on from search. <span className="font-medium text-emerald-700">Our content</span> marks pages
        we published for you.
      </p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No page data yet.</p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead><HeadRow /></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.page} className="border-b border-slate-50 last:border-0">
                <td className="py-2 pr-3 text-left">
                  <div className="flex items-center gap-2">
                    <a
                      href={p.page}
                      target="_blank"
                      rel="noreferrer"
                      title={p.page}
                      className="min-w-0 truncate text-slate-800 hover:text-indigo-600"
                    >
                      {pagePath(p.page)}
                    </a>
                    {p.is_our_content && (
                      <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200">
                        Our content
                      </span>
                    )}
                  </div>
                </td>
                <Metrics row={p} />
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
