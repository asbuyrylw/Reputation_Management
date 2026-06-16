"use client";

import { repBand, repClasses, repScore } from "@/lib/repScore";
import { Card } from "./ui";

function SubStat({
  label,
  value,
  tone = "gray",
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "gray";
}) {
  const c = tone === "good" ? "text-green-700" : tone === "bad" ? "text-red-600" : "text-gray-900";
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold ${c}`}>{value}</div>
    </div>
  );
}

// The headline "AI Reputation Score" card: a big 0–100 score + band, a band-position bar, the
// key drivers, and a work-completion progress bar. Mirrors the health-score hero cards in
// ClickRank / Screpy.
export function ReputationHero({
  goalAlignment,
  contestedRate,
  ownedRate,
  groundedRate,
  coverage,
  woCounts,
  assetsN,
}: {
  goalAlignment: number | null;
  contestedRate: number | null;
  ownedRate: number | null;
  groundedRate: number | null;
  coverage: { configured: string[]; expected: string[]; partial: boolean } | null;
  woCounts: Record<string, number>;
  assetsN: number;
}) {
  const score = repScore(goalAlignment);
  const band = repBand(score);
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

  const totalWo = Object.values(woCounts).reduce((a, b) => a + b, 0);
  const doneWo = (woCounts.done ?? 0) + (woCounts.verified ?? 0);
  const woPct = totalWo ? Math.round((doneWo / totalWo) * 100) : 0;
  const engines = coverage ? `${coverage.configured.length} / ${coverage.expected.length}` : "—";

  return (
    <Card>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
        {/* score */}
        <div className="shrink-0 text-center sm:w-44 sm:text-left">
          <div className="text-xs font-medium uppercase tracking-wide text-gray-400">
            AI Reputation Score
          </div>
          <div className="mt-1 flex items-end gap-2 sm:block">
            <span className="text-5xl font-bold text-gray-900">{score ?? "—"}</span>
            <span className="pb-1 text-base font-normal text-gray-400">/ 100</span>
          </div>
          <span
            className={`mt-2 inline-block rounded-full border px-2.5 py-0.5 text-sm font-semibold ${repClasses(score)}`}
          >
            {band.label}
          </span>
        </div>

        {/* band bar + drivers */}
        <div className="flex-1">
          <div className="relative h-2.5 w-full rounded-full bg-gradient-to-r from-red-400 via-gray-300 to-green-500">
            {score != null && (
              <div
                className="absolute -top-1 h-4.5 w-1.5 -translate-x-1/2 rounded-full border border-white bg-gray-900 shadow"
                style={{ left: `${score}%`, height: "1.1rem" }}
                aria-hidden
              />
            )}
          </div>
          <div className="mt-1 flex justify-between text-[10px] uppercase tracking-wide text-gray-400">
            <span>Poor</span><span>Weak</span><span>Neutral</span><span>Strong</span><span>Excellent</span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SubStat label="Contested" value={pct(contestedRate)} tone={contestedRate ? "bad" : "good"} />
            <SubStat label="Owned sources" value={pct(ownedRate)} tone={ownedRate ? "good" : "gray"} />
            <SubStat label="Grounded" value={pct(groundedRate)} />
            <SubStat label="Engines" value={engines} tone={coverage?.partial ? "bad" : "good"} />
          </div>
        </div>
      </div>

      {/* work progress */}
      <div className="mt-6 border-t border-gray-100 pt-4">
        <div className="mb-1.5 flex items-center justify-between text-sm">
          <span className="font-medium text-gray-700">Action plan</span>
          <span className="text-gray-500">
            {doneWo} of {totalWo} work items done · {assetsN} assets published
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
          <div className="h-full rounded-full bg-green-500 transition-all" style={{ width: `${woPct}%` }} />
        </div>
      </div>
    </Card>
  );
}
