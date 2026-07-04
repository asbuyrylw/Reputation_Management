"use client";

import Link from "next/link";
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

  // Degraded plan (mirrors the backend's assemble_plan `degraded` flag): the gap model came back
  // with zero content across every category, so any plan built from it is baseline boilerplate.
  const model = (data?.model ?? null) as Record<string, unknown> | null;
  const GAP_KEYS = ["missing_owned_content", "weak_queries", "schema_gaps", "thin_corroboration",
    "local_seo_gaps", "competitor_defense", "site_technical_gaps", "surface_actions"];
  const isDegraded = !!model && GAP_KEYS.every((k) => {
    const v = model[k];
    if (!v) return true;
    if (Array.isArray(v)) return v.length === 0;
    if (typeof v === "object") return Object.keys(v as object).length === 0;
    return !v;
  });

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
          cta={{ label: "Run an audit", href: "/runs" }}
        />
      ) : (
        <div className="space-y-6">
          {isDegraded && (
            <div className="rounded-[12px] border border-line-2 bg-paper p-4">
              <div className="flex items-center gap-2 text-[14px] font-semibold text-amber">
                <span aria-hidden>⚠</span> Your plan is running on baseline steps only
              </div>
              <div className="mt-1 text-[13px] text-ink-3">The last gap analysis came back empty, so this is generic setup work rather than gap-driven actions. Re-run an audit to rebuild your gaps and get targeted work.</div>
              {canEdit && (
                <Link href="/runs" className="mt-2.5 inline-flex items-center rounded-[8px] bg-indigo px-3 py-1.5 text-[12.5px] font-semibold text-white hover:bg-indigo-strong">Re-run an audit</Link>
              )}
            </div>
          )}
          <GapsView
            model={data.model}
            asOf={new Date(data.created_at).toLocaleDateString()}
            businessId={businessId}
            canEdit={canEdit}
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
