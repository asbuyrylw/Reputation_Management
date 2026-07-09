"use client";

// Right-side slide-over editor for a content draft (the Katteb-style review UX the owner asked
// for): Publish at the top, the full editable article on the left, and a scores/report panel on
// the RIGHT with a "Scores" tab and an "Analyze Competitors" tab (our SERP benchmark + a
// human-triggered Katteb SEO analysis). Reuses the existing draft hooks; nothing auto-publishes.

import { useState } from "react";
import Link from "next/link";
import { useEditDraft, useApproveDraft, useAnalyzeSeo, useKattebCredits, useHumanizeDraft } from "@/lib/hooks";
import { ApiError } from "@/lib/api";
import { MarkdownBody } from "@/components/MarkdownBody";
import type { ContentDraft, DraftKatteb } from "@/lib/types";

function scoreTone(n: number | null | undefined): string {
  if (n == null) return "text-slate-400";
  if (n >= 70) return "text-emerald-600";
  if (n >= 50) return "text-amber-600";
  return "text-rose-600";
}

// Readability is stored as a Flesch-Kincaid GRADE (lower = easier; ideal ~8-10). Convert it to a
// comparable 0-100 readability score so it sits alongside the other scores. Exported for the table.
export function readabilityScore(grade: number | null | undefined): number | null {
  if (grade == null) return null;
  return Math.max(0, Math.min(100, Math.round(100 - Math.abs(grade - 9) * 8)));
}

function ScoreRow({ label, score, max = 100, hint }: { label: string; score: number | null | undefined; max?: number; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-slate-100 py-1.5 last:border-0">
      <div className="min-w-0">
        <div className="text-[12.5px] font-medium text-slate-700">{label}</div>
        {hint && <div className="text-[10.5px] text-slate-400">{hint}</div>}
      </div>
      <div className={`shrink-0 font-mono text-sm font-bold ${scoreTone(score)}`}>
        {score == null ? "—" : `${Math.round(score)}${max === 100 ? "" : `/${max}`}`}
      </div>
    </div>
  );
}

