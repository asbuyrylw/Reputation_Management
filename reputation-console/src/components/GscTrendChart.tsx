"use client";

import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "./ui";
import { useGscTrend } from "@/lib/hooks";

// Real Google Search traffic over time: clicks (navy, bold, left axis) + impressions (muted,
// right axis). Modeled on VisibilityTrendChart, but dual-series with its own days-range toggle
// (28 / 90 / 365) since Search Console keeps far more history than our benchmark runs.
const CLICKS_COLOR = "#1e3a8a";
const IMPRESSIONS_COLOR = "#94a3b8";

const RANGES: { days: number; label: string }[] = [
  { days: 28, label: "28d" },
  { days: 90, label: "90d" },
  { days: 365, label: "12mo" },
];

function fmtDate(d: string): string {
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? d : `${dt.getMonth() + 1}/${dt.getDate()}`;
}

export default function GscTrendChart({ businessId }: { businessId: number | null }) {
  const [days, setDays] = useState(28);
  const { data } = useGscTrend(businessId, days);
  const points = data ?? [];

  const rows = points.map((p) => ({
    date: fmtDate(p.date),
    clicks: p.clicks,
    impressions: p.impressions,
  }));

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">Clicks &amp; impressions over time</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Real Google search traffic. <span className="font-medium text-slate-600">Clicks</span> are visits to your
            site; <span className="font-medium text-slate-600">impressions</span> are times you appeared in results.
          </p>
        </div>
        {/* days-range toggle */}
        <div className="flex shrink-0 gap-1 rounded-lg bg-slate-100 p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.days}
              type="button"
              onClick={() => setDays(r.days)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                days === r.days ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {rows.length < 2 ? (
        <p className="mt-4 text-sm text-slate-500">Not enough data in this window yet — check back as history accrues.</p>
      ) : (
        <div className="mt-3 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 5, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
              <YAxis yAxisId="clicks" tick={{ fontSize: 11 }} allowDecimals={false} />
              <YAxis yAxisId="impressions" orientation="right" tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line yAxisId="clicks" type="monotone" dataKey="clicks" name="Clicks" stroke={CLICKS_COLOR} strokeWidth={3} dot={false} />
              <Line yAxisId="impressions" type="monotone" dataKey="impressions" name="Impressions" stroke={IMPRESSIONS_COLOR} strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
