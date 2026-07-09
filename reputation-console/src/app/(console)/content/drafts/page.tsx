"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useContentOptimizationStatus, useApproveDraft, useRejectDraft, useKattebCredits } from "@/lib/hooks";
import { DraftReviewCard } from "@/components/DraftReviewCard";
import { DraftEditorPanel, readabilityScore } from "@/components/DraftEditorPanel";
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
    const base = tab === "all" ? (data ?? []) : tab === "ready" ? ready : fixes;
    return sortDrafts(base, sort);
  }, [tab, data, ready, fixes, sort]);

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

  const selectAllShown = () => setSelected(new Set(approvableShown.map((d) => d.id)));
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

  const allShownSelected =
    approvableShown.length > 0 && approvableShown.every((d) => selected.has(d.id));

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

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-3">
            {tab === "ready" ? "Nothing waiting on you right now — check “Held — need an author” or generate a draft from a content task." : "No drafts here."}
          </p>
        </Card>
      ) : grouping ? (
        <FlawGroups
          drafts={shown}
          businessId={businessId}
          canEdit={canEdit}
          selectable={approvableShown}
          selected={selected}
          onToggle={toggleOne}
        />
      ) : (
        <DraftTable
          drafts={shown}
          canEdit={canEdit}
          selected={selected}
          onToggle={toggleOne}
          onToggleAll={(all) => (all ? selectAllShown() : clearSelected())}
          allSelected={shown.length > 0 && shown.every((d) => selected.has(d.id))}
          onOpen={setOpenDraft}
        />
      )}

      {/* right-side slide-over editor */}
      {liveOpen && (
        <DraftEditorPanel draft={liveOpen} businessId={businessId} canEdit={canEdit} onClose={() => setOpenDraft(null)} />
      )}
    </div>
  );
}

// The drafts TABLE — one scannable row per draft (title, area/gap, words, keywords, image,
// readability, AI-visibility, status), a select checkbox for bulk actions, and a click that opens
// the slide-over editor.
function DraftTable({ drafts, canEdit, selected, onToggle, onToggleAll, allSelected, onOpen }: {
  drafts: ContentDraft[]; canEdit: boolean; selected: Set<number>; onToggle: (id: number) => void;
  onToggleAll: (all: boolean) => void; allSelected: boolean; onOpen: (d: ContentDraft) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400">
            {canEdit && <th className="py-2 pl-3"><input type="checkbox" checked={allSelected} onChange={(e) => onToggleAll(e.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300" aria-label="Select all" /></th>}
            <th className="py-2 pr-3">Title</th>
            <th className="py-2 pr-3">Area / gap</th>
            <th className="py-2 pr-3 text-right">Words</th>
            <th className="py-2 pr-3">Keywords</th>
            <th className="py-2 pr-3 text-center">Img</th>
            <th className="py-2 pr-3 text-right">Read</th>
            <th className="py-2 pr-3 text-right">AI-Vis</th>
            <th className="py-2 pr-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {drafts.map((d) => {
            const ai = aiVisScore(d), rd = readScore(d);
            return (
              <tr key={d.id} className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50" onClick={() => onOpen(d)}>
                {canEdit && (
                  <td className="py-2 pl-3" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(d.id)} onChange={() => onToggle(d.id)} className="h-3.5 w-3.5 rounded border-slate-300" aria-label={`Select ${d.title}`} />
                  </td>
                )}
                <td className="max-w-0 py-2 pr-3"><div className="truncate font-medium text-slate-800">{d.title || "Untitled"}</div></td>
                <td className="whitespace-nowrap py-2 pr-3 text-xs text-slate-500">{d.gap_source || d.content_type || d.asset_type || "—"}</td>
                <td className="py-2 pr-3 text-right tabular-nums text-slate-600">{draftWords(d)}</td>
                <td className="max-w-[180px] py-2 pr-3"><div className="truncate text-xs text-slate-500">{d.target_query || "—"}</div></td>
                <td className="py-2 pr-3 text-center">{draftHasImage(d) ? "🖼" : <span className="text-slate-300">—</span>}</td>
                <td className={`py-2 pr-3 text-right font-mono text-xs font-semibold ${scoreCls(rd)}`}>{rd ?? "—"}</td>
                <td className={`py-2 pr-3 text-right font-mono text-xs font-semibold ${scoreCls(ai)}`}>{ai ?? "—"}</td>
                <td className="whitespace-nowrap py-2 pr-3"><StatusBadge status={d.status} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
