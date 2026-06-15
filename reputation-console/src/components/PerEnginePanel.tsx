"use client";

import type { PerEngineMetrics } from "@/lib/types";
import { Card } from "@/components/ui";

const fmt = (n: number) => (n >= 0 ? "+" : "") + n.toFixed(2);

// Per-engine read for one run: what EACH AI engine said, with sample sizes, 95% CIs, and
// how much of it was grounded in live web retrieval vs. model memory. Surfaces the
// partial-coverage flag so a run that only hit some engines never reads as the full picture.
export function PerEnginePanel({ data }: { data: PerEngineMetrics }) {
  const engines = Object.entries(data.engines);
  if (engines.length === 0) return null;
  return (
    <Card>
      <h2 className="mb-1 text-lg font-semibold text-gray-900">What each AI engine says</h2>
      <p className="mb-3 text-sm text-gray-500">
        Per-engine read for this run, with sample sizes and 95% confidence intervals.
        “Grounded” means the engine answered from a live web search, not model memory.
      </p>
      {data.coverage.partial && (
        <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Partial coverage — {data.coverage.configured.join(", ") || "no engines"} of the four major
          engines ran.
          {data.coverage.missing.length > 0 && <> Missing: {data.coverage.missing.join(", ")}.</>}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase tracking-wide text-gray-400">
              <th className="py-2 pr-4">Engine</th>
              <th className="py-2 pr-4">Answers</th>
              <th className="py-2 pr-4">Goal alignment (95% CI)</th>
              <th className="py-2 pr-4">Grounded</th>
            </tr>
          </thead>
          <tbody>
            {engines.map(([name, m]) => {
              const ga = m.goal_alignment;
              const gr = m.grounded_rate;
              return (
                <tr key={name} className="border-b last:border-0">
                  <td className="py-2 pr-4 font-medium text-gray-900">{name}</td>
                  <td className="py-2 pr-4 text-gray-600">{m.n}</td>
                  <td className="py-2 pr-4 text-gray-600">
                    {ga?.mean == null ? (
                      "n/a"
                    ) : (
                      <>
                        {fmt(ga.mean)}
                        {ga.low != null && ga.high != null && (
                          <span className="text-gray-400">
                            {" "}
                            ({fmt(ga.low)}…{fmt(ga.high)})
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-gray-600">
                    {gr ? `${Math.round(gr.p! * 100)}% (n=${gr.n})` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
