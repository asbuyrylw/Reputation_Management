"use client";

import { useBusiness } from "@/lib/business";
import { useProductionBriefs } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

function humanize(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// A clean "content recipe": each brief field as a labeled row, arrays as bullets — instead
// of the raw JSON dump. Tells the producer exactly what to make and what question it answers.
function Recipe({ brief }: { brief: Record<string, unknown> }) {
  const entries = Object.entries(brief).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return <p className="text-sm text-gray-400">No recipe details.</p>;
  return (
    <dl className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[160px_1fr]">
          <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">{humanize(k)}</dt>
          <dd className="text-sm text-gray-700">
            {Array.isArray(v) ? (
              <ul className="list-disc space-y-0.5 pl-4">
                {v.map((it, i) => <li key={i}>{typeof it === "object" ? JSON.stringify(it) : String(it)}</li>)}
              </ul>
            ) : typeof v === "object" ? (
              <span className="text-gray-500">{JSON.stringify(v)}</span>
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function BriefsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useProductionBriefs(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Content to produce"
        subtitle="Recipes for video & social content to create — what to make, and the question it answers when someone asks AI about you."
      />
      {data.length === 0 ? (
        <EmptyState
          title="Nothing queued to produce right now"
          why="Production recipes are generated for off-platform content (video, social) when the plan calls for it."
          produces="When ready, each will show the platform, the target question, and the full recipe to film/post."
          timing="Created as your plan progresses."
        />
      ) : (
        <div className="space-y-3">
          {data.map((b) => (
            <Card key={b.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">{b.channel}</span>
                {b.platform && <span className="text-xs text-gray-500">{b.platform}</span>}
              </div>
              <div className="mt-1 text-sm font-semibold text-gray-900">{b.title}</div>
              {b.target_query && (
                <div className="mt-0.5 text-xs text-gray-500">Answers the question: “{b.target_query}”</div>
              )}
              <div className="mt-3 border-t border-gray-100 pt-3">
                <Recipe brief={b.brief} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
