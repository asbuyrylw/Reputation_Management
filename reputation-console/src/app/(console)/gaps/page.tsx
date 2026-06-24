"use client";

import { useBusiness } from "@/lib/business";
import { useGapModel, useSocialPresence } from "@/lib/hooks";
import { PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { GapsView } from "@/components/GapsView";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { RunJobButton } from "@/components/RunJobButton";

export default function GapsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useGapModel(businessId);
  const presence = useSocialPresence(businessId);

  if (isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        eyebrow="Gaps"
        title="Your gaps"
        subtitle="What's holding your AI reputation back — and exactly what to do about each one."
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />
      {!data ? (
        <EmptyState
          title="No gaps analysis yet"
          why="Your gaps are worked out from an audit of what AI assistants say about you."
          produces="Once an audit runs, you'll see the questions AI gets wrong, the pages to create, and the order to do them."
          timing="An audit takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <GapsView
          model={data.model}
          asOf={new Date(data.created_at).toLocaleDateString()}
          socialPresence={presence.data}
          verifyButton={
            canEdit ? <RunJobButton businessId={businessId} jobType="social_verify" label="Check my profiles" variant="secondary" /> : null
          }
        />
      )}
    </div>
  );
}
