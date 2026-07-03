"use client";

import { Card } from "./ui";
import { ToneBar } from "./primitives";

// Plain-English names + an order that reads from "your own" through earned third-party.
const TYPE_LABELS: Record<string, string> = {
  own: "Your own site",
  review: "Review sites",
  directory: "Directories",
  news: "News / press",
  reference: "Reference (Wikipedia, etc.)",
  forum: "Forums (Reddit, Quora)",
  social: "Social media",
  complaint: "Complaint sites",
  other: "Other sites",
};
const ORDER = ["own", "review", "directory", "news", "reference", "forum", "social", "complaint", "other"];

// The MIX of source TYPES behind the AI answers — tells the owner where to earn presence
// ("AI leans on review sites → get listed on more"), beyond owned/contested/neutral.
export function SourceMix({ bySource }: { bySource: Record<string, { cites: number; share: number }> }) {
  const entries = Object.entries(bySource).filter(([, v]) => v.cites > 0);
  if (entries.length === 0) return null;
  const totalCites = entries.reduce((s, [, v]) => s + v.cites, 0) || 1;
  const sorted = [...entries].sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]));
  const topType = [...entries].filter(([k]) => k !== "own").sort((a, b) => b[1].cites - a[1].cites)[0];

  return (
    <Card>
      <h3 className="text-sm font-semibold text-slate-900">What kinds of sources AI cites</h3>
      <p className="mt-0.5 text-xs text-slate-500">
        The mix of source <em>types</em> behind the answers — it tells you where to earn more accurate presence.
      </p>
      <div className="mt-3 space-y-2">
        {sorted.map(([type, v]) => (
          <div key={type}>
            <div className="mb-0.5 flex items-baseline justify-between text-sm">
              <span className="text-slate-700">{TYPE_LABELS[type] ?? type}</span>
              <span className="tabular-nums text-slate-500">
                {Math.round((v.cites / totalCites) * 100)}% · {v.cites}
              </span>
            </div>
            <ToneBar
              pct={(v.cites / totalCites) * 100}
              tone={type === "own" ? "good" : type === "complaint" ? "bad" : "neutral"}
            />
          </div>
        ))}
      </div>
      {topType && (
        <p className="mt-3 text-xs text-slate-500">
          AI leans most on{" "}
          <span className="font-medium">{(TYPE_LABELS[topType[0]] ?? topType[0]).toLowerCase()}</span> — a strong
          place to earn more accurate presence.
        </p>
      )}
    </Card>
  );
}
