"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useContentOptimizationStatus, useApproveDraft, useRejectDraft, useKattebCredits } from "@/lib/hooks";
import { DraftReviewCard } from "@/components/DraftReviewCard";
import { DraftEditorPanel, readabilityScore } from "@/components/DraftEditorPanel";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusBadge } from "@/components/content/StatusBadge";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { TabNav } from "@/components/content/TabNav";
import type { ContentDraft } from "@/lib/types";

// Per-draft metadata for the table, read from its quality_notes (all already computed).
function draftWords(d: ContentDraft): number {
  return d.quality_notes?.on_page?.word_count ?? (d.body ?? "").split(/\s+/).filter(Boolean).length;
}
function draftHasImage(d: ContentDraft): boolean {
  return (d.quality_notes?.on_page?.images ?? 0) > 0;
}
function aiVisScore(d: ContentDraft): number | null {
  return d.quality_notes?.citation_ready?.score ?? null;
}
function readScore(d: ContentDraft): number | null {
  return readabilityScore(d.quality_notes?.readability?.grade);
}
function scoreCls(n: number | null): string {
  if (n == null) return "text-slate-400";
  if (n >= 70) return "text-emerald-600";
  if (n >= 50) return "text-amber-600";
  return "text-rose-600";
}
function seoScore(d: ContentDraft): number | null {
  return d.quality_notes?.katteb?.seo_score ?? d.quality_notes?.on_page?.score ?? null;
}
// The content AREA of a draft (for the area filter), from its content/asset type.
const CONTENT_AREA: Record<string, string> = {
  article: "Article", blog: "Blog", white_paper: "Article", faq: "Website",
  landing_page: "Website", local_page: "Local", gbp_post: "Local",
  social_post: "Social", video_script: "Social", schema: "Website",
};
function draftArea(d: ContentDraft): string {
  return CONTENT_AREA[(d.content_type || d.asset_type || "").toLowerCase()] ?? "Website";
}
// The gap SECTION a draft closes (for the gap-type filter), from its gap_source.
function draftSection(d: ContentDraft): string {
  const gs = (d.gap_source || "").toLowerCase();
  if (gs.includes("local search") || gs.includes("local")) return "Local Ranking";
  if (gs.includes("schema") || gs.includes("site crawl")) return "SEO";
  if (gs.includes("search") || gs.includes("ranking")) return "Search";
  return "AI Visibility";
}
const AREA_OPTIONS = ["Website", "Article", "Blog", "Social", "Local"];
const GAP_OPTIONS = ["AI Visibility", "SEO", "Local Ranking", "Search"];
const typeLabel = (d: ContentDraft) => (d.content_type || d.asset_type || "—").replace(/_/g, " ");

// The drafts grid columns — everything readable in-row (title, type, area, gap, words, keywords,
// image, readability, AI-visibility, SEO, status). Resizable + hideable via DataGrid.
const DRAFT_COLUMNS: DataGridColumn<ContentDraft>[] = [
  { key: "title", label: "Title", width: 260, hideable: false, sortValue: (d) => (d.title || "").toLowerCase(),
    render: (d) => <span className="font-medium text-slate-800">{d.title || "Untitled"}</span> },
  { key: "type", label: "Type", width: 100, sortValue: (d) => typeLabel(d),
    render: (d) => <span className="text-xs text-slate-500 capitalize">{typeLabel(d)}</span> },
  { key: "area", label: "Area", width: 90, sortValue: draftArea, render: (d) => <span className="text-xs text-slate-500">{draftArea(d)}</span> },
  { key: "gap", label: "Gap type", width: 120, sortValue: draftSection, render: (d) => <span className="text-xs text-slate-500">{draftSection(d)}</span> },
  { key: "words", label: "Words", width: 72, align: "right", sortValue: draftWords, render: (d) => <span className="tabular-nums text-slate-600">{draftWords(d)}</span> },
  { key: "keywords", label: "Keywords", width: 220, sortValue: (d) => (d.target_query || "").toLowerCase(), render: (d) => <span className="text-xs text-slate-500">{d.target_query || "—"}</span> },
  { key: "img", label: "Img", width: 52, align: "center", sortValue: (d) => (draftHasImage(d) ? 1 : 0), render: (d) => draftHasImage(d) ? <span>🖼</span> : <span className="text-slate-300">—</span> },
  { key: "read", label: "Read", width: 68, align: "right", sortValue: (d) => readScore(d) ?? -1, render: (d) => { const n = readScore(d); return <span className={`font-mono text-xs font-semibold ${scoreCls(n)}`}>{n ?? "—"}</span>; } },
  { key: "aivis", label: "AI-Vis", width: 76, align: "right", sortValue: (d) => aiVisScore(d) ?? -1, render: (d) => { const n = aiVisScore(d); return <span className={`font-mono text-xs font-semibold ${scoreCls(n)}`}>{n ?? "—"}</span>; } },
  { key: "seo", label: "SEO", width: 68, align: "right", defaultHidden: true, sortValue: (d) => seoScore(d) ?? -1, render: (d) => { const n = seoScore(d); return <span className={`font-mono text-xs font-semibold ${scoreCls(n)}`}>{n ?? "—"}</span>; } },
  { key: "status", label: "Status", width: 130, sortValue: (d) => d.status, render: (d) => <StatusBadge status={d.status} /> },
];

