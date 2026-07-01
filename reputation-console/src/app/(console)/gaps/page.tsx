"use client";

import { useBusiness } from "@/lib/business";
import { useGapModel } from "@/lib/hooks";
import { PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { GapsView } from "@/components/GapsView";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { RunJobButton } from "@/components/RunJobButton";
import { FlowStep, NextActions } from "@/components/flow";

export default function GapsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useGapModel(businessId);

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
        <div className="space-y-6">
          <GapsView
            model={data.model}
            asOf={new Date(data.created_at).toLocaleDateString()}
            verifyButton={
              canEdit ? <RunJobButton businessId={businessId} jobType="social_verify" label="Audit socials" variant="secondary" /> : null
            }
          />
          {/* Close the flow loop: from "what's hurting you" → the plan to fix it → when it pays off. */}
          <FlowStep label="What's next" hint="Close these gaps, then watch your score climb." action={{ label: "Full plan", href: "/next-steps" }}>
            <NextActions
              items={[
                { title: "Do this next", note: "Your prioritized, highest-impact actions.", href: "/next-steps" },
                { title: "See when you'll hit your goal", note: "Your projected timeline as these gaps close.", href: "/timeline" },
              ]}
            />
          </FlowStep>
        </div>
      )}
    </div>
  );
}
