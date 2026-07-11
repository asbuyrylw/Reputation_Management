"use client";

// Media hub — the one place to SEE every generated asset: videos (real player), images / quote-cards
// / infographics (lightbox), podcasts (audio player + transcript), and rich content (slide decks,
// explainers, briefs, long-form as rendered markdown). Unions two live sources — visual_assets
// (/visuals, binaries) and rich_media_drafts (/rich-media-drafts, text + podcast audio) — so nothing
// the engine generates stays invisible. Fully wired; every item is fetched from the API.

import { useMemo, useState } from "react";
import { useBusiness } from "@/lib/business";
import { useVisuals, useRichMediaDrafts, useRichMediaDraft, useApproveRichMedia, useRejectRichMedia } from "@/lib/hooks";
import { apiBase } from "@/lib/api";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { MarkdownBody } from "@/components/MarkdownBody";
import type { VisualAsset, RichMediaDraft } from "@/lib/types";

type Kind = "video" | "image" | "podcast" | "deck" | "infographic" | "text";
type MediaItem = {
  key: string; source: "visual" | "rich"; id: number; kind: Kind;
  title: string; assetType: string; status: string;
  fileUrl?: string; audioUrl?: string | null; durationSecs?: number | null;
  createdAt?: string | null;
};

const KIND_META: Record<Kind, { label: string; icon: string; tone: string }> = {
  video: { label: "Video", icon: "▶", tone: "#6d4bd0" },
  image: { label: "Image", icon: "▦", tone: "#0d8a6b" },
  podcast: { label: "Podcast", icon: "♪", tone: "#c67c15" },
  deck: { label: "Slide deck", icon: "▤", tone: "#2563c9" },
  infographic: { label: "Infographic", icon: "◫", tone: "#0a6b53" },
  text: { label: "Content", icon: "¶", tone: "#5d6f77" },
};

const STATUS_TONE: Record<string, string> = {
  approved: "#0f9d63", pending: "#c67c15", pending_review: "#c67c15", rejected: "#b1442f", live: "#0f9d63",
};

function richKind(t: string): Kind {
  if (t === "podcast" || t === "report_audio") return "podcast";
  if (t === "slide_deck") return "deck";
  if (t === "infographic") return "infographic";
  return "text";
}
function visualKind(k: string): Kind | null {
  if (k === "video") return "video";
  if (k === "image" || k === "quote_card" || k === "meme") return "image";
  return null; // video_brief etc. — a spec, not a viewable asset
}
function titleCase(s: string) { return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); }

const FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "All" }, { key: "video", label: "Video" }, { key: "image", label: "Image" },
  { key: "podcast", label: "Podcast" }, { key: "deck", label: "Decks" }, { key: "infographic", label: "Infographics" }, { key: "text", label: "Content" },
];

function MediaCard({ item, onOpen }: { item: MediaItem; onOpen: () => void }) {
  const m = KIND_META[item.kind];
  const st = STATUS_TONE[item.status] ?? "#8698a0";
  return (
    <button onClick={onOpen} className="group flex flex-col overflow-hidden rounded-[14px] border border-line bg-card text-left shadow-[0_1px_2px_rgba(20,24,31,0.05)] transition hover:border-line-2 hover:shadow-[0_8px_26px_-8px_rgba(20,24,31,0.18)]">
      <div className="relative flex aspect-[16/10] items-center justify-center overflow-hidden bg-paper">
        {item.kind === "image" && item.fileUrl ? (
          <img src={item.fileUrl} alt={item.title} className="h-full w-full object-cover" loading="lazy" />
        ) : item.kind === "video" && item.fileUrl ? (
          <><video src={item.fileUrl} className="h-full w-full object-cover" preload="metadata" muted /><span className="absolute grid h-11 w-11 place-items-center rounded-full bg-black/55 text-[15px] text-white">▶</span></>
        ) : (
          <span className="font-display text-[34px]" style={{ color: m.tone }}>{m.icon}</span>
        )}
        <span className="absolute left-2 top-2 rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold" style={{ color: "#fff", background: m.tone }}>{m.label}</span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <div className="line-clamp-2 text-[13.5px] font-semibold leading-snug text-ink">{item.title}</div>
        <div className="mt-auto flex items-center justify-between pt-1">
          <span className="font-mono text-[10.5px] text-ink-4">{titleCase(item.assetType)}</span>
          <span className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold" style={{ color: st, background: `${st}18` }}>{item.status.replace("_", " ")}</span>
        </div>
      </div>
    </button>
  );
}

