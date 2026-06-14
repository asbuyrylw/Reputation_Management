"use client";

import { useBusiness } from "@/lib/business";
import { useDashboard } from "@/lib/hooks";
import { KpiStatCard } from "@/components/KpiStatCard";
import { TrendChart } from "@/components/TrendChart";
import { Card, PageHeader, Spinner } from "@/components/ui";
import type { SeriesPoint } from "@/lib/types";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function DashboardPage() {
  const { businessId, businesses, loading: bizLoading } = useBusiness();
  const { data, isLoading, error } = useDashboard(businessId);

  if (bizLoading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <Card>
        <p className="text-sm text-gray-600">No businesses are available to your account yet.</p>
      </Card>
    );
  }
  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-red-600">Could not load the dashboard.</p>;

  const s = data.series;
  const latest: SeriesPoint | undefined = s[s.length - 1];
  const prev: SeriesPoint | undefined = s.length > 1 ? s[s.length - 2] : undefined;
  const delta = (k: keyof Pick<SeriesPoint, "goal_alignment" | "owned_rate" | "contested_rate">) =>
    latest && prev ? latest[k] - prev[k] : null;
  const openWork = Object.entries(data.wo_counts)
    .filter(([k]) => k !== "done" && k !== "verified")
    .reduce((a, [, n]) => a + n, 0);

  return (
    <div>
      <PageHeader
        title={`Dashboard — ${data.business.name}`}
        subtitle="A snapshot of how AI engines portray this business and how the program is progressing."
      />

      {!latest ? (
        <Card>
          <p className="text-sm text-gray-600">
            No audit has run yet. Once the first audit completes, the metrics and trend appear here.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiStatCard
              label="Goal alignment"
              value={latest.goal_alignment.toFixed(2)}
              delta={delta("goal_alignment")}
              goodDirection="up"
              hint="How favorably AI answers track your goal (−1…+1). Higher is better."
            />
            <KpiStatCard
              label="Owned-content surfacing"
              value={pct(latest.owned_rate)}
              delta={delta("owned_rate")}
              goodDirection="up"
              hint="Share of answers citing your own content. Higher is better."
            />
            <KpiStatCard
              label="Contested mentions"
              value={pct(latest.contested_rate)}
              delta={delta("contested_rate")}
              goodDirection="down"
              hint="Share of answers raising contested terms. Lower is better."
            />
            <KpiStatCard
              label="Open work items"
              value={String(openWork)}
              hint={`${data.assets_n} assets published to date.`}
            />
          </div>

          <Card className="mt-6">
            <div className="mb-3 text-sm font-medium text-gray-700">AI visibility trend across audits</div>
            <TrendChart series={s} />
          </Card>
        </>
      )}
    </div>
  );
}
