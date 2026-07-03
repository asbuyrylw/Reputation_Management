import { repBand, repClasses, repScore } from "@/lib/repScore";

// Shows goal_alignment as a 0–100 reputation score + band (e.g. "22 · Weak", "50 · Neutral").
export function RepScoreBadge({
  goalAlignment,
  showLabel = true,
}: {
  goalAlignment: number | null | undefined;
  showLabel?: boolean;
}) {
  const score = repScore(goalAlignment);
  const band = repBand(score);
  return (
    <span
      title="AI reputation score (0–100). 50 = neutral/no information; higher is more favorable."
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${repClasses(score)}`}
    >
      <span className="font-semibold">{score == null ? "—" : score}</span>
      {showLabel && <span className="opacity-80">· {band.label}</span>}
    </span>
  );
}
