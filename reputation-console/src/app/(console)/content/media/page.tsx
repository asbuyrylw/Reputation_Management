"use client";

// Media hub — the one place to SEE every generated asset: videos (real player), images / quote-cards
// / infographics (lightbox), podcasts (audio player + transcript), and rich content (slide decks,
// explainers, briefs, long-form as rendered markdown). Unions two live sources — visual_assets
// (/visuals, binaries) and rich_media_drafts (/rich-media-drafts, text + podcast audio) — so nothing
// the engine generates stays invisible. Fully wired; every item is fetched from the API.

import { useEffect, useMemo, useRef, useState } from "react";
import { useBusiness } from "@/lib/business";
import { useVisuals, useRichMediaDrafts, useRichMediaDraft, useApproveRichMedia, useRejectRichMedia, useRenderRichMediaVideo, useEditRichMedia, usePublishVisualYouTube, useDeleteVisual, useDeleteRichMedia } from "@/lib/hooks";
import { apiBase } from "@/lib/api";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { CreateContentButton } from "@/components/CreateContentButton";
import { EmptyState } from "@/components/primitives";
import { MarkdownBody } from "@/components/MarkdownBody";
import type { VisualAsset, RichMediaDraft } from "@/lib/types";

type Kind = "video" | "image" | "podcast" | "deck" | "infographic" | "text";
type MediaItem = {
  key: string; source: "visual" | "rich"; id: number; kind: Kind;
  title: string; assetType: string; status: string;
  fileUrl?: string; audioUrl?: string | null; durationSecs?: number | null;
  notebookUrl?: string | null; generator?: string | null;
  fixReasons?: string[]; isEditableDraft?: boolean;
  draftId?: number | null;   // for a rendered video: the rich-media script draft it came from (re-render)
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

function MediaModal({ item, businessId, canEdit, onClose }: { item: MediaItem; businessId: number | null; canEdit: boolean; onClose: () => void }) {
  // The rich-media script draft this media item maps to: for a `rich` item it's the item itself; for a
  // rendered `video` (a visual asset) it's the draft the render came from — so "send back with changes"
  // works from the video player too.
  const scriptDraftId = item.source === "rich" ? item.id : (item.kind === "video" ? (item.draftId ?? null) : null);
  // Rich-media details carry the full body AND (for podcasts) the transcript — fetch for every rich
  // item, including podcasts, so the transcript section actually renders; also for a rendered video so
  // the re-render panel can prefill its script.
  const needsBody = item.source === "rich";
  const detail = useRichMediaDraft(businessId, needsBody ? item.id : scriptDraftId);
  const approve = useApproveRichMedia(businessId);
  const reject = useRejectRichMedia(businessId);
  const renderVideo = useRenderRichMediaVideo(businessId);
  const publishYT = usePublishVisualYouTube(businessId);
  const delVisual = useDeleteVisual(businessId);
  const delRich = useDeleteRichMedia(businessId);
  const del = item.source === "visual" ? delVisual : delRich;
  const editRich = useEditRichMedia(businessId);
  const [editing, setEditing] = useState(false);
  const [draftBody, setDraftBody] = useState("");
  // "Send back with changes" (re-render) panel state.
  const [changesOpen, setChangesOpen] = useState(false);
  const [cScript, setCScript] = useState("");
  const [cAvatar, setCAvatar] = useState("");
  const [cVoice, setCVoice] = useState("");
  const [cBg, setCBg] = useState("");
  const [cAspect, setCAspect] = useState<"16:9" | "9:16">("16:9");
  useEffect(() => {
    // prefill the editable script from the draft body/transcript when the panel opens / detail loads
    if (changesOpen && !cScript) setCScript(detail.data?.body || detail.data?.transcript || "");
  }, [changesOpen, detail.data?.body, detail.data?.transcript, cScript]);
  function submitChanges() {
    if (scriptDraftId == null) return;
    renderVideo.mutate({
      draftId: scriptDraftId,
      script: cScript.trim() || undefined,
      avatar_id: cAvatar.trim() || undefined,
      voice_id: cVoice.trim() || undefined,
      background: cBg.trim() || undefined,
      aspect: cAspect,
    });
  }
  const videoRef = useRef<HTMLVideoElement>(null);
  function skip(sec: number) {
    const v = videoRef.current;
    if (v) v.currentTime = Math.max(0, Math.min(v.duration || Number.MAX_SAFE_INTEGER, v.currentTime + sec));
  }
  // The full detail carries the freshest fix_reasons (recomputed on the last edit); fall back to the
  // list row's reasons before the detail loads.
  const fixReasons = (detail.data?.fix_reasons && detail.data.fix_reasons.length ? detail.data.fix_reasons : item.fixReasons) ?? [];
  const canFix = canEdit && item.source === "rich" && (item.isEditableDraft ?? false) &&
    item.status !== "approved" && item.status !== "rejected";
  useEffect(() => { if (detail.data?.body != null) setDraftBody(detail.data.body); }, [detail.data?.body]);
  function saveEdit() {
    editRich.mutate({ draftId: item.id, body: draftBody }, { onSuccess: () => setEditing(false) });
  }
  function handleDelete() {
    const warn = item.status === "approved"
      ? "Delete this asset permanently? It's approved and may be embedded in a published piece — that reference would break. This can't be undone."
      : "Delete this asset permanently? This can't be undone.";
    if (!window.confirm(warn)) return;
    del.mutate(item.id, { onSuccess: onClose });
  }
  const isVideoScript = item.source === "rich" && (item.assetType === "explainer_video" || item.assetType === "video_script");
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
          {(item.status === "needs_fix" || item.status === "held" || (item.status === "pending_review" && fixReasons.length > 0)) && fixReasons.length > 0 && (
            <div className="mb-3 rounded-[10px] border border-amber-300 bg-amber-50 p-3">
              <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-amber-800">What needs fixed</div>
              <ul className="list-disc space-y-0.5 pl-4 text-[12.5px] leading-relaxed text-amber-900">
                {fixReasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
              {canFix && !editing && <button onClick={() => setEditing(true)} className="mt-2 rounded-[8px] bg-amber-600 px-2.5 py-1 text-[12px] font-semibold text-white hover:bg-amber-700">Edit &amp; fix</button>}
            </div>
          )}
          {item.kind === "video" && item.fileUrl && (
            <div className="space-y-2">
              <video ref={videoRef} src={item.fileUrl} controls playsInline className="max-h-[68vh] w-full rounded-[12px] bg-black" />
              <div className="flex items-center justify-center gap-2">
                <button onClick={() => skip(-10)} className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper" title="Back 10 seconds">⏪ 10s</button>
                <button onClick={() => skip(-1)} className="rounded-[10px] border border-line bg-white px-2.5 py-1.5 text-[12.5px] font-semibold text-ink hover:bg-paper" title="Back 1 second">◀ 1s</button>
                <button onClick={() => { const v = videoRef.current; if (v) v.paused ? v.play() : v.pause(); }} className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper" title="Play/Pause">⏯</button>
                <button onClick={() => skip(1)} className="rounded-[10px] border border-line bg-white px-2.5 py-1.5 text-[12.5px] font-semibold text-ink hover:bg-paper" title="Forward 1 second">1s ▶</button>
                <button onClick={() => skip(10)} className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper" title="Forward 10 seconds">10s ⏩</button>
              </div>
            </div>
          )}
          {item.kind === "image" && item.fileUrl && (
            <img src={item.fileUrl} alt={item.title} className="max-h-[68vh] w-full rounded-[12px] object-contain" />
          )}
          {item.kind === "podcast" && (
            <div className="space-y-3">
              {item.audioUrl ? (
                <audio src={item.audioUrl} controls className="w-full" />
              ) : item.notebookUrl ? (
                <>
                  <a href={item.notebookUrl} target="_blank" rel="noreferrer"
                    className="flex items-center justify-center gap-2 rounded-[12px] bg-indigo px-4 py-3 text-[14.5px] font-semibold text-white shadow-sm hover:bg-indigo-strong">
                    <span aria-hidden>▶</span> Open in NotebookLM to listen &amp; download
                  </a>
                  <p className="text-[12px] leading-relaxed text-ink-4">Generated in NotebookLM under your Gemini Enterprise account. Google doesn&apos;t offer an audio-download API, so the finished episode plays and downloads from NotebookLM Studio.</p>
                </>
              ) : (
                <div className="rounded-[10px] border border-line bg-paper p-3 text-[13px] text-ink-3">This is an AI-generated podcast <b>script</b> (no rendered audio).</div>
              )}
              {/* Script/transcript — for the LLM-script drafts. NotebookLM drafts carry only the link
                  message in the body, so we skip it there (the button above is the deliverable). */}
              {!item.notebookUrl && (detail.isLoading ? <Spinner /> : d?.transcript ? (
                <div><div className="mb-1 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Script</div><MarkdownBody text={d.transcript} className="text-[13.5px] leading-relaxed text-ink-2" /></div>
              ) : null)}
            </div>
          )}
          {(item.kind === "deck" || item.kind === "infographic" || item.kind === "text") && (
            detail.isLoading ? <div className="py-8"><Spinner /></div> :
              editing ? (
                <div className="space-y-2">
                  <textarea value={draftBody} onChange={(e) => setDraftBody(e.target.value)} spellCheck
                    className="h-[52vh] w-full resize-y rounded-[10px] border border-line bg-paper p-3 font-mono text-[12.5px] leading-relaxed text-ink-2 focus:border-ink-4 focus:outline-none" />
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => { setEditing(false); setDraftBody(d?.body || ""); }}
                      className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper">Cancel</button>
                    <button onClick={saveEdit} disabled={editRich.isPending}
                      className="rounded-[10px] bg-indigo px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-60">{editRich.isPending ? "Saving…" : "Save & re-check"}</button>
                  </div>
                </div>
              ) : d?.body ? (
                <div className="space-y-2">
                  <MarkdownBody text={d.body} className="max-h-[68vh] overflow-y-auto text-[14px] leading-relaxed text-ink-2" />
                  {canFix && <button onClick={() => setEditing(true)} className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper">✎ Edit</button>}
                </div>
              ) : <p className="py-6 text-center text-[13.5px] text-ink-3">No content body to display.</p>
          )}

          {/* Send back with changes: edit the script and/or pick a different presenter, voice,
              background, or orientation, then re-render. Works from the video player (a rendered
              video links back to its script draft) and from the script draft itself. */}
          {canEdit && scriptDraftId != null && (isVideoScript || item.kind === "video") && (
            <div className="mt-4 rounded-[12px] border border-line bg-paper/50 p-3">
              <button onClick={() => setChangesOpen((o) => !o)} className="flex w-full items-center justify-between text-left">
                <span className="text-[13px] font-semibold text-ink">✎ Send back with changes &amp; re-render</span>
                <span className="text-ink-4">{changesOpen ? "▲" : "▼"}</span>
              </button>
              {changesOpen && (
                <div className="mt-3 space-y-3">
                  <p className="text-[11.5px] leading-snug text-ink-4">Edit the narration and/or pick a different presenter, voice, background, or orientation, then re-render. The avatar speaks the edited script <b>verbatim</b>.</p>
                  <div>
                    <label className="mb-1 block font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Narration script</label>
                    <textarea value={cScript} onChange={(e) => setCScript(e.target.value)} spellCheck
                      className="h-40 w-full resize-y rounded-[10px] border border-line bg-white p-2.5 font-mono text-[12.5px] leading-relaxed text-ink-2 focus:border-ink-4 focus:outline-none"
                      placeholder="Leave unchanged to keep the current script" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Orientation</label>
                      <select value={cAspect} onChange={(e) => setCAspect(e.target.value as "16:9" | "9:16")}
                        className="w-full rounded-[10px] border border-line bg-white px-2.5 py-1.5 text-[13px] text-ink focus:border-ink-4 focus:outline-none">
                        <option value="16:9">Landscape (16:9)</option>
                        <option value="9:16">Portrait / Reels (9:16)</option>
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Background</label>
                      <input value={cBg} onChange={(e) => setCBg(e.target.value)} placeholder="#0b1020 or image URL"
                        className="w-full rounded-[10px] border border-line bg-white px-2.5 py-1.5 text-[13px] text-ink focus:border-ink-4 focus:outline-none" />
                    </div>
                    <div>
                      <label className="mb-1 block font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Avatar ID <span className="normal-case text-ink-4/70">(optional)</span></label>
                      <input value={cAvatar} onChange={(e) => setCAvatar(e.target.value)} placeholder="default presenter"
                        className="w-full rounded-[10px] border border-line bg-white px-2.5 py-1.5 text-[13px] text-ink focus:border-ink-4 focus:outline-none" />
                    </div>
                    <div>
                      <label className="mb-1 block font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Voice ID <span className="normal-case text-ink-4/70">(optional)</span></label>
                      <input value={cVoice} onChange={(e) => setCVoice(e.target.value)} placeholder="default voice"
                        className="w-full rounded-[10px] border border-line bg-white px-2.5 py-1.5 text-[13px] text-ink focus:border-ink-4 focus:outline-none" />
                    </div>
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={submitChanges} disabled={renderVideo.isPending || renderVideo.isSuccess}
                      className="rounded-[10px] bg-indigo px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-60">
                      {renderVideo.isPending ? "Starting…" : renderVideo.isSuccess ? "Re-rendering…" : "Save changes & re-render"}</button>
                  </div>
                  <p className="text-[11px] leading-snug text-ink-4">Avatar &amp; voice IDs are HeyGen identifiers — leave blank to keep the current professional presenter. Re-rendering costs one render.</p>
                </div>
              )}
            </div>
          )}
        </div>

        {isVideoScript && (
          <div className="space-y-2 border-t border-line p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] leading-snug text-ink-4"><b>Render video</b> = HeyGen avatar speaks the script <b>verbatim</b> (brand-safe — recommended for financial content).</span>
              <button onClick={() => renderVideo.mutate({ draftId: item.id })} disabled={renderVideo.isPending || renderVideo.isSuccess}
                className="shrink-0 rounded-[10px] bg-indigo px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-60">
                {renderVideo.isPending ? "Starting…" : renderVideo.isSuccess ? "Rendering…" : "▶ Render video"}</button>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11.5px] leading-snug text-ink-4"><b>Produced</b> = HeyGen Video Agent adds B-roll + motion graphics (~20–45 min; AI-expands narration — review before publishing). <b>Veo clip</b> = short generative clip.</span>
              <div className="flex shrink-0 items-center gap-2">
                <button onClick={() => renderVideo.mutate({ draftId: item.id, provider: "heygen_agent" })} disabled={renderVideo.isPending || renderVideo.isSuccess}
                  className="rounded-[10px] border border-indigo/40 bg-indigo-050 px-3 py-1.5 text-[12.5px] font-semibold text-indigo-strong hover:bg-indigo-050/70 disabled:opacity-60">✨ Produced</button>
                <button onClick={() => renderVideo.mutate({ draftId: item.id, provider: "veo" })} disabled={renderVideo.isPending || renderVideo.isSuccess}
                  className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-ink hover:bg-paper disabled:opacity-60">Veo clip</button>
              </div>
            </div>
          </div>
        )}
        {item.kind === "video" && item.fileUrl && (
          <div className="flex items-center justify-between gap-2 border-t border-line p-3">
            <span className="text-[12px] leading-snug text-ink-4">Publish to YouTube (unlisted, with captions) — the most-cited source in AI answers.</span>
            <button onClick={() => publishYT.mutate(item.id)} disabled={publishYT.isPending || publishYT.isSuccess}
              className="shrink-0 rounded-[10px] bg-[#c4302b] px-3.5 py-1.5 text-[13px] font-semibold text-white hover:opacity-90 disabled:opacity-60">
              {publishYT.isPending ? "Publishing…" : publishYT.isSuccess ? "Queued ✓" : "▶ Publish to YouTube"}</button>
          </div>
        )}
        {isPending && (
          <div className="flex items-center justify-end gap-2 border-t border-line p-3">
            <button onClick={() => { reject.mutate(item.id, { onSuccess: onClose }); }} disabled={reject.isPending}
              className="rounded-[10px] border border-line bg-white px-3.5 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper disabled:opacity-60">Reject</button>
            <button onClick={() => { approve.mutate(item.id, { onSuccess: onClose }); }} disabled={approve.isPending}
              className="rounded-[10px] bg-emerald-600 px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-60">{approve.isPending ? "Approving…" : "Approve"}</button>
          </div>
        )}
        {canEdit && (
          <div className="flex items-center justify-between gap-2 border-t border-line p-3">
            <span className="text-[11.5px] leading-snug text-ink-4">
              Remove this asset permanently{item.status === "approved" ? " (it may be referenced in a published piece)" : ""}.
            </span>
            <button onClick={handleDelete} disabled={del.isPending}
              className="shrink-0 rounded-[10px] border border-rose-200 bg-white px-3.5 py-1.5 text-[13px] font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-60">
              {del.isPending ? "Deleting…" : "Delete"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function MediaPage() {
  const { businessId, businesses, canEdit, loading } = useBusiness();
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
        assetType: v.kind, status: v.status, draftId: v.draft_id,
        fileUrl: businessId != null ? `${apiBase()}/businesses/${businessId}/visuals/${v.id}/file` : undefined, createdAt: v.created_at });
    }
    for (const r of rich.data?.drafts ?? []) {
      const k = richKind(r.asset_type);
      out.push({ key: `r${r.id}`, source: "rich", id: r.id, kind: k, title: r.title || titleCase(r.asset_type),
        assetType: r.asset_type, status: r.status, audioUrl: r.audio_url, durationSecs: r.duration_secs,
        notebookUrl: r.notebook_url, generator: r.generator, fixReasons: r.fix_reasons, isEditableDraft: r.is_editable_draft,
        createdAt: r.created_at });
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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader eyebrow="Content · Media" title="Media gallery"
          subtitle="Every asset the engine generated — videos, images, podcasts, slide decks, infographics and long-form — in one place, each with the right viewer. Preview, then approve or reject." />
        <CreateContentButton className="inline-flex h-9 shrink-0 items-center rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white shadow-sm hover:bg-indigo-strong" />
      </div>

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

      {open && <MediaModal item={open} businessId={businessId} canEdit={canEdit} onClose={() => setOpen(null)} />}
    </div>
  );
}
