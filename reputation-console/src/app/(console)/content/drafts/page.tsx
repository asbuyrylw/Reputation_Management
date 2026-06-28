"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useContentDrafts, useContentOptimizationStatus } from "@/lib/hooks";
import { DraftReviewCard } from "@/components/DraftReviewCard";
import { Card, PageHeader, Spinner } from "@/components/ui";

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

  const TabBtn = ({ id, label, n }: { id: Tab; label: string; n: number }) => (
    <button
      onClick={() => setTab(id)}
      className={`rounded-full px-3 py-1 text-sm ${tab === id ? "bg-slate-900 font-medium text-white" : "text-slate-500 hover:text-slate-700"}`}
    >
      {label} ({n})
    </button>
  );

  return (
    <div>
      <PageHeader
        title="Content drafts"
        subtitle="AI-drafted content waiting for your review. Approving publishes it as an asset and advances its work order — nothing publishes without you."
      />

      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <TabBtn id="ready" label="Ready to review" n={ready.length} />
          <TabBtn id="fixes" label="Needs fixes first" n={fixes.length} />
          <TabBtn id="all" label="All" n={data.length} />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {tab === "fixes"
            ? "These passed the writing-quality bar but were flagged on a compliance check — usually a missing disclosure (e.g. broker-dealer / licensing). Edit the draft to resolve the flag, which re-screens it, then approve."
            : "“Ready to review” passed our quality + compliance checks and just needs your sign-off. Approving publishes it and advances its task."}
        </p>
        {/* Subtle dormant-feature hint: only when content-optimization is wired in the app but
            not yet configured for this business — drafts will then carry a SERP-coverage score. */}
        {optStatus && !optStatus.configured && (
          <p className="mt-2 text-[11px] text-slate-400">
            Content optimization:{" "}
            <Link href="/integrations" className="font-medium text-indigo-600 hover:underline">connect NeuronWriter</Link>{" "}
            to score each draft on SERP content coverage.
          </p>
        )}
      </Card>

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-600">
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
