"use client";

import { repBand, repScore, RepTone } from "@/lib/repScore";
import { Card, StatTile } from "./ui";
import { Tone } from "@/lib/uiTokens";

// Ring stroke + soft halo per band — the score's color is the first thing the eye reads.
const RING: Record<RepTone, { stroke: string; halo: string; text: string; chip: string }> = {
  red: { stroke: "#f43f5e", halo: "bg-rose-100", text: "text-rose-600", chip: "bg-rose-50 text-rose-700 ring-rose-200" },
  orange: { stroke: "#f59e0b", halo: "bg-amber-100", text: "text-amber-600", chip: "bg-amber-50 text-amber-700 ring-amber-200" },
  gray: { stroke: "#94a3b8", halo: "bg-slate-100", text: "text-slate-600", chip: "bg-slate-100 text-slate-600 ring-slate-200" },
  green: { stroke: "#22c55e", halo: "bg-emerald-100", text: "text-emerald-600", chip: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  emerald: { stroke: "#10b981", halo: "bg-emerald-100", text: "text-emerald-600", chip: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
};

const MEANING: Record<RepTone, string> = {
  red: "AI assistants currently portray you unfavorably. This is the gap to close.",
  orange: "AI still leans slightly unfavorable about you — there's clear room to climb.",
  gray: "AI is even-handed about you — often a sign it simply has little to say yet.",
  green: "AI assistants speak favorably about you. Keep reinforcing it.",
  emerald: "AI assistants strongly champion you. Defend this position.",
};

const BANDS = ["Poor", "Weak", "Neutral", "Strong", "Excellent"];

function ScoreRing({ score, stroke }: { score: number | null; stroke: string }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, score ?? 0));
  const dash = (v / 100) * circ;
  return (
    <div className="relative h-36 w-36 shrink-0">
      <svg viewBox="0 0 128 128" className="h-36 w-36 -rotate-90">
        <circle cx="64" cy="64" r={r} fill="none" stroke="#e2e8f0" strokeWidth="11" />
        <circle
          cx="64"
          cy="64"
          r={r}
          fill="none"
          stroke={stroke}
          strokeWidth="11"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
          style={{ transition: "stroke-dasharray 0.6s cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[42px] font-bold leading-none tracking-tight text-slate-900">{score ?? "—"}</span>
        <span className="mt-0.5 text-xs font-medium text-slate-400">out of 100</span>
      </div>
    </div>
  );
}

// The headline "AI Reputation Score" block — now SPLIT into distinct surfaces so each driver
// reads on its own: (1) a prominent score card with a circular gauge + band, (2) four separate
// stat tiles for the drivers, (3) a dedicated action-plan card. Previously all crammed together.
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
  const ring = RING[band.tone];
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  const pctNum = (v: number | null) => (v == null ? null : Math.round(v * 100));

  const totalWo = Object.values(woCounts).reduce((a, b) => a + b, 0);
  const doneWo = (woCounts.done ?? 0) + (woCounts.verified ?? 0);
  const inProg = (woCounts.in_progress ?? 0) + (woCounts.in_review ?? 0) + (woCounts.review ?? 0);
  const openWo = Math.max(0, totalWo - doneWo - inProg);
  const woPct = totalWo ? Math.round((doneWo / totalWo) * 100) : 0;
  const enginesN = coverage ? coverage.configured.length : null;
  const enginesExp = coverage ? coverage.expected.length : null;

  const contestedTone: Tone = contestedRate && contestedRate > 0 ? "bad" : "good";
  const ownedTone: Tone = ownedRate && ownedRate > 0 ? "good" : "neutral";

  return (
    <div className="space-y-4">
      {/* 1 — Score card (its own prominent surface) */}
      <Card className="overflow-hidden">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center sm:gap-8">
          {/* ring with soft band-colored halo */}
          <div className="relative">
            <div className={`absolute -inset-3 rounded-full ${ring.halo} opacity-50 blur-2xl`} aria-hidden />
            <div className="relative">
              <ScoreRing score={score} stroke={ring.stroke} />
            </div>
          </div>

          {/* meaning + band gauge */}
          <div className="min-w-0 flex-1 text-center sm:text-left">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">
              AI Reputation Score
            </div>
            <div className="mt-1.5 flex items-center justify-center gap-2 sm:justify-start">
              <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold ring-1 ring-inset ${ring.chip}`}>
                {band.label}
              </span>
              <span className="text-sm text-slate-400">·</span>
              <span className="text-sm font-medium text-slate-500">0 = unfavorable · 50 = neutral · 100 = champion</span>
            </div>
            <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-600">{MEANING[band.tone]}</p>

            {/* Poor → Excellent position gauge */}
            <div className="mt-4">
              <div className="relative h-2.5 w-full rounded-full bg-linear-to-r from-rose-400 via-slate-300 to-emerald-500">
                {score != null && (
                  <div
                    className="absolute -top-1 h-4.5 w-1.5 -translate-x-1/2 rounded-full border-2 border-white bg-slate-900 shadow-md"
                    style={{ left: `${score}%`, height: "1.15rem" }}
                    aria-hidden
                  />
                )}
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] font-medium uppercase tracking-wide text-slate-400">
                {BANDS.map((b) => (
                  <span key={b}>{b}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* 2 — Drivers, each its own tile */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Contested"
          value={pct(contestedRate)}
          tone={contestedTone}
          bar={pctNum(contestedRate)}
          hint="Share of sources arguing against you. Lower is better."
        />
        <StatTile
          label="Owned sources"
          value={pct(ownedRate)}
          tone={ownedTone}
          bar={pctNum(ownedRate)}
          hint="Citations from channels you control. Higher is better."
        />
        <StatTile
          label="Grounded"
          value={pct(groundedRate)}
          tone="info"
          bar={pctNum(groundedRate)}
          hint="Answers backed by real citations, not guesses."
        />
        <StatTile
          label="Engines covered"
          value={enginesN == null ? "—" : `${enginesN} / ${enginesExp}`}
          tone={coverage?.partial ? "bad" : "good"}
          bar={enginesN != null && enginesExp ? Math.round((enginesN / enginesExp) * 100) : null}
          hint="AI assistants checked in the latest audit."
        />
      </div>

      {/* 3 — Action plan (its own card) */}
      <Card accent="good">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Action plan progress</h3>
            <p className="mt-0.5 text-xs text-slate-500">Completing these work items is what moves your score.</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold leading-none text-emerald-600">{woPct}%</div>
            <div className="mt-0.5 text-xs text-slate-500">
              {doneWo} of {totalWo} done · {assetsN} published
            </div>
          </div>
        </div>
        <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-linear-to-r from-emerald-400 to-emerald-600 transition-all"
            style={{ width: `${woPct}%` }}
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs font-medium">
          <span className="flex items-center gap-1.5 text-slate-600">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> {doneWo} done
          </span>
          <span className="flex items-center gap-1.5 text-slate-600">
            <span className="h-2 w-2 rounded-full bg-amber-500" /> {inProg} in progress
          </span>
          <span className="flex items-center gap-1.5 text-slate-600">
            <span className="h-2 w-2 rounded-full bg-slate-300" /> {openWo} not started
          </span>
        </div>
      </Card>
    </div>
  );
}
