"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useLocalRankings, useTriggerJob } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { LocalRankEntry } from "@/lib/types";

// Plain-English rank label + a tone for color. Local lead-gen reads opposite to the
// reputation board: a LOW organic number (page one) / a map-pack spot is GOOD.
function rankLabel(e: LocalRankEntry | null): { text: string; tone: string } {
  if (!e || !e.found) return { text: "Not ranking", tone: "text-rose-600" };
  const parts: string[] = [];
  if (e.organic_rank != null) parts.push(e.on_page_one ? `#${e.organic_rank} (page 1)` : `#${e.organic_rank} (page 2+)`);
  if (e.local_pack_rank != null) parts.push(`map pack #${e.local_pack_rank}`);
  const good = e.on_page_one || e.local_pack_rank != null;
  return { text: parts.join(" · ") || "Listed", tone: good ? "text-emerald-700" : "text-amber-600" };
}

// Plain-English "how far from the front page" — the thing an owner actually wants to know.
function pageDistance(e: LocalRankEntry | null): { text: string; tone: string } {
  if (!e || !e.found || e.organic_rank == null) {
    if (e?.local_pack_rank != null)
      return { text: `In the map pack (#${e.local_pack_rank}), but not in the organic top 20`, tone: "text-amber-600" };
    return { text: "Not in the top 20 — needs to break in", tone: "text-rose-600" };
  }
  if (e.organic_rank <= 10) return { text: `On page 1 — position ${e.organic_rank}`, tone: "text-emerald-700" };
  if (e.organic_rank <= 20) {
    const gap = e.organic_rank - 10;
    return { text: `Page 2, position ${gap} — ${gap} spot${gap === 1 ? "" : "s"} from page 1`, tone: "text-amber-600" };
  }
  return { text: `Position ${e.organic_rank} — well off page 1`, tone: "text-rose-600" };
}

// A 1→20 rank track: page-1 zone (left) green, page-2 zone (right) amber, a marker at your
// position. Makes "how far to the front page" visual at a glance.
function PositionBar({ rank }: { rank: number | null | undefined }) {
  const pct = rank != null && rank >= 1 ? (Math.min(20, rank) / 20) * 100 : null;
  return (
    <div className="mt-2">
      <div className="relative h-2.5 w-full overflow-hidden rounded-full ring-1 ring-slate-900/5">
        <div className="absolute inset-y-0 left-0 w-1/2 bg-emerald-100" />
        <div className="absolute inset-y-0 left-1/2 right-0 bg-amber-100" />
        <div className="absolute inset-y-0 left-1/2 w-px bg-slate-400" aria-hidden />
        {pct != null && (
          <div
            className="absolute top-1/2 h-3.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white bg-slate-900 shadow"
            style={{ left: `${pct}%` }}
            aria-hidden
          />
        )}
      </div>
      <div className="mt-0.5 flex justify-between text-[10px] font-medium uppercase tracking-wide text-slate-400">
        <span>#1</span>
        <span className="text-emerald-600">page 1 ends · #10</span>
        <span>#20{rank != null && rank > 20 ? "+" : ""}</span>
      </div>
    </div>
  );
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

      <JobProgressBanner businessId={businessId} className="mb-4" />

      <div className="mb-4 text-sm text-slate-500">
        Your page-1 goal &amp; scorecard live on the{" "}
        <Link href="/seo-overview" className="font-medium text-indigo-600 hover:text-indigo-700">SEO overview</Link>. This page is the
        per-search detail.
      </div>

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-slate-600">
              Track your Google rank (organic + map pack) for local-category searches vs. your rivals.
            </span>
            <button
              onClick={runTrack}
              disabled={trigger.isPending}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {trigger.isPending ? "Checking…" : "Run local rank check"}
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
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
          {/* per-query board */}
          <Card>
            <h3 className="text-sm font-semibold text-slate-900">Local searches</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              Your rank vs. competitors for each local-category search{queries[0]?.location ? ` in ${queries[0].location}` : ""}.
            </p>
            <div className="mt-3 space-y-4">
              {queries.map((q, qi) => {
                const dist = pageDistance(q.subject);
                const ranked = (q.competitors ?? [])
                  .filter((c) => c.found)
                  .sort((a, b) => (a.organic_rank ?? 99) - (b.organic_rank ?? 99));
                return (
                  <div key={`${q.query}__${qi}`} className="border-t border-slate-100 pt-3 first:border-0 first:pt-0">
                    {/* the actual search the customer types */}
                    <div className="text-sm font-medium text-slate-900">&ldquo;{q.query}&rdquo;</div>
                    <div className={`mt-0.5 text-sm font-semibold ${dist.tone}`}>You: {dist.text}</div>
                    <PositionBar rank={q.subject?.organic_rank ?? null} />
                    {ranked.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <span className="text-xs text-slate-400">Ahead of you:</span>
                        {ranked.map((c) => {
                          const lbl = rankLabel(c);
                          return (
                            <span
                              key={c.name}
                              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600"
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
            {s.note && <p className="mt-4 text-xs text-slate-400">{s.note}</p>}
          </Card>
        </div>
      )}
    </div>
  );
}