function MediaModal({ item, businessId, onClose }: { item: MediaItem; businessId: number | null; onClose: () => void }) {
  const needsBody = item.source === "rich" && item.kind !== "podcast";
  const detail = useRichMediaDraft(businessId, needsBody ? item.id : null);
  const approve = useApproveRichMedia(businessId);
  const reject = useRejectRichMedia(businessId);
  const d: RichMediaDraft | undefined = detail.data;
  const m = KIND_META[item.kind];
  const isPending = item.source === "rich" && (item.status === "pending_review" || item.status === "pending");

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-[16px] border border-line bg-card shadow-[0_24px_80px_-20px_rgba(0,0,0,0.5)]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div>
            <div className="mb-0.5 font-mono text-[11px] uppercase tracking-[0.06em]" style={{ color: m.tone }}>{m.label} · {titleCase(item.assetType)}</div>
            <h2 className="font-display text-[18px] font-semibold leading-tight text-ink">{item.title}</h2>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-3 hover:bg-paper">✕</button>
        </div>

        <div className="p-4">
          {item.kind === "video" && item.fileUrl && (
            <video src={item.fileUrl} controls className="max-h-[68vh] w-full rounded-[12px] bg-black" />
          )}
          {item.kind === "image" && item.fileUrl && (
            <img src={item.fileUrl} alt={item.title} className="max-h-[68vh] w-full rounded-[12px] object-contain" />
          )}
          {item.kind === "podcast" && (
            <div className="space-y-3">
              {item.audioUrl ? <audio src={item.audioUrl} controls className="w-full" /> :
                <div className="rounded-[10px] border border-line bg-paper p-3 text-[13px] text-ink-3">Audio isn&apos;t available for this draft (generated as a script/transcript). Connect the NotebookLM audio path to render the podcast.</div>}
              {detail.isLoading ? <Spinner /> : d?.transcript ? (
                <div><div className="mb-1 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Transcript</div><MarkdownBody text={d.transcript} className="text-[13.5px] leading-relaxed text-ink-2" /></div>
              ) : null}
            </div>
          )}
          {(item.kind === "deck" || item.kind === "infographic" || item.kind === "text") && (
            detail.isLoading ? <div className="py-8"><Spinner /></div> :
              d?.body ? <MarkdownBody text={d.body} className="max-h-[68vh] overflow-y-auto text-[14px] leading-relaxed text-ink-2" />
                : <p className="py-6 text-center text-[13.5px] text-ink-3">No content body to display.</p>
          )}
        </div>

        {isPending && (
          <div className="flex items-center justify-end gap-2 border-t border-line p-3">
            <button onClick={() => { reject.mutate(item.id, { onSuccess: onClose }); }} disabled={reject.isPending}
              className="rounded-[10px] border border-line bg-white px-3.5 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper disabled:opacity-60">Reject</button>
            <button onClick={() => { approve.mutate(item.id, { onSuccess: onClose }); }} disabled={approve.isPending}
              className="rounded-[10px] bg-emerald-600 px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-60">{approve.isPending ? "Approving…" : "Approve"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MediaPage() {
  const { businessId, businesses, loading } = useBusiness();
  const visuals = useVisuals(businessId);
  const rich = useRichMediaDrafts(businessId);
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<MediaItem | null>(null);

  const items = useMemo<MediaItem[]>(() => {
    const out: MediaItem[] = [];
    for (const v of (visuals.data?.visuals ?? []) as VisualAsset[]) {
      const k = visualKind(v.kind);
      if (!k) continue;
      out.push({ key: `v${v.id}`, source: "visual", id: v.id, kind: k, title: v.prompt?.slice(0, 80) || titleCase(v.kind),
        assetType: v.kind, status: v.status, fileUrl: businessId != null ? `${apiBase()}/businesses/${businessId}/visuals/${v.id}/file` : undefined, createdAt: v.created_at });
    }
    for (const r of rich.data?.drafts ?? []) {
      const k = richKind(r.asset_type);
      out.push({ key: `r${r.id}`, source: "rich", id: r.id, kind: k, title: r.title || titleCase(r.asset_type),
        assetType: r.asset_type, status: r.status, audioUrl: r.audio_url, durationSecs: r.duration_secs, createdAt: r.created_at });
    }
    out.sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || ""));
    return out;
  }, [visuals.data, rich.data, businessId]);

  const shown = filter === "all" ? items : items.filter((i) => i.kind === filter);
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length };
    for (const i of items) c[i.kind] = (c[i.kind] || 0) + 1;
    return c;
  }, [items]);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return <div><PageHeader eyebrow="Content · Media" title="Media gallery" /><EmptyState title="No business yet" why="Set up a business and generate content to see your media here." cta={{ label: "Set up a business", href: "/onboarding" }} /></div>;
  }

  return (
    <div>
      <PageHeader eyebrow="Content · Media" title="Media gallery"
        subtitle="Every asset the engine generated — videos, images, podcasts, slide decks, infographics and long-form — in one place, each with the right viewer. Preview, then approve or reject." />

      {/* filter bar */}
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {FILTERS.map((f) => (
          <button key={f.key} onClick={() => setFilter(f.key)}
            className={`rounded-full px-3 py-1.5 text-[13px] font-semibold transition ${filter === f.key ? "bg-ink text-white" : "border border-line bg-card text-ink-2 hover:bg-paper"}`}>
            {f.label}{counts[f.key] ? <span className={`ml-1.5 font-mono text-[11px] ${filter === f.key ? "text-white/70" : "text-ink-4"}`}>{counts[f.key]}</span> : null}
          </button>
        ))}
      </div>

      {(visuals.isLoading || rich.isLoading) && items.length === 0 ? (
        <div className="py-10"><Spinner /></div>
      ) : shown.length === 0 ? (
        <Card>
          <p className="py-6 text-center text-[14px] text-ink-3">
            {items.length === 0
              ? "No media yet. Generate visuals from a content brief, or run the rich-media (podcast / deck / infographic) generator — everything you produce shows up here."
              : "No items of this type yet."}
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {shown.map((it) => <MediaCard key={it.key} item={it} onOpen={() => setOpen(it)} />)}
        </div>
      )}

      {open && <MediaModal item={open} businessId={businessId} onClose={() => setOpen(null)} />}
    </div>
  );
}
