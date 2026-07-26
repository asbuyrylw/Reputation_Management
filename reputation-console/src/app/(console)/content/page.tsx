"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useWorkOrders, useTopicalAuthority, useFreshnessQueue, useProduceTopicCluster, useVisuals, useRichMediaDrafts } from "@/lib/hooks";
import { apiBase } from "@/lib/api";
import { contentToProduce, CAP_LABEL } from "@/lib/content";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { EmptyState } from "@/components/primitives";
import { CreateContentButton } from "@/components/CreateContentButton";

function Tile({ k, value, sub, color }: { k: string; value: string; sub: string; color?: string }) {
  return (
    <div className="rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[28px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}</div>
      <div className="mt-1.5 text-[12px] text-ink-3">{sub}</div>
    </div>
  );
}

// A recommended topic -> a real pillar + supporting-spokes PROGRAM (not one article). Producing it runs
// the same cluster builder the strategist uses: a comprehensive pillar page + cross-linked spoke pages,
// recorded as a measured content batch — so "add recommended content" builds real topical authority.
function RecommendRow({ r, businessId, canEdit }: { r: { topic: string; covers_keywords?: number; spokes?: string[]; why?: string }; businessId: number | null; canEdit: boolean }) {
  const produce = useProduceTopicCluster(businessId);
  const nPieces = 1 + Math.min((r.spokes?.length ?? 0), 4);
  return (
    <div className="flex items-center gap-3 border-b border-indigo-100 py-2.5 last:border-0">
      <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink" title={r.why}>{r.topic}</span>
      <span className="shrink-0 font-mono text-[11px] text-ink-4">{r.covers_keywords} kw · {nPieces} pieces</span>
      {!canEdit ? null : produce.isSuccess ? (
        <Link href="/content/briefs" className="shrink-0 rounded-[8px] border border-indigo-100 bg-white px-2.5 py-1 text-[12px] font-semibold text-good hover:bg-indigo-050">✓ Producing — drafts →</Link>
      ) : (
        <button
          type="button"
          onClick={() => produce.mutate({ topic: r.topic, spokes: r.spokes })}
          disabled={produce.isPending}
          title={`Builds a pillar page + ${Math.min((r.spokes?.length ?? 0), 4)} supporting posts, cross-linked`}
          className="shrink-0 rounded-[8px] border border-indigo-100 bg-white px-2.5 py-1 text-[12px] font-semibold text-indigo hover:bg-indigo-050 disabled:opacity-50"
        >
          {produce.isPending ? "Starting…" : "Produce program"}
        </button>
      )}
    </div>
  );
}

// Content hub landing — "everything content, in one view": what to produce, what's in draft,
// what's published, and the topic-authority recommendations not yet on the board, plus the
// outreach that pulls the timeline forward. All read-only; row actions deep-link into the tabs.
// Recent media — a discoverable strip of the videos / images / podcasts / rich content the engine
// generated, linking to the full Media gallery. Only renders when there's media to show.
function RecentMediaCard({ businessId }: { businessId: number | null }) {
  const visuals = useVisuals(businessId);
  const rich = useRichMediaDrafts(businessId);
  const icon = (t: string) => t === "video" ? "▶" : t === "podcast" || t === "report_audio" ? "♪"
    : t === "slide_deck" ? "▤" : t === "infographic" ? "◫" : (t === "image" || t === "quote_card" || t === "meme") ? "▦" : "¶";
  const items: { key: string; kind: string; fileUrl?: string }[] = [];
  for (const v of visuals.data?.visuals ?? []) {
    if (["image", "quote_card", "meme", "video"].includes(v.kind))
      items.push({ key: `v${v.id}`, kind: v.kind, fileUrl: businessId != null ? `${apiBase()}/businesses/${businessId}/visuals/${v.id}/file` : undefined });
  }
  for (const r of rich.data?.drafts ?? []) items.push({ key: `r${r.id}`, kind: r.asset_type });
  if (items.length === 0) return null;
  return (
    <Card className="mb-6">
      <SecHead title="Recent media" note="videos, images, podcasts & rich content you've generated" link={{ label: "Media gallery", href: "/content/media" }} />
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-8">
        {items.slice(0, 8).map((it) => (
          <Link key={it.key} href="/content/media" className="grid aspect-square place-items-center overflow-hidden rounded-[10px] border border-line bg-paper transition hover:border-line-2" title={it.kind.replace(/_/g, " ")}>
            {it.fileUrl && it.kind !== "video" ? <img src={it.fileUrl} alt="" className="h-full w-full object-cover" loading="lazy" /> : <span className="text-[20px] text-ink-3">{icon(it.kind)}</span>}
          </Link>
        ))}
      </div>
    </Card>
  );
}

export default function ContentOverviewPage() {
  const { businessId, businesses, loading, canEdit } = useBusiness();
  const { data: drafts } = useContentDrafts(businessId);
  const { data: workOrders } = useWorkOrders(businessId);
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

  // Same source + filter the Briefs "To Produce" page uses (via the shared contentToProduce helper), so
  // the hub's "produce next" list + KPI tile can never disagree with the Briefs page again.
  const toProduce = contentToProduce(workOrders);
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
        <div className="flex shrink-0 items-center gap-2">
          <CreateContentButton className="inline-flex h-9 items-center rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(79,70,229,0.5)] hover:bg-indigo-strong" />
          <Link href="/content/briefs" className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-white px-4 text-[13.5px] font-semibold text-ink hover:bg-paper">
            See what to produce
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[13px] w-[13px]"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </Link>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile k="To produce" value={String(toProduce.length)} sub="Content on your plan" />
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
              {toProduce.slice(0, 5).map((w) => (
                <div key={w.id} className="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
                  <span className="shrink-0 rounded-[5px] border border-line-2 bg-paper px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-2">{CAP_LABEL[w.capability ?? ""] ?? "Content"}</span>
                  <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">{w.title || "Untitled piece"}</span>
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

      {/* recent media — discoverable gallery entry point */}
      <RecentMediaCard businessId={businessId} />

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
