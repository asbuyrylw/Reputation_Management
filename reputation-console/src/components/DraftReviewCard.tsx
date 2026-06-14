"use client";

import { useState } from "react";
import { Card } from "./ui";
import { useApproveDraft, useRejectDraft } from "@/lib/hooks";
import type { ContentDraft } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  pending_review: "bg-amber-100 text-amber-800",
  needs_fix: "bg-orange-100 text-orange-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-gray-200 text-gray-600",
};

export function DraftReviewCard({
  draft,
  businessId,
  canEdit,
}: {
  draft: ContentDraft;
  businessId: number | null;
  canEdit: boolean;
}) {
  const [open, setOpen] = useState(false);
  const approve = useApproveDraft(businessId);
  const reject = useRejectDraft(businessId);
  const body = draft.body || "";
  const long = body.length > 400;
  const pending = draft.status === "pending_review" || draft.status === "needs_fix";
  const flags = Array.isArray(draft.compliance_flags) ? draft.compliance_flags : [];

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">{draft.asset_type}</span>
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[draft.status] || "bg-gray-100 text-gray-700"}`}>
          {draft.status.replace(/_/g, " ")}
        </span>
        {draft.quality_score != null && (
          <span className="text-xs text-gray-500">quality {draft.quality_score.toFixed(2)}</span>
        )}
        {draft.compliance_pass === true && (
          <span className="rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700">compliance ✓</span>
        )}
        {draft.compliance_pass === false && (
          <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-700">compliance ✗</span>
        )}
        {draft.compliance_pass == null && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">not screened</span>
        )}
      </div>
      <div className="mt-2 text-sm font-medium text-gray-900">{draft.title}</div>
      <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700">
        {open || !long ? body : body.slice(0, 400) + "…"}
      </p>
      {long && (
        <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-blue-600 hover:underline">
          {open ? "Show less" : "Show full draft"}
        </button>
      )}
      {flags.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-red-700">
          {flags.map((f, i) => (
            <li key={i}>{String(f)}</li>
          ))}
        </ul>
      )}
      {canEdit && pending && (
        <div className="mt-3 flex gap-2">
          <button
            disabled={approve.isPending}
            onClick={() => approve.mutate({ draftId: draft.id })}
            className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Approve &amp; publish
          </button>
          <button
            disabled={reject.isPending}
            onClick={() => {
              const notes = window.prompt("Reason for rejecting (optional):") || undefined;
              reject.mutate({ draftId: draft.id, notes });
            }}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
          >
            Reject
          </button>
        </div>
      )}
      {(approve.isError || reject.isError) && (
        <p className="mt-2 text-xs text-red-600">Action failed — please retry.</p>
      )}
    </Card>
  );
}
