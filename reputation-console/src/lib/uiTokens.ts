// Centralized good/bad/neutral color semantics, used app-wide so "red always means bad
// for your reputation" regardless of which underlying metric it is. Inverted metrics
// (contested-down-is-good, recognition-gap-down-is-good) resolve their tone here via
// goodDirection, never per-page.

export type Tone = "good" | "bad" | "neutral";

export const toneText: Record<Tone, string> = {
  good: "text-green-700",
  bad: "text-rose-600",
  neutral: "text-gray-700",
};

export const toneChip: Record<Tone, string> = {
  good: "bg-green-50 text-green-700 border-green-200",
  bad: "bg-rose-50 text-rose-700 border-rose-200",
  neutral: "bg-gray-100 text-gray-600 border-gray-200",
};

export const toneBar: Record<Tone, string> = {
  good: "bg-green-500",
  bad: "bg-rose-500",
  neutral: "bg-gray-400",
};

// Severity (for section headers / gap cards) -> tone + label.
export type Severity = "high" | "med" | "low" | "good";
export const severityChip: Record<Severity, string> = {
  high: "bg-rose-50 text-rose-700 border-rose-200",
  med: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-gray-100 text-gray-600 border-gray-200",
  good: "bg-green-50 text-green-700 border-green-200",
};
export const severityDot: Record<Severity, string> = {
  high: "bg-rose-500",
  med: "bg-amber-500",
  low: "bg-gray-400",
  good: "bg-green-500",
};

// Resolve the tone of a change given which direction is good for the user.
export function deltaTone(delta: number, goodDirection: "up" | "down" = "up"): Tone {
  if (Math.abs(delta) < 1e-9) return "neutral";
  const up = delta > 0;
  return (goodDirection === "up" ? up : !up) ? "good" : "bad";
}
