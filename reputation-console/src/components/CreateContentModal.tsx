"use client";

// Create Content — one button, any format. The owner describes what they want and picks a type;
// every format funnels through the SAME grounded, human-gated pipeline on the backend (text/rich
// media → drafts, images/video → media), so whatever comes out is on-brand (brand rules + source
// material) and waits for approval. Nothing auto-publishes.

import Link from "next/link";
import { useMemo, useState } from "react";
import { useContentTypes, useCreateContent, useGapCompletion, useEnhancePrompt } from "@/lib/hooks";
import type { ContentTypeOption, GapCompletion } from "@/lib/types";

const FAMILY_ORDER: { key: string; label: string; hint: string }[] = [
  { key: "text", label: "Written content", hint: "Blog, article, FAQ, white paper, newsletter…" },
  { key: "rich_media", label: "Audio & rich media", hint: "Podcast, explainer, slide deck, research brief…" },
  { key: "visual", label: "Images & video", hint: "AI image, quote card, generated video clip" },
];

const PLACEHOLDER: Record<string, string> = {
  podcast: "e.g. A 5-minute episode on how term life insurance protects a young Cincinnati family, in plain language.",
  video: "e.g. A 8-second clip: warm scene of a family reviewing finances at their kitchen table, calm and reassuring.",
  explainer_video: "e.g. Explain the debt snowball method step by step for someone new to budgeting.",
  quote_card: "e.g. \"Protecting your family's future starts with one conversation.\" — a shareable quote card.",
  image: "e.g. A friendly, professional hero image of a financial coaching session (no real faces).",
  faq: "e.g. Answer the top 8 questions people ask before their first financial review.",
  white_paper: "e.g. A guide to building an emergency fund on a variable income, for working families.",
};

