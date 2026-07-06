"use client";

// Narrative crowding-out score — the headline metric. The big 0-100 "Narrative dominance"
// number, its band label (e.g. "47/100 — Weak"), the delta vs the last audit, a desired%
// vs contested% split bar, a small sparkline, and a CTA into the action plan. Bands reuse
// the shared rep thresholds (repBand) so colors match the rest of the dashboard. Renders a
// skeleton while loading, a graceful line on error, and a pre-first-audit placeholder.

import Link from "next/link";
import type { NarrativeScore } from "@/lib/types";
import { Card, CardSkeleton } from "./ui";
import { Sparkline } from "./Sparkline";
import { repBand, repClasses, type RepTone } from "@/lib/repScore";

// Map the shared rep band tone -> the value text + ring used on this card, so the
// headline color matches the VerdictBanner / ReputationHero band system exactly.
const BAND_TEXT: Record<RepTone, string> = {
  red: "text-rose-600",
  orange: "text-orange-600",
  gray: "text-slate-600",
  green: "text-emerald-600",
  emerald: "text-emerald-600",
};
const BAND_RING: Record<RepTone, string> = {
  red: "ring-rose-200/70",
  orange: "ring-orange-200/70",
  gray: "ring-slate-200/70",
  green: "ring-emerald-200/70",
  emerald: "ring-emerald-200/70",
};

// desired_pct / contested_pct arrive already on a 0–100 scale from narrative_score.py — do NOT
// multiply by 100 again (that produced the "1600% / 5080%" double-scaling bug).
const pctOf = (v: number) => `${Math.round(v)}%`;

export function NarrativeScoreCard({
  narrative,
  loading = false,
  error = false,
}: {
  narrative: NarrativeScore | null | undefined;
  loading?: boolean;
  error?: boolean;
}) {
  if (loading) return <CardSkeleton lines={3} />;

  if (error) {
    return (
      <Card accent="info">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">Narrative dominance</div>
        <p className="mt-2 text-sm text-slate-500">We couldn&apos;t load your narrative score just now. Refresh in a moment.</p>
      </Card>
    );
  }

  const latest = narrative?.latest ?? null;
  if (!latest) {
    // Pre-first-audit placeholder — never render nothing.
    return (
      <Card accent="info" className="bg-linear-to-br from-indigo-50/70 to-white">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">Narrative dominance</div>
        <p className="mt-2 text-sm text-slate-600">Your narrative score appears after your first audit.</p>
        <p className="mt-1 text-xs text-slate-400">
          It measures how much your desired story dominates AI answers vs. the contested one (0–100).
        </p>
      </Card>
    );
  }

  const score = Math.round(latest.score);
  const band = repBand(score);
  const text = BAND_TEXT[band.tone];
  const ring = BAND_RING[band.tone];
  const delta = narrative?.delta ?? null;
  const desired = latest.desired_pct ?? 0;
  const contested = latest.contested_pct ?? 0;
  // The split bar is desired-vs-contested; remaining width is neutral.
  const desiredW = Math.max(0, Math.min(100, Math.round(desired)));
  const contestedW = Math.max(0, Math.min(100 - desiredW, Math.round(contested)));
  const neutralW = Math.max(0, 100 - desiredW - contestedW);

  const series = (narrative?.series ?? []).map((p) => p.score).filter((v): v is number => v != null);

  return (
    <Card accent="info" className="bg-linear-to-br from-indigo-50/70 to-white">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">Narrative dominance</div>
          {/* always-visible plain-language gloss */}
          <p className="text-xs text-slate-400">How much your desired story dominates AI answers vs. the contested one.</p>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className={`text-[52px] font-bold leading-none tracking-tight ${text}`}>{score}</span>
            <span className="text-base font-medium text-slate-400">/100</span>
            <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${repClasses(score)}`}>{band.label}</span>
            {delta != null && Math.abs(delta) >= 0.5 && (
              <span className={`text-sm font-semibold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                {delta >= 0 ? "▲ +" : "▼ "}
                {Math.abs(Math.round(delta))} pts vs last audit
              </span>
            )}
            {delta != null && Math.abs(delta) < 0.5 && (
              <span className="text-sm font-medium text-slate-400">no change vs last audit</span>
            )}
          </div>
          <Link
            href="/content/work-orders"
            className="mt-2 inline-block text-sm font-semibold text-indigo-600 hover:text-indigo-700"
          >
            See what raises this →
          </Link>
        </div>
        {series.length >= 2 && (
          <div className={`shrink-0 rounded-xl bg-white px-3 py-2 ring-1 ${ring}`}>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Trend</div>
            <Sparkline values={series} width={120} height={34} />
          </div>
        )}
      </div>

      {/* desired vs contested split bar */}
      <div className="mt-4">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-inset ring-slate-200">
          {desiredW > 0 && <div className="h-full bg-linear-to-r from-emerald-400 to-emerald-600" style={{ width: `${desiredW}%` }} />}
          {neutralW > 0 && <div className="h-full bg-slate-200" style={{ width: `${neutralW}%` }} />}
          {contestedW > 0 && <div className="h-full bg-linear-to-r from-rose-400 to-rose-600" style={{ width: `${contestedW}%` }} />}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-medium">
          <span className="flex items-center gap-1.5 text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> {pctOf(desired)} desired narrative
          </span>
          <span className="flex items-center gap-1.5 text-rose-700">
            <span className="h-2 w-2 rounded-full bg-rose-500" /> {pctOf(contested)} contested narrative
          </span>
        </div>
      </div>
    </Card>
  );
}