const filterSelectCls = "rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700";

type Tab = "ready" | "fixes" | "all";
type Sort = "impact" | "quality" | "newest";

// The predicted-impact points live on the linked work order. If the API ever inlines them on
// the draft they'll be read here; until then this is null and impact-sort falls back to quality.
// Typed defensively (the field isn't declared on ContentDraft) so this stays safe either way.
function predictedPoints(d: ContentDraft): number | null {
  const v = (d as { predicted_ai_points?: unknown }).predicted_ai_points;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

// compliance_flags is typed `unknown` on the wire — coerce to a string[] the same way the card does.
function draftFlags(d: ContentDraft): string[] {
  return Array.isArray(d.compliance_flags) ? d.compliance_flags.map((f) => String(f)) : [];
}

// The primary reason a needs_fix draft is blocked — its first compliance flag, else the top
// quality/keyword issue, else a generic bucket. Used to group a cohort that shares one flaw.
function primaryFlaw(d: ContentDraft): string {
  const flags = draftFlags(d);
  if (flags.length > 0) return flags[0];
  const qn = d.quality_notes;
  const structIssue = qn?.structure?.issues?.[0]?.label;
  if (structIssue) return structIssue;
  const aeoTip = qn?.aeo?.tips?.[0]?.label;
  if (aeoTip) return aeoTip;
  const missing = qn?.keyword_coverage?.missing;
  if (Array.isArray(missing) && missing.length > 0) return `Missing keywords (${missing.length})`;
  return "Other issues";
}

// The exact approvability guard the card enforces: not compliance-failed, no unresolved
// placeholders, and compliance actually confirmed (null needs a manual per-draft sign-off reason,
// which we never fabricate in bulk).
function bulkApprovable(d: ContentDraft): boolean {
  if (d.status !== "pending_review") return false;
  if (d.compliance_pass !== true) return false;
  const placeholders = Array.isArray(d.placeholders_pending) ? d.placeholders_pending : [];
  return placeholders.length === 0;
}

function sortDrafts(list: ContentDraft[], sort: Sort): ContentDraft[] {
  const copy = [...list];
  if (sort === "newest") return copy.sort((a, b) => b.id - a.id);
  if (sort === "quality") {
    return copy.sort((a, b) => (b.quality_score ?? -1) - (a.quality_score ?? -1) || b.id - a.id);
  }
  // impact: predicted points desc, then quality desc, then newest — so drafts with no linked
  // prediction still sort sensibly instead of sinking to the bottom.
  return copy.sort((a, b) => {
    const pa = predictedPoints(a);
    const pb = predictedPoints(b);
    if (pa != null && pb != null && pa !== pb) return pb - pa;
    if (pa != null && pb == null) return -1;
    if (pa == null && pb != null) return 1;
    return (b.quality_score ?? -1) - (a.quality_score ?? -1) || b.id - a.id;
  });
}

const selectClass =
  "rounded-md border border-line-2 bg-card px-2 py-1 text-sm text-ink-2 focus:border-ink-4 focus:outline-none";

export default function DraftsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useContentDrafts(businessId);
  const { data: optStatus } = useContentOptimizationStatus(businessId);
  const approve = useApproveDraft(businessId);
  const reject = useRejectDraft(businessId);
  const { data: kattebCredits } = useKattebCredits(businessId);
  const [tab, setTab] = useState<Tab>("ready");
  const [sort, setSort] = useState<Sort>("impact");
  const [groupFlaws, setGroupFlaws] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulk, setBulk] = useState<{ done: number; total: number } | null>(null);
  const [openDraft, setOpenDraft] = useState<ContentDraft | null>(null);
  const [areaFilter, setAreaFilter] = useState("all");
  const [gapFilter, setGapFilter] = useState("all");

  // "Ready" = passed our checks and waiting on you. "Needs fixes" = flagged (usually a missing
  // disclosure) — high quality can still land here; it's a compliance gate, not a quality one.
  const ready = useMemo(
    () => (data ?? []).filter((d) => d.status === "pending_review" && d.compliance_pass !== false),
    [data],
  );
  // "Held" = the engine couldn't get it over the quality/compliance/citation bar after its
  // auto-revisions, so it's kept OUT of the review queue and parked here for an author to finish.
  // (needs_fix kept for any drafts created before the revise-until-clean change.)
  const fixes = useMemo(
    () =>
      (data ?? []).filter(
        (d) => d.status === "held" || d.status === "needs_fix" || (d.status === "pending_review" && d.compliance_pass === false),
      ),
    [data],
  );
  const shown = useMemo(() => {
    let base = tab === "all" ? (data ?? []) : tab === "ready" ? ready : fixes;
    if (areaFilter !== "all") base = base.filter((d) => draftArea(d) === areaFilter);
    if (gapFilter !== "all") base = base.filter((d) => draftSection(d) === gapFilter);
    return sortDrafts(base, sort);
  }, [tab, data, ready, fixes, sort, areaFilter, gapFilter]);

  // Which of the shown drafts a "Approve selected" run could act on (reusing the card's guard).
  const approvableShown = useMemo(() => shown.filter(bulkApprovable), [shown]);
  const selectedApprovable = approvableShown.filter((d) => selected.has(d.id));
  const grouping = groupFlaws && tab === "fixes";

  if (isLoading || !data) return <Spinner />;

  const toggleOne = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const clearSelected = () => setSelected(new Set());

  const approveSelected = async () => {
    // Snapshot up front: each approval invalidates the drafts query, so the list re-fetches
    // mid-loop; iterating the snapshot keeps the run stable. Failures are skipped, not fatal.
    const batch = [...selectedApprovable];
    if (batch.length === 0) return;
    setBulk({ done: 0, total: batch.length });
    for (let i = 0; i < batch.length; i++) {
      try {
        await approve.mutateAsync({ draftId: batch[i].id });
      } catch {
        // leave it selected so the reviewer can see it didn't go through
      }
      setBulk({ done: i + 1, total: batch.length });
    }
    setBulk(null);
    setSelected(new Set());
  };

  // Delete/dismiss selected drafts (reject removes them from the queue). Snapshot like approve.
  const deleteSelected = async () => {
    const batch = shown.filter((d) => selected.has(d.id));
    if (batch.length === 0 || !confirm(`Delete ${batch.length} draft${batch.length === 1 ? "" : "s"}? This removes them from the queue.`)) return;
    setBulk({ done: 0, total: batch.length });
    for (let i = 0; i < batch.length; i++) {
      try { await reject.mutateAsync({ draftId: batch[i].id }); } catch { /* skip */ }
      setBulk({ done: i + 1, total: batch.length });
    }
    setBulk(null);
    setSelected(new Set());
  };

  // The open draft, kept live from the latest fetch so a finished Katteb analysis (which lands in
  // quality_notes.katteb after a refetch) shows up in the slide-over without reopening it.
  const liveOpen = openDraft ? ((data ?? []).find((d) => d.id === openDraft.id) ?? openDraft) : null;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageHeader
          title="Content drafts"
          subtitle="Your drafts at a glance — click any row to review, edit, and publish. Nothing publishes without you."
        />
        {kattebCredits?.configured && kattebCredits.credits_available != null && (
          <span className="mt-1 shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 font-mono text-[11px] text-indigo-700" title="Katteb credits for deep SEO analysis this month">
            Katteb: {kattebCredits.credits_available.toLocaleString()} / {kattebCredits.credits_total?.toLocaleString()} credits
          </span>
        )}
      </div>

      <Card className="mb-4">
        <TabNav
          tabs={[
            { key: "ready", label: "Ready to review", count: ready.length },
            { key: "fixes", label: "Held — need an author", count: fixes.length },
            { key: "all", label: "All", count: data.length },
          ]}
          active={tab}
          onSelect={(k) => { setTab(k as Tab); clearSelected(); }}
        />

        {/* Triage controls: sort the queue, and (on the fixes tab) group drafts by their shared flaw. */}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-ink-3">
            Sort
            <select
              aria-label="Sort drafts"
              className={selectClass}
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
            >
              <option value="impact">By impact</option>
              <option value="quality">By quality</option>
              <option value="newest">Newest first</option>
            </select>
          </label>
          {tab === "fixes" && (
            <label className="flex items-center gap-1.5 text-xs text-ink-3">
              <input
                type="checkbox"
                checked={groupFlaws}
                onChange={(e) => setGroupFlaws(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-line-2"
              />
              Group by shared flaw
            </label>
          )}
        </div>

        <p className="mt-2 text-xs text-ink-3">
          {tab === "fixes"
            ? "The engine tried to auto-fix these but couldn't get them over the quality, compliance, or citation-readiness bar — so they're held out of your review queue for an author to finish. Edit one to resolve it (which re-screens it), then it moves to “Ready to review.”"
            : "“Ready to review” passed our quality + compliance checks and just needs your sign-off — no issues to fix. Approving publishes it and advances its task."}
        </p>
        {/* Subtle dormant-feature hint: only when content-optimization is wired in the app but
            not yet configured for this business — drafts will then carry a SERP-coverage score. */}
        {optStatus && !optStatus.configured && (
          <p className="mt-2 text-[11px] text-ink-4">
            Content optimization:{" "}
            <Link href="/integrations" className="font-medium text-indigo hover:text-indigo-strong">connect NeuronWriter</Link>{" "}
            to score each draft on SERP content coverage.
          </p>
        )}
      </Card>

      {/* Bulk action bar — publish (approvable only) or delete any selected rows. */}
      {canEdit && selected.size > 0 && (
        <Card className="mb-3 flex flex-wrap items-center gap-3 py-2.5">
          <span className="text-sm font-medium text-ink-2">{selected.size} selected</span>
          <button
            type="button"
            disabled={selectedApprovable.length === 0 || bulk != null}
            onClick={approveSelected}
            className="rounded-md bg-good px-3 py-1.5 text-sm font-medium text-white hover:brightness-95 disabled:opacity-50"
            title={selectedApprovable.length === 0 ? "Only fully-checked drafts (compliance passed, no placeholders) can be published in bulk." : undefined}
          >
            {bulk ? `Working ${bulk.done}/${bulk.total}…` : `Publish selected (${selectedApprovable.length})`}
          </button>
          <button
            type="button"
            disabled={bulk != null}
            onClick={deleteSelected}
            className="rounded-md border border-rose-300 px-3 py-1.5 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
          >
            Delete selected ({selected.size})
          </button>
          <button type="button" onClick={clearSelected} className="text-xs text-ink-3 hover:text-ink-2">Clear</button>
        </Card>
      )}

      {/* filters: by content area + by gap type */}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="font-semibold uppercase tracking-wide text-slate-400">Filter</span>
        <label className="inline-flex items-center gap-1">Area
          <select value={areaFilter} onChange={(e) => setAreaFilter(e.target.value)} className={filterSelectCls}>
            <option value="all">All</option>
            {AREA_OPTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <label className="inline-flex items-center gap-1">Gap type
          <select value={gapFilter} onChange={(e) => setGapFilter(e.target.value)} className={filterSelectCls}>
            <option value="all">All</option>
            {GAP_OPTIONS.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>
        {(areaFilter !== "all" || gapFilter !== "all") && (
          <button type="button" onClick={() => { setAreaFilter("all"); setGapFilter("all"); }} className="font-medium text-indigo-600 hover:underline">Clear</button>
        )}
        <span className="text-slate-400">· {shown.length} shown</span>
        {grouping && <button type="button" onClick={() => setGroupFlaws(false)} className="ml-auto font-medium text-indigo-600 hover:underline">Show as table</button>}
      </div>

      {grouping ? (
        <FlawGroups drafts={shown} businessId={businessId} canEdit={canEdit} selectable={approvableShown} selected={selected} onToggle={toggleOne} />
      ) : (
        <DataGrid
          columns={DRAFT_COLUMNS}
          rows={shown}
          getId={(d) => d.id}
          storageKey="drafts"
          onRowClick={(d) => setOpenDraft(d)}
          selectable={canEdit}
          selected={selected as Set<number | string>}
          onToggle={(id) => toggleOne(Number(id))}
          onToggleAll={(all) => (all ? setSelected(new Set(shown.map((d) => d.id))) : clearSelected())}
          emptyText={tab === "ready" ? "Nothing waiting on you — generate a draft from a content task." : "No drafts here."}
        />
      )}

      {/* right-side slide-over editor */}
      {liveOpen && (
        <DraftEditorPanel draft={liveOpen} businessId={businessId} canEdit={canEdit} onClose={() => setOpenDraft(null)} />
      )}
    </div>
  );
}

// A draft card plus (when eligible) a select checkbox for the bulk-approve run. The checkbox sits
// above the untouched DraftReviewCard so the card itself is unchanged.
function DraftRow({
  draft,
  businessId,
  canEdit,
  selectable,
  selected,
  onToggle,
}: {
  draft: ContentDraft;
  businessId: number | null;
  canEdit: boolean;
  selectable: boolean;
  selected: boolean;
  onToggle: (id: number) => void;
}) {
  return (
    <div>
      {canEdit && selectable && (
        <label className="mb-1 flex items-center gap-1.5 pl-1 text-xs text-ink-3">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggle(draft.id)}
            className="h-3.5 w-3.5 rounded border-line-2"
          />
          Select for bulk approve
        </label>
      )}
      <DraftReviewCard draft={draft} businessId={businessId} canEdit={canEdit} />
    </div>
  );
}

// needs_fix drafts grouped by their shared primary flaw, so a reviewer can see (and fix) a whole
// cohort — "8 drafts all need the same disclosure" — instead of hunting it card by card.
function FlawGroups({
  drafts,
  businessId,
  canEdit,
  selectable,
  selected,
  onToggle,
}: {
  drafts: ContentDraft[];
  businessId: number | null;
  canEdit: boolean;
  selectable: ContentDraft[];
  selected: Set<number>;
  onToggle: (id: number) => void;
}) {
  const selectableIds = new Set(selectable.map((d) => d.id));
  // Preserve the incoming (sorted) order of first appearance for each flaw bucket.
  const groups: { flaw: string; items: ContentDraft[] }[] = [];
  const index = new Map<string, number>();
  for (const d of drafts) {
    const flaw = primaryFlaw(d);
    let at = index.get(flaw);
    if (at == null) {
      at = groups.length;
      index.set(flaw, at);
      groups.push({ flaw, items: [] });
    }
    groups[at].items.push(d);
  }

  return (
    <div className="space-y-5">
      {groups.map((g) => (
        <div key={g.flaw}>
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{g.flaw}</h3>
            <span className="rounded-full bg-alert-bg px-2 py-0.5 text-[11px] font-medium text-alert">
              {g.items.length} draft{g.items.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="space-y-3">
            {g.items.map((d) => (
              <DraftRow
                key={d.id}
                draft={d}
                businessId={businessId}
                canEdit={canEdit}
                selectable={selectableIds.has(d.id)}
                selected={selected.has(d.id)}
                onToggle={onToggle}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
