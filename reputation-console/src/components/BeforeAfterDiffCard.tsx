import { Card } from "./ui";
import type { BeforeAfterPair } from "@/lib/types";

const ga = (v: unknown) => (typeof v === "number" ? ` (${v.toFixed(2)})` : "");
const snippet = (v: unknown) => (typeof v === "string" ? v.slice(0, 280) : "");

export function BeforeAfterDiffCard({ pair }: { pair: BeforeAfterPair }) {
  const before = pair.before || {};
  const after = pair.after || {};
  return (
    <Card>
      <div className="text-sm font-medium text-slate-900">{pair.prompt}</div>
      <div className="mt-0.5 text-xs text-slate-400">{pair.engine}</div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-rose-100 bg-rose-50 p-3">
          <div className="text-xs font-semibold text-rose-800">Before{ga(before.goal_alignment)}</div>
          <p className="mt-1 text-xs text-slate-700">{snippet(before.answer_text)}</p>
        </div>
        <div className="rounded-md border border-emerald-100 bg-emerald-50 p-3">
          <div className="text-xs font-semibold text-emerald-800">Now{ga(after.goal_alignment)}</div>
          <p className="mt-1 text-xs text-slate-700">{snippet(after.answer_text)}</p>
        </div>
      </div>
    </Card>
  );
}
