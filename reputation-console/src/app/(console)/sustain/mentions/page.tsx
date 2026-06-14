"use client";

import { useBusiness } from "@/lib/business";
import { useMentions } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SentimentBadge } from "@/components/SentimentBadge";

export default function MentionsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useMentions(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Mentions"
        subtitle="What's being said about this business across the web that the monitor has picked up."
      />
      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No mentions captured yet.</p>
        </Card>
      ) : (
        <div className="space-y-2">
          {data.map((m) => (
            <Card key={m.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{m.source}</span>
                <SentimentBadge sentiment={m.sentiment} />
                {m.relevance != null && <span className="text-xs text-gray-400">relevance {m.relevance.toFixed(2)}</span>}
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
      )}
    </div>
  );
}
