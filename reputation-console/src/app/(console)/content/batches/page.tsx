"use client";

import { useBusiness } from "@/lib/business";
import { useContentBatches, useGapCompletion, useGenerateContentBatch, useContentImpact } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { StatusBadge } from "@/components/content/StatusBadge";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { EmptyState } from "@/components/primitives";
import type { ContentBatch, GapCompletion, ContentImpactRow } from "@/lib/types";

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const gTone = (s: number | null | undefined) => (s == null ? "text-ink-4" : s >= 75 ? "text-good" : s >= 55 ? "text-amber" : "text-alert");
const signed = (v: number | null | undefined, digits = 2) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`);

// Human labels for content-type tokens (so a video batch reads "Video script", not "video_script").
const TYPE_LABEL: Record<string, string> = {
  video_script: "Video script", white_paper: "White paper", social_post: "Social post",
  landing_page: "Landing page", local_page: "Local page", blog: "Blog", article: "Article", faq: "FAQ",
};
const typeLabel = (t: string | null | undefined) => (t ? TYPE_LABEL[t] ?? t.replace(/_/g, " ") : "");

// The measured effect of a batch on the gap it targets — the wedge no standalone writing tool has.
function ImpactStrip({ impact }: { impact: ContentImpactRow | null }) {
  if (!impact) {
    return <div className="mt-2 text-[12px] text-ink-4">Impact pending — publish the pieces, then the next audit measures the lift.</div>;
  }
  const closed = impact.gap_pct_closed;
  const tone = closed == null ? "text-ink-3" : closed >= 0.5 ? "text-good" : closed >= 0.15 ? "text-amber" : "text-alert";
  return (
    <div className="mt-2 rounded-[10px] border border-line bg-paper/60 p-2.5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12.5px]">
        <span><span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">% gap closed</span> <b className={tone}>{pct(closed)}</b></span>
        <span><span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">alignment</span> <b className={(impact.alignment_delta ?? 0) >= 0 ? "text-good" : "text-alert"}>{signed(impact.alignment_delta)}</b> <span className="text-ink-4 tabular-nums">({signed(impact.baseline_alignment,2)}→{signed(impact.measured_alignment,2)})</span></span>
        <span><span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">share of voice</span> <b className="text-ink-2">{impact.baseline_sov == null ? "—" : pct(impact.baseline_sov)}→{impact.measured_sov == null ? "—" : pct(impact.measured_sov)}</b></span>
      </div>
      {impact.notes && <div className="mt-1.5 text-[12px] text-ink-3">↳ {impact.notes}</div>}
    </div>
  );
}

function BatchCard({ batch, businessId }: { batch: ContentBatch; businessId: number | null }) {
  const gen = useGenerateContentBatch(businessId);
  const published = (batch.pieces || []).filter((p) => p.published || p.published_asset_id).length;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[14.5px] font-semibold text-ink">{batch.target_topic || batch.label}</div>
          <div className="mt-0.5 text-[11.5px] text-ink-4">{batch.gap_source} · {(batch.content_types || []).map(typeLabel).join(", ")} · {published}/{batch.pieces?.length ?? 0} published</div>
        </div>
        <StatusBadge status={batch.status} />
      </div>
      {/* the pieces — one row per content type with its GEO grade + status */}
      <div className="mt-2.5 space-y-1">
        {(batch.pieces || []).map((p) => (
          <div key={p.id} className="flex items-center gap-2 text-[12.5px]">
            <span className="w-24 shrink-0 rounded bg-line/60 px-1.5 py-0.5 text-center text-[10px] font-semibold uppercase text-ink-3">{typeLabel(p.content_type || p.asset_type)}</span>
            <span className="min-w-0 flex-1 truncate text-ink-2">{p.title}</span>
            {p.geo_score != null && <span className={`font-mono text-[11px] ${gTone(p.geo_score)}`}>GEO {Math.round(p.geo_score)}</span>}
            <StatusBadge status={p.status} />
          </div>
        ))}
      </div>
      <ImpactStrip impact={batch.impact} />
      <div className="mt-2.5 flex items-center gap-2">
        <button
          onClick={() => gen.mutate({ gap_key: batch.gap_key })}
          disabled={gen.isPending}
          className="rounded-[8px] border border-line-2 bg-white px-2.5 py-1 text-[12px] font-medium text-ink-2 hover:bg-line/60 disabled:opacity-50"
        >
          {gen.isPending ? "Queuing…" : "＋ Produce more for this gap"}
        </button>
        {gen.isSuccess && <span className="text-[11px] text-good">Queued ✓</span>}
      </div>
    </Card>
  );
}

// The gap-completion meter — every open content gap and how far the content has moved it.
function GapMeter({ gaps }: { gaps: GapCompletion[] }) {
  if (!gaps.length) return null;
  return (
    <div className="space-y-1.5">
      {gaps.map((g) => {
        const closed = g.impact?.gap_pct_closed ?? null;
        const w = closed == null ? (g.pieces_published > 0 ? 8 : g.pieces_drafted > 0 ? 4 : 0) : Math.max(4, Math.round(closed * 100));
        const tone = closed == null ? "bg-line-2" : closed >= 0.5 ? "bg-good" : closed >= 0.15 ? "bg-amber" : "bg-alert";
        return (
          <div key={g.gap_key} className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] text-ink-2">{g.topic}</div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-line/60"><div className={`h-full rounded-full ${tone}`} style={{ width: `${w}%` }} /></div>
            </div>
            <div className="w-40 shrink-0 text-right font-mono text-[11px] text-ink-4">
              {g.pieces_drafted}p · {g.pieces_published} live{closed != null ? ` · ${pct(closed)} closed` : ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// The rest of the gap analysis — gaps a content PIECE doesn't close (weak AI answers, thin
// corroboration, schema, technical, per-platform actions). Surfaced so "gap completion" reflects the
// WHOLE analysis (answering "are all my gaps showing?"), each with WHERE it's actually worked.
const CATEGORY_LABEL: Record<string, string> = {
  weak_queries: "Weak AI answers",
  thin_corroboration: "Thin third-party corroboration",
  schema_gaps: "Schema / structured data",
  site_technical_gaps: "Technical SEO",
  surface_actions: "Per-platform presence",
};
function OtherGaps({ gaps }: { gaps: GapCompletion[] }) {
  const groups = new Map<string, GapCompletion[]>();
  for (const g of gaps) {
    const k = g.category || g.gap_source || "other";
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(g);
  }
  return (
    <div>
      <SecHead title="Also in your gap analysis" note="gaps a content piece doesn't close — tracked on other surfaces" />
      <Card>
        <div className="space-y-3.5">
          {Array.from(groups.entries()).map(([cat, items]) => (
            <div key={cat}>
              <div className="flex items-center justify-between">
                <span className="text-[12.5px] font-semibold text-ink-2">{CATEGORY_LABEL[cat] ?? cat.replace(/_/g, " ")}</span>
                <span className="font-mono text-[11px] text-ink-4">{items.length}</span>
              </div>
              {items[0]?.where && <div className="text-[11.5px] text-ink-4">{items[0].where}</div>}
              <ul className="mt-1 space-y-0.5">
                {items.slice(0, 6).map((g) => (
                  <li key={g.gap_key} className="flex items-start gap-1.5 text-[12px] text-ink-3">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-line-2" aria-hidden />
                    <span className="min-w-0 truncate">{g.topic}</span>
                  </li>
                ))}
                {items.length > 6 && <li className="pl-2.5 text-[11px] text-ink-4">+{items.length - 6} more</li>}
              </ul>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// Chronological ROI log — every measurement, newest first (wires the /content-impact ledger).
function ImpactLedger({ rows }: { rows: ContentImpactRow[] }) {
  if (!rows.length) return null;
  return (
    <div className="mt-6">
      <SecHead title="Impact log" note="what each measurement moved, most recent first" />
      <Card>
        <div className="space-y-1.5">
          {rows.slice(0, 20).map((r, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-line/50 pb-1.5 text-[12.5px] last:border-0">
              <span className="min-w-0 flex-1 truncate text-ink-2">{r.target_topic || r.label}</span>
              <span className="font-mono text-[11px] text-ink-4">{r.measured_at ? new Date(r.measured_at).toLocaleDateString() : ""}</span>
              <span className={(r.gap_pct_closed ?? 0) >= 0.15 ? "text-good" : "text-ink-3"}>{r.gap_pct_closed == null ? "—" : `${Math.round(r.gap_pct_closed * 100)}% closed`}</span>
              <span className={(r.alignment_delta ?? 0) >= 0 ? "text-good" : "text-alert"}>{r.alignment_delta == null ? "" : `align ${r.alignment_delta >= 0 ? "+" : ""}${r.alignment_delta.toFixed(2)}`}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

export default function BatchesPage() {
  const { businessId, loading } = useBusiness();
  const { data: batches, isLoading } = useContentBatches(businessId);
  const { data: gaps } = useGapCompletion(businessId);
  const { data: ledger } = useContentImpact(businessId);

  if (loading) return <Spinner />;
  return (
    <div>
      <PageHeader
        eyebrow="Monitor · Content impact"
        title="Did the content move the needle?"
        subtitle="The measured effect of your published content on each gap it targeted — how far each gap closed, and how AI answers shifted after the next audit. Produce content over in “To produce.”"
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />

      {gaps && gaps.length > 0 && (() => {
        // Split the whole gap analysis: content-addressable gaps drive the completion meter; the rest
        // (schema, technical, weak queries, corroboration, per-platform) are shown as "tracked
        // elsewhere" so the view reflects EVERY gap, not just the content-fillable slice.
        const contentGaps = gaps.filter((g) => g.content_addressable !== false);
        const otherGaps = gaps.filter((g) => g.content_addressable === false);
        return (
          <div className="mb-6 space-y-4">
            {contentGaps.length > 0 && (
              <div>
                <SecHead title="Gap completion" note="how far content has moved each gap a content piece can close" />
                <Card><GapMeter gaps={contentGaps} /></Card>
              </div>
            )}
            {otherGaps.length > 0 && <OtherGaps gaps={otherGaps} />}
          </div>
        );
      })()}

      <SecHead title="Batches" note="multi-type content per gap, with measured impact" />
      {isLoading ? (
        <Spinner />
      ) : !batches || batches.length === 0 ? (
        <EmptyState title="No content batches yet" why="A batch creates several content types for one gap at once, so you can measure which content — and the collective — moves the score."
          produces="Once you run an audit + plan, use “Fill all gaps” to produce batches; each piece is graded and the batch's impact is measured after the next audit."
          cta={{ label: "Run an audit", href: "/runs" }} />
      ) : (
        <div className="space-y-4">
          {batches.map((b) => <BatchCard key={b.id} batch={b} businessId={businessId} />)}
        </div>
      )}

      {ledger && ledger.length > 0 && <ImpactLedger rows={ledger} />}
    </div>
  );
}
