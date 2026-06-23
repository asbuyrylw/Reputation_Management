"use client";

// The one plain-English sentence the dashboard opens with: where you stand + is it good
// or bad + what the main issue is — color-coded to the band. This is the highest-leverage
// fix for "I don't understand what the dashboard is telling me."

import type { Challenge } from "@/lib/types";
import { repBand, repClasses } from "@/lib/repScore";

function leanPhrase(score: number): string {
  if (score < 40) return "lean UNFAVORABLE about";
  if (score < 60) return "are NEUTRAL about (and mostly don't know)";
  if (score < 80) return "lean FAVORABLE about";
  return "are VERY FAVORABLE about";
}

function issuePhrase(challenge: Challenge | null | undefined): string {
  switch (challenge?.profile) {
    case "awareness_gap":
      return "The main issue: they don't know you well yet — the FASTER problem to fix by publishing accurate content.";
    case "negative_narrative":
      return "The main issue: some sources are unfavorable — the slower problem, fixed by out-publishing them with accurate content.";
    case "mixed":
      return "The main issue is a mix: they only half-know you AND some sources are unfavorable — so we run two tracks at once.";
    case "established_positive":
      return "You're in good shape — the focus now is defending and extending the position.";
    default:
      return "Run an audit to diagnose the main issue.";
  }
}

export function VerdictBanner({
  businessName,
  score,
  challenge,
}: {
  businessName: string;
  score: number | null;
  challenge: Challenge | null | undefined;
}) {
  if (score == null) return null;
  const band = repBand(score);
  const dot =
    band.tone === "red"
      ? "bg-rose-500"
      : band.tone === "orange"
        ? "bg-amber-500"
        : band.tone === "gray"
          ? "bg-slate-400"
          : "bg-emerald-500";
  return (
    <div className={`relative overflow-hidden rounded-2xl border p-5 shadow-sm ${repClasses(score)}`}>
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1.5 ${dot}`} />
      <div className="flex items-start gap-3">
        <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${dot} ring-4 ring-white/60`} aria-hidden />
        <p className="text-[15px] font-medium leading-relaxed">
          AI assistants currently {leanPhrase(score)} <span className="font-bold">{businessName}</span> (
          <span className="font-bold">{score}/100, {band.label}</span>). {issuePhrase(challenge)}
        </p>
      </div>
    </div>
  );
}
