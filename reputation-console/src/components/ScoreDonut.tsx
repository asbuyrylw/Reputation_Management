"use client";

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { Card } from "./ui";

export type DonutSlice = { name: string; value: number; color: string };

// A donut + legend for a categorical distribution (e.g. answer sentiment, source share-of-voice).
export function ScoreDonut({
  title,
  subtitle,
  data,
  centerLabel,
}: {
  title: string;
  subtitle?: string;
  data: DonutSlice[];
  centerLabel?: string;
}) {
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <Card>
      <div className="text-sm font-medium text-slate-700">{title}</div>
      {subtitle && <div className="mt-0.5 text-xs text-slate-400">{subtitle}</div>}
      {total === 0 ? (
        <p className="mt-3 text-sm text-slate-400">No data yet.</p>
      ) : (
        <div className="mt-2 flex items-center gap-5">
          <div className="relative h-40 w-40 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data.filter((d) => d.value > 0)}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={48}
                  outerRadius={68}
                  paddingAngle={2}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {data.filter((d) => d.value > 0).map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold text-slate-900">{total}</span>
              {centerLabel && <span className="text-xs text-slate-400">{centerLabel}</span>}
            </div>
          </div>
          <ul className="flex-1 space-y-1.5">
            {data.filter((d) => d.value > 0).map((d) => (
              <li key={d.name} className="flex items-center gap-2 text-sm">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: d.color }} />
                <span className="flex-1 capitalize text-slate-700">{d.name}</span>
                <span className="font-medium text-slate-900">{d.value}</span>
                <span className="w-9 text-right text-xs text-slate-400">
                  {Math.round((d.value / total) * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
