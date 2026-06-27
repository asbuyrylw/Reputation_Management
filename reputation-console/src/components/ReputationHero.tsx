"use client";

import { repBand, repScore, RepTone } from "@/lib/repScore";
import { Card } from "./ui";
import { Tone, toneText, toneBar, toneDot } from "@/lib/uiTokens";
import { ScoreDonut, DonutSlice } from "./ScoreDonut";

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

// Compact driver tile — a smaller version of StatTile that lives INSIDE the score block.
// `gloss` is an always-visible one-line plain-language definition (not tooltip-only).
function MiniDriver({ label, value, tone, bar, hint, gloss }: { label: string; value: string; tone: Tone; bar: number | null; hint: string; gloss: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-white/70 p-3" title={hint}>
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${toneDot[tone]}`} aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      </div>
      <div className={`mt-1 text-xl font-bold leading-none ${toneText[tone]}`}>{value}</div>
      {bar != null && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full rounded-full ${toneBar[tone]}`} style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} />
        </div>
      )}
      <p className="mt-2 text-xs leading-snug text-slate-400">{gloss}</p>
    </div>
  );
}

// The consolidated "AI Reputation Score" block: the score gauge, its three drivers (contested /
// owned / grounded) as SMALL tiles inside, and the answer-sentiment donut — everything about what
// AI thinks of you right now, in one surface. (Engines-covered is a caption, not a tile; the
// action-plan progress is its own block below on the dashboard.)
export function ReputationHero({
  goalAlignment,
  contestedRate,
  ownedRate,
  groundedRate,
  coverage,
  sentiment,
  asOf,
}: {
  goalAlignment: number | null;
  contestedRate: number | null;
  ownedRate: number | null;
  groundedRate: number | null;
  coverage: { configured: string[]; expected: string[]; partial: boolean } | null;
  sentiment?: DonutSlice[];
  asOf?: string | null;
}) {
  const score = repScore(goalAlignment);
  const band = repBand(score);
  const ring = RING[band.tone];
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  const pctNum = (v: number | null) => (v == null ? null : Math.round(v * 100));
  const enginesN = coverage ? coverage.configured.length : null;
  const enginesExp = coverage ? coverage.expected.length : null;
  const contestedTone: Tone = contestedRate && contestedRate > 0 ? "bad" : "good";
  const ownedTone: Tone = ownedRate && ownedRate > 0 ? "good" : "neutral";
  const hasSentiment = !!sentiment && sentiment.some((d) => d.value > 0);

  return (
    <Card className="overflow-hidden">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">AI Reputation Score</div>

      <div className="mt-3 flex flex-col gap-6 lg:flex-row lg:items-center">
        {/* gauge + meaning */}
        <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-7 lg:flex-1">
          <div className="relative">
            <div className={`absolute -inset-3 rounded-full ${ring.halo} opacity-50 blur-2xl`} aria-hidden />
            <div className="relative"><ScoreRing score={score} stroke={ring.stroke} /></div>
          </div>
          <div className="min-w-0 flex-1 text-center sm:text-left">
            <div className="flex items-center justify-center gap-2 sm:justify-start">
              <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold ring-1 ring-inset ${ring.chip}`}>{band.label}</span>
              <span className="text-sm font-medium text-slate-500">0 = unfavorable · 100 = champion</span>
            </div>
            <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-600">{MEANING[band.tone]}</p>
            <div className="mt-4">
              <div className="relative h-2.5 w-full rounded-full bg-linear-to-r from-rose-400 via-slate-300 to-emerald-500">
                {score != null && (
                  <div className="absolute -top-1 w-1.5 -translate-x-1/2 rounded-full border-2 border-white bg-slate-900 shadow-md" style={{ left: `${score}%`, height: "1.15rem" }} aria-hidden />
                )}
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] font-medium uppercase tracking-wide text-slate-400">
                {BANDS.map((b) => <span key={b}>{b}</span>)}
              </div>
            </div>
          </div>
        </div>

        {/* answer-sentiment donut, nested here (moved up from the bottom of the page) */}
        {hasSentiment && (
          <div className="shrink-0 border-t border-slate-100 pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
            <ScoreDonut bare title="How AI answers lean" subtitle="Sentiment of the latest run" data={sentiment!} centerLabel="answers" />
          </div>
        )}
      </div>

      {/* the three drivers as small tiles inside the block */}
      <div className="mt-5 grid grid-cols-3 gap-3">
        <MiniDriver label="Contested" value={pct(contestedRate)} tone={contestedTone} bar={pctNum(contestedRate)} hint="Share of sources arguing against you. Lower is better." gloss="Share of sources arguing against you — lower is better." />
        <MiniDriver label="Owned sources" value={pct(ownedRate)} tone={ownedTone} bar={pctNum(ownedRate)} hint="Citations from channels you control. Higher is better." gloss="Citations from channels you control — higher is better." />
        <MiniDriver label="Grounded" value={pct(groundedRate)} tone="info" bar={pctNum(groundedRate)} hint="Answers backed by real citations, not guesses." gloss="Answers backed by real citations, not guesses." />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 text-[11px] text-slate-400">
        {enginesN != null && (
          <span className={coverage?.partial ? "text-amber-600" : ""}>{enginesN}/{enginesExp} AI engines checked</span>
        )}
        {asOf && <><span aria-hidden>·</span><span>Latest audit {asOf}</span></>}
      </div>
    </Card>
  );
}
