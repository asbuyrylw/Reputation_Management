"use client";

// Briefs & scripts (rich-media drafts) that still need editing / fixing / producing, surfaced in the
// DRAFTS flow — deep articles, research briefs, slide decks, infographic briefs, and video/podcast
// scripts. These are editable text drafts (not finished media), so they belong here alongside content
// drafts rather than in Media. Once approved + produced, the rendered artifact shows up in Media.
import { useEffect, useState } from "react";
import {
  useRichMediaDrafts, useRichMediaDraft, useEditRichMedia, useApproveRichMedia,
  useRejectRichMedia, useRenderRichMediaVideo,
} from "@/lib/hooks";
import { MarkdownBody } from "@/components/MarkdownBody";
import { Spinner } from "@/components/ui";
import type { RichMediaDraft } from "@/lib/types";

const STATUS_TONE: Record<string, string> = {
  pending_review: "#c67c15", held: "#b1442f", needs_fix: "#b1442f", approved: "#0f9d63", rejected: "#8698a0",
};
function titleCase(s: string) { return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); }

function EditorModal({ businessId, draftId, canEdit, onClose }: {
  businessId: number | null; draftId: number; canEdit: boolean; onClose: () => void;
}) {
  const detail = useRichMediaDraft(businessId, draftId);
  const edit = useEditRichMedia(businessId);
  const approve = useApproveRichMedia(businessId);
  const reject = useRejectRichMedia(businessId);
  const render = useRenderRichMediaVideo(businessId);
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState("");
  const d: RichMediaDraft | undefined = detail.data;
  useEffect(() => { if (d?.body != null) setBody(d.body); }, [d?.body]);
  const fixReasons = d?.fix_reasons ?? [];
  const isVideoScript = d?.asset_type === "explainer_video" || d?.asset_type === "video_script";
  const canAct = canEdit && d && d.status !== "approved" && d.status !== "rejected";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:p-8" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-[16px] border border-line bg-card shadow-[0_24px_80px_-20px_rgba(0,0,0,0.5)]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div>
            <div className="mb-0.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">{titleCase(d?.asset_type || "")}</div>
            <h2 className="font-display text-[18px] font-semibold leading-tight text-ink">{d?.title || "Draft"}</h2>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-3 hover:bg-paper">✕</button>
        </div>

        <div className="p-4">
          {fixReasons.length > 0 && (
            <div className="mb-3 rounded-[10px] border border-amber-300 bg-amber-50 p-3">
              <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-amber-800">What needs fixed</div>
              <ul className="list-disc space-y-0.5 pl-4 text-[12.5px] leading-relaxed text-amber-900">
                {fixReasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
              {canAct && !editing && <button onClick={() => setEditing(true)} className="mt-2 rounded-[8px] bg-amber-600 px-2.5 py-1 text-[12px] font-semibold text-white hover:bg-amber-700">Edit &amp; fix</button>}
            </div>
          )}
          {detail.isLoading ? <div className="py-8"><Spinner /></div> : editing ? (
            <div className="space-y-2">
              <textarea value={body} onChange={(e) => setBody(e.target.value)} spellCheck
                className="h-[52vh] w-full resize-y rounded-[10px] border border-line bg-paper p-3 font-mono text-[12.5px] leading-relaxed text-ink-2 focus:border-ink-4 focus:outline-none" />
              <div className="flex items-center justify-end gap-2">
                <button onClick={() => { setEditing(false); setBody(d?.body || ""); }} className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper">Cancel</button>
                <button onClick={() => edit.mutate({ draftId, body }, { onSuccess: () => setEditing(false) })} disabled={edit.isPending}
                  className="rounded-[10px] bg-indigo px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-60">{edit.isPending ? "Saving…" : "Save & re-check"}</button>
              </div>
            </div>
          ) : d?.body ? (
            <div className="space-y-2">
              <MarkdownBody text={d.body} className="max-h-[60vh] overflow-y-auto text-[14px] leading-relaxed text-ink-2" />
              {canAct && <button onClick={() => setEditing(true)} className="rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper">✎ Edit</button>}
            </div>
          ) : <p className="py-6 text-center text-[13.5px] text-ink-3">No content body to display.</p>}
        </div>

        {canAct && !editing && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line p-3">
            {isVideoScript && (
              <button onClick={() => render.mutate({ draftId })} disabled={render.isPending || render.isSuccess}
                className="mr-auto rounded-[10px] bg-indigo px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-60">
                {render.isPending ? "Starting…" : render.isSuccess ? "Rendering…" : "▶ Produce video"}</button>
            )}
            <button onClick={() => reject.mutate(draftId, { onSuccess: onClose })} disabled={reject.isPending}
              className="rounded-[10px] border border-line bg-white px-3.5 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper disabled:opacity-60">Reject</button>
            <button onClick={() => approve.mutate(draftId, { onSuccess: onClose })} disabled={approve.isPending}
              className="rounded-[10px] bg-emerald-600 px-3.5 py-1.5 text-[13px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-60">{approve.isPending ? "Approving…" : "Approve"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

export function RichMediaDraftsSection({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data } = useRichMediaDrafts(businessId);
  const [open, setOpen] = useState<number | null>(null);
  // Editable, not-yet-produced text drafts (deep_article/research_brief/slide_deck/infographic/video/
  // podcast scripts) that still need review or a fix — the ones that belong in the Drafts flow.
  const drafts = (data?.drafts ?? []).filter(
    (d) => (d.is_editable_draft ?? false) && ["pending_review", "held", "needs_fix", "pending"].includes(d.status),
  );
  if (drafts.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="mb-1 font-display text-[15px] font-semibold text-ink">Briefs &amp; scripts to fix or produce</h2>
      <p className="mb-3 text-[12.5px] text-ink-4">Editable long-form / deck / infographic / video &amp; podcast scripts. Fix them here, then approve or produce — the finished video/audio then appears in Media.</p>
      <div className="overflow-hidden rounded-[12px] border border-line">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-paper text-[11px] uppercase tracking-[0.05em] text-ink-4">
            <tr><th className="px-3 py-2 font-semibold">Title</th><th className="px-3 py-2 font-semibold">Type</th><th className="px-3 py-2 font-semibold">Status</th><th className="px-3 py-2 font-semibold">Needs fixed</th><th className="px-3 py-2" /></tr>
          </thead>
          <tbody>
            {drafts.map((d) => {
              const tone = STATUS_TONE[d.status] ?? "#8698a0";
              return (
                <tr key={d.id} className="border-t border-line hover:bg-paper/60">
                  <td className="max-w-[280px] truncate px-3 py-2 text-ink">{d.title || titleCase(d.asset_type)}</td>
                  <td className="px-3 py-2 text-ink-3">{titleCase(d.asset_type)}</td>
                  <td className="px-3 py-2"><span className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold" style={{ color: tone, background: `${tone}18` }}>{d.status.replace("_", " ")}</span></td>
                  <td className="max-w-[260px] truncate px-3 py-2 text-[12px] text-ink-4">{(d.fix_reasons && d.fix_reasons[0]) || (d.status === "pending_review" ? "—" : "review needed")}{d.fix_reasons && d.fix_reasons.length > 1 ? ` (+${d.fix_reasons.length - 1})` : ""}</td>
                  <td className="px-3 py-2 text-right"><button onClick={() => setOpen(d.id)} className="rounded-[8px] border border-line bg-white px-2.5 py-1 text-[12px] font-semibold text-ink hover:bg-paper">{canEdit ? "Open & edit" : "View"}</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {open != null && <EditorModal businessId={businessId} draftId={open} canEdit={canEdit} onClose={() => setOpen(null)} />}
    </section>
  );
}
