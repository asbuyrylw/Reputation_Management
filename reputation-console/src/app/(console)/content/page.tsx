"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useProductionBriefs, useTopicalAuthority, useFreshnessQueue, useAddWorkOrder } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { EmptyState } from "@/components/primitives";

function Tile({ k, value, sub, color }: { k: string; value: string; sub: string; color?: string }) {
  return (
    <div className="rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[28px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}</div>
      <div className="mt-1.5 text-[12px] text-ink-3">{sub}</div>
    </div>
  );
}

// A recommended topic -> a real content task (so "needs content" actually produces content):
// adds it to the board, where it shows up on the briefs page with Generate + its spec.
function RecommendRow({ r, businessId, canEdit }: { r: { topic: string; covers_keywords?: number; why?: string }; businessId: number | null; canEdit: boolean }) {
  const add = useAddWorkOrder(businessId);
  return (
    <div className="flex items-center gap-3 border-b border-indigo-100 py-2.5 last:border-0">
      <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink" title={r.why}>{r.topic}</span>
      <span className="shrink-0 font-mono text-[11px] text-ink-4">{r.covers_keywords} kw</span>
      {!canEdit ? null : add.isSuccess ? (
        <Link href="/content/briefs" className="shrink-0 rounded-[8px] border border-indigo-100 bg-white px-2.5 py-1 text-[12px] font-semibold text-good hover:bg-indigo-050">✓ Added — produce →</Link>
      ) : (
        <button
          type="button"
          onClick={() => add.mutate({ title: `Create content: ${r.topic}`, capability: "content_writing", gap_source: "topic authority", source_query: r.topic, area: "content", instruction: r.why, why_helps_ai_rep: r.why })}
          disabled={add.isPending}
          className="shrink-0 rounded-[8px] border border-indigo-100 bg-white px-2.5 py-1 text-[12px] font-semibold text-indigo hover:bg-indigo-050 disabled:opacity-50"
        >
          {add.isPending ? "Adding…" : "+ Add as task"}
        </button>
      )}
    </div>
  );
}

