"use client";

// Keywords to win — turns the SEO keyword set into a decision: which keywords are actually
// winnable for page 1 (real demand + low difficulty), which ones competitors rank for that we
// don't, and where the biggest demand is. Each row can become a content task in one click, with
// the target keyword carried into the brief so the piece is written to rank for it.

import { useMemo, useState } from "react";
import { useTargetKeywords, useAddWorkOrder } from "@/lib/hooks";
import type { TargetKeyword } from "@/lib/types";
import { Card } from "@/components/ui";

const WINNABLE_MAX_DIFF = 35;   // mirrors KEYWORD_WINNABLE_MAX_DIFFICULTY on the backend
const MIN_VOLUME = 20;

function DiffBadge({ d }: { d: number | null | undefined }) {
  if (d == null) return <span className="font-mono text-[11px] text-ink-4">—</span>;
  const tone = d <= 20 ? "bg-green-100 text-green-700" : d <= 35 ? "bg-emerald-50 text-emerald-700"
    : d <= 60 ? "bg-amber-50 text-amber-700" : "bg-rose-50 text-rose-700";
  return <span className={`rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold ${tone}`}>{Math.round(d)}</span>;
}

function KwRow({ k, businessId, canEdit }: { k: TargetKeyword; businessId: number | null; canEdit: boolean }) {
  const add = useAddWorkOrder(businessId);
  return (
    <div className="flex items-center gap-3 border-b border-line py-2 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-medium text-ink">{k.keyword}</div>
        {k.intent && <div className="text-[11px] text-ink-4">{k.intent}{k.kind ? ` · ${k.kind}` : ""}</div>}
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-[12.5px] font-semibold text-ink tabular-nums">{k.search_volume != null ? k.search_volume.toLocaleString() : "—"}</div>
        <div className="text-[10px] uppercase tracking-wide text-ink-4">vol/mo</div>
      </div>
      <div className="w-9 shrink-0 text-center"><DiffBadge d={k.keyword_difficulty} /></div>
      {canEdit && (add.isSuccess ? (
        <span className="shrink-0 text-[12px] font-semibold text-good">✓ Added</span>
      ) : (
        <button onClick={() => add.mutate({ title: `Rank for: ${k.keyword}`, capability: "content_writing", gap_source: "keyword opportunity", source_query: k.keyword, area: "content", why_helps_seo: `Target keyword — ${k.search_volume ?? "?"} searches/mo, difficulty ${k.keyword_difficulty ?? "?"}.` })}
          disabled={add.isPending}
          className="shrink-0 rounded-[8px] border border-line bg-white px-2.5 py-1 text-[12px] font-semibold text-indigo hover:bg-paper disabled:opacity-50">
          {add.isPending ? "…" : "+ Task"}
        </button>
      ))}
    </div>
  );
}

export function KeywordsToWinPanel({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const kws = useTargetKeywords(businessId);
  const [tab, setTab] = useState<"winnable" | "competitor" | "demand">("winnable");

  const { winnable, competitor, demand, enriched } = useMemo(() => {
    const all = kws.data ?? [];
    const withVol = all.filter((k) => k.search_volume != null);
    const winnable = withVol
      .filter((k) => (k.search_volume ?? 0) >= MIN_VOLUME && k.keyword_difficulty != null && k.keyword_difficulty <= WINNABLE_MAX_DIFF)
      .sort((a, b) => (b.search_volume ?? 0) - (a.search_volume ?? 0));
    const competitor = all.filter((k) => k.source === "dataforseo_competitor")
      .sort((a, b) => (b.search_volume ?? 0) - (a.search_volume ?? 0));
    const demand = [...withVol].sort((a, b) => (b.search_volume ?? 0) - (a.search_volume ?? 0));
    return { winnable, competitor, demand, enriched: withVol.length };
  }, [kws.data]);

  if (kws.isLoading) return null;
  const total = kws.data?.length ?? 0;
  if (total === 0) return null;

  const tabs: { key: typeof tab; label: string; count: number; blurb: string }[] = [
    { key: "winnable", label: "Winnable", count: winnable.length, blurb: `Real demand + low difficulty (≤${WINNABLE_MAX_DIFF}) — attack these for page 1.` },
    { key: "competitor", label: "Competitor gaps", count: competitor.length, blurb: "Keywords competitors rank for that you don't — steal the ground." },
    { key: "demand", label: "Highest demand", count: demand.length, blurb: "Where the search volume is, hardest first — the long game." },
  ];
  const active = tabs.find((t) => t.key === tab)!;
  const rows = tab === "winnable" ? winnable : tab === "competitor" ? competitor : demand;

  return (
    <Card>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold tracking-tight text-slate-900">Keywords to win</h3>
        <div className="flex gap-1 rounded-[10px] bg-paper p-0.5">
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`rounded-[8px] px-2.5 py-1 text-[12px] font-semibold transition ${tab === t.key ? "bg-white text-indigo shadow-sm" : "text-ink-3 hover:text-ink"}`}>
              {t.label} <span className="font-mono text-[10.5px] text-ink-4">{t.count}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-[12.5px] text-slate-500">{active.blurb}</p>
      {enriched === 0 ? (
        <p className="rounded-lg bg-paper px-3 py-3 text-center text-[12.5px] text-ink-4">
          Run keyword volume enrichment (DataForSEO) to see real search volume + difficulty and rank these opportunities.
        </p>
      ) : rows.length === 0 ? (
        <p className="py-3 text-center text-[13px] text-ink-4">Nothing here yet — {tab === "competitor" ? "run competitor intel to find gaps." : "enrich more keywords to surface opportunities."}</p>
      ) : (
        <div className="max-h-[360px] overflow-y-auto pr-1">
          {rows.slice(0, 20).map((k) => <KwRow key={`${k.keyword}-${k.source}`} k={k} businessId={businessId} canEdit={canEdit} />)}
        </div>
      )}
    </Card>
  );
}