// The "Analyze Competitors" tab: our own SERP benchmark (free, already computed) + the deeper
// Katteb SEO/competitor analysis (human-triggered, ~1000 credits).
function CompetitorsTab({ draft, businessId }: { draft: ContentDraft; businessId: number | null }) {
  const analyze = useAnalyzeSeo(businessId);
  const { data: credits } = useKattebCredits(businessId);
  const qn = draft.quality_notes || {};
  const serp = qn.serp;
  const katteb: DraftKatteb | undefined = qn.katteb;
  const st = katteb?.structure;

  return (
    <div className="space-y-4">
      {/* our own SERP benchmark (free) */}
      {serp && !serp.skipped ? (
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Our SERP benchmark</div>
          <div className="mt-1 text-[12.5px] text-slate-600">
            {serp.our_words != null && <>Your piece: <b>{serp.our_words}</b> words {serp.target_words != null && <>· ranking pages avg <b>{serp.target_words}</b></>}<br /></>}
            {serp.covered_pct != null && <>Term coverage: <b>{Math.round(serp.covered_pct)}%</b> of what ranking pages cover</>}
          </div>
          {serp.competitors && serp.competitors.length > 0 && (
            <ul className="mt-1.5 space-y-1 text-[12px] text-slate-500">
              {serp.competitors.slice(0, 5).map((c, i) => (
                <li key={i} className="truncate">{c.link ? <a href={c.link} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{c.title || c.link}</a> : c.title}{c.words != null && ` · ${c.words}w`}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="text-[12.5px] text-slate-400">No SERP benchmark on this piece yet.</div>
      )}

      {/* Katteb deep analysis */}
      <div className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[12.5px] font-semibold text-indigo-800">Katteb deep SEO analysis</div>
          {credits?.configured && credits.credits_available != null && (
            <span className="font-mono text-[10.5px] text-slate-400">{credits.credits_available.toLocaleString()} credits left</span>
          )}
        </div>
        {katteb ? (
          <div className="mt-2">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]">
              <span>Your SEO score: <b className={scoreTone(katteb.seo_score)}>{katteb.seo_score ?? "—"}</b></span>
              {katteb.competitor_scores && <span className="text-slate-500">competitors avg <b>{katteb.competitor_scores.avg}</b> · top <b>{katteb.competitor_scores.top}</b></span>}
            </div>
            {st && (
              <div className="mt-1.5 grid grid-cols-3 gap-2 text-center text-[11px]">
                <div className="rounded bg-white p-1.5"><div className="font-bold text-slate-800">{st.word_count_avg}<span className="text-slate-400"> / {st.word_count_top}</span></div><div className="text-slate-400">words avg/top</div></div>
                <div className="rounded bg-white p-1.5"><div className="font-bold text-slate-800">{st.headings_avg}<span className="text-slate-400"> / {st.headings_top}</span></div><div className="text-slate-400">headings</div></div>
                <div className="rounded bg-white p-1.5"><div className="font-bold text-slate-800">{st.images_avg}<span className="text-slate-400"> / {st.images_top}</span></div><div className="text-slate-400">images</div></div>
              </div>
            )}
            {katteb.competitors && katteb.competitors.length > 0 && (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-[11.5px]">
                  <thead><tr className="text-[10px] uppercase tracking-wide text-slate-400">
                    <th className="py-1 pr-2">Domain</th><th className="py-1 pr-2 text-right">Words</th><th className="py-1 pr-2 text-right">H</th><th className="py-1 pr-2 text-right">Img</th><th className="py-1 pr-2 text-right">Ent</th><th className="py-1 text-right">SEO</th>
                  </tr></thead>
                  <tbody>
                    {katteb.competitors.map((c, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-1 pr-2"><a href={c.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{c.domain}</a></td>
                        <td className="py-1 pr-2 text-right tabular-nums">{c.words ?? "—"}</td>
                        <td className="py-1 pr-2 text-right tabular-nums">{c.headings ?? "—"}</td>
                        <td className="py-1 pr-2 text-right tabular-nums">{c.images ?? "—"}</td>
                        <td className="py-1 pr-2 text-right tabular-nums">{c.entities ?? "—"}</td>
                        <td className={`py-1 text-right font-semibold tabular-nums ${scoreTone(c.seo_score)}`}>{c.seo_score ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-1 text-[10.5px] text-slate-400">Analyzed {katteb.analyzed_at ? new Date(katteb.analyzed_at).toLocaleDateString() : ""}{katteb.keyword ? ` · "${katteb.keyword}"` : ""}</div>
          </div>
        ) : credits?.configured ? (
          <div className="mt-2">
            <p className="text-[12px] text-slate-500">See how this piece stacks up against the actual top-ranking pages for its keyword (competitor stats + an SEO score). Uses ~1,000 Katteb credits.</p>
            <button
              type="button"
              onClick={() => analyze.mutate({ draftId: draft.id })}
              disabled={analyze.isPending || analyze.isSuccess}
              className="mt-2 rounded-md bg-indigo-600 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {analyze.isPending ? "Starting…" : analyze.isSuccess ? "Running… (1-3 min)" : "Run Katteb analysis"}
            </button>
            {analyze.isSuccess && <p className="mt-1 text-[11px] text-slate-500">Analyzing — the results appear here in a minute or two (refresh the draft).</p>}
            {analyze.isError && <p className="mt-1 text-[11px] text-rose-600">{(analyze.error as ApiError)?.message ?? "Couldn't start."}</p>}
          </div>
        ) : (
          <p className="mt-2 text-[12px] text-slate-400">Katteb isn&apos;t configured (add KATTEB_API_KEY on the backend to enable deep SEO analysis).</p>
        )}
      </div>
    </div>
  );
}

export function DraftEditorPanel({ draft, businessId, canEdit, onClose }: {
  draft: ContentDraft; businessId: number | null; canEdit: boolean; onClose: () => void;
}) {
  const edit = useEditDraft(businessId);
  const approve = useApproveDraft(businessId);
  const humanize = useHumanizeDraft(businessId);
  const [tab, setTab] = useState<"scores" | "competitors">("scores");
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [title, setTitle] = useState(draft.title ?? "");
  const [body, setBody] = useState(draft.body ?? "");
  const [err, setErr] = useState<string | null>(null);
  const qn = draft.quality_notes || {};
  const wordCount = qn.on_page?.word_count ?? (draft.body ?? "").split(/\s+/).filter(Boolean).length;

  const save = () => {
    setErr(null);
    edit.mutate({ draftId: draft.id, title, body }, { onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't save."), onSuccess: () => setMode("read") });
  };
  const publish = () => {
    setErr(null);
    approve.mutate({ draftId: draft.id }, {
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't publish."),
      onSuccess: onClose,
    });
  };
  const runHumanize = () => {
    setErr(null);
    humanize.mutate(draft.id, {
      onSuccess: (r) => { setBody(r.rewritten_text); setMode("edit"); },
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't humanize."),
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30" onClick={onClose}>
      <div className="flex h-full w-full max-w-3xl flex-col bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* top bar — Publish lives here */}
        <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-2.5">
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close">✕</button>
          <div className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800">{draft.title || "Untitled draft"}</div>
          {canEdit && (
            <div className="flex items-center gap-2">
              {mode === "edit" ? (
                <button onClick={save} disabled={edit.isPending} className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50">{edit.isPending ? "Saving…" : "Save edits"}</button>
              ) : (
                <button onClick={() => setMode("edit")} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">Edit</button>
              )}
              <button onClick={publish} disabled={approve.isPending} className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">{approve.isPending ? "Publishing…" : "Publish"}</button>
            </div>
          )}
        </div>
        {err && <div className="border-b border-rose-100 bg-rose-50 px-4 py-1.5 text-[12px] text-rose-700">{err}</div>}

        {/* body: article (left) + scores/competitors (right) */}
        <div className="flex min-h-0 flex-1">
          {/* left — the article */}
          <div className="min-w-0 flex-1 overflow-y-auto p-4">
            {mode === "edit" ? (
              <div className="space-y-2">
                <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm font-semibold" placeholder="Title" />
                <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={28} className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-[12.5px] leading-relaxed" placeholder="Article (markdown)" />
              </div>
            ) : (
              <MarkdownBody text={draft.body || ""} className="text-sm text-slate-700" />
            )}
          </div>

          {/* right — scores / competitors */}
          <div className="w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-slate-50/60 p-3">
            <div className="mb-2 inline-flex rounded-md border border-slate-200 bg-white p-0.5 text-xs">
              {(["scores", "competitors"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`rounded px-2.5 py-1 font-medium capitalize ${tab === t ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                  {t === "competitors" ? "Competitors" : "Scores"}
                </button>
              ))}
            </div>

            {tab === "scores" ? (
              <div className="space-y-2">
                <div className="rounded-lg bg-white p-2.5">
                  <ScoreRow label="AI Visibility" score={qn.citation_ready?.score} hint="Will AI quote this?" />
                  <ScoreRow label="Readability" score={readabilityScore(qn.readability?.grade)} hint={qn.readability?.grade != null ? `Grade ${qn.readability.grade}` : undefined} />
                  <ScoreRow label="On-page SEO" score={qn.on_page?.score} />
                  <ScoreRow label="GEO grade" score={qn.geo?.score} hint="Answer-engine ready" />
                  {qn.katteb?.seo_score != null && <ScoreRow label="Katteb SEO" score={qn.katteb.seo_score} />}
                </div>
                <div className="rounded-lg bg-white p-2.5 text-[12px] text-slate-600">
                  <div className="flex justify-between"><span>Words</span><b className="tabular-nums">{wordCount}</b></div>
                  <div className="flex justify-between"><span>Images</span><b className="tabular-nums">{qn.on_page?.images ?? 0}</b></div>
                  {draft.target_query && <div className="mt-1 truncate"><span className="text-slate-400">Target:</span> {draft.target_query}</div>}
                  {draft.gap_source && <div className="truncate"><span className="text-slate-400">Closes gap:</span> {draft.gap_source}</div>}
                </div>
                {canEdit && (
                  <button onClick={runHumanize} disabled={humanize.isPending} className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50">
                    {humanize.isPending ? "Humanizing…" : "✨ Humanize (Katteb, ~100 cr)"}
                  </button>
                )}
                <Link href="/content/drafts" onClick={onClose} className="block text-center text-[11px] text-indigo-600 hover:underline">Full review card →</Link>
              </div>
            ) : (
              <CompetitorsTab draft={draft} businessId={businessId} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
