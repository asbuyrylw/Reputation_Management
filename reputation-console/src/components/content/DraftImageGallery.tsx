"use client";

// The images for one content draft — generated from its ![alt](IMAGE: prompt) markers. Renders
// each generated visual as a thumbnail (served by the tenancy-checked /visuals/{id}/file endpoint),
// with its SEO alt text, a compliance note when present, and per-image approve/reject. A "Generate
// images" button enqueues one image job per marker (with the draft_id + the marker's prompt/alt).

import { apiBase } from "@/lib/api";
import { useDraftVisuals, useGenerateVisual, useApproveVisual, useRejectVisual } from "@/lib/hooks";
import { StatusBadge } from "./StatusBadge";
import { ComplianceNotice } from "./ComplianceNotice";
import type { DraftImageMarker } from "@/lib/types";

export function DraftImageGallery({
  businessId,
  draftId,
  markers,
  canEdit,
}: {
  businessId: number | null;
  draftId: number;
  markers: DraftImageMarker[];
  canEdit: boolean;
}) {
  const { data } = useDraftVisuals(businessId, draftId);
  const gen = useGenerateVisual(businessId);
  const approve = useApproveVisual(businessId);
  const reject = useRejectVisual(businessId);
  const visuals = data?.visuals ?? [];
  const configured = data?.image_configured ?? false;

  // Nothing to show and nothing to generate → render nothing (keeps quiet drafts clean).
  if (visuals.length === 0 && markers.length === 0) return null;

  const generateAll = () => {
    for (const m of markers) {
      gen.mutate({ kind: "image", prompt: m.prompt || m.alt_text, draft_id: draftId });
    }
  };
  const pending = gen.isPending || visuals.some((v) => v.status === "pending");

  return (
    <div className="mt-2 rounded-[12px] border border-line bg-paper/60 p-2.5 text-xs">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">
          Images{visuals.length > 0 ? ` · ${visuals.length}` : markers.length > 0 ? ` · ${markers.length} planned` : ""}
        </span>
        {canEdit && markers.length > 0 && (
          <button
            type="button"
            disabled={!configured || pending}
            title={!configured ? "No image provider key configured" : undefined}
            onClick={generateAll}
            className="rounded-md bg-indigo px-2.5 py-1 text-[12px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-50"
          >
            {pending ? "Generating…" : `Generate ${markers.length} image${markers.length === 1 ? "" : "s"}`}
          </button>
        )}
      </div>

      {!configured && visuals.length === 0 && (
        <ComplianceNotice tone="info">Connect an image provider (Gemini / OpenAI) to generate these images.</ComplianceNotice>
      )}

      {/* Planned images (the markers the writer embedded) shown until they're generated */}
      {visuals.length === 0 && markers.length > 0 && (
        <ul className="space-y-1.5">
          {markers.map((m) => (
            <li key={m.index} className="rounded-[10px] border border-line bg-card px-2 py-1.5">
              <div className="flex items-center gap-1.5">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3 w-3 shrink-0 text-indigo"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>
                {m.section_heading && <span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">{m.section_heading}</span>}
              </div>
              <div className="mt-0.5 font-medium text-ink-2">{m.alt_text || "(no alt text)"}</div>
              {m.prompt && <div className="text-ink-4">prompt: {m.prompt}</div>}
            </li>
          ))}
        </ul>
      )}

      {visuals.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {visuals.map((v) => {
            const src = `${apiBase()}/businesses/${businessId}/visuals/${v.id}/file`;
            const alt = (typeof v.meta?.alt_text === "string" && v.meta.alt_text) || v.prompt || "generated image";
            return (
              <div key={v.id} className="overflow-hidden rounded-[10px] border border-line bg-card">
                {v.file_path ? (
                  // eslint-disable-next-line @next/next/no-img-element -- served by our tenancy-checked API, not a static asset
                  <img src={src} alt={alt} className="h-24 w-full object-cover" loading="lazy" />
                ) : (
                  <div className="grid h-24 w-full place-items-center bg-line text-[11px] text-ink-4">
                    {v.status === "pending" ? "generating…" : "no image"}
                  </div>
                )}
                <div className="p-1.5">
                  <div className="mb-1 flex items-center justify-between gap-1">
                    <StatusBadge status={v.status} />
                    <span className="font-mono text-[9px] text-ink-4">{v.provider}</span>
                  </div>
                  <div className="line-clamp-2 text-[11px] text-ink-2" title={alt}>{alt}</div>
                  {v.compliance_note && <div className="mt-1 text-[10px] text-amber">{v.compliance_note}</div>}
                  {canEdit && v.status === "pending" && (
                    <div className="mt-1 flex gap-1">
                      <button type="button" onClick={() => approve.mutate(v.id)} disabled={approve.isPending}
                        className="rounded bg-good px-1.5 py-0.5 text-[10px] font-semibold text-white hover:brightness-95 disabled:opacity-50">Approve</button>
                      <button type="button" onClick={() => reject.mutate(v.id)} disabled={reject.isPending}
                        className="rounded border border-line-2 px-1.5 py-0.5 text-[10px] font-semibold text-ink-2 hover:bg-line/60 disabled:opacity-50">Reject</button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
