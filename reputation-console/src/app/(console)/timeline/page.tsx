"use client";

import { useBusiness } from "@/lib/business";
import { useAcceleration, useTimeline } from "@/lib/hooks";
import { PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { PrimaryChallengeCard } from "@/components/PrimaryChallengeCard";
import { TimelineView } from "@/components/TimelineView";
import type { Challenge } from "@/lib/types";

type Json = Record<string, unknown>;

export default function TimelinePage() {
  const { businessId } = useBusiness();
  const tl = useTimeline(businessId);
  const acc = useAcceleration(businessId);

  if (tl.isLoading) return <Spinner />;

  const challenge = (tl.data?.challenge as Challenge | undefined) ?? null;
  const hasData = !!tl.data && tl.data.current_alignment != null;

  return (
    <div>
      <PageHeader
        title="Time to goal"
        subtitle="When your AI reputation will reach your goal — and what would get you there sooner."
      />
      {!hasData ? (
        <EmptyState
          title="No projection yet"
          why="We project your finish date from your audit history and how much accurate content is shipping."
          produces="After your first audit you'll see a projected date; it sharpens with each additional audit."
          timing="Run an audit to begin."
          cta={{ label: "Run an audit", href: "/runs" }}
        />
      ) : (
        <div className="space-y-6">
          <TimelineView timeline={tl.data as Json} acceleration={acc.data as Json | undefined} />
          {challenge && <PrimaryChallengeCard challenge={challenge} />}
        </div>
      )}
    </div>
  );
}
