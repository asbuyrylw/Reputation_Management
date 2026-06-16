"use client";

import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useRunAnswers } from "@/lib/hooks";
import { KpiStatCard } from "@/components/KpiStatCard";
import { TrendChart } from "@/components/TrendChart";
import { ReputationHero } from "@/components/ReputationHero";
import { ScoreDonut } from "@/components/ScoreDonut";
import { PerEnginePanel } from "@/components/PerEnginePanel";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { repScore } from "@/lib/repScore";
import type { SeriesPoint } from "@/lib/types";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function DashboardPage() {
  const { businessId, businesses, loading: bizLoading } = useBusiness();
  const { data, isLoading, error } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: perEngine } = usePerEngine(businessId, latestRunId);
  const { data: answers } = useRunAnswers(businessId, latestRunId);

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

  const openWork = Object.entries(data.wo_counts)
    .filter(([k]) => k !== "done" && k !== "verified")
    .reduce((a, [, n]) => a + n, 0);

  // grounded rate across engines (from the latest run's per-engine metrics)
  const engVals = perEngine ? Object.values(perEngine.engines) : [];
  const grounded = engVals.filter((e) => e.grounded_rate);
  const groundedRate = grounded.length
    ? grounded.reduce((a, e) => a + (e.grounded_rate!.p ?? 0), 0) / grounded.length
    : null;

  // sentiment distribution of the latest run's answers
  const counts: Record<string, number> = { positive: 0, neutral: 0, mixed: 0, negative: 0 };
  for (const a of answers ?? []) if (a.sentiment && a.sentiment in counts) counts[a.sentiment]++;
  const sentimentData = [
    { name: "positive", value: counts.positive, color: "#16a34a" },
    { name: "neutral", value: counts.neutral, color: "#9ca3af" },
    { name: "mixed", value: counts.mixed, color: "#f59e0b" },
    { name: "negative", value: counts.negative, color: "#dc2626" },
  ];

  const scoreNow = repScore(latest?.goal_alignment ?? null);
  const scorePrev = repScore(prev?.goal_alignment ?? null);
  const scoreDelta = scoreNow != null && scorePrev != null ? scoreNow - scorePrev : null;
  const rateDelta = (k: "owned_rate" | "contested_rate") =>
    latest && prev ? latest[k] - prev[k] : null;

  return (
    <div>
      <PageHeader
        title={`Dashboard — ${data.business.name}`}
        subtitle="How AI engines portray this business, and how the program is progressing."
      />

      {!latest ? (
        <Card>
          <p className="text-sm text-gray-600">
            No audit has run yet. Once the first audit completes, your reputation score and trend appear here.
          </p>
        </Card>
      ) : (
        <div className="space-y-6">
          <ReputationHero
            goalAlignment={latest.goal_alignment}
            contestedRate={latest.contested_rate}
            ownedRate={latest.owned_rate}
            groundedRate={groundedRate}
            coverage={perEngine?.coverage ?? null}
            woCounts={data.wo_counts}
            assetsN={data.assets_n}
          />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiStatCard
              label="Reputation score"
              value={scoreNow == null ? "—" : `${scoreNow}`}
              delta={scoreDelta}
              goodDirection="up"
              hint="0–100; 50 = neutral / no information. Higher is more favorable."
            />
            <KpiStatCard
              label="Owned-content surfacing"
              value={pct(latest.owned_rate)}
              delta={rateDelta("owned_rate")}
              goodDirection="up"
              hint="Share of answers citing your own content. Higher is better."
            />
            <KpiStatCard
              label="Contested mentions"
              value={pct(latest.contested_rate)}
              delta={rateDelta("contested_rate")}
              goodDirection="down"
              hint="Share of answers raising contested terms. Lower is better."
            />
            <KpiStatCard
              label="Open work items"
              value={String(openWork)}
              hint={`${data.assets_n} assets published to date.`}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <div className="mb-3 text-sm font-medium text-gray-700">Reputation trend across audits</div>
              <TrendChart series={s} />
            </Card>
            <ScoreDonut
              title="How AI answers lean"
              subtitle="Sentiment of the latest run's answers"
              data={sentimentData}
              centerLabel="answers"
            />
          </div>

          {perEngine && Object.keys(perEngine.engines).length > 0 && <PerEnginePanel data={perEngine} />}
        </div>
      )}
    </div>
  );
}
