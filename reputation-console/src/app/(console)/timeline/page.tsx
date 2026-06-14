"use client";

import { useBusiness } from "@/lib/business";
import { useAcceleration, useTimeline } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { DataBlocks } from "@/components/DataBlocks";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";

export default function TimelinePage() {
  const { businessId } = useBusiness();
  const tl = useTimeline(businessId);
  const acc = useAcceleration(businessId);

  if (tl.isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Time to goal"
        subtitle="A projection of how long until the accurate narrative dominates — and what would compress it."
      />
      <DisclaimerBanner>
        This is a projection, not a promise. It reflects how much accurate content is shipping and this
        business&apos;s own measured rate of change, which sharpens as more audits accumulate.
      </DisclaimerBanner>
      <div className="space-y-6">
        {tl.data && (
          <Card>
            <div className="mb-2 text-sm font-medium text-gray-700">Projection</div>
            <DataBlocks data={tl.data} />
          </Card>
        )}
        {acc.data && (
          <Card>
            <div className="mb-2 text-sm font-medium text-gray-700">Acceleration options</div>
            <DataBlocks data={acc.data} />
          </Card>
        )}
      </div>
    </div>
  );
}
