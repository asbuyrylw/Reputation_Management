"use client";

// "Worst things AI is saying now" — the lowest-scoring / contested / wrong-entity answers
// from the latest run, surfaced so the owner sees the problems without drilling into a run.
// Reused on the dashboard and the Audits index.

import Link from "next/link";
import type { Answer } from "@/lib/types";
import { repScore, repBand, repClasses } from "@/lib/repScore";
import { engineLabel } from "@/lib/engines";

// A weak query from the gap model — carries the LLM-authored `fix` (and `addressed_by` topic)
// once the gap model has run with the newer prompt; older audits have only prompt/problem.
export type WeakQuery = { prompt?: string; engine?: string; problem?: string; fix?: string; addressed_by?: string };

function reason(a: Answer): string {
  if (a.entity_confusion) return "AI is describing a different business with your name.";
  if (a.awareness === false) return "AI doesn't know your business here.";
  if (a.mentions_contested) return "AI raises a concern/complaint about you.";
  if ((a.goal_alignment ?? 0) < 0) return "AI leans unfavorable here.";
  return "Weak or off-message answer.";
}

// The specific move that fixes this answer. Prefers the gap model's LLM-authored fix; otherwise
// falls back to a category recommendation keyed off why the answer is weak, so this is useful
// even before the newer gap model has run.
function fixFor(a: Answer, wq?: WeakQuery): string {
  if (wq?.fix) return wq.fix;
  if (a.entity_confusion) return "Publish clear identity / disambiguation content (who you are, where, what you do) so AI stops confusing you with another business.";
  if (a.awareness === false) return "Create foundational owned content (About, Services, FAQ) so AI actually learns and can describe your business here.";
  if (a.mentions_contested) return "Answer this concern head-on with an honest, factual owned page, then earn third-party corroboration AI will cite.";
  if ((a.goal_alignment ?? 0) < 0) return "Out-produce the negative: an accurate, quotable, answer-first page that directly answers this question.";
  return "Answer this question directly on your site with a crisp, quotable, answer-first page.";
}

const norm = (s?: string | null) => (s ?? "").trim().toLowerCase().replace(/\s+/g, " ");

export function WorstAnswers({
  answers,
  runId,
  limit = 3,
  href = "/audits",
  weakQueries,
  showFix = false,
}: {
  answers: Answer[] | undefined;
  runId: number | null;
  limit?: number;
  href?: string;
  weakQueries?: WeakQuery[];
  showFix?: boolean;
}) {
  const scored = (answers ?? []).filter((a) => !a.failed && a.goal_alignment != null);
  const worst = [...scored].sort((a, b) => (a.goal_alignment ?? 0) - (b.goal_alignment ?? 0)).slice(0, limit);
  if (worst.length === 0) return null;
  const byPrompt = new Map<string, WeakQuery>();
  for (const w of weakQueries ?? []) if (w.prompt) byPrompt.set(norm(w.prompt), w);

  return (
    <div className="space-y-2">
      {worst.map((a) => {
        const score = repScore(a.goal_alignment);
        const snippet = (a.answer_text ?? "").slice(0, 150);
        const wq = byPrompt.get(norm(a.prompt));
        return (
          <div key={a.id} className="rounded-lg border border-slate-100 p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">
                {engineLabel(a.engine)}
              </span>
              {score != null && (
                <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${repClasses(score)}`}>
                  {score}/100 · {repBand(score).label}
                </span>
              )}
              <span className="font-medium text-slate-800">“{a.prompt}”</span>
            </div>
            {snippet && <p className="mt-1 text-sm text-slate-600">“{snippet}…”</p>}
            <div className="mt-1 text-xs text-rose-600">Why: {reason(a)}</div>
            {showFix && (
              <div className="mt-2 rounded-md bg-emerald-50 p-2 ring-1 ring-inset ring-emerald-200">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700">The fix — biggest return on your time</span>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-700">{fixFor(a, wq)}</p>
              </div>
            )}
            <div className="mt-2 flex items-center justify-end gap-3">
              <Link href="/next-steps" className="text-xs font-medium text-emerald-700 hover:underline">
                {showFix ? "See it in your plan →" : "Fix this →"}
              </Link>
              <Link
                href={runId ? `/audits/${runId}` : href}
                className="text-xs font-medium text-indigo-600 hover:underline"
              >
                See in audit →
              </Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}
