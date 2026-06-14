"use client";

import { useBusiness } from "@/lib/business";
import { useProductionBriefs } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { DataBlocks } from "@/components/DataBlocks";

export default function BriefsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useProductionBriefs(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Content to produce"
        subtitle="Specs for video & social content to create off-platform — target query, keywords, length, hook, and call to action."
      />
      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No production briefs to produce right now.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {data.map((b) => (
            <Card key={b.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">{b.channel}</span>
                {b.platform && <span className="text-xs text-gray-500">{b.platform}</span>}
              </div>
              <div className="mt-1 text-sm font-medium text-gray-900">{b.title}</div>
              {b.target_query && <div className="mt-0.5 text-xs text-gray-500">Targets: {b.target_query}</div>}
              <div className="mt-3">
                <DataBlocks data={b.brief} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
