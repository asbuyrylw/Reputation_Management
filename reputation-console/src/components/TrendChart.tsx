"use client";

// Lightweight inline-SVG line chart (no charting dependency, so it always builds).
// Domain fixed to [-1, 1]: goal_alignment is -1..1, the rates are 0..1.

import type { SeriesPoint } from "@/lib/types";

const LINES = [
  { key: "goal_alignment", color: "#2E6B3E", label: "Goal alignment" },
  { key: "owned_rate", color: "#1F3A5F", label: "Owned-content surfacing" },
  { key: "contested_rate", color: "#8A3B2E", label: "Contested-term mentions" },
] as const;

export function TrendChart({ series }: { series: SeriesPoint[] }) {
  if (series.length < 2) {
    return <p className="text-sm text-gray-400">Need at least two audits to show a trend.</p>;
  }
  const W = 640, H = 220, P = 28;
  const xs = series.map((_, i) => P + (i * (W - 2 * P)) / (series.length - 1));
  const yMin = -1, yMax = 1;
  const y = (v: number) => H - P - ((v - yMin) / (yMax - yMin)) * (H - 2 * P);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-3xl" role="img" aria-label="AI visibility trend">
        <line x1={P} x2={W - P} y1={y(0)} y2={y(0)} stroke="#e5e7eb" strokeWidth={1} />
        {LINES.map((l) => {
          const d = series
            .map((s, i) => `${i === 0 ? "M" : "L"} ${xs[i].toFixed(1)} ${y(s[l.key]).toFixed(1)}`)
            .join(" ");
          return (
            <g key={l.key}>
              <path d={d} fill="none" stroke={l.color} strokeWidth={2} />
              {series.map((s, i) => (
                <circle key={i} cx={xs[i]} cy={y(s[l.key])} r={2.5} fill={l.color} />
              ))}
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-gray-600">
        {LINES.map((l) => (
          <span key={l.key} className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-3 rounded" style={{ background: l.color }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}
