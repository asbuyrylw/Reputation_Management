"use client";

import { useBusiness } from "@/lib/business";
import { useMentions } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SentimentBadge } from "@/components/SentimentBadge";
import { EmptyState } from "@/components/primitives";

function relevanceLabel(r: number | null): string {
  if (r == null) return "";
  if (r >= 0.8) return "Strong match";
  if (r >= 0.5) return "Likely about you";
  return "Possibly unrelated";
}

export default function MentionsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useMentions(businessId);

  if (isLoading || !data) return <Spinner />;

  const counts = { positive: 0, neutral: 0, negative: 0, mixed: 0 } as Record<string, number>;
  for (const m of data) if (m.sentiment && m.sentiment in counts) counts[m.sentiment]++;
  const sourceCounts: Record<string, number> = {};
  for (const m of data) if (m.source) sourceCounts[m.source] = (sourceCounts[m.source] ?? 0) + 1;
  const topSources = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]).slice(0, 5);

  return (
    <div>
      <PageHeader
        title="Mentions"
        subtitle="What's being said about you across the web that we've picked up — and how it leans."
      />
      {data.length === 0 ? (
        <EmptyState
          title="No mentions captured yet"
          why="We watch the web for posts, reviews, and articles that mention your business."
          produces="New mentions show up here with how positive or negative they are and how sure we are they're about you."
          timing="Runs on a schedule once monitoring keywords are set."
        />
      ) : (
        <>
          {/* sentiment rollup */}
          <Card className="mb-4">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-gray-500">{data.length} mentions</span>
              <span className="text-green-700">{counts.positive} positive</span>
              <span className="text-gray-600">{counts.neutral} neutral</span>
              <span className="text-amber-700">{counts.mixed} mixed</span>
              <span className="text-rose-600">{counts.negative} negative</span>
            </div>
            {topSources.length > 0 && (
              <div className="mt-2 border-t border-gray-100 pt-2 text-xs text-gray-500">
                <span className="font-medium text-gray-600">Top sources talking about you:</span>{" "}
                {topSources.map(([src, n]) => `${src} (${n})`).join(" · ")}
              </div>
            )}
          </Card>

          <div className="space-y-2">
            {data.map((m) => (
              <Card key={m.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{m.source}</span>
                  <SentimentBadge sentiment={m.sentiment} />
                  {m.relevance != null && (
                    <span className="text-xs text-gray-400">{relevanceLabel(m.relevance)}</span>
                  )}
                  {m.matched_keyword && <span className="text-xs text-gray-400">&ldquo;{m.matched_keyword}&rdquo;</span>}
                </div>
                {m.title && <div className="mt-1 text-sm font-medium text-gray-900">{m.title}</div>}
                {m.body && (
                  <p className="mt-1 text-sm text-gray-700">
                    {m.body.slice(0, 240)}
                    {m.body.length > 240 ? "…" : ""}
                  </p>
                )}
                {m.source_url && (
                  <a href={m.source_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-blue-600 hover:underline">
                    {m.source_url}
                  </a>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
