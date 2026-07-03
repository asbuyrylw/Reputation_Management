"use client";

import { useState } from "react";
import { useJobs, useTriggerJob, useAddKeyword } from "@/lib/hooks";

type Suggestion = { keyword: string; why?: string; negative?: boolean };

// "Suggest keywords with AI" — mirrors the AI prompt suggestions. Triggers the
// suggest_keywords background job, polls until it completes (via useJobs), then renders the
// proposed keywords (stored in the job's `result`) as click-to-add chips. Nothing is saved
// until the owner adds it, and already-tracked terms are filtered out.
export function KeywordSuggestions({
  businessId,
  existing,
  canEdit,
}: {
  businessId: number | null;
  existing: string[];
  canEdit: boolean;
}) {
  const trigger = useTriggerJob(businessId);
  const add = useAddKeyword(businessId);
  const { data: jobsData } = useJobs(businessId);
  const [added, setAdded] = useState<Set<string>>(new Set());

  if (!canEdit) return null;

  // Pick the LATEST suggest_keywords job explicitly (don't depend on list ordering).
  const skJobs = (jobsData?.jobs ?? []).filter((j) => j.job_type === "suggest_keywords");
  const skJob = skJobs.length ? skJobs.reduce((a, b) => (b.id > a.id ? b : a)) : undefined;
  const running = (!!skJob && (skJob.status === "queued" || skJob.status === "running")) || trigger.isPending;
  const result = skJob?.status === "complete" ? (skJob.result as { keywords?: Suggestion[] } | null) : null;
  const raw = Array.isArray(result?.keywords) ? (result!.keywords as Suggestion[]) : [];

  const existingSet = new Set(existing.map((k) => k.toLowerCase()));
  const suggestions = raw.filter((s) => s.keyword && !existingSet.has(s.keyword.toLowerCase()) && !added.has(s.keyword.toLowerCase()));

  const onAdd = (s: Suggestion) => {
    add.mutate(
      { keyword: s.keyword, negative: !!s.negative },
      { onSuccess: () => setAdded((a) => new Set(a).add(s.keyword.toLowerCase())) },
    );
  };

  return (
    <div className="mt-3 rounded-xl border border-violet-200 bg-violet-50/40 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-violet-100 text-violet-600" aria-hidden>
            <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5"><path d="M10 1l1.9 4.7L17 7l-4 3.3L14.2 16 10 13.2 5.8 16 7 10.3 3 7l5.1-1.3L10 1z" /></svg>
          </span>
          <span className="text-sm font-semibold text-slate-800">Let AI suggest keywords</span>
        </div>
        <button
          onClick={() => trigger.mutate({ jobType: "suggest_keywords" })}
          disabled={running}
          className="rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-sm font-semibold text-violet-700 hover:bg-violet-50 disabled:opacity-50"
        >
          {running ? "Thinking…" : suggestions.length > 0 ? "Suggest more" : "Suggest keywords with AI"}
        </button>
      </div>

      {running && (
        <p className="mt-2 text-xs text-slate-500">Reading your profile and proposing high-signal terms…</p>
      )}

      {!running && suggestions.length > 0 && (
        <>
          <p className="mt-2 text-xs text-slate-500">Click one to start tracking it. &ldquo;Risk&rdquo; terms are added as watch-only.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s.keyword}
                onClick={() => onAdd(s)}
                disabled={add.isPending}
                title={s.why || undefined}
                className={`group inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition disabled:opacity-50 ${
                  s.negative
                    ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
                    : "border-violet-200 bg-white text-violet-700 hover:bg-violet-100"
                }`}
              >
                <span className="text-violet-400 group-hover:text-violet-600">+</span>
                {s.keyword}
                {s.negative && <span className="text-[10px] uppercase text-rose-400">risk</span>}
              </button>
            ))}
          </div>
        </>
      )}

      {!running && skJob?.status === "complete" && suggestions.length === 0 && raw.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">You&apos;ve added all the suggestions — run again for more.</p>
      )}
    </div>
  );
}
