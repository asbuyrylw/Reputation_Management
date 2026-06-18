"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useCompetitors, useCompare, useAddCompetitor, useDeleteCompetitor, useTriggerJob } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, ToneBar } from "@/components/primitives";

const pct = (v: number | undefined | null) => `${Math.round((v ?? 0) * 100)}%`;

export default function CompetitorsPage() {
  const { businessId, canEdit } = useBusiness();
  const competitors = useCompetitors(businessId);
  const compare = useCompare(businessId);
  const add = useAddCompetitor(businessId);
  const del = useDeleteCompetitor(businessId);
  const bench = useTriggerJob(businessId);
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");

  if (competitors.isLoading) return <Spinner />;
  const comps = competitors.data ?? [];
  const c = compare.data ?? {};
  const standings = c.standings ?? [];
  const subject = standings.find((s) => s.is_subject);

  const runBench = () =>
    bench.mutate(
      { jobType: "benchmark" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["compare", businessId] }), 12000) },
    );

  return (
    <div>
      <PageHeader
        title="Competitors"
        subtitle="When AI answers questions in your category, how often does it surface YOU vs. your rivals?"
      />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-gray-600">Track rivals, then benchmark how often AI mentions each of you.</span>
            <button
              onClick={runBench}
              disabled={bench.isPending || comps.length === 0}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              {bench.isPending ? "Benchmarking…" : "Run benchmark"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Competitor name" className="min-w-[14rem] flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm" />
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="Domain (optional)" className="rounded-md border border-gray-300 px-3 py-1.5 text-sm" />
            <button
              onClick={() => name.trim() && add.mutate({ name, domain }, { onSuccess: () => { setName(""); setDomain(""); } })}
              disabled={add.isPending || !name.trim()}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
            >
              Add competitor
            </button>
          </div>
          {comps.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {comps.map((cm) => (
                <span key={cm.id} className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-700">
                  {cm.name}
                  <button onClick={() => del.mutate(cm.id)} className="text-gray-400 hover:text-gray-700" aria-label="remove">×</button>
                </span>
              ))}
            </div>
          )}
        </Card>
      )}

      {standings.length === 0 ? (
        <EmptyState
          title="No benchmark yet"
          why="Add the competitors you care about, then run a benchmark to see how often AI mentions you vs. them for category questions."
          produces="You'll get a ranked share-of-voice board and a head-to-head breakdown."
          timing="A benchmark runs against the AI engines and takes a few minutes."
        />
      ) : (
        <div className="space-y-4">
          {/* standings */}
          <Card>
            <p className="text-sm text-gray-800">
              AI surfaces <span className="font-semibold">{c.business}</span> in{" "}
              <span className="font-semibold">{pct(subject?.appearance_rate)}</span> of category questions — rank{" "}
              <span className={`font-semibold ${(c.subject_rank ?? 99) > 2 ? "text-rose-600" : "text-green-700"}`}>
                {c.subject_rank} of {c.field_size}
              </span>
              . {(c.subject_rank ?? 99) > Math.ceil((c.field_size ?? 1) / 2)
                ? "You're being out-surfaced — the plan's job is to close that gap."
                : "You're holding your own; keep widening the lead."}
            </p>
            <div className="mt-4 space-y-2.5">
              {standings.map((s) => (
                <div key={s.name}>
                  <div className="mb-1 flex items-baseline justify-between text-sm">
                    <span className={s.is_subject ? "font-bold text-gray-900" : "text-gray-700"}>
                      {s.name}{s.is_subject ? " (you)" : ""}
                    </span>
                    <span className="tabular-nums text-gray-600">{pct(s.appearance_rate)} · {s.appears_in} of {c.prompts_compared}</span>
                  </div>
                  <ToneBar pct={s.appearance_rate * 100} tone={s.is_subject ? "bad" : "neutral"} />
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-gray-400">
              Appearance rate = share of category questions where AI mentions the party by name or cites its site.
            </p>
          </Card>

          {/* head to head */}
          {c.head_to_head && c.head_to_head.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-gray-900">Head-to-head</h3>
              <table className="mt-2 w-full text-sm">
                <thead className="text-left text-xs uppercase text-gray-500">
                  <tr>
                    <th className="py-1">Competitor</th>
                    <th className="py-1">Questions only you win</th>
                    <th className="py-1">Questions only they win</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 text-gray-700">
                  {c.head_to_head.map((h) => (
                    <tr key={h.competitor}>
                      <td className="py-1 font-medium text-gray-900">{h.competitor}</td>
                      <td className="py-1 text-green-700">{h.subject_only_prompts}</td>
                      <td className="py-1 text-rose-600">{h.competitor_only_prompts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
