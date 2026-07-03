"use client";

// Per-engine reputation trend (0-100), one line per AI assistant, so you can see which engine
// is rising or drifting — not just today's snapshot. Hand-rolled SVG (matches ScoreTrend).

import type { MetricsTrend } from "@/lib/types";

const COLORS: Record<string, string> = {
  openai: "#10a37f", anthropic: "#d97757", claude: "#d97757", perplexity: "#6366f1",
  gemini: "#4285f4", google: "#4285f4", grok: "#111827", bing: "#0ea5e9", copilot: "#0ea5e9",
};
const PALETTE = ["#6366f1", "#10a37f", "#d97757", "#4285f4", "#f59e0b", "#ec4899", "#0ea5e9"];
const colorFor = (e: string, i: number) => COLORS[e.toLowerCase()] ?? PALETTE[i % PALETTE.length];
const label = (e: string) => e.charAt(0).toUpperCase() + e.slice(1);

export function PerEngineTrend({ data }: { data: MetricsTrend | undefined }) {
  const series = data?.series ?? [];
  const engines = data?.engines ?? [];
  if (series.length < 2 || engines.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        Each AI engine&apos;s trend line appears after your second audit, so you can see which ones are improving.
      </p>
    );
  }
  const W = 640, H = 220, P = 32;
  const x = (i: number) => P + (i * (W - 2 * P)) / (series.length - 1);
  const y = (v: number) => H - P - (v / 100) * (H - 2 * P);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Per-engine reputation score over time">
        <rect x={P} y={y(100)} width={W - 2 * P} height={y(60) - y(100)} fill="#16a34a" opacity={0.05} />
        <rect x={P} y={y(40)} width={W - 2 * P} height={y(0) - y(40)} fill="#dc2626" opacity={0.05} />
        <line x1={P} x2={W - P} y1={y(50)} y2={y(50)} stroke="#d1d5db" strokeWidth={1} strokeDasharray="4 4" />
        {engines.map((e, ei) => {
          const pts = series
            .map((s, i) => ({ i, v: s.per_engine?.[e] }))
            .filter((p): p is { i: number; v: number } => p.v != null);
          if (pts.length < 2) return null;
          const d = pts.map((p, k) => `${k === 0 ? "M" : "L"} ${x(p.i).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
          const last = pts[pts.length - 1];
          return (
            <g key={e}>
              <path d={d} fill="none" stroke={colorFor(e, ei)} strokeWidth={2} />
              <circle cx={x(last.i)} cy={y(last.v)} r={3} fill={colorFor(e, ei)} />
              <text x={x(last.i) - 6} y={y(last.v) - 6} textAnchor="end" className="text-[10px]" fill={colorFor(e, ei)}>{last.v}</text>
            </g>
          );
        })}
      </svg>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {engines.map((e, ei) => (
          <span key={e} className="inline-flex items-center gap-1 text-[11px] text-slate-600">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: colorFor(e, ei) }} />{label(e)}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-slate-400">{series[0].date} → {series[series.length - 1].date}</span>
      </div>
    </div>
  );
}
