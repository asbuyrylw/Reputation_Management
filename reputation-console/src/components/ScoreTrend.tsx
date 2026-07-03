"use client";

// Reputation-score trend in the SAME 0-100 language as the rest of the app (not the raw
// -1..1 the old TrendChart used). Good (>=60) and poor (<40) bands are shaded so "is this
// going the right way" is obvious; the latest point is labeled with its score.

import { useState } from "react";
import type { SeriesPoint } from "@/lib/types";
import { repScore } from "@/lib/repScore";

export function ScoreTrend({ series, goal, projected }: { series: SeriesPoint[]; goal?: number | null; projected?: number | null }) {
  const pts = series
    .map((s) => ({ date: s.date, score: repScore(s.goal_alignment) }))
    .filter((p): p is { date: string; score: number } => p.score != null);

  // Interactive hover: index of the point the pointer is over (null = none).
  const [hover, setHover] = useState<number | null>(null);

  if (pts.length < 2) {
    return (
      <p className="text-sm text-slate-500">
        Your trend line appears after your second audit, so you can see whether your score is rising.
      </p>
    );
  }

  const W = 640, H = 200, P = 30;
  // When a projection is supplied, reserve room on the right for the dashed "expected path" to it.
  const hasProj = projected != null && Number.isFinite(projected);
  const rightPad = hasProj ? 96 : 0;
  const lastX = W - P - rightPad;
  const xs = pts.map((_, i) => P + (i * (lastX - P)) / (pts.length - 1));
  const y = (v: number) => H - P - (v / 100) * (H - 2 * P);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${xs[i].toFixed(1)} ${y(p.score).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const first = pts[0];
  const rising = last.score >= first.score;
  // Even hit bands so hovering anywhere near a point selects it.
  const bandW = (lastX - P) / (pts.length - 1);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Reputation score over time" onMouseLeave={() => setHover(null)}>
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
        {/* expected path: dashed projection from the latest actual point toward the target */}
        {hasProj && (
          <>
            <line x1={xs[xs.length - 1]} y1={y(last.score)} x2={W - P} y2={y(projected!)} stroke="#6366f1" strokeWidth={2} strokeDasharray="5 4" opacity={0.85} />
            <circle cx={W - P} cy={y(projected!)} r={3.5} fill="none" stroke="#6366f1" strokeWidth={2} />
            <text x={W - P} y={y(projected!) - 8} textAnchor="end" className="fill-indigo-600 text-xs font-semibold">~{Math.round(projected!)}</text>
            <text x={W - P} y={H - 8} textAnchor="end" className="fill-indigo-400 text-[10px]">expected</text>
          </>
        )}
        {/* hover: guide line, emphasized point, and a tooltip with the exact score */}
        {hover != null && pts[hover] && (() => {
          const hx = xs[hover];
          const hy = y(pts[hover].score);
          const bw = 104, bh = 36;
          const bx = Math.min(Math.max(hx - bw / 2, P), W - P - bw);
          const by = hy - bh - 12 < 2 ? hy + 12 : hy - bh - 12;
          return (
            <g pointerEvents="none">
              <line x1={hx} x2={hx} y1={P} y2={H - P} stroke="#94a3b8" strokeWidth={1} strokeDasharray="3 3" />
              <circle cx={hx} cy={hy} r={5} fill="#fff" stroke={rising ? "#16a34a" : "#dc2626"} strokeWidth={2.5} />
              <rect x={bx} y={by} width={bw} height={bh} rx={6} fill="#0f172a" opacity={0.92} />
              <text x={bx + bw / 2} y={by + 14} textAnchor="middle" className="fill-slate-300 text-[10px]">{pts[hover].date}</text>
              <text x={bx + bw / 2} y={by + 28} textAnchor="middle" className="fill-white text-xs font-semibold">{pts[hover].score}/100</text>
            </g>
          );
        })()}
        {/* transparent hit bands — one per point */}
        {pts.map((p, i) => (
          <rect
            key={`hit-${i}`}
            x={Math.max(xs[i] - bandW / 2, 0)}
            y={0}
            width={bandW}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          >
            <title>{`${p.date}: ${p.score}/100`}</title>
          </rect>
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>{first.date}</span>
        <span>{last.date}</span>
      </div>
    </div>
  );
}
