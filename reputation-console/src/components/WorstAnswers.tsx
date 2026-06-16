"use client";

// "Worst things AI is saying now" — the lowest-scoring / contested / wrong-entity answers
// from the latest run, surfaced so the owner sees the problems without drilling into a run.
// Reused on the dashboard and the Audits index.

import Link from "next/link";
import type { Answer } from "@/lib/types";
import { repScore, repBand, repClasses } from "@/lib/repScore";
import { engineLabel } from "@/lib/engines";

function reason(a: Answer): string {
  if (a.entity_confusion) return "AI is describing a different business with your name.";
  if (a.awareness === false) return "AI doesn't know your business here.";
  if (a.mentions_contested) return "AI raises a concern/complaint about you.";
  if ((a.goal_alignment ?? 0) < 0) return "AI leans unfavorable here.";
  return "Weak or off-message answer.";
}

export function WorstAnswers({
  answers,
  runId,
  limit = 3,
  href = "/audits",
}: {
  answers: Answer[] | undefined;
  runId: number | null;
  limit?: number;
  href?: string;
}) {
  const scored = (answers ?? []).filter((a) => !a.failed && a.goal_alignment != null);
  const worst = [...scored].sort((a, b) => (a.goal_alignment ?? 0) - (b.goal_alignment ?? 0)).slice(0, limit);
  if (worst.length === 0) return null;

  return (
    <div className="space-y-2">
      {worst.map((a) => {
        const score = repScore(a.goal_alignment);
        const snippet = (a.answer_text ?? "").slice(0, 150);
        return (
          <div key={a.id} className="rounded-lg border border-gray-100 p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">
                {engineLabel(a.engine)}
              </span>
              {score != null && (
                <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${repClasses(score)}`}>
                  {score}/100 · {repBand(score).label}
                </span>
              )}
              <span className="font-medium text-gray-800">“{a.prompt}”</span>
            </div>
            {snippet && <p className="mt-1 text-sm text-gray-600">“{snippet}…”</p>}
            <div className="mt-1 flex items-center justify-between">
              <span className="text-xs text-rose-600">Why: {reason(a)}</span>
              <Link
                href={runId ? `/audits/${runId}` : href}
                className="text-xs font-medium text-blue-600 hover:underline"
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
