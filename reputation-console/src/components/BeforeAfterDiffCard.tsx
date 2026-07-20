import { Card } from "./ui";
import type { BeforeAfterPair } from "@/lib/types";
import { repScore, repBand, repClasses } from "@/lib/repScore";

const snippet = (v: unknown) => (typeof v === "string" ? v.slice(0, 280) : "");

// A single side's AI Reputation Score (0–100) chip + band label — the same canonical scale as the
// dashboard, so a client reads one number everywhere instead of an opaque goal_alignment like 0.42.
function ScorePill({ label, ga }: { label: string; ga: unknown }) {
  const score = typeof ga === "number" ? repScore(ga) : null;
  const band = repBand(score);
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-semibold text-slate-500">{label}</span>
      {score != null ? (
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${repClasses(score)}`}>
          {score}<span className="font-normal opacity-70">· {band.label}</span>
        </span>
      ) : (
        <span className="text-[11px] text-slate-400">—</span>
      )}
    </div>
  );
}

export function BeforeAfterDiffCard({ pair }: { pair: BeforeAfterPair }) {
  const before = pair.before || {};
  const after = pair.after || {};
  const bScore = typeof before.goal_alignment === "number" ? repScore(before.goal_alignment) : null;
  const aScore = typeof after.goal_alignment === "number" ? repScore(after.goal_alignment) : null;
  const delta = bScore != null && aScore != null ? aScore - bScore : null;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-900">{pair.prompt}</div>
          <div className="mt-0.5 text-xs text-slate-400">{pair.engine}</div>
        </div>
        {delta != null && delta !== 0 && (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ${delta > 0 ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
            {delta > 0 ? "+" : ""}{delta} pts
          </span>
        )}
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-rose-100 bg-rose-50 p-3">
          <ScorePill label="Before" ga={before.goal_alignment} />
          <p className="mt-1.5 text-xs text-slate-700">{snippet(before.answer_text)}</p>
        </div>
        <div className="rounded-md border border-emerald-100 bg-emerald-50 p-3">
          <ScorePill label="Now" ga={after.goal_alignment} />
          <p className="mt-1.5 text-xs text-slate-700">{snippet(after.answer_text)}</p>
        </div>
      </div>
    </Card>
  );
}
