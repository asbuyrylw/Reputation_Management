"use client";

// A compact per-engine read: each AI assistant's 0-100 score + a one-word state
// (Favorable / Neutral / Doesn't know you / Unfavorable). Makes the bimodal reality
// visible (e.g. ChatGPT doesn't know you while Gemini is unfavorable).

import type { PerEngineMetrics, Challenge } from "@/lib/types";
import { repScore, repClasses } from "@/lib/repScore";
import { engineLabel, engineState } from "@/lib/engines";

export function EngineScoreStrip({
  perEngine,
  challenge,
}: {
  perEngine: PerEngineMetrics | undefined;
  challenge: Challenge | null | undefined;
}) {
  const engines = perEngine ? Object.entries(perEngine.engines) : [];
  if (engines.length === 0) return null;
  const byEngine = challenge?.by_engine ?? {};

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {engines.map(([key, m]) => {
        const score = repScore(m.goal_alignment?.mean ?? null);
        const state = engineState(byEngine[key]?.profile);
        return (
          <div key={key} className="rounded-lg border border-gray-100 p-2.5 text-center">
            <div className="text-xs font-medium text-gray-500">{engineLabel(key)}</div>
            <div className="mt-0.5">
              {score != null ? (
                <span className={`inline-block rounded-full border px-2 py-0.5 text-sm font-semibold ${repClasses(score)}`}>
                  {score}
                </span>
              ) : (
                <span className="text-sm text-gray-400">—</span>
              )}
            </div>
            <div className="mt-1 text-[11px] text-gray-500">{state}</div>
          </div>
        );
      })}
    </div>
  );
}
