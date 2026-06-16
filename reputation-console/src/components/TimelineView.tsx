"use client";

// Plain-English replacement for the DataBlocks dump on Time to Goal. Leads with the ONE
// answer the owner wants — "when will it be fixed?" — then a you-are-here->goal bar, an
// explained confidence + recheck cue, and a ranked "speed it up" list. Raw methodology
// stays behind a details disclosure.

import { Card } from "./ui";
import { DataSection, ToneBar } from "./primitives";
import { Term } from "./Term";
import { repScore } from "@/lib/repScore";

type Json = Record<string, unknown>;
type Window = { months?: number; weeks?: number; target_date?: string };
type Lever = {
  lever?: string;
  unit?: string;
  suggested_per_month?: { low?: number; high?: number };
  weeks_saved_range?: { low?: number; high?: number };
  note?: string;
};

const LEVER_LABELS: Record<string, string> = {
  earned_links: "Earned links & citations",
  reviews: "Genuine customer reviews",
  press: "Press / media coverage",
  third_party_mentions: "Third-party mentions",
  directory_listings: "Directory & registry listings",
  social_proof: "Social proof",
};
function leverLabel(k: string | undefined): string {
  if (!k) return "Action";
  return LEVER_LABELS[k] ?? k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function confidenceNote(c: string | undefined): string {
  if (c === "high") return "We've measured your real pace across several audits, so this date is firm.";
  if (c === "medium") return "Based on early measured movement — it'll firm up with another audit or two.";
  return "This is an early estimate from a baseline model. It sharpens after your next audit measures your real pace.";
}

export function TimelineView({ timeline, acceleration }: { timeline: Json; acceleration?: Json }) {
  const cur = repScore((timeline.current_alignment as number) ?? null);
  const goal = repScore((timeline.dominance_target as number) ?? null);
  const confidence = timeline.confidence as string | undefined;
  const proj = (timeline.projection as Json | undefined) ?? {};
  const expected = proj.expected as Window | undefined;
  const optimistic = proj.optimistic as Window | undefined;
  const conservative = proj.conservative as Window | undefined;
  const levers = (acceleration?.levers_ranked_by_impact as Lever[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      {/* projected finish hero */}
      <Card>
        <div className="text-xs font-medium uppercase tracking-wide text-gray-400">Projected finish</div>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-3xl font-bold text-gray-900">{expected?.target_date ?? "—"}</span>
          <span className="text-sm text-gray-500">
            (~{expected?.months ?? "—"} months) to reach your goal of {goal ?? "—"}/100
          </span>
        </div>
        {(optimistic || conservative) && (
          <div className="mt-1 text-sm text-gray-500">
            If things go well: <span className="font-medium text-gray-700">{optimistic?.target_date ?? "—"}</span> ·
            If slower: <span className="font-medium text-gray-700">{conservative?.target_date ?? "—"}</span>
          </div>
        )}
        {confidence && (
          <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm">
            <span className="font-medium text-gray-700">Confidence: {confidence}.</span>{" "}
            <span className="text-gray-600">{confidenceNote(confidence)}</span>
          </div>
        )}
        <p className="mt-2 text-xs text-gray-400">
          A projection, not a promise — it tracks how fast accurate content is out-publishing the negatives. Recheck after your next audit.
        </p>
      </Card>

      {/* you are here -> goal */}
      <Card>
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="font-medium text-gray-700">You are here → your goal</span>
          <span className="text-gray-500">{cur ?? "—"}/100 → {goal ?? "—"}/100</span>
        </div>
        <ToneBar pct={cur != null && goal ? Math.min(100, (cur / goal) * 100) : 0} tone="good" />
        <div className="mt-1 flex justify-between text-xs text-gray-400">
          <span>Today: {cur ?? "—"}</span>
          <span>Goal: {goal ?? "—"} (AI mostly accurate &amp; positive)</span>
        </div>
      </Card>

      {/* speed it up */}
      {levers.length > 0 && (
        <DataSection
          title="Speed it up"
          severity="low"
          headline="Outside actions that finish you sooner. Each shows how many weeks it could cut off — most impactful first."
          highlights={[{ label: "Options", value: String(levers.length) }]}
          defaultOpen
          detailsLabel="See the options"
        >
          <ul className="space-y-2">
            {levers.slice(0, 6).map((l, i) => {
              const ws = l.weeks_saved_range;
              const pm = l.suggested_per_month;
              return (
                <li key={i} className="flex items-start justify-between gap-3 rounded-lg border border-gray-100 p-2.5">
                  <div>
                    <div className="text-sm font-medium text-gray-800">{leverLabel(l.lever)}</div>
                    {pm && (
                      <div className="text-xs text-gray-500">
                        Suggested: {pm.low}–{pm.high} per month{l.unit ? ` (${l.unit})` : ""}
                      </div>
                    )}
                  </div>
                  {ws && (
                    <span className="shrink-0 rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-semibold text-green-700">
                      saves {ws.low}–{ws.high} wks
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </DataSection>
      )}

      {/* methodology behind a disclosure */}
      <DataSection
        title="How this projection works"
        severity="good"
        headline="The date is driven by how entrenched the negatives are, how much accurate content is shipping, and your own measured pace once we have two audits."
        detailsLabel="See the methodology & assumptions"
      >
        <p className="text-sm text-gray-600">
          <Term name="confidence">Confidence</Term> starts low and rises as your own measured pace accumulates.
          {timeline.gain_basis ? ` Basis: ${timeline.gain_basis}.` : ""} AI-platform behavior and competitor
          activity can shift the timeline. This estimates when the accurate narrative DOMINATES what AI
          surfaces — drowning out, not removing, the negatives.
        </p>
      </DataSection>
    </div>
  );
}
