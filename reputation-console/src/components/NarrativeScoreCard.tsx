"use client";

// Narrative crowding-out score — the headline metric. The big 0-100 "Narrative dominance"
// number, the delta vs the last audit, a desired% vs contested% split bar, and a small
// sparkline of the score over time. Renders nothing until the first audit produces a score.

import type { NarrativeScore } from "@/lib/types";
import { Card } from "./ui";
import { Sparkline } from "./Sparkline";

function scoreTone(score: number): { text: string; ring: string } {
  if (score >= 60) return { text: "text-emerald-600", ring: "ring-emerald-200/70" };
  if (score >= 40) return { text: "text-amber-600", ring: "ring-amber-200/70" };
  return { text: "text-rose-600", ring: "ring-rose-200/70" };
}

const pctOf = (v: number) => `${Math.round(v * 100)}%`;

export function NarrativeScoreCard({ narrative }: { narrative: NarrativeScore | null | undefined }) {
  const latest = narrative?.latest ?? null;
  if (!latest) return null;

  const score = Math.round(latest.score);
  const tone = scoreTone(score);
  const delta = narrative?.delta ?? null;
  const desired = latest.desired_pct ?? 0;
  const contested = latest.contested_pct ?? 0;
  // The split bar is desired-vs-contested; remaining width is neutral.
  const desiredW = Math.max(0, Math.min(100, Math.round(desired * 100)));
  const contestedW = Math.max(0, Math.min(100 - desiredW, Math.round(contested * 100)));
  const neutralW = Math.max(0, 100 - desiredW - contestedW);

  const series = (narrative?.series ?? []).map((p) => p.score).filter((v): v is number => v != null);

  return (
    <Card accent="info" className="bg-linear-to-br from-indigo-50/70 to-white">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">Narrative dominance</div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className={`text-[52px] font-bold leading-none tracking-tight ${tone.text}`}>{score}</span>
            <span className="text-base font-medium text-slate-400">/100</span>
            {delta != null && Math.abs(delta) >= 0.5 && (
              <span className={`text-sm font-semibold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                {delta >= 0 ? "▲ +" : "▼ "}
                {Math.abs(Math.round(delta))} pts vs last audit
              </span>
            )}
            {delta != null && Math.abs(delta) < 0.5 && (
              <span className="text-sm font-medium text-slate-400">no change vs last audit</span>
            )}
          </div>
          <p className="mt-2 max-w-xl text-sm leading-snug text-slate-600">
            How much the desired narrative dominates AI answers vs the contested one (0-100).
          </p>
        </div>
        {series.length >= 2 && (
          <div className={`shrink-0 rounded-xl bg-white px-3 py-2 ring-1 ${tone.ring}`}>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Trend</div>
            <Sparkline values={series} width={120} height={34} />
          </div>
        )}
      </div>

      {/* desired vs contested split bar */}
      <div className="mt-4">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-inset ring-slate-200">
          {desiredW > 0 && <div className="h-full bg-linear-to-r from-emerald-400 to-emerald-600" style={{ width: `${desiredW}%` }} />}
          {neutralW > 0 && <div className="h-full bg-slate-200" style={{ width: `${neutralW}%` }} />}
          {contestedW > 0 && <div className="h-full bg-linear-to-r from-rose-400 to-rose-600" style={{ width: `${contestedW}%` }} />}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-medium">
          <span className="flex items-center gap-1.5 text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> {pctOf(desired)} desired narrative
          </span>
          <span className="flex items-center gap-1.5 text-rose-700">
            <span className="h-2 w-2 rounded-full bg-rose-500" /> {pctOf(contested)} contested narrative
          </span>
        </div>
      </div>
    </Card>
  );
}
