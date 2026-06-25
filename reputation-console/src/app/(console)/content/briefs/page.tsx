"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useProductionBriefs, useWorkOrders, useContentDrafts, useAssets, useGenerateDraftForWo } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { RunJobButton } from "@/components/RunJobButton";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { WorkOrder, ContentDraft, Asset } from "@/lib/types";

function humanize(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// The content the gap analysis says to produce (these are work-orders), vs. the off-platform
// video/social recipes (production_briefs). video_creation appears here but is produced from a recipe.
const CONTENT_CAPS = new Set(["content_writing", "schema_markup", "review_generation", "local_content_creation", "video_creation"]);
const DRAFTABLE = new Set(["content_writing", "schema_markup", "review_generation", "local_content_creation"]);

const CAP_LABEL: Record<string, string> = {
  content_writing: "Website content",
  schema_markup: "Website code (schema)",
  review_generation: "Reviews",
  local_content_creation: "Local / geo page",
  video_creation: "Video",
};

// Lifecycle stage for a content item, derived from its latest draft + any published asset.
function stageOf(draft: ContentDraft | undefined, asset: Asset | undefined): { label: string; cls: string } {
  if (asset && (asset.published_status === "live" || asset.published_url)) return { label: "Published", cls: "bg-emerald-100 text-emerald-700" };
  if (asset || draft?.status === "approved") return { label: "Approved — ready to publish", cls: "bg-sky-100 text-sky-700" };
  if (draft?.status === "pending_review") return { label: "Draft in review", cls: "bg-amber-100 text-amber-700" };
  if (draft?.status === "needs_fix") return { label: "Draft needs a fix", cls: "bg-rose-100 text-rose-700" };
  if (draft?.status === "rejected") return { label: "Draft rejected", cls: "bg-slate-200 text-slate-600" };
  return { label: "Not started", cls: "bg-slate-100 text-slate-500" };
}

function ContentItem({ wo, draft, asset, businessId, canEdit }: {
  wo: WorkOrder; draft?: ContentDraft; asset?: Asset; businessId: number | null; canEdit: boolean;
}) {
  const gen = useGenerateDraftForWo(businessId);
  const stage = stageOf(draft, asset);
  const target = draft?.target_query ?? asset?.target_query ?? null;
  const published = asset && (asset.published_status === "live" || asset.published_url);
  const canDraft = canEdit && DRAFTABLE.has(wo.capability ?? "") && !draft && !asset;
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{CAP_LABEL[wo.capability ?? ""] ?? humanize(wo.capability ?? "Content")}</span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${stage.cls}`}>{stage.label}</span>
        {wo.predicted_ai_points != null && wo.predicted_ai_points > 0 && (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">≈ +{wo.predicted_ai_points} AI pts</span>
        )}
      </div>
      <div className="mt-1.5 text-sm font-semibold text-slate-900">{wo.title}</div>
      {target && <div className="mt-0.5 text-xs text-slate-500">Targets the search: “{target}”</div>}
      {(wo.why_helps_ai_rep || wo.why_helps_seo) && (
        <div className="mt-1 space-y-0.5 text-[11px]">
          {wo.why_helps_ai_rep && <div><span className="font-medium text-indigo-600">AI reputation:</span> {wo.why_helps_ai_rep}</div>}
          {wo.why_helps_seo && <div><span className="font-medium text-emerald-600">SEO:</span> {wo.why_helps_seo}</div>}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        {canDraft && (
          <button
            onClick={() => gen.mutate({ woId: wo.id })}
            disabled={gen.isPending || gen.isSuccess}
            className="rounded-md bg-indigo-600 px-2.5 py-1.5 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {gen.isPending ? "Generating draft…" : gen.isSuccess ? "Draft queued ✓" : "✨ Generate draft"}
          </button>
        )}
        {draft && !published && (
          <Link href="/content/drafts" className="font-medium text-indigo-600 hover:underline">Review draft →</Link>
        )}
        {published && asset?.published_url ? (
          <a href={asset.published_url} target="_blank" rel="noreferrer" className="font-medium text-emerald-700 hover:underline">View published →</a>
        ) : published ? (
          <Link href="/content/finalized" className="font-medium text-emerald-700 hover:underline">View published →</Link>
        ) : null}
        {!canDraft && !draft && (wo.capability === "video_creation") && (
          <span className="text-slate-400">Produce from a recipe below</span>
        )}
      </div>
    </Card>
  );
}

// A clean "content recipe": each brief field as a labeled row, arrays as bullets.
function Recipe({ brief }: { brief: Record<string, unknown> }) {
  const entries = Object.entries(brief).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return <p className="text-sm text-slate-400">No recipe details.</p>;
  return (
    <dl className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[160px_1fr]">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{humanize(k)}</dt>
          <dd className="text-sm text-slate-700">
            {Array.isArray(v) ? (
              <ul className="list-disc space-y-0.5 pl-4">
                {v.map((it, i) => <li key={i}>{typeof it === "object" ? JSON.stringify(it) : String(it)}</li>)}
              </ul>
            ) : typeof v === "object" ? (
              <span className="text-slate-500">{JSON.stringify(v)}</span>
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function BriefsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data: briefs, isLoading: lb } = useProductionBriefs(businessId);
  const { data: workOrders, isLoading: lw } = useWorkOrders(businessId);
  const { data: drafts } = useContentDrafts(businessId);
  const { data: assets } = useAssets(businessId);

  if (lb || lw || !workOrders) return <Spinner />;

  // Latest draft + published asset per work order (drafts come back newest-first).
  const draftByWo = new Map<number, ContentDraft>();
  for (const d of drafts ?? []) if (d.work_order_id != null && !draftByWo.has(d.work_order_id)) draftByWo.set(d.work_order_id, d);
  const assetByWo = new Map<number, Asset>();
  for (const a of assets ?? []) if (a.work_order_id != null && !assetByWo.has(a.work_order_id)) assetByWo.set(a.work_order_id, a);

  const contentItems = workOrders
    .filter((w) => CONTENT_CAPS.has(w.capability ?? "") && !w.superseded && !["skipped"].includes(w.status))
    .sort((a, b) => (b.predicted_ai_points ?? -1) - (a.predicted_ai_points ?? -1));
  const recipes = briefs ?? [];

  return (
    <div>
      <PageHeader
        title="Content to produce"
        subtitle="The content your gap analysis says to create — each piece's status, the search it targets, and why it helps. Generate a draft, review it, then publish."
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />
      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-slate-600">
              Content comes from your latest gap analysis &amp; plan. Refresh the off-platform recipes below from the plan.
            </span>
            <RunJobButton businessId={businessId} jobType="production_briefs" label="Refresh recipes" />
          </div>
        </Card>
      )}

      {contentItems.length === 0 && recipes.length === 0 ? (
        <EmptyState
          title="Nothing to produce yet"
          why="Content to produce is built from the gaps an audit + plan find."
          produces="Once a plan runs, each content piece appears here with its status and a one-click “Generate draft.”"
          timing="An audit + plan takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-6">
          {contentItems.length > 0 && (
            <section>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">Content pieces ({contentItems.length})</h3>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {contentItems.map((w) => (
                  <ContentItem
                    key={w.id}
                    wo={w}
                    draft={draftByWo.get(w.id)}
                    asset={assetByWo.get(w.id)}
                    businessId={businessId}
                    canEdit={canEdit}
                  />
                ))}
              </div>
            </section>
          )}

          {recipes.length > 0 && (
            <section>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">Video &amp; social recipes ({recipes.length})</h3>
              <p className="mb-2 text-xs text-slate-500">Off-platform pieces to film/post — what to make and the question it answers when someone asks AI about you.</p>
              <div className="space-y-3">
                {recipes.map((b) => (
                  <Card key={b.id}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">{b.channel}</span>
                      {b.platform && <span className="text-xs text-slate-500">{b.platform}</span>}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">{b.title}</div>
                    {b.target_query && (
                      <div className="mt-0.5 text-xs text-slate-500">Answers the question: “{b.target_query}”</div>
                    )}
                    <div className="mt-3 border-t border-slate-100 pt-3">
                      <Recipe brief={b.brief} />
                    </div>
                    {b.amplification_playbook && (
                      <div className="mt-3 rounded-lg border border-indigo-100 bg-indigo-50/50 p-3">
                        <div className="text-xs font-semibold uppercase tracking-wide text-indigo-500">How to share it (don’t just post once)</div>
                        {b.amplification_playbook.post_to && b.amplification_playbook.post_to.length > 0 && (
                          <div className="mt-1 text-sm text-slate-700"><span className="font-medium">Post to:</span> {b.amplification_playbook.post_to.join(", ")}</div>
                        )}
                        {b.amplification_playbook.cross_share && b.amplification_playbook.cross_share.length > 0 && (
                          <div className="text-sm text-slate-700"><span className="font-medium">Then share on:</span> {b.amplification_playbook.cross_share.join(", ")}</div>
                        )}
                        {b.amplification_playbook.sequence && <div className="mt-1 text-xs text-slate-600">{b.amplification_playbook.sequence}</div>}
                        <div className="mt-2 space-y-0.5 text-xs">
                          {b.why_helps_ai_rep && <div><span className="font-medium text-indigo-600">AI reputation:</span> {b.why_helps_ai_rep}</div>}
                          {b.why_helps_seo && <div><span className="font-medium text-emerald-600">SEO:</span> {b.why_helps_seo}</div>}
                        </div>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
