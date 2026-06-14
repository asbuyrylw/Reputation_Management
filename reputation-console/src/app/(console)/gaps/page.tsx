"use client";

import { useBusiness } from "@/lib/business";
import { useGapModel } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { DataBlocks } from "@/components/DataBlocks";

export default function GapsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useGapModel(businessId);

  if (isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Gaps"
        subtitle="Where AI answers fall short of your goal, and what's missing that would move them — the engine's gap analysis."
      />
      {!data ? (
        <Card>
          <p className="text-sm text-gray-600">No gap model yet — it's built from the latest audit.</p>
        </Card>
      ) : (
        <Card>
          <div className="mb-3 text-xs text-gray-400">As of {new Date(data.created_at).toLocaleDateString()}</div>
          <DataBlocks data={data.model} />
        </Card>
      )}
    </div>
  );
}
