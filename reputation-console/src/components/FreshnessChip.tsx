"use client";

import { useEffect, useState } from "react";

// Always-on data-freshness chip: tells the owner, at a glance, how current the numbers are and
// when they're going stale. Green ≤10d, amber ≤30d, red/"stale" beyond — a stale chip is the cue
// to hit Refresh. Renders even with no data yet ("Not run yet") so the header state is never blank.
export function FreshnessChip({ asOf, staleDays = 30 }: { asOf?: string | null; staleDays?: number }) {
  // `now` lives in state (calling Date.now() during render is impure and flagged) and is set once
  // on mount; day-granularity needs no ticker. Until it's set we render as fresh, then it corrects.
  const [now, setNow] = useState(0);
  useEffect(() => {
    // Deferred (not a synchronous setState in the effect body) so it reads as an external-system
    // callback and doesn't trip the cascading-render rule; day granularity needs no ongoing ticker.
    const id = setTimeout(() => setNow(Date.now()), 0);
    return () => clearTimeout(id);
  }, [asOf]);

  if (!asOf) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-line-2 bg-white px-2.5 py-1 text-[11.5px] font-medium text-ink-4">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-300" aria-hidden /> Not run yet
      </span>
    );
  }
  const then = new Date(asOf).getTime();
  const days = now ? Math.max(0, Math.floor((now - then) / 86_400_000)) : 0;
  const rel = days <= 0 ? "today" : days === 1 ? "yesterday" : days < 30 ? `${days}d ago`
    : days < 365 ? `${Math.round(days / 30)}mo ago` : `${Math.round(days / 365)}y ago`;
  const tone = days <= 10
    ? { dot: "bg-good", box: "border-good bg-good-bg text-good", tip: "" }
    : days <= staleDays
      ? { dot: "bg-amber-500", box: "border-amber-200 bg-amber-50 text-amber-800", tip: "" }
      : { dot: "bg-alert", box: "border-alert bg-alert-bg text-alert", tip: " · refresh recommended" };
  return (
    <span
      title={`Latest audit: ${new Date(asOf).toLocaleString()}`}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium ${tone.box}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden /> Updated {rel}{tone.tip}
    </span>
  );
}
