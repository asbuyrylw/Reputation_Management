"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "./ui";
import { useVisibilityTrend } from "@/lib/hooks";
import { useFilters, withinPeriod } from "@/lib/filters";

// Subject (navy, bold) vs competitors (muted) — share of category questions where AI
// surfaces each party, across benchmark runs over time.
const SUBJECT_COLOR = "#1e3a8a";
const COMPETITOR_COLORS = ["#94a3b8", "#a8a29e", "#cbd5e1", "#d6d3d1", "#e7e5e4"];

function fmtDate(d: string): string {
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? d : `${dt.getMonth() + 1}/${dt.getDate()}`;
}

export default function VisibilityTrendChart({ businessId }: { businessId: number | null }) {
  const { data } = useVisibilityTrend(businessId);
  const { period } = useFilters();
  if (!data) return null;
  const points = data.points.filter((p) => withinPeriod(p.date, period));
  if (points.length < 2) return null; // need at least two points in the window for a trend

  // Reshape to chart rows. Use SAFE, index-based dataKeys (you, c0, c1, …) so a competitor
  // name with a dot/bracket (recharts reads those as nested paths) or a literal "You"/"date"
  // can't collide with a reserved key; the human-readable name rides on each Line's `name`.
  const rows = points.map((p) => {
    const row: Record<string, number | string> = { date: fmtDate(p.date), you: Math.round(p.subject_rate * 100) };
    data.competitors.forEach((name, i) => {
      row[`c${i}`] = Math.round((p.competitors[name] ?? 0) * 100);
    });
    return row;
  });

  return (
    <Card>
      <h3 className="text-sm font-semibold text-slate-900">Visibility over time</h3>
      <p className="mt-0.5 text-xs text-slate-500">
        Share of category questions where AI surfaces you vs. competitors. Higher is better — the goal is your line
        climbing past theirs.
      </p>
      <div className="mt-3 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 5, right: 12, left: -18, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
            <Tooltip formatter={(v) => `${v}%`} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="you" name="You" stroke={SUBJECT_COLOR} strokeWidth={3} dot={{ r: 3 }} />
            {data.competitors.map((c, i) => (
              <Line
                key={c}
                type="monotone"
                dataKey={`c${i}`}
                name={c}
                stroke={COMPETITOR_COLORS[i % COMPETITOR_COLORS.length]}
                strokeWidth={1.5}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
