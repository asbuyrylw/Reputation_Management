"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useContentOptimizationStatus } from "@/lib/hooks";
import { DraftReviewCard } from "@/components/DraftReviewCard";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { TabNav } from "@/components/content/TabNav";

type Tab = "ready" | "fixes" | "all";

export default function DraftsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useContentDrafts(businessId);
  const { data: optStatus } = useContentOptimizationStatus(businessId);
  const [tab, setTab] = useState<Tab>("ready");

  if (isLoading || !data) return <Spinner />;

  // "Ready" = passed our checks and waiting on you. "Needs fixes" = flagged (usually a missing
  // disclosure) — high quality can still land here; it's a compliance gate, not a quality one.
  const ready = data.filter((d) => d.status === "pending_review" && d.compliance_pass !== false);
  const fixes = data.filter((d) => d.status === "needs_fix" || (d.status === "pending_review" && d.compliance_pass === false));
  const shown = tab === "all" ? data : tab === "ready" ? ready : fixes;

  return (
    <div>
      <PageHeader
        title="Content drafts"
        subtitle="AI-drafted content waiting for your review. Approving publishes it as an asset and advances its work order — nothing publishes without you."
      />

      <Card className="mb-4">
        <TabNav
          tabs={[
            { key: "ready", label: "Ready to review", count: ready.length },
            { key: "fixes", label: "Needs fixes first", count: fixes.length },
            { key: "all", label: "All", count: data.length },
          ]}
          active={tab}
          onSelect={(k) => setTab(k as Tab)}
        />
        <p className="mt-2 text-xs text-ink-3">
          {tab === "fixes"
            ? "These passed the writing-quality bar but were flagged on a compliance check — usually a missing disclosure (e.g. broker-dealer / licensing). Edit the draft to resolve the flag, which re-screens it, then approve."
            : "“Ready to review” passed our quality + compliance checks and just needs your sign-off. Approving publishes it and advances its task."}
        </p>
        {/* Subtle dormant-feature hint: only when content-optimization is wired in the app but
            not yet configured for this business — drafts will then carry a SERP-coverage score. */}
        {optStatus && !optStatus.configured && (
          <p className="mt-2 text-[11px] text-ink-4">
            Content optimization:{" "}
            <Link href="/integrations" className="font-medium text-indigo hover:text-indigo-strong">connect NeuronWriter</Link>{" "}
            to score each draft on SERP content coverage.
          </p>
        )}
      </Card>

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-3">
            {tab === "ready" ? "Nothing waiting on you right now — check “Needs fixes first” or generate a draft from a content task." : "No drafts here."}
          </p>
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
