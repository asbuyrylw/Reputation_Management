"use client";

// Right-side slide-over editor for a content draft: Publish at the top, the full editable article
// on the left, and a scores/benchmark panel on the RIGHT. AI assist (Edit-with-AI + Humanize-with-AI)
// runs through the budget-gated verified orchestrator; nothing auto-saves or auto-publishes — the
// operator reviews every change and clicks Save / Publish.

import { useState } from "react";
import Link from "next/link";
import { useEditDraft, useApproveDraft, useHumanizeDraft, useAiEditDraft } from "@/lib/hooks";
import { ApiError } from "@/lib/api";
import { MarkdownBody } from "@/components/MarkdownBody";
import type { ContentDraft } from "@/lib/types";

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

// The "Benchmark" tab: our own SERP benchmark (free, already computed) — how the piece stacks up
// against the pages actually ranking for its query.
function BenchmarkTab({ draft }: { draft: ContentDraft }) {
  const qn = draft.quality_notes || {};
  const serp = qn.serp;

  if (!serp || serp.skipped) {
    return <div className="text-[12.5px] text-slate-400">No SERP benchmark on this piece yet. It’s computed when the draft is generated for a target keyword.</div>;
  }
  return (
    <div className="space-y-3">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">How you compare to ranking pages</div>
        <div className="mt-1 text-[12.5px] text-slate-600">
          {serp.our_words != null && <>Your piece: <b>{serp.our_words}</b> words {serp.target_words != null && <>· ranking pages avg <b>{serp.target_words}</b></>}<br /></>}
          {serp.covered_pct != null && <>Term coverage: <b>{Math.round(serp.covered_pct)}%</b> of what ranking pages cover</>}
          {serp.in_range === false && <span className="ml-1 rounded bg-rose-50 px-1.5 py-0.5 text-[11px] font-medium text-rose-600">thin — add depth</span>}
        </div>
      </div>
      {(serp.terms_missing?.length ?? 0) > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Terms to weave in</div>
          <div className="flex flex-wrap gap-1">
            {serp.terms_missing!.slice(0, 16).map((t) => (
              <span key={t} className="rounded-full bg-rose-50 px-1.5 py-0.5 text-[10.5px] text-rose-600">✗ {t}</span>
            ))}
          </div>
        </div>
      )}
      {serp.competitors && serp.competitors.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Pages you’re up against</div>
          <ul className="space-y-1 text-[12px] text-slate-500">
            {serp.competitors.slice(0, 5).map((c, i) => (
              <li key={i} className="truncate">{c.link ? <a href={c.link} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{c.title || c.link}</a> : c.title}{c.words != null && ` · ${c.words}w`}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function DraftEditorPanel({ draft, businessId, canEdit, onClose }: {
  draft: ContentDraft; businessId: number | null; canEdit: boolean; onClose: () => void;
}) {
  const edit = useEditDraft(businessId);
  const approve = useApproveDraft(businessId);
  const humanize = useHumanizeDraft(businessId);
  const aiEdit = useAiEditDraft(businessId);
  const [tab, setTab] = useState<"scores" | "benchmark">("scores");
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [title, setTitle] = useState(draft.title ?? "");
  const [body, setBody] = useState(draft.body ?? "");
  const [instruction, setInstruction] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const qn = draft.quality_notes || {};
  const wordCount = qn.on_page?.word_count ?? (draft.body ?? "").split(/\s+/).filter(Boolean).length;
  const kwRate = qn.keyword_coverage?.rate != null ? Math.round(qn.keyword_coverage.rate * 100) : null;

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
  const runAiEdit = () => {
    if (!instruction.trim()) return;
    setErr(null);
    aiEdit.mutate({ draftId: draft.id, instruction: instruction.trim() }, {
      onSuccess: (r) => { setBody(r.rewritten_text); setMode("edit"); setInstruction(""); },
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't apply that edit."),
    });
  };
  const assistBusy = humanize.isPending || aiEdit.isPending;

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

        {/* body: article (left) + scores/benchmark (right) */}
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

          {/* right — scores / benchmark */}
          <div className="w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-slate-50/60 p-3">
            <div className="mb-2 inline-flex rounded-md border border-slate-200 bg-white p-0.5 text-xs">
              {(["scores", "benchmark"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`rounded px-2.5 py-1 font-medium capitalize ${tab === t ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                  {t === "benchmark" ? "Benchmark" : "Scores"}
                </button>
              ))}
            </div>

            {tab === "scores" ? (
              <div className="space-y-2">
                <div className="rounded-lg bg-white p-2.5">
                  <ScoreRow label="AI visibility" score={qn.citation_ready?.score} hint="Will AI quote this?" />
                  <ScoreRow label="AEO" score={qn.aeo?.score} hint="Answer-engine ready" />
                  <ScoreRow label="GEO" score={qn.geo?.score} hint="AI-citability grade" />
                  <ScoreRow label="Keywords" score={kwRate} hint="Target terms included" />
                  <ScoreRow label="Naturalness" score={qn.distinctiveness?.score} hint="Reads human, not AI" />
                  <ScoreRow label="On-page SEO" score={qn.on_page?.score} />
                  <ScoreRow label="Readability" score={readabilityScore(qn.readability?.grade)} hint={qn.readability?.grade != null ? `Grade ${qn.readability.grade}` : undefined} />
                </div>
                <div className="rounded-lg bg-white p-2.5 text-[12px] text-slate-600">
                  <div className="flex justify-between"><span>Words</span><b className="tabular-nums">{wordCount}</b></div>
                  <div className="flex justify-between"><span>Images</span><b className="tabular-nums">{qn.on_page?.images ?? 0}</b></div>
                  {draft.target_query && <div className="mt-1 truncate"><span className="text-slate-400">Target:</span> {draft.target_query}</div>}
                  {draft.gap_source && <div className="truncate"><span className="text-slate-400">Closes gap:</span> {draft.gap_source}</div>}
                </div>

                {/* AI assist — edit + humanize via the budget-gated orchestrator (never auto-saves) */}
                {canEdit && (
                  <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-2.5">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">AI assist</div>
                    <textarea
                      value={instruction}
                      onChange={(e) => setInstruction(e.target.value)}
                      rows={2}
                      placeholder="Tell AI what to change — e.g. “make it shorter and warmer”, “add an FAQ section”, “lead with the answer”"
                      className="mt-1.5 w-full rounded-md border border-slate-300 px-2 py-1.5 text-[12px]"
                    />
                    <button
                      onClick={runAiEdit}
                      disabled={assistBusy || !instruction.trim()}
                      className="mt-1.5 w-full rounded-md bg-indigo-600 px-2 py-1.5 text-[12px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {aiEdit.isPending ? "Editing…" : "✎ Edit with AI"}
                    </button>
                    <button
                      onClick={runHumanize}
                      disabled={assistBusy}
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                    >
                      {humanize.isPending ? "Humanizing…" : "✨ Humanize with AI"}
                    </button>
                    <p className="mt-1 text-[10.5px] text-slate-400">AI rewrites into the editor — review it, then Save edits. Nothing publishes automatically.</p>
                  </div>
                )}
                <Link href="/content/drafts" onClick={onClose} className="block text-center text-[11px] text-indigo-600 hover:underline">Full review card →</Link>
              </div>
            ) : (
              <BenchmarkTab draft={draft} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
