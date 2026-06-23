"use client";

import { useState } from "react";
import type { Answer } from "@/lib/types";
import { AnswerCard } from "./AnswerCard";
import { RepScoreBadge } from "./RepScoreBadge";

// Consolidates a run's answers into one collapsible row per question (prompt), instead of a
// flat 80+ card scroll. Each row shows the average reputation score + which engines answered;
// expand to read the individual answers.
export function AnswersByPrompt({ answers }: { answers: Answer[] }) {
  const groups = new Map<string, Answer[]>();
  for (const a of answers) {
    const key = a.prompt || "(no prompt)";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(a);
  }
  const entries = [...groups.entries()];
  const [open, setOpen] = useState<Set<string>>(new Set());
  const allOpen = open.size === entries.length && entries.length > 0;

  const toggle = (k: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });
  const toggleAll = () => setOpen(allOpen ? new Set() : new Set(entries.map(([k]) => k)));

  const avgGA = (arr: Answer[]) => {
    const v = arr.map((a) => a.goal_alignment).filter((x): x is number => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-slate-400">
          {entries.length} questions · {answers.length} answers
        </span>
        <button onClick={toggleAll} className="text-xs font-medium text-indigo-600 hover:underline">
          {allOpen ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="space-y-2">
        {entries.map(([prompt, arr]) => {
          const isOpen = open.has(prompt);
          const engines = [...new Set(arr.map((a) => a.engine))];
          const contested = arr.some((a) => a.mentions_contested);
          const owned = arr.some((a) => a.surfaces_owned);
          return (
            <div key={prompt} className="overflow-hidden rounded-lg border border-slate-200">
              <button
                onClick={() => toggle(prompt)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50"
              >
                <RepScoreBadge goalAlignment={avgGA(arr)} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-slate-900">{prompt}</div>
                  <div className="truncate text-xs text-slate-400">
                    {arr.length} {arr.length === 1 ? "answer" : "answers"} · {engines.join(", ")}
                    {contested && <span className="text-rose-500"> · ⚠ contested</span>}
                    {owned && <span className="text-emerald-600"> · owned source</span>}
                  </div>
                </div>
                <svg
                  viewBox="0 0 20 20"
                  className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                  fill="currentColor"
                  aria-hidden
                >
                  <path d="M5.2 7.5L10 12.3l4.8-4.8 1.2 1.2-6 6-6-6z" />
                </svg>
              </button>
              {isOpen && (
                <div className="space-y-2 border-t border-slate-100 bg-slate-50/40 p-3">
                  {arr.map((a) => (
                    <AnswerCard key={a.id} a={a} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
