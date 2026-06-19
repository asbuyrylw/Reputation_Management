"use client";

import { useState } from "react";
import { usePromptResults } from "@/lib/hooks";
import { Card } from "@/components/ui";
import { ToneBar } from "@/components/primitives";
import { engineLabel } from "@/lib/engines";
import { useFilters } from "@/lib/filters";
import type { PromptResult } from "@/lib/types";

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

function sentimentTone(s: string): string {
  return s === "positive" ? "text-green-700" : s === "negative" ? "text-rose-600"
    : s === "mixed" ? "text-amber-600" : "text-gray-500";
}

function PromptRow({ p, isCustom, engineKey }: { p: PromptResult; isCustom: boolean; engineKey: string | null }) {
  const [open, setOpen] = useState(false);
  const ga = p.goal_alignment?.mean ?? null;
  const engines = Object.entries(p.engines);
  // when a model is selected, the headline visibility + sentiment reflect THAT model only
  const focus = engineKey ? p.engines[engineKey] : null;
  const visibility = engineKey ? focus?.visibility ?? null : p.visibility;
  return (
    <div className="border-t border-gray-100 py-2.5 first:border-0">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-start justify-between gap-3 text-left">
        <div className="min-w-0">
          <p className="text-sm text-gray-900">
            {isCustom && <span className="mr-1.5 rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-700">yours</span>}
            {p.prompt}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
            {engineKey ? (
              <>
                <span>{engineLabel(engineKey)} · {focus?.sentiment ?? "—"}</span>
                {focus?.goal_alignment != null && (
                  <span className={focus.goal_alignment < 0 ? "text-rose-600" : "text-green-700"}>
                    goal {focus.goal_alignment >= 0 ? "+" : ""}{focus.goal_alignment.toFixed(2)}
                  </span>
                )}
              </>
            ) : (
              <>
                <span>across {Object.keys(p.engines).length} engines · {p.n} answers</span>
                {p.sentiment.negative > 0 && <span className="text-rose-600">{p.sentiment.negative} negative</span>}
                {ga != null && <span className={ga < 0 ? "text-rose-600" : "text-green-700"}>goal {ga >= 0 ? "+" : ""}{ga.toFixed(2)}</span>}
              </>
            )}
          </div>
        </div>
        <div className="flex w-28 shrink-0 flex-col items-end gap-1">
          {visibility == null ? (
            <span className="text-xs text-gray-400">no signal</span>
          ) : (
            <>
              <span className="text-sm font-semibold tabular-nums text-gray-900">{pct(visibility)}</span>
              <ToneBar pct={visibility * 100} tone={visibility >= 0.5 ? "good" : "bad"} />
            </>
          )}
        </div>
      </button>
      {open && engines.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3">
          {engines.map(([key, e]) => (
            <div key={key} className="rounded-md border border-gray-100 bg-gray-50 px-2 py-1 text-xs">
              <div className="font-medium text-gray-700">{engineLabel(key)}</div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">{e.visibility == null ? "—" : `${pct(e.visibility)} visible`}</span>
                <span className={sentimentTone(e.sentiment)}>{e.sentiment}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PromptResultsPanel({
  businessId, customTexts,
}: { businessId: number | null; customTexts: Set<string> }) {
  const results = usePromptResults(businessId);
  const { engine } = useFilters();
  const data = results.data;
  if (!data || !data.run_id || data.prompts.length === 0) return null;

  // when a model is selected, keep only prompts that model answered and re-sort by THAT
  // model's visibility (worst first; no-signal last) -- "show me how Perplexity sees each".
  let prompts = data.prompts;
  if (engine) {
    prompts = data.prompts
      .filter((p) => p.engines[engine])
      .slice()
      .sort((a, b) => {
        const av = a.engines[engine]?.visibility, bv = b.engines[engine]?.visibility;
        if (av == null) return bv == null ? 0 : 1;
        if (bv == null) return -1;
        return av - bv;
      });
  }

  return (
    <Card>
      <h3 className="text-sm font-semibold text-gray-900">How your prompts are performing</h3>
      <p className="mt-0.5 text-xs text-gray-500">
        From the latest audit — visibility is how often the AIs surface you for each question (lowest first, so the
        gaps are on top){engine ? <> · showing <span className="font-medium">{engineLabel(engine)}</span></> : " (all models)"}.
        Click a prompt for the per-engine breakdown.
      </p>
      <div className="mt-2">
        {prompts.length === 0 ? (
          <p className="py-2 text-sm text-gray-400">No prompts answered by {engine ? engineLabel(engine) : "this model"} in the latest audit.</p>
        ) : (
          prompts.map((p) => (
            <PromptRow key={p.prompt} p={p} isCustom={customTexts.has(p.prompt)} engineKey={engine} />
          ))
        )}
      </div>
    </Card>
  );
}
