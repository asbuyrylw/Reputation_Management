"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useContentDrafts } from "@/lib/hooks";
import { DraftReviewCard } from "@/components/DraftReviewCard";
import { Card, PageHeader, Spinner } from "@/components/ui";

export default function DraftsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useContentDrafts(businessId);
  const [showAll, setShowAll] = useState(false);

  if (isLoading || !data) return <Spinner />;

  const pending = data.filter((d) => d.status === "pending_review" || d.status === "needs_fix");
  const shown = showAll ? data : pending;

  return (
    <div>
      <PageHeader
        title="Content drafts"
        subtitle="AI-drafted content waiting for your review. Approving publishes it as an asset and advances its work order — nothing publishes without you."
      />
      <div className="mb-4 flex items-center gap-4 text-sm">
        <button onClick={() => setShowAll(false)} className={!showAll ? "font-medium text-slate-900" : "text-slate-500"}>
          Pending ({pending.length})
        </button>
        <button onClick={() => setShowAll(true)} className={showAll ? "font-medium text-slate-900" : "text-slate-500"}>
          All ({data.length})
        </button>
      </div>
      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-600">No drafts to review.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {shown.map((d) => (
            <DraftReviewCard key={d.id} draft={d} businessId={businessId} canEdit={canEdit} />
          ))}
        </div>
      )}
    </div>
  );
}
