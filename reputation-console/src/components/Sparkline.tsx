"use client";

// Tiny inline-SVG sparkline for a sequence of 0-100 scores (chronological order).
export function Sparkline({ values, width = 96, height = 28 }: { values: number[]; width?: number; height?: number }) {
  const pts = values.filter((v) => v != null);
  if (pts.length < 2) return null;
  const min = Math.min(...pts), max = Math.max(...pts);
  const span = max - min || 1;
  const x = (i: number) => (i * (width - 4)) / (pts.length - 1) + 2;
  const y = (v: number) => height - 2 - ((v - min) / span) * (height - 4);
  const d = pts.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const rising = pts[pts.length - 1] >= pts[0];
  const color = rising ? "#16a34a" : "#dc2626";
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="score trend">
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={x(pts.length - 1)} cy={y(pts[pts.length - 1])} r={2} fill={color} />
    </svg>
  );
}
