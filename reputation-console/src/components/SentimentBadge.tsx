const COLORS: Record<string, string> = {
  positive: "bg-green-100 text-green-800",
  negative: "bg-red-100 text-red-800",
  neutral: "bg-gray-100 text-gray-700",
  mixed: "bg-amber-100 text-amber-800",
};

export function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return null;
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${COLORS[sentiment] || "bg-gray-100 text-gray-700"}`}>
      {sentiment}
    </span>
  );
}

const STATUS_COLORS: Record<string, string> = {
  complete: "bg-green-100 text-green-800",
  in_progress: "bg-blue-100 text-blue-800",
  aborted: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[status] || "bg-gray-100 text-gray-700"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
