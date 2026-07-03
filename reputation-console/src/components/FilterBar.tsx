"use client";

import { useFilters, type Period } from "@/lib/filters";
import { engineLabel } from "@/lib/engines";

// Every engine we can produce data for: the core four plus the expansion engines, which
// become active once their keys are configured. Selecting one with no data in the current
// view is handled gracefully downstream ("no data for <model>"), so listing all of them
// keeps the comment and the array honest and lets the filter target a live expansion engine.
const FILTER_ENGINES = [
  "openai_search", "anthropic", "perplexity", "gemini", "grok", "google_aio", "bing_copilot",
];

const PERIODS: { value: Period; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "90d", label: "Last 90 days" },
  { value: "30d", label: "Last 30 days" },
];

const selectClass =
  "rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700 focus:border-slate-400 focus:outline-none";

// Period + model filters. Applies to the views that have something to filter (per-engine
// analytics, per-prompt results, the visibility trend); other views ignore it.
export function FilterBar() {
  const { engine, setEngine, period, setPeriod } = useFilters();
  return (
    <div className="flex items-center gap-2">
      <select
        aria-label="Time period"
        className={selectClass}
        value={period}
        onChange={(e) => setPeriod(e.target.value as Period)}
      >
        {PERIODS.map((p) => (
          <option key={p.value} value={p.value}>{p.label}</option>
        ))}
      </select>
      <select
        aria-label="AI model"
        className={selectClass}
        value={engine ?? ""}
        onChange={(e) => setEngine(e.target.value || null)}
      >
        <option value="">All models</option>
        {FILTER_ENGINES.map((k) => (
          <option key={k} value={k}>{engineLabel(k)}</option>
        ))}
      </select>
    </div>
  );
}
