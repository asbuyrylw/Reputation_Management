"use client";

import { useState } from "react";
import { useVisuals, useGenerateVisual, useApproveVisual, useRejectVisual, useVisualBrief } from "@/lib/hooks";
import { ApiError, apiBase } from "@/lib/api";
import { Pill } from "@/components/ui";
import type { VisualAsset } from "@/lib/types";

// Plain-English kind labels.
const KIND_LABEL: Record<string, string> = {
  image: "AI image",
  quote_card: "Quote card",
  video_brief: "Video brief",
  video: "AI video",
};
const kindLabel = (k: string) => KIND_LABEL[k] ?? k.replace(/_/g, " ");

// Status pill tone.
function statusPill(status: string) {
  if (status === "approved") return <Pill tone="good">Approved</Pill>;
  if (status === "rejected") return <Pill tone="bad">Rejected</Pill>;
  return <Pill tone="neutral">Pending</Pill>;
}

// One generated visual row: kind + status pill, the server-side file path (as text — the file
// lives on the server, so we never try to render the image), compliance note, and approve/reject.
function VisualRow({
  v,
  businessId,
  canEdit,
}: {
  v: VisualAsset;
  businessId: number | null;
  canEdit: boolean;
}) {
  const approve = useApproveVisual(businessId);
  const reject = useRejectVisual(businessId);
  const pending = v.status === "pending";
  const [imgOk, setImgOk] = useState(true);
  const hasImage = !!v.file_path && (v.kind === "image" || v.kind === "quote_card" || v.kind === "meme");
  const hasVideo = !!v.file_path && v.kind === "video";
  const fileSrc = (hasImage || hasVideo) && businessId != null ? `${apiBase()}/businesses/${businessId}/visuals/${v.id}/file` : null;
  const imgSrc = hasImage ? fileSrc : null;
  const videoSrc = hasVideo ? fileSrc : null;
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-700">{kindLabel(v.kind)}</span>
          {statusPill(v.status)}
        </div>
        {canEdit && pending && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => approve.mutate(v.id)}
              disabled={approve.isPending || reject.isPending}
              className="rounded bg-emerald-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {approve.isPending ? "…" : "Approve"}
            </button>
            <button
              type="button"
              onClick={() => reject.mutate(v.id)}
              disabled={approve.isPending || reject.isPending}
              className="rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              {reject.isPending ? "…" : "Reject"}
            </button>
          </div>
        )}
      </div>
      {/* render the actual generated image/video; fall back to the path text if it can't be served */}
      {imgSrc && imgOk ? (
        <a href={imgSrc} target="_blank" rel="noreferrer" className="mt-1.5 block">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imgSrc} alt={kindLabel(v.kind)} onError={() => setImgOk(false)} loading="lazy" className="max-h-56 w-auto rounded border border-slate-200" />
        </a>
      ) : videoSrc && imgOk ? (
        <video src={videoSrc} controls onError={() => setImgOk(false)} className="mt-1.5 max-h-56 w-auto rounded border border-slate-200" />
      ) : v.file_path ? (
        <div className="mt-1 truncate text-[11px] text-slate-400" title={v.file_path}>{v.file_path}</div>
      ) : null}
      {v.compliance_note && (
        <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">
          {v.compliance_note}
        </div>
      )}
    </div>
  );
}