// Content hub landing — "everything content, in one view": what to produce, what's in draft,
// what's published, and the topic-authority recommendations not yet on the board, plus the
// outreach that pulls the timeline forward. All read-only; row actions deep-link into the tabs.
export default function ContentOverviewPage() {
  const { businessId, businesses, loading, canEdit } = useBusiness();
  const { data: drafts } = useContentDrafts(businessId);
  const { data: briefs } = useProductionBriefs(businessId);
  const { data: topical } = useTopicalAuthority(businessId);
  const { data: freshness } = useFreshnessQueue(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Content · Overview" title="Content at a glance" />
        <EmptyState title="No data yet" why="Set up a business and run an audit to start producing content." cta={{ label: "Set up a business", href: "/onboarding" }} />
      </div>
    );
  }

  const toProduce = briefs ?? [];
  const recommended = topical?.next_to_write ?? [];
  const inDraft = (drafts ?? []).filter((d) => d.status === "pending_review" || d.status === "needs_fix" || d.status === "held");
  // "Published" = actually LIVE (matches the backend's live-only definition in gap_completion /
  // content_impact). An approved draft that hasn't gone live yet is surfaced separately, not counted
  // as published — approved is not the same as live-and-earning-traffic.
  const published = (drafts ?? []).filter((d) => ["published", "live"].includes((d.status || "").toLowerCase()));
  const approvedNotLive = (drafts ?? []).filter((d) => (d.status || "").toLowerCase() === "approved");

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader eyebrow="Content · Overview" title="Content at a glance" subtitle="What to produce, what's in draft, what's published, what's recommended — plus the outreach that speeds your timeline. Everything content, in one view." />
        <Link href="/content/briefs" className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(79,70,229,0.5)] hover:bg-indigo-strong">
          See what to produce
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[13px] w-[13px]"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </Link>
      </div>

      {/* KPI tiles */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile k="To produce" value={String(toProduce.length)} sub="Added from your tasks" />
        <Tile k="Recommended" value={String(recommended.length)} sub="Not yet on your board" color="var(--indigo)" />
        <Tile k="In draft" value={String(inDraft.length)} sub="Awaiting review" />
        <Tile k="Published" value={String(published.length)} sub={approvedNotLive.length ? `Live · ${approvedNotLive.length} approved awaiting go-live` : "Live & earning traffic"} color="var(--good)" />
      </div>

      {/* two columns: from your tasks (produce next) + recommended content */}
      <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <SecHead title="From your tasks — produce next" link={{ label: "All", href: "/content/briefs" }} />
          {toProduce.length === 0 ? (
            <p className="text-[13px] text-ink-4">No content tasks queued. Add one from your plan.</p>
          ) : (
            <div>
              {toProduce.slice(0, 5).map((b) => (
                <div key={b.id} className="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
                  <span className="shrink-0 rounded-[5px] border border-line-2 bg-paper px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-2">{b.platform || b.channel}</span>
                  <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">{b.title || b.target_query || "Untitled piece"}</span>
                  <Link href="/content/briefs" className="shrink-0 rounded-[8px] bg-indigo px-2.5 py-1 text-[12px] font-semibold text-white hover:bg-indigo-strong">Generate</Link>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="rounded-[18px] border border-indigo-100 bg-indigo-050 p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_16px_-6px_rgba(15,23,42,0.08)]">
          <SecHead title="Recommended content" link={{ label: "All", href: "/content/briefs" }} />
          <p className="mb-3 text-[13px] text-indigo-strong/85">From your topic authority — add any as a content task and it&apos;s ready to produce on the briefs page.</p>
          {recommended.length === 0 ? (
            <p className="text-[13px] text-ink-4">No recommendations yet — run keyword research to build your topic map.</p>
          ) : (
            <div>
              {recommended.slice(0, 5).map((r) => (
                <RecommendRow key={r.topic} r={r} businessId={businessId} canEdit={canEdit} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* outreach accelerator promo */}
      <Card className="flex flex-wrap items-center gap-4">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-[12px] bg-ink text-white">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[22px] w-[22px]"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" /></svg>
        </div>
        <div className="min-w-[240px] flex-1">
          <div className="font-display text-[17px] font-semibold text-ink">Speed things up with outreach</div>
          <p className="mt-0.5 text-[13.5px] text-ink-3">Earned mentions and directory listings that match your niche pull your timeline forward by weeks.</p>
        </div>
        <Link href="/content/outreach" className="inline-flex h-9 shrink-0 items-center rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white hover:bg-indigo-strong">Open outreach</Link>
      </Card>

      {/* freshness queue — published pieces due for a refresh (Phase-5 freshness lever) */}
      {freshness && freshness.count > 0 && (
        <Card className="mt-5">
          <SecHead title="Due for a refresh" note={`published over ${freshness.threshold_months} months ago`} link={{ label: "Published", href: "/content/finalized" }} />
          <p className="mb-3 text-[13px] text-ink-3"><b className="font-semibold text-ink-2">{freshness.count}</b> piece{freshness.count === 1 ? "" : "s"} could use a refresh — a visible &ldquo;last updated&rdquo; edit keeps AI &amp; Google freshness signals warm.</p>
          <div className="space-y-1.5">
            {freshness.items.slice(0, 5).map((f) => (
              <div key={f.asset_id} className="flex items-center gap-3 border-b border-line py-2 last:border-0">
                <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-ink">{f.title || f.published_url}</span>
                <span className="shrink-0 rounded-full bg-amber-bg px-2 py-0.5 font-mono text-[11px] font-semibold text-amber">{f.age_months} mo old</span>
                <a href={f.published_url} target="_blank" rel="noreferrer" className="shrink-0 text-[12px] font-semibold text-indigo hover:text-indigo-strong">Open →</a>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
