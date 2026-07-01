// Reputation score: the engine measures goal_alignment on a −1..+1 axis, which isn't
// intuitive. We present it as a 0–100 score plus a plain-language band. 50 = neutral (the
// AI is even-handed or simply has no information), <50 leans unfavorable, >50 leans favorable.

export type RepTone = "red" | "orange" | "gray" | "green" | "emerald";

export function repScore(goalAlignment: number | null | undefined): number | null {
  if (goalAlignment == null || Number.isNaN(goalAlignment)) return null;
  return Math.round(((goalAlignment + 1) / 2) * 100);
}

export function repBand(score: number | null | undefined): { label: string; tone: RepTone } {
  if (score == null) return { label: "—", tone: "gray" };
  if (score < 20) return { label: "Poor", tone: "red" };
  if (score < 40) return { label: "Weak", tone: "orange" };
  if (score < 60) return { label: "Neutral", tone: "gray" };
  if (score < 80) return { label: "Strong", tone: "green" };
  return { label: "Excellent", tone: "emerald" };
}

const TONE_CLASSES: Record<RepTone, string> = {
  red: "text-rose-700 bg-rose-50 border-rose-200",
  orange: "text-orange-700 bg-orange-50 border-orange-200",
  gray: "text-slate-600 bg-slate-100 border-slate-200",
  green: "text-emerald-700 bg-emerald-50 border-emerald-200",
  emerald: "text-emerald-700 bg-emerald-50 border-emerald-200",
};

export function repClasses(score: number | null | undefined): string {
  return TONE_CLASSES[repBand(score).tone];
}

// Canonical dashboard score selector — computed ONCE from the run series and consumed by every
// dashboard card so the headline score + its deltas can never drift between surfaces. `score` is
// the single 0–100 AI Reputation Score (repScore of the latest goal_alignment); `deltaVsLast`
// compares the latest two audits; `deltaSinceStart` compares the latest to the first.
export interface DashboardScore {
  score: number | null;
  band: { label: string; tone: RepTone };
  deltaVsLast: number | null;
  deltaSinceStart: number | null;
}

export function dashboardScore(series: { goal_alignment: number | null }[] | null | undefined): DashboardScore {
  const s = series ?? [];
  const at = (i: number) => (i >= 0 && i < s.length ? repScore(s[i]?.goal_alignment ?? null) : null);
  const lastIdx = s.length - 1;
  const score = at(lastIdx);
  const prev = at(lastIdx - 1);
  const first = at(0);
  return {
    score,
    band: repBand(score),
    deltaVsLast: score != null && prev != null ? score - prev : null,
    deltaSinceStart: score != null && first != null && s.length >= 2 ? score - first : null,
  };
}
