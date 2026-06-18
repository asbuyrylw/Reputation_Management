"use client";

import { useBusiness } from "@/lib/business";
import { useAssets } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

function fmtDate(d?: string | null): string {
  if (!d) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${m[2]}-${m[3]}-${m[1]}` : d;
}

export default function FinalizedContentPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useAssets(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Published content"
        subtitle="The finished content you've approved and published — your reputation assets working for you."
      />
      {data.length === 0 ? (
        <EmptyState
          title="No published content yet"
          why="When you approve a content draft, it's published as an asset and recorded here as one of your reputation assets."
          produces="You'll see each published piece, the question it answers, and where it lives."
          cta={{ label: "Review drafts", href: "/content/drafts" }}
        />
      ) : (
        <div className="space-y-3">
          {data.map((a) => (
            <Card key={a.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-800">Published</span>
                {a.asset_type && <span className="text-xs text-gray-500">{a.asset_type}</span>}
                {a.surface && <span className="text-xs text-gray-400">on {a.surface}</span>}
                {a.published_at && <span className="ml-auto text-xs text-gray-400">{fmtDate(a.published_at)}</span>}
              </div>
              <div className="mt-1 text-sm font-semibold text-gray-900">{a.title || "(untitled)"}</div>
              {a.target_query && <div className="text-xs text-gray-500">Answers: &ldquo;{a.target_query}&rdquo;</div>}
              {a.body && (
                <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700">
                  {a.body.slice(0, 400)}
                  {a.body.length > 400 ? "…" : ""}
                </p>
              )}
              {a.url && (
                <a href={a.url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-blue-600 hover:underline">
                  {a.url}
                </a>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
