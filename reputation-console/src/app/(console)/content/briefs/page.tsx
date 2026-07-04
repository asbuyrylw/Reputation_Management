"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useProductionBriefs, useWorkOrders, useContentDrafts, useAssets, useGenerateDraftForWo, useTopicalAuthority, useKeywordIntent, useSetBriefStatus } from "@/lib/hooks";
import { downloadCsv } from "@/lib/download";
import { Button, Card, Chip, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { EmptyState } from "@/components/primitives";
import { RunJobButton } from "@/components/RunJobButton";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { WorkOrder, ContentDraft, Asset, TopicalAuthority, KeywordIntent, ProductionBrief } from "@/lib/types";

// Today as a YYYY-MM-DD string in the local timezone (default for "produced on").
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// "Mark produced" control on a recipe card: reveals a date field (default today, back-datable)
// + Confirm. On success the brief leaves the to-produce list (the list only returns to_produce).
function MarkProducedControl({ brief, businessId }: { brief: ProductionBrief; businessId: number | null }) {
  const setStatus = useSetBriefStatus(businessId);
  const [open, setOpen] = useState(false);
  const [producedOn, setProducedOn] = useState(todayISO());
  return (
    <div className="mt-3 border-t border-line pt-3">
      {!open ? (
        <button
          onClick={() => { setProducedOn(todayISO()); setOpen(true); }}
          className="rounded-md bg-emerald-700 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800"
        >
          ✓ Mark produced
        </button>
      ) : (
        <div className="space-y-1.5 rounded-md bg-emerald-50 p-2 ring-1 ring-inset ring-emerald-200">
          <label className="block text-[11px] font-medium text-emerald-800">
            Produced on
            <input
              type="date"
              value={producedOn}
              max={todayISO()}
              onChange={(e) => setProducedOn(e.target.value)}
              className="mt-0.5 w-full rounded border border-emerald-300 px-1.5 py-1 text-xs"
            />
          </label>
          <p className="text-[10px] text-emerald-700">Defaults to today — change it if it was made earlier.</p>
          <div className="flex gap-1.5">
            <button
              onClick={() => setStatus.mutate({ briefId: brief.id, status: "produced", produced_on: producedOn || todayISO() })}
              disabled={setStatus.isPending}
              className="rounded bg-emerald-700 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {setStatus.isPending ? "Saving…" : "Confirm produced"}
            </button>
            <button onClick={() => setOpen(false)} className="text-[11px] text-ink-3 hover:text-ink-2">Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

// "Topic authority" — the pillar/spoke clusters to own, with a needs-content badge + what to
// write next. Helps the owner see which topics they cover vs. still need a piece for.
function TopicAuthoritySection({ data }: { data: TopicalAuthority | undefined }) {
  if (!data || data.clusters.length === 0) return null;
  const clusters = [...data.clusters].sort((a, b) => a.priority - b.priority).slice(0, 8);
  return (
    <section>
      <SecHead
        title="Topic authority"
        note={`${data.summary.topics} topic${data.summary.topics === 1 ? "" : "s"} from your keywords${data.summary.uncovered > 0 ? ` · ${data.summary.uncovered} still need content` : " · all covered"}. Own a topic by covering its pillar plus the supporting questions.`}
      />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {clusters.map((c) => (
          <Card key={c.topic}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-ink">{c.topic}</span>
              {c.needs_content ? (
                <Chip tone="info">Needs content</Chip>
              ) : (
                <Chip tone="good">{c.owned_pieces} covered</Chip>
              )}
            </div>
            <div className="mt-0.5 text-xs text-ink-3">
              Pillar: {c.pillar} · {c.keyword_count} keyword{c.keyword_count === 1 ? "" : "s"}
              {c.total_search_volume != null ? ` · ~${c.total_search_volume.toLocaleString()} searches/mo` : ""}
            </div>
            {c.spokes.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {c.spokes.slice(0, 6).map((s) => (
                  <span key={s} className="rounded-full bg-line px-1.5 py-0.5 text-[10px] text-ink-3">{s}</span>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
      {data.next_to_write.length > 0 && (
        <Card className="mt-3" accent="info">
          <div className="text-sm font-semibold text-ink">What to write next</div>
          <ul className="mt-2 space-y-2 text-sm text-ink-2">
            {data.next_to_write.slice(0, 3).map((n, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo" aria-hidden />
                <span>
                  <span className="font-semibold text-ink">{n.topic}</span>
                  <span className="text-ink-3"> — covers {n.covers_keywords} keyword{n.covers_keywords === 1 ? "" : "s"}. {n.why}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

// "Keywords by intent" — a small breakdown of how many target keywords sit in each search
// intent, and whether you've published anything for that intent yet.
function KeywordIntentSection({ data }: { data: KeywordIntent | undefined }) {
  if (!data || data.by_intent.length === 0) return null;
  return (
    <section>
      <SecHead
        title="Keywords by intent"
        note={`What people are trying to do when they search these terms — ${data.summary.uncovered > 0 ? `${data.summary.uncovered} intent${data.summary.uncovered === 1 ? "" : "s"} have no content yet.` : "all intents have content."}`}
      />
      <Card>
        <ul className="divide-y divide-line">
          {data.by_intent.map((b) => (
            <li key={b.intent} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <span className="font-medium capitalize text-ink-2">{b.intent.replace(/_/g, " ")}</span>
                {b.examples.length > 0 && (
                  <span className="ml-2 text-xs text-ink-4">e.g. {b.examples.slice(0, 3).join(", ")}</span>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-ink-3">{b.keywords} keyword{b.keywords === 1 ? "" : "s"}</span>
                {b.needs_content ? (
                  <Chip tone="info">Needs content</Chip>
                ) : (
                  <Chip tone="good">{b.owned_pieces} covered</Chip>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}

function humanize(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Pretty platform names for the per-platform recipe headings.
const PLATFORM_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
  reddit: "Reddit",
  gbp: "Google Business Profile",
};
const platformLabel = (p: string) => PLATFORM_LABEL[p.toLowerCase()] ?? humanize(p);

// Group recipes by platform, falling back to the channel when platform is null. Returns the
// groups ordered by size (largest first) so the busiest platforms lead.
function groupByPlatform(recipes: ProductionBrief[]): { key: string; label: string; items: ProductionBrief[] }[] {
  const map = new Map<string, { label: string; items: ProductionBrief[] }>();
  for (const b of recipes) {
    const raw = (b.platform || b.channel || "other").trim();
    const key = raw.toLowerCase();
    if (!map.has(key)) map.set(key, { label: b.platform ? platformLabel(raw) : humanize(raw), items: [] });
    map.get(key)!.items.push(b);
  }
  return Array.from(map.entries())
    .map(([key, g]) => ({ key, ...g }))
    .sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label));
}

// The content the gap analysis says to produce (these are work-orders), vs. the off-platform
// video/social recipes (production_briefs). video_creation appears here but is produced from a recipe.
const CONTENT_CAPS = new Set(["content_writing", "schema_markup", "review_generation", "local_content_creation", "video_creation"]);
const DRAFTABLE = new Set(["content_writing", "schema_markup", "review_generation", "local_content_creation"]);
// Show a manageable first page of content pieces, then expand for the rest.
const CONTENT_PREVIEW = 8;

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
  if (draft?.status === "rejected") return { label: "Draft rejected", cls: "bg-line text-ink-3" };
  return { label: "Not started", cls: "bg-line text-ink-4" };
}

function ContentItem({ wo, draft, asset, businessId, canEdit }: {
  wo: WorkOrder; draft?: ContentDraft; asset?: Asset; businessId: number | null; canEdit: boolean;
}) {
  const gen = useGenerateDraftForWo(businessId);
  const stage = stageOf(draft, asset);
  const target = draft?.target_query ?? asset?.target_query ?? null;
  const published = asset && (asset.published_status === "live" || asset.published_url);
  // A local page-1 GOAL isn't one draftable piece — it needs a program (geo page + blogs + FAQ +
  // social). Route it to the batch flow instead of a single "Generate draft".
  const isLocalGoal = wo.capability === "local_content_creation";
  const canDraft = canEdit && DRAFTABLE.has(wo.capability ?? "") && !isLocalGoal && !draft && !asset;
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-line px-1.5 py-0.5 text-[11px] font-medium text-ink-3">{CAP_LABEL[wo.capability ?? ""] ?? humanize(wo.capability ?? "Content")}</span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${stage.cls}`}>{stage.label}</span>
        {wo.predicted_ai_points != null && wo.predicted_ai_points > 0 && (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">≈ +{wo.predicted_ai_points} AI pts</span>
        )}
      </div>
      <div className="mt-1.5 text-sm font-semibold text-ink">{wo.title}</div>
      {target && <div className="mt-0.5 text-xs text-ink-3">Targets the search: “{target}”</div>}
      {isLocalGoal && !draft && !asset && <div className="mt-0.5 text-[11px] text-ink-4">A page-1 goal needs several pieces (geo page + blogs + FAQ + social) — produce them as a program.</div>}
      {(wo.why_helps_ai_rep || wo.why_helps_seo) && (
        <div className="mt-1 space-y-0.5 text-[11px]">
          {wo.why_helps_ai_rep && <div><span className="font-medium text-indigo">AI reputation:</span> {wo.why_helps_ai_rep}</div>}
          {wo.why_helps_seo && <div><span className="font-medium text-emerald-600">SEO:</span> {wo.why_helps_seo}</div>}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        {canDraft && (
          <Button
            size="sm"
            onClick={() => gen.mutate({ woId: wo.id })}
            disabled={gen.isPending || gen.isSuccess}
          >
            {gen.isPending ? "Generating draft…" : gen.isSuccess ? "Draft queued ✓" : "✨ Generate draft"}
          </Button>
        )}
        {canEdit && isLocalGoal && !draft && !asset && (
          <Link href="/content/batches" className="inline-flex items-center rounded-md bg-indigo px-2.5 py-1 font-semibold text-white hover:bg-indigo-strong">Produce content program →</Link>
        )}
        {draft && !published && (
          <Link href="/content/drafts" className="font-medium text-indigo hover:underline">Review draft →</Link>
        )}
        {published && asset?.published_url ? (
          <a href={asset.published_url} target="_blank" rel="noreferrer" className="font-medium text-emerald-700 hover:underline">View published →</a>
        ) : published ? (
          <Link href="/content/finalized" className="font-medium text-emerald-700 hover:underline">View published →</Link>
        ) : null}
        {!canDraft && !draft && (wo.capability === "video_creation") && (
          <span className="text-ink-4">Produce from a recipe below</span>
        )}
      </div>
    </Card>
  );
}

// A clean "content recipe": each brief field as a labeled row, arrays as bullets.
function Recipe({ brief }: { brief: Record<string, unknown> }) {
  const entries = Object.entries(brief).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return <p className="text-sm text-ink-4">No recipe details.</p>;
  return (
    <dl className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[160px_1fr]">
          <dt className="text-xs font-medium uppercase tracking-wide text-ink-4">{humanize(k)}</dt>
          <dd className="text-sm text-ink-2">
            {Array.isArray(v) ? (
              <ul className="list-disc space-y-0.5 pl-4">
                {v.map((it, i) => <li key={i}>{typeof it === "object" ? JSON.stringify(it) : String(it)}</li>)}
              </ul>
            ) : typeof v === "object" ? (
              <span className="text-ink-3">{JSON.stringify(v)}</span>
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// One recipe card — the brief header, the recipe, the amplification playbook, and the
// "mark produced" control. Extracted so the recipes list can group cards by platform.
function RecipeCard({ brief: b, businessId, canEdit }: { brief: ProductionBrief; businessId: number | null; canEdit: boolean }) {
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-ink px-1.5 py-0.5 text-xs font-medium text-white">{b.channel}</span>
        {b.platform && <span className="text-xs text-ink-3">{b.platform}</span>}
      </div>
      <div className="mt-1 text-sm font-semibold text-ink">{b.title}</div>
      {b.target_query && (
        <div className="mt-0.5 text-xs text-ink-3">Answers the question: “{b.target_query}”</div>
      )}
      <div className="mt-3 border-t border-line pt-3">
        <Recipe brief={b.brief} />
      </div>
      {b.amplification_playbook && (
        <div className="mt-3 rounded-lg border border-indigo-100 bg-indigo-050 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-indigo">How to share it (don’t just post once)</div>
          {b.amplification_playbook.post_to && b.amplification_playbook.post_to.length > 0 && (
            <div className="mt-1 text-sm text-ink-2"><span className="font-medium">Post to:</span> {b.amplification_playbook.post_to.join(", ")}</div>
          )}
          {b.amplification_playbook.cross_share && b.amplification_playbook.cross_share.length > 0 && (
            <div className="text-sm text-ink-2"><span className="font-medium">Then share on:</span> {b.amplification_playbook.cross_share.join(", ")}</div>
          )}
          {b.amplification_playbook.sequence && <div className="mt-1 text-xs text-ink-3">{b.amplification_playbook.sequence}</div>}
          <div className="mt-2 space-y-0.5 text-xs">
            {b.why_helps_ai_rep && <div><span className="font-medium text-indigo">AI reputation:</span> {b.why_helps_ai_rep}</div>}
            {b.why_helps_seo && <div><span className="font-medium text-emerald-600">SEO:</span> {b.why_helps_seo}</div>}
          </div>
        </div>
      )}
      {canEdit && <MarkProducedControl brief={b} businessId={businessId} />}
    </Card>
  );
}

export default function BriefsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data: briefs, isLoading: lb } = useProductionBriefs(businessId);
  const { data: workOrders, isLoading: lw } = useWorkOrders(businessId);
  const { data: drafts } = useContentDrafts(businessId);
  const { data: assets } = useAssets(businessId);
  const { data: topical } = useTopicalAuthority(businessId);
  const { data: keywordIntent } = useKeywordIntent(businessId);
  const [showAllContent, setShowAllContent] = useState(false);

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
            <span className="text-sm text-ink-3">
              Content comes from your latest gap analysis &amp; plan. Refresh the off-platform recipes below from the plan.
            </span>
            <RunJobButton businessId={businessId} jobType="production_briefs" label="Refresh recipes" />
          </div>
        </Card>
      )}

      {contentItems.length === 0 && recipes.length === 0 && !topical?.clusters.length && !keywordIntent?.by_intent.length ? (
        <EmptyState
          title="Nothing to produce yet"
          why="Content to produce is built from the gaps an audit + plan find."
          produces="Once a plan runs, each content piece appears here with its status and a one-click “Generate draft.”"
          timing="An audit + plan takes a few minutes."
          cta={{ label: "Run an audit", href: "/runs" }}
        />
      ) : (
        <div className="space-y-6">
          <TopicAuthoritySection data={topical} />
          <KeywordIntentSection data={keywordIntent} />
          {contentItems.length > 0 && (
            <section>
              <h3 className="mb-2 text-sm font-semibold text-ink">Content pieces ({contentItems.length})</h3>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {(showAllContent ? contentItems : contentItems.slice(0, CONTENT_PREVIEW)).map((w) => (
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
              {contentItems.length > CONTENT_PREVIEW && (
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-3"
                  onClick={() => setShowAllContent((v) => !v)}
                >
                  {showAllContent
                    ? "Show fewer"
                    : `Show ${contentItems.length - CONTENT_PREVIEW} more`}
                </Button>
              )}
            </section>
          )}

          {recipes.length > 0 && (
            <section>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">Video &amp; social recipes ({recipes.length})</h3>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => businessId && downloadCsv(`/businesses/${businessId}/production-briefs/export`, "production_briefs.csv")}
                >
                  Export all (CSV)
                </Button>
              </div>
              <p className="mb-2 text-xs text-ink-3">Off-platform pieces to film/post — what to make and the question it answers when someone asks AI about you. Grouped by platform.</p>
              <div className="space-y-5">
                {groupByPlatform(recipes).map((g) => (
                  <div key={g.key}>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-sm font-semibold text-ink-2">{g.label}</span>
                      <span className="text-xs text-ink-4">{g.items.length}</span>
                    </div>
                    <div className="space-y-3">
                      {g.items.map((b) => (
                        <RecipeCard key={b.id} brief={b} businessId={businessId} canEdit={canEdit} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