// Collapsible "Add a visual" panel for a single work order. Generates quote cards (work now),
// AI images (needs an image-provider key), or a shootable video brief (until a video key is
// added). Files are produced server-side; this lists them with an approve/reject gate.
export function VisualContentPanel({
  businessId,
  workOrderId,
  canEdit,
}: {
  businessId: number | null;
  workOrderId: number;
  canEdit: boolean;
}) {
  const [open, setOpen] = useState(false);
  // Poll the list while open so a freshly-queued visual appears when its job finishes.
  const { data } = useVisuals(businessId, undefined, open);
  const gen = useGenerateVisual(businessId);
  const [err, setErr] = useState<string | null>(null);
  // Gap-grounded suggestion for the prompt — pulled once the panel is open, so "Add a visual"
  // starts from what this task is actually supposed to convey instead of a blank box.
  const { data: brief } = useVisualBrief(businessId, open ? workOrderId : null);
  const suggested = brief?.prompt || "";

  const imageConfigured = data?.image_configured ?? false;
  const videoConfigured = data?.video_configured ?? false;
  // Only this work order's visuals.
  const visuals = (data?.visuals ?? []).filter((v) => v.work_order_id === workOrderId);

  const submit = (
    kind: "image" | "quote_card" | "video_brief" | "video",
    body: { prompt?: string; text?: string; attribution?: string; topic?: string },
  ) => {
    setErr(null);
    gen.mutate(
      { kind, work_order_id: workOrderId, ...body },
      { onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't start — try again.") },
    );
  };

  const onQuoteCard = () => {
    if (typeof window === "undefined") return;
    const text = window.prompt("Short quote for the card (e.g. a customer testimonial):")?.trim();
    if (!text) return;
    const attribution = window.prompt("Attribution (optional, e.g. — Jane D., Google review):")?.trim();
    submit("quote_card", { text, attribution: attribution || undefined });
  };
  const onImage = () => {
    if (typeof window === "undefined") return;
    const prompt = window.prompt("Describe the image you want generated:", suggested)?.trim();
    if (!prompt) return;
    submit("image", { prompt });
  };
  const onVideoBrief = () => {
    if (typeof window === "undefined") return;
    const topic = window.prompt("Topic for the video brief:", suggested)?.trim();
    if (!topic) return;
    submit("video_brief", { topic });
  };
  const onVideo = () => {
    if (typeof window === "undefined") return;
    const prompt = window.prompt("Describe the short video you want generated (8 seconds):", suggested)?.trim();
    if (!prompt) return;
    submit("video", { prompt });
  };

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-[11px] font-medium text-indigo-600 hover:underline"
      >
        {open ? "▾ Hide visuals" : "▸ Add a visual"}
      </button>
      {open && (
        <div className="mt-1.5 space-y-2 rounded-md bg-slate-50 p-2">
          {/* honesty note: AI images need a key; quote cards work now */}
          {!imageConfigured && (
            <p className="rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">
              AI image generation is off — add an image provider key in .env to enable. Quote cards work now.
            </p>
          )}
          {!videoConfigured && (
            <p className="rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">
              AI video generation is off — set VIDEO_PROVIDER=veo + a Gemini key in .env to render real clips. Video brief works now.
            </p>
          )}

          {canEdit ? (
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={onQuoteCard}
                disabled={gen.isPending}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
              >
                Quote card
              </button>
              <button
                type="button"
                onClick={onImage}
                disabled={gen.isPending || !imageConfigured}
                title={imageConfigured ? undefined : "Add an image provider key in .env to enable AI images."}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                AI image
              </button>
              <button
                type="button"
                onClick={onVideoBrief}
                disabled={gen.isPending}
                title={videoConfigured ? undefined : "A shootable brief until a video provider key is added."}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
              >
                Video brief
              </button>
              <button
                type="button"
                onClick={onVideo}
                disabled={gen.isPending || !videoConfigured}
                title={videoConfigured ? "Renders in 1-3 minutes." : "Set VIDEO_PROVIDER=veo + a Gemini key in .env to enable AI video."}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                AI video
              </button>
            </div>
          ) : (
            <p className="text-[11px] text-slate-400">You don&apos;t have edit access to generate visuals.</p>
          )}

          {gen.isPending && <p className="text-[11px] text-slate-500">Queuing…</p>}
          {err && <p className="text-[11px] text-rose-600">{err}</p>}

          {visuals.length > 0 ? (
            <div className="space-y-1.5">
              {visuals.map((v) => (
                <VisualRow key={v.id} v={v} businessId={businessId} canEdit={canEdit} />
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-slate-400">No visuals yet for this task.</p>
          )}
        </div>
      )}
    </div>
  );
}
