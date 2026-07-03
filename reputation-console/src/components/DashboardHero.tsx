"use client";

// The dashboard HERO: the whole picture in one glance for a busy owner — the one AI Reputation
// Score (centerpiece) plus the three headline statuses (goal, time-to-goal, local search). Deeper
// detail lives in the sections below. Pattern follows how reputation SaaS (e.g. Reputation.com's
// composite "Reputation Score") lead with a single number + a few KPI tiles.

import Link from "next/link";
import { repBand } from "@/lib/repScore";
import { useLocalRankings } from "@/lib/hooks";
import type { LocalSeoGoal } from "@/lib/types";
import { Card } from "./ui";

type Json = Record<string, unknown>;

const BAND_TEXT = {
  red: "text-rose-600",
  orange: "text-orange-600",
  gray: "text-slate-600",
  green: "text-emerald-600",
  emerald: "text-emerald-600",
} as const;

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

// One headline tile — a labeled number that links into its hub.
function Tile({
  label,
  value,
  sub,
  href,
  size = "lg",
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  href: string;
  size?: "lg" | "md";
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col justify-center rounded-2xl bg-white p-4 ring-1 ring-slate-900/5 transition hover:ring-indigo-200"
    >
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-1 font-bold leading-tight tracking-tight text-slate-900 ${size === "lg" ? "text-3xl" : "text-xl"}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </Link>
  );
}

export function DashboardHero({
  businessId,
  score,
  delta,
  goalScore,
  timeline,
  goalText,
  localGoal,
}: {
  businessId: number | null;
  score: number | null;
  delta?: number | null;
  goalScore: number | null;
  timeline: Json | undefined;
  goalText?: string;
  localGoal?: LocalSeoGoal;
}) {
  const band = repBand(score);
  const { data: ranks } = useLocalRankings(businessId);
  const local = ranks?.summary ?? null;
  const proj = (timeline?.projection as Json | undefined)?.expected as Json | undefined;
  const targetDate = proj?.target_date as string | undefined;
  const gap = score != null && goalScore != null ? Math.max(0, goalScore - score) : null;

  // Local page-1 goal + ETA — mirrors the AI "Time to goal" tile. Grounded projection from the
  // local-SEO estimator; degrades to today's page-1 rate when no projection exists yet.
  const lgMet = !!localGoal && (localGoal.remaining_gap ?? 1) <= 0;
  const lgDate = localGoal?.projection?.expected?.target_date;
  const lgMonths = localGoal?.projection?.expected?.months;
  const lgNow = localGoal?.current_page_one_rate ?? local?.page_one_rate ?? null;
  const lgValue = lgMet ? "On page 1 🎉" : lgDate ?? (lgNow != null ? pct(lgNow) : "—");
  const lgSub = lgMet
    ? "holding your position"
    : lgDate
    ? `~${lgMonths} mo · now ${pct(lgNow)} on page 1`
    : "run a local check";

  return (
    <Card className="overflow-hidden bg-linear-to-br from-indigo-50/60 to-white">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">Where you stand</div>
      {goalText && (
        <p className="mt-1 max-w-3xl text-sm font-normal leading-relaxed text-slate-600">
          <span className="font-medium text-slate-500">Your goal:</span> {goalText}
        </p>
      )}
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.5fr)_repeat(3,minmax(0,1fr))]">
        {/* AI Reputation Score — the centerpiece */}
        <div className="flex flex-col justify-center rounded-2xl bg-white p-4 ring-1 ring-slate-900/5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">AI Reputation Score</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className={`text-5xl font-bold leading-none tracking-tight ${BAND_TEXT[band.tone]}`}>{score ?? "—"}</span>
            <span className="text-sm font-medium text-slate-400">/100</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{band.label}</span>
          </div>
          {delta != null && Math.abs(delta) >= 0.5 ? (
            <div className={`mt-1.5 text-sm font-semibold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
              {delta >= 0 ? "▲ +" : "▼ "}
              {Math.abs(delta)} pts vs last audit
            </div>
          ) : (
            <div className="mt-1.5 text-sm font-medium text-slate-400">no change vs last audit</div>
          )}
          <div className="mt-1 text-xs text-slate-500">How favorably AI assistants describe you (0–100).</div>
        </div>

        <Tile
          label="Goal score"
          value={goalScore ?? "—"}
          sub={gap == null ? "your target" : gap > 0 ? `${gap} pts to reach it` : "reached 🎉"}
          href="/timeline"
        />
        <Tile
          label="Time to goal"
          value={targetDate ?? "—"}
          sub={targetDate ? "on your current pace" : "appears after a 2nd audit"}
          href="/timeline"
          size="md"
        />
        <Tile
          label="Local page-1 goal"
          value={lgValue}
          sub={lgSub}
          href="/seo-overview"
          size={lgDate && !lgMet ? "md" : "lg"}
        />
      </div>
    </Card>
  );
}
