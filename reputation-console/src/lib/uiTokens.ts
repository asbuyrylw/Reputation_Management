// Centralized good/bad/neutral color semantics, used app-wide so "emerald always means good
// for your reputation" regardless of which underlying metric it is. Inverted metrics
// (contested-down-is-good, recognition-gap-down-is-good) resolve their tone here via
// goodDirection, never per-page. Palette is intentionally restrained: emerald = good,
// rose = bad, amber = caution, sky/indigo = informational, slate = neutral.

export type Tone = "good" | "bad" | "neutral" | "info";

// Value text color.
export const toneText: Record<Tone, string> = {
  good: "text-emerald-600",
  bad: "text-rose-600",
  neutral: "text-slate-700",
  info: "text-indigo-600",
};

// Soft pill/chip: tinted surface + ring + readable ink.
export const toneChip: Record<Tone, string> = {
  good: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200",
  bad: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200",
  neutral: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200",
  info: "bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-200",
};

// Progress-bar fill — a subtle gradient gives bars depth instead of a flat block.
export const toneBar: Record<Tone, string> = {
  good: "bg-linear-to-r from-emerald-400 to-emerald-600",
  bad: "bg-linear-to-r from-rose-400 to-rose-600",
  neutral: "bg-linear-to-r from-slate-300 to-slate-400",
  info: "bg-linear-to-r from-indigo-400 to-indigo-600",
};

// Card surface tint (very soft) — for cards that should carry a semantic accent.
export const toneSurface: Record<Tone, string> = {
  good: "bg-emerald-50/50 ring-emerald-200/70",
  bad: "bg-rose-50/50 ring-rose-200/70",
  neutral: "bg-slate-50 ring-slate-200",
  info: "bg-indigo-50/50 ring-indigo-200/70",
};

// Left/edge accent bar color.
export const toneAccentBar: Record<Tone, string> = {
  good: "bg-emerald-500",
  bad: "bg-rose-500",
  neutral: "bg-slate-300",
  info: "bg-indigo-500",
};

// Soft icon-dot color.
export const toneDot: Record<Tone, string> = {
  good: "bg-emerald-500",
  bad: "bg-rose-500",
  neutral: "bg-slate-400",
  info: "bg-indigo-500",
};

// Severity (for section headers / gap cards) -> tone + label.
export type Severity = "high" | "med" | "low" | "good";
export const severityChip: Record<Severity, string> = {
  high: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200",
  med: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200",
  low: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200",
  good: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200",
};
export const severityDot: Record<Severity, string> = {
  high: "bg-rose-500",
  med: "bg-amber-500",
  low: "bg-slate-400",
  good: "bg-emerald-500",
};

// Resolve the tone of a change given which direction is good for the user.
export function deltaTone(delta: number, goodDirection: "up" | "down" = "up"): Tone {
  if (Math.abs(delta) < 1e-9) return "neutral";
  const up = delta > 0;
  return (goodDirection === "up" ? up : !up) ? "good" : "bad";
}
