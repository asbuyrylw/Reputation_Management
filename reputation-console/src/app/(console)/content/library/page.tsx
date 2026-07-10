"use client";

// Content Library — every piece of content you've created (drafts + published), browsable by
// content TYPE and by the GAP it closes. A single scannable, sortable, filterable grid so you can
// find "all the local-ranking blogs" or "everything for the AI-visibility gap" at a glance.

import { useMemo, useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useAssets, useWorkOrders } from "@/lib/hooks";
import { PageHeader, Spinner, Card } from "@/components/ui";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { EmptyState } from "@/components/primitives";
import type { ContentDraft, Asset, WorkOrder } from "@/lib/types";

type Piece = {
  key: string;              // unique row id ("d123" / "a45")
  title: string;
  type: string;             // content/asset type
  gap: string;              // gap_source (resolved via work order)
  section: string;          // AI Visibility / SEO / Local Ranking / Search
  area: string;             // Website / Blog / Social / Local / Article
  status: string;           // Published / Draft / Held / Approved …
  words: number;
  keywords: string;
  href: string;
};

const CONTENT_AREA: Record<string, string> = {
  article: "Article", blog: "Blog", white_paper: "Article", faq: "Website",
  landing_page: "Website", local_page: "Local", gbp_post: "Local",
  social_post: "Social", video_script: "Social",
};
function areaOf(type: string): string { return CONTENT_AREA[(type || "").toLowerCase()] ?? "Website"; }
function sectionOf(gap: string): string {
  const gs = (gap || "").toLowerCase();
  if (gs.includes("local")) return "Local Ranking";
  if (gs.includes("schema") || gs.includes("site crawl")) return "SEO";
  if (gs.includes("search") || gs.includes("ranking")) return "Search";
  return "AI Visibility";
}
const wordCount = (body?: string | null) => (body ?? "").split(/\s+/).filter(Boolean).length;
const draftStatusLabel: Record<string, string> = {
  pending_review: "Draft", needs_fix: "Held", held: "Held", approved: "Approved", rejected: "Rejected",
};

