"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useLocalRankings, useTriggerJob } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { MetricCard, EmptyState } from "@/components/primitives";
import type { LocalRankEntry } from "@/lib/types";

const pct = (v: number | undefined | null) => `${Math.round((v ?? 0) * 100)}%`;

// Plain-English rank label + a tone for color. Local lead-gen reads opposite to the
// reputation board: a LOW organic number (page one) / a map-pack spot is GOOD.
function rankLabel(e: LocalRankEntry | null): { text: string; tone: string } {
  if (!e || !e.found) return { text: "Not ranking", tone: "text-rose-600" };
  const parts: string[] = [];
  if (e.organic_rank != null) parts.push(e.on_page_one ? `#${e.organic_rank} (page 1)` : `#${e.organic_rank} (page 2+)`);
  if (e.local_pack_rank != null) parts.push(`map pack #${e.local_pack_rank}`);
  const good = e.on_page_one || e.local_pack_rank != null;
  return { text: parts.join(" · ") || "Listed", tone: good ? "text-green-700" : "text-amber-600" };
}

export default function LocalSeoPage() {
  const { businessId, canEdit } = useBusiness();
  const ranks = useLocalRankings(businessId);
  const trigger = useTriggerJob(businessId);
  const qc = useQueryClient();

  if (ranks.isLoading) return <Spinner />;
  const data = ranks.data;
  const queries = data?.queries ?? [];
  const s = data?.summary ?? null;

  const runTrack = () =>
    trigger.mutate(
      { jobType: "local_rank" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["local-rankings", businessId] }), 15000) },
    );

  return (
    <div>
      <PageHeader
        title="Local search rankings"
        subtitle="Where you land on Google's first page — and in the map pack — for the local searches your neighbors actually type."
      />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-gray-600">
              Track your Google rank (organic + map pack) for local-category searches vs. your rivals.
            </span>
            <button
              onClick={runTrack}
              disabled={trigger.isPending}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              {trigger.isPending ? "Checking…" : "Run local rank check"}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Live tracking uses a Google SERP source (set <code>SERPER_API_KEY</code>); without it the page shows the
            most recent captured snapshot.
          </p>
        </Card>
      )}

      {!s || queries.length === 0 ? (
        <EmptyState
          title="No local rank snapshot yet"
          why="We haven't captured where you rank on Google for local-category searches like “financial services in your city” or “… near me”."
          produces="You'll see your Google organic + map-pack rank for each local search, side-by-side with competitors, plus a page-one / map-pack scorecard."
          timing="A local rank check runs against Google results and takes a minute or two."
        />
      ) : (
        <div className="space-y-4">
          {/* scorecard */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <MetricCard
              label="On page one"
              value={pct(s.page_one_rate)}
              tone={s.page_one_rate >= 0.5 ? "good" : "bad"}
              whyItMatters="Share of local searches where you appear on Google's first page. Almost all clicks happen here."
            />
            <MetricCard
              label="In the map pack"
              value={pct(s.local_pack_rate)}
              tone={s.local_pack_rate >= 0.5 ? "good" : "bad"}
              whyItMatters="Share of searches where you show in Google's local 3-pack — the map results a nearby customer sees first."
            />
            <MetricCard
              label="Avg. position"
              value={s.avg_organic_rank == null ? "—" : `#${s.avg_organic_rank}`}
              tone={s.avg_organic_rank != null && s.avg_organic_rank <= 10 ? "good" : "bad"}
              whyItMatters={`Average Google rank where you appear (${s.ranked_queries} of ${s.queries} local searches).`}
            />
          </div>

          {/* per-query board */}
          <Card>
            <h3 className="text-sm font-semibold text-gray-900">Local searches</h3>
            <p className="mt-0.5 text-xs text-gray-500">
              Your rank vs. competitors for each local-category search{queries[0]?.location ? ` in ${queries[0].location}` : ""}.
            </p>
            <div className="mt-3 space-y-4">
              {queries.map((q) => {
                const me = rankLabel(q.subject);
                const ranked = (q.competitors ?? [])
                  .filter((c) => c.found)
                  .sort((a, b) => (a.organic_rank ?? 99) - (b.organic_rank ?? 99));
                return (
                  <div key={q.query} className="border-t border-gray-100 pt-3 first:border-0 first:pt-0">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="text-sm font-medium text-gray-900">{q.query}</span>
                      <span className={`text-sm font-semibold ${me.tone}`}>You: {me.text}</span>
                    </div>
                    {ranked.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {ranked.map((c) => {
                          const lbl = rankLabel(c);
                          return (
                            <span
                              key={c.name}
                              className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-600"
                            >
                              {c.name}
                              <span className={lbl.tone}>{lbl.text}</span>
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {s.note && <p className="mt-4 text-xs text-gray-400">{s.note}</p>}
          </Card>
        </div>
      )}
    </div>
  );
}