export function CreateContentModal({ businessId, onClose, initialType, initialDescription, initialGapLabel }: {
  businessId: number | null; onClose: () => void;
  initialType?: string; initialDescription?: string; initialGapLabel?: string;
}) {
  const catalogue = useContentTypes(businessId);
  const gaps = useGapCompletion(businessId);
  const create = useCreateContent(businessId);
  const enhance = useEnhancePrompt(businessId);

  const [type, setType] = useState<string>(initialType ?? "");
  const [description, setDescription] = useState(initialDescription ?? "");
  const [gapKey, setGapKey] = useState("");
  const [aspect, setAspect] = useState("16:9");
  const [done, setDone] = useState<null | { where: string }>(null);
  const [err, setErr] = useState<string | null>(null);
  const [enhancing, setEnhancing] = useState(false);

  async function enhancePrompt() {
    if (!type || !description.trim()) return;
    setErr(null); setEnhancing(true);
    try {
      const r = await enhance.mutateAsync({ content_type: type, description: description.trim() });
      if (r.ok && r.enhanced_prompt) setDescription(r.enhanced_prompt);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't enhance the prompt — please try again.");
    } finally {
      setEnhancing(false);
    }
  }

  const types = catalogue.data?.types ?? [];
  const selected = useMemo(() => types.find((t) => t.content_type === type), [types, type]);
  const isVisualMedia = type === "image" || type === "video";
  const grouped = useMemo(() => {
    const by: Record<string, ContentTypeOption[]> = {};
    for (const t of types) (by[t.family] ||= []).push(t);
    return by;
  }, [types]);

  async function generate() {
    if (!type || !description.trim()) return;
    setErr(null);
    const gap = (gaps.data ?? []).find((g) => g.gap_key === gapKey);
    try {
      const r = await create.mutateAsync({
        content_type: type,
        description: description.trim(),
        gap_key: gapKey || undefined,
        gap_label: gap?.topic || initialGapLabel || undefined,
        aspect_ratio: isVisualMedia ? aspect : undefined,
      });
      setDone({ where: r.family === "visual" ? "Media" : selected?.family === "text" ? "Drafts" : "Media" });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't start generation — please try again.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:p-8" onClick={onClose}>
      <div className="my-auto w-full max-w-2xl rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* header */}
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-slate-900">Create content</h2>
            <p className="mt-0.5 text-[13px] text-slate-500">
              Describe it, pick a format. It&apos;s drafted from your brand rules + source material, then waits for your approval.
            </p>
          </div>
          <button onClick={onClose} className="-mr-1 rounded-lg px-2 py-1 text-xl leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700">×</button>
        </div>

        {done ? (
          <div className="px-6 py-10 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-2xl">✓</div>
            <h3 className="text-base font-semibold text-slate-900">Generating now</h3>
            <p className="mx-auto mt-1 max-w-sm text-[13.5px] text-slate-500">
              Your {selected?.label.toLowerCase()} is being created. It&apos;ll appear in <span className="font-semibold text-slate-700">{done.where}</span> for review in a few minutes — nothing publishes until you approve it.
            </p>
            <div className="mt-5 flex items-center justify-center gap-2">
              <button onClick={() => { setDone(null); setDescription(""); setGapKey(""); }} className="rounded-[10px] border border-line bg-white px-4 py-2 text-[13px] font-semibold text-ink hover:bg-paper">Create another</button>
              <button onClick={onClose} className="rounded-[10px] bg-indigo px-4 py-2 text-[13px] font-semibold text-white hover:bg-indigo-strong">Done</button>
            </div>
          </div>
        ) : (
          <div className="max-h-[70vh] space-y-5 overflow-y-auto px-6 py-5">
            {/* 1. type */}
            <div>
              <label className="mb-2 block text-[11px] font-semibold uppercase tracking-wide text-slate-400">1 · Pick a format</label>
              {catalogue.isLoading ? (
                <div className="py-6 text-center text-[13px] text-slate-400">Loading formats…</div>
              ) : (
                <div className="space-y-3">
                  {FAMILY_ORDER.filter((f) => grouped[f.key]?.length).map((fam) => (
                    <div key={fam.key}>
                      <div className="mb-1.5 text-[12px] font-medium text-slate-600">{fam.label} <span className="text-slate-400">· {fam.hint}</span></div>
                      <div className="flex flex-wrap gap-2">
                        {grouped[fam.key].map((t) => {
                          const active = t.content_type === type;
                          return (
                            <button key={t.content_type} onClick={() => setType(t.content_type)}
                              title={t.needs || undefined}
                              className={`rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition ${active ? "border-indigo bg-indigo text-white" : "border-line bg-paper text-ink-2 hover:border-indigo hover:text-indigo"}`}>
                              {t.label}
                              {!t.ready && <span className={`ml-1.5 text-[10px] ${active ? "text-indigo-100" : "text-amber-500"}`}>needs key</span>}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {selected && !selected.ready && selected.needs && (
                <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-700">⚠ {selected.needs}</p>
              )}
              {selected && selected.ready && selected.needs && (
                <p className="mt-2 text-[12px] text-slate-500">ℹ {selected.needs}</p>
              )}
            </div>

            {/* 2. describe */}
            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">2 · Describe what you want</label>
                <button type="button" onClick={enhancePrompt} disabled={!type || !description.trim() || enhancing}
                  title={type ? "Let AI expand this into an optimized brief for this format (keywords, structure, length, targets — or a HeyGen-ready brief for video)" : "Pick a format first"}
                  className="rounded-full border border-indigo/40 bg-indigo-050 px-2.5 py-1 text-[11.5px] font-semibold text-indigo-strong transition hover:bg-indigo-050/70 disabled:opacity-40">
                  {enhancing ? "Enhancing…" : "✨ Enhance"}
                </button>
              </div>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
                placeholder={PLACEHOLDER[type] || "Describe the piece — the topic, angle, audience, and anything it must include. Then hit ✨ Enhance to turn it into an optimized brief."}
                className="w-full rounded-[10px] border border-line bg-paper p-3 text-[13.5px] leading-relaxed text-ink outline-none focus:border-indigo" />
              <p className="mt-1 text-[11.5px] text-slate-400">
                ✨ Enhance rewrites your description into an optimized brief for this format{type ? "" : " (pick a format first)"} — grounded in your brand rules &amp; source material.
              </p>
            </div>

            {/* 3. options */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-slate-400">Tie to a gap (optional)</label>
                <select value={gapKey} onChange={(e) => setGapKey(e.target.value)}
                  className="w-full rounded-[10px] border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-indigo">
                  <option value="">Not tied to a specific gap</option>
                  {(gaps.data ?? []).filter((g: GapCompletion) => g.content_addressable !== false).map((g: GapCompletion) => (
                    <option key={g.gap_key} value={g.gap_key}>{g.topic}</option>
                  ))}
                </select>
              </div>
              {isVisualMedia && (
                <div>
                  <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-slate-400">Aspect ratio</label>
                  <select value={aspect} onChange={(e) => setAspect(e.target.value)}
                    className="w-full rounded-[10px] border border-line bg-paper px-3 py-2 text-[13px] text-ink outline-none focus:border-indigo">
                    <option value="16:9">Landscape 16:9</option>
                    <option value="1:1">Square 1:1</option>
                    <option value="9:16">Portrait 9:16 (reels/stories)</option>
                  </select>
                </div>
              )}
            </div>

            <p className="text-[12px] text-slate-500">
              Grounded in your <Link href="/content/source" onClick={onClose} className="font-semibold text-indigo hover:underline">brand rules & source material</Link>. Add more docs there for richer, more accurate content.
            </p>

            {err && <p className="rounded-lg bg-rose-50 px-3 py-2 text-[12.5px] text-rose-700">{err}</p>}
          </div>
        )}

        {!done && (
          <div className="flex items-center justify-end gap-2 border-t border-line px-6 py-4">
            <button onClick={onClose} className="rounded-[10px] border border-line bg-white px-4 py-2 text-[13px] font-semibold text-ink hover:bg-paper">Cancel</button>
            <button onClick={generate} disabled={!type || !description.trim() || create.isPending}
              className="rounded-[10px] bg-indigo px-5 py-2 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-50">
              {create.isPending ? "Starting…" : "Generate"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
