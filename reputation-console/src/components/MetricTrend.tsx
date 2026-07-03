"use client";

// A compact 0–100 sparkline for any trackable metric (site-health readiness, local visibility, …)
// so it reads the same way as the AI reputation score: latest value + delta + a hoverable line.
// Fixed 0–100 domain; needs >= 2 points to draw a line.

import { useState } from "react";
import type { MetricTrendPoint } from "@/lib/hooks";

export function MetricTrend({
  data,
  label,
  suffix = "/100",
  hint,
}: {
  data: MetricTrendPoint[] | undefined;
  label: string;
  suffix?: string;
  hint?: string;
}) {
  const pts = (data ?? []).filter((d) => typeof d.score === "number");
  const [hover, setHover] = useState<number | null>(null);
  if (pts.length === 0) return null;

  const latest = pts[pts.length - 1];
  const first = pts[0];

  if (pts.length < 2) {
    return (
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
        <div className="mt-1 flex items-baseline gap-1">
          <span className="text-2xl font-bold text-slate-900">{latest.score}</span>
          <span className="text-xs text-slate-400">{suffix}</span>
        </div>
        <p className="mt-1 text-[11px] text-slate-400">A trend line appears after your second reading.</p>
      </div>
    );
  }

  const W = 320, H = 84, P = 10, LO = 0, HI = 100;
  const delta = latest.score - first.score;
  const rising = latest.score >= first.score;
  const xs = pts.map((_, i) => P + (i * (W - 2 * P)) / (pts.length - 1));
  const y = (v: number) => H - P - ((v - LO) / (HI - LO)) * (H - 2 * P);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${xs[i].toFixed(1)} ${y(p.score).toFixed(1)}`).join(" ");
  const bandW = (W - 2 * P) / (pts.length - 1);
  const stroke = rising ? "#16a34a" : "#dc2626";

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xl font-bold text-slate-900">{latest.score}</span>
          <span className="text-xs text-slate-400">{suffix}</span>
          {Math.abs(delta) >= 1 && (
            <span className={`text-xs font-semibold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
              {delta >= 0 ? "▲ +" : "▼ "}
              {Math.abs(delta)}
            </span>
          )}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" role="img" aria-label={label} onMouseLeave={() => setHover(null)}>
        <path d={d} fill="none" stroke={stroke} strokeWidth={2} />
        {pts.map((p, i) => (
          <circle key={i} cx={xs[i]} cy={y(p.score)} r={2.5} fill={stroke} />
        ))}
        {hover != null && pts[hover] && (() => {
          const hx = xs[hover], hy = y(pts[hover].score);
          const bw = 96, bh = 32;
          const bx = Math.min(Math.max(hx - bw / 2, 0), W - bw);
          const by = hy - bh - 8 < 0 ? hy + 8 : hy - bh - 8;
          return (
            <g pointerEvents="none">
              <line x1={hx} x2={hx} y1={P} y2={H - P} stroke="#94a3b8" strokeWidth={1} strokeDasharray="3 3" />
              <circle cx={hx} cy={hy} r={4} fill="#fff" stroke={stroke} strokeWidth={2} />
              <rect x={bx} y={by} width={bw} height={bh} rx={5} fill="#0f172a" opacity={0.92} />
              <text x={bx + bw / 2} y={by + 13} textAnchor="middle" className="fill-slate-300 text-[9px]">{pts[hover].date}</text>
              <text x={bx + bw / 2} y={by + 25} textAnchor="middle" className="fill-white text-[11px] font-semibold">
                {pts[hover].score}{suffix}
              </text>
            </g>
          );
        })()}
        {pts.map((p, i) => (
          <rect key={`h-${i}`} x={Math.max(xs[i] - bandW / 2, 0)} y={0} width={bandW} height={H} fill="transparent" onMouseEnter={() => setHover(i)}>
            <title>{`${p.date}: ${p.score}${suffix}`}</title>
          </rect>
        ))}
      </svg>
      {hint && <p className="mt-1 text-[11px] text-slate-400">{hint}</p>}
    </div>
  );
}
