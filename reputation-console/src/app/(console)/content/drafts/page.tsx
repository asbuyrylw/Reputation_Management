"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useContentOptimizationStatus, useApproveDraft } from "@/lib/hooks";
import { DraftReviewCard } from "@/components/DraftReviewCard";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { TabNav } from "@/components/content/TabNav";
import type { ContentDraft } from "@/lib/types";

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
  const [tab, setTab] = useState<Tab>("ready");
  const [sort, setSort] = useState<Sort>("impact");
  const [groupFlaws, setGroupFlaws] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulk, setBulk] = useState<{ done: number; total: number } | null>(null);

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

  return (
    <div>
      <PageHeader
        title="Content drafts"
        subtitle="AI-drafted content waiting for your review. Approving publishes it as an asset and advances its work order — nothing publishes without you."
      />

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

      {/* Bulk approve bar — only when there's something you're allowed to approve in bulk. */}
      {canEdit && approvableShown.length > 0 && (
        <Card className="mb-3 flex flex-wrap items-center gap-3 py-2.5">
          <label className="flex items-center gap-1.5 text-sm text-ink-2">
            <input
              type="checkbox"
              checked={allShownSelected}
              onChange={(e) => (e.target.checked ? selectAllShown() : clearSelected())}
              className="h-4 w-4 rounded border-line-2"
            />
            Select all approvable ({approvableShown.length})
          </label>
          <button
            type="button"
            disabled={selectedApprovable.length === 0 || bulk != null}
            onClick={approveSelected}
            className="rounded-md bg-good px-3 py-1.5 text-sm font-medium text-white hover:brightness-95 disabled:opacity-50"
          >
            {bulk ? `Approving ${bulk.done}/${bulk.total}…` : `Approve selected (${selectedApprovable.length})`}
          </button>
          {selected.size > 0 && !bulk && (
            <button
              type="button"
              onClick={clearSelected}
              className="text-xs text-ink-3 hover:text-ink-2"
            >
              Clear
            </button>
          )}
          <span className="text-xs text-ink-4">
            Only fully-checked drafts (compliance passed, no placeholders) can be approved here — others need per-draft sign-off.
          </span>
        </Card>
      )}

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-3">
            {tab === "ready" ? "Nothing waiting on you right now — check “Needs fixes first” or generate a draft from a content task." : "No drafts here."}
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
        <div className="space-y-3">
          {shown.map((d) => (
            <DraftRow
              key={d.id}
              draft={d}
              businessId={businessId}
              canEdit={canEdit}
              selectable={approvableShown.some((s) => s.id === d.id)}
              selected={selected.has(d.id)}
              onToggle={toggleOne}
            />
          ))}
        </div>
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
