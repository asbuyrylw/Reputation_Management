"use client";

// Reputation-score trend in the SAME 0-100 language as the rest of the app (not the raw
// -1..1 the old TrendChart used). Good (>=60) and poor (<40) bands are shaded so "is this
// going the right way" is obvious; the latest point is labeled with its score.

import type { SeriesPoint } from "@/lib/types";
import { repScore } from "@/lib/repScore";

export function ScoreTrend({ series, goal }: { series: SeriesPoint[]; goal?: number | null }) {
  const pts = series
    .map((s) => ({ date: s.date, score: repScore(s.goal_alignment) }))
    .filter((p): p is { date: string; score: number } => p.score != null);

  if (pts.length < 2) {
    return (
      <p className="text-sm text-slate-500">
        Your trend line appears after your second audit, so you can see whether your score is rising.
      </p>
    );
  }

  const W = 640, H = 200, P = 30;
  const xs = pts.map((_, i) => P + (i * (W - 2 * P)) / (pts.length - 1));
  const y = (v: number) => H - P - (v / 100) * (H - 2 * P);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${xs[i].toFixed(1)} ${y(p.score).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const first = pts[0];
  const rising = last.score >= first.score;

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Reputation score over time">
        {/* good band >=60, poor band <40 */}
        <rect x={P} y={y(100)} width={W - 2 * P} height={y(60) - y(100)} fill="#16a34a" opacity={0.06} />
        <rect x={P} y={y(40)} width={W - 2 * P} height={y(0) - y(40)} fill="#dc2626" opacity={0.06} />
        <line x1={P} x2={W - P} y1={y(50)} y2={y(50)} stroke="#d1d5db" strokeWidth={1} strokeDasharray="4 4" />
        <text x={W - P} y={y(50) - 4} textAnchor="end" className="fill-slate-400 text-[10px]">50 = neutral</text>
        {goal != null && (
          <>
            <line x1={P} x2={W - P} y1={y(goal)} y2={y(goal)} stroke="#16a34a" strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
            <text x={P} y={y(goal) - 4} className="fill-emerald-700 text-[10px]">Goal {goal}</text>
          </>
        )}
        <path d={d} fill="none" stroke={rising ? "#16a34a" : "#dc2626"} strokeWidth={2.5} />
        {pts.map((p, i) => (
          <circle key={i} cx={xs[i]} cy={y(p.score)} r={3} fill={rising ? "#16a34a" : "#dc2626"} />
        ))}
        {/* label the latest point */}
        <text x={xs[xs.length - 1]} y={y(last.score) - 8} textAnchor="end" className="fill-slate-900 text-xs font-semibold">
          {last.score}
        </text>
      </svg>
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>{first.date}</span>
        <span>{last.date}</span>
      </div>
    </div>
  );
}