const COLUMNS: DataGridColumn<Piece>[] = [
  { key: "title", label: "Title", width: 280, hideable: false, sortValue: (p) => p.title.toLowerCase(),
    render: (p) => <Link href={p.href} className="font-medium text-slate-800 hover:text-indigo-600 hover:underline">{p.title || "Untitled"}</Link> },
  { key: "type", label: "Type", width: 110, sortValue: (p) => p.type, render: (p) => <span className="text-xs capitalize text-slate-500">{p.type.replace(/_/g, " ")}</span> },
  { key: "area", label: "Area", width: 90, sortValue: (p) => p.area, render: (p) => <span className="text-xs text-slate-500">{p.area}</span> },
  { key: "gap", label: "Gap it closes", width: 200, wrap: true, sortValue: (p) => p.gap, render: (p) => <span className="text-xs text-slate-500">{p.gap || "—"}</span> },
  { key: "section", label: "Gap type", width: 120, sortValue: (p) => p.section, render: (p) => <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-600">{p.section}</span> },
  { key: "words", label: "Words", width: 70, align: "right", sortValue: (p) => p.words, render: (p) => <span className="tabular-nums text-slate-600">{p.words || "—"}</span> },
  { key: "keywords", label: "Keywords", width: 200, defaultHidden: true, sortValue: (p) => p.keywords.toLowerCase(), render: (p) => <span className="text-xs text-slate-500">{p.keywords || "—"}</span> },
  { key: "status", label: "Status", width: 110, sortValue: (p) => p.status,
    render: (p) => <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${p.status === "Published" ? "bg-emerald-50 text-emerald-700" : p.status === "Held" ? "bg-rose-50 text-rose-600" : "bg-slate-100 text-slate-600"}`}>{p.status}</span> },
];

const selCls = "rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700";

export default function LibraryPage() {
  const { businessId } = useBusiness();
  const { data: drafts, isLoading: ld } = useContentDrafts(businessId);
  const { data: assets, isLoading: la } = useAssets(businessId);
  const { data: workOrders } = useWorkOrders(businessId);
  const [typeFilter, setTypeFilter] = useState("all");
  const [sectionFilter, setSectionFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const pieces = useMemo<Piece[]>(() => {
    const woById = new Map<number, WorkOrder>((workOrders ?? []).map((w) => [w.id, w]));
    const gapFor = (woId: number | null) => (woId != null ? woById.get(woId) : undefined);
    const out: Piece[] = [];
    // published assets first (the finished library), then non-published drafts
    const publishedWoIds = new Set<number>();
    for (const a of assets ?? []) {
      const wo = gapFor(a.work_order_id);
      const gap = wo?.gap_source ?? "";
      const type = a.asset_type ?? "";
      if (a.work_order_id != null) publishedWoIds.add(a.work_order_id);
      out.push({
        key: `a${a.id}`, title: a.title ?? "Untitled", type, gap, section: sectionOf(gap),
        area: wo?.area ? wo.area.charAt(0).toUpperCase() + wo.area.slice(1) : areaOf(type),
        status: (a.published_status === "live" || a.published_url) ? "Published" : "Approved",
        words: wordCount(a.body), keywords: a.target_query ?? "", href: "/content/finalized",
      });
    }
    for (const d of drafts ?? []) {
      // skip a draft that already became a published asset (avoid double-listing)
      if (d.work_order_id != null && publishedWoIds.has(d.work_order_id) && d.status === "approved") continue;
      const wo = gapFor(d.work_order_id);
      const gap = d.gap_source ?? wo?.gap_source ?? "";
      const type = d.content_type ?? d.asset_type ?? "";
      out.push({
        key: `d${d.id}`, title: d.title ?? "Untitled", type, gap, section: sectionOf(gap),
        area: wo?.area ? wo.area.charAt(0).toUpperCase() + wo.area.slice(1) : areaOf(type),
        status: draftStatusLabel[d.status] ?? "Draft",
        words: wordCount(d.body), keywords: d.target_query ?? "", href: "/content/drafts",
      });
    }
    return out;
  }, [drafts, assets, workOrders]);

  const types = Array.from(new Set(pieces.map((p) => p.type).filter(Boolean))).sort();
  const sections = Array.from(new Set(pieces.map((p) => p.section))).sort();
  const statuses = Array.from(new Set(pieces.map((p) => p.status))).sort();
  const rows = pieces.filter((p) =>
    (typeFilter === "all" || p.type === typeFilter) &&
    (sectionFilter === "all" || p.section === sectionFilter) &&
    (statusFilter === "all" || p.status === statusFilter));

  if (ld || la) return <Spinner />;

  return (
    <div>
      <PageHeader title="Content library" subtitle="Everything you've created — drafts and published — browsable by content type and by the gap it closes." />
      {pieces.length === 0 ? (
        <EmptyState title="No content yet" why="Your library fills as you generate drafts and publish them." produces="Generate content from a task or the To-produce page, and every piece shows up here by type and gap." cta={{ label: "See what to produce", href: "/content/briefs" }} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="font-semibold uppercase tracking-wide text-slate-400">Filter</span>
            <label className="inline-flex items-center gap-1">Type
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className={`${selCls} capitalize`}>
                <option value="all">All</option>{types.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </label>
            <label className="inline-flex items-center gap-1">Gap type
              <select value={sectionFilter} onChange={(e) => setSectionFilter(e.target.value)} className={selCls}>
                <option value="all">All</option>{sections.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="inline-flex items-center gap-1">Status
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selCls}>
                <option value="all">All</option>{statuses.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            {(typeFilter !== "all" || sectionFilter !== "all" || statusFilter !== "all") && (
              <button type="button" onClick={() => { setTypeFilter("all"); setSectionFilter("all"); setStatusFilter("all"); }} className="font-medium text-indigo-600 hover:underline">Clear</button>
            )}
            <span className="text-slate-400">· {rows.length} of {pieces.length} pieces</span>
          </div>
          <DataGrid columns={COLUMNS} rows={rows} getId={(p) => p.key} storageKey="library" emptyText="No content matches these filters." />
          <Card className="mt-3 bg-slate-50 text-[12px] text-slate-500">Tip: click a title to open it, drag column edges to resize, click a header to sort, and use “Columns” to show/hide fields.</Card>
        </>
      )}
    </div>
  );
}
