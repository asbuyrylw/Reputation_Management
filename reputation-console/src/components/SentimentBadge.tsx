const COLORS: Record<string, string> = {
  positive: "bg-emerald-100 text-emerald-800",
  negative: "bg-rose-100 text-rose-800",
  neutral: "bg-slate-100 text-slate-700",
  mixed: "bg-amber-100 text-amber-800",
};

export function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return null;
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${COLORS[sentiment] || "bg-slate-100 text-slate-700"}`}>
      {sentiment}
    </span>
  );
}

const STATUS_COLORS: Record<string, string> = {
  complete: "bg-emerald-100 text-emerald-800",
  in_progress: "bg-indigo-100 text-indigo-800",
  aborted: "bg-amber-100 text-amber-800",
  failed: "bg-rose-100 text-rose-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[status] || "bg-slate-100 text-slate-700"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
