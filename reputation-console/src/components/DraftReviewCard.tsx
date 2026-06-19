"use client";

import { useState } from "react";
import { Card } from "./ui";
import { useApproveDraft, useEditDraft, useRejectDraft } from "@/lib/hooks";
import type { ContentDraft } from "@/lib/types";

const STATUS_WORDS: Record<string, string> = {
  pending_review: "Waiting for you",
  needs_fix: "Needs a fix",
  approved: "Approved",
  rejected: "Rejected",
};
const STATUS_COLORS: Record<string, string> = {
  pending_review: "bg-amber-100 text-amber-800",
  needs_fix: "bg-orange-100 text-orange-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-gray-200 text-gray-600",
};

function quality(s: number | null): { label: string; cls: string } | null {
  if (s == null) return null;
  const v = Math.round(s * 100);
  if (s >= 0.8) return { label: `Strong ${v}/100`, cls: "text-green-700" };
  if (s >= 0.6) return { label: `OK ${v}/100`, cls: "text-amber-700" };
  return { label: `Weak ${v}/100`, cls: "text-rose-600" };
}

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
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState("");
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(draft.title || "");
  const [editBody, setEditBody] = useState(draft.body || "");
  const approve = useApproveDraft(businessId);
  const reject = useRejectDraft(businessId);
  const edit = useEditDraft(businessId);
  const body = draft.body || "";
  const long = body.length > 400;
  const pending = draft.status === "pending_review" || draft.status === "needs_fix";
  const flags = Array.isArray(draft.compliance_flags) ? draft.compliance_flags : [];
  const q = quality(draft.quality_score);

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">{draft.asset_type}</span>
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[draft.status] || "bg-gray-100 text-gray-700"}`}>
          {STATUS_WORDS[draft.status] ?? draft.status.replace(/_/g, " ")}
        </span>
        {q && <span className={`text-xs font-medium ${q.cls}`}>Quality: {q.label}</span>}
        {draft.compliance_pass === true && (
          <span className="rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700">checks passed ✓</span>
        )}
        {draft.compliance_pass === false && (
          <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-700">flagged — review ✗</span>
        )}
        {draft.compliance_pass == null && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">not checked yet</span>
        )}
      </div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            placeholder="Title"
            className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium"
          />
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            rows={12}
            className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
          />
          <div className="flex items-center gap-2">
            <button
              disabled={edit.isPending || !editTitle.trim() || !editBody.trim()}
              onClick={() =>
                edit.mutate(
                  { draftId: draft.id, title: editTitle, body: editBody },
                  { onSuccess: () => setEditing(false) },
                )
              }
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              {edit.isPending ? "Saving…" : "Save changes"}
            </button>
            <button
              onClick={() => { setEditing(false); setEditTitle(draft.title || ""); setEditBody(draft.body || ""); }}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
            >
              Cancel
            </button>
            <span className="text-xs text-gray-400">Edit the copy, then approve the revised version.</span>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-2 text-sm font-medium text-gray-900">{draft.title}</div>
          {draft.target_query && (
            <div className="text-xs text-gray-500">Answers the question: “{draft.target_query}”</div>
          )}
          <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700">
            {open || !long ? body : body.slice(0, 400) + "…"}
          </p>
          {long && (
            <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-blue-600 hover:underline">
              {open ? "Show less" : "Show full draft"}
            </button>
          )}
        </>
      )}
      {flags.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-red-700">
          {flags.map((f, i) => (
            <li key={i}>{String(f)}</li>
          ))}
        </ul>
      )}
      {canEdit && pending && !rejecting && !editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            disabled={approve.isPending}
            onClick={() => approve.mutate({ draftId: draft.id })}
            className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Approve &amp; publish
          </button>
          <button
            onClick={() => { setEditTitle(draft.title || ""); setEditBody(draft.body || ""); setEditing(true); }}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
          >
            Edit
          </button>
          <button
            disabled={reject.isPending}
            onClick={() => setRejecting(true)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
          >
            Send back
          </button>
          <span className="text-xs text-gray-400">Approving adds it to your published content.</span>
        </div>
      )}
      {canEdit && pending && rejecting && !editing && (
        <div className="mt-3">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What should change? (optional)"
            rows={2}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <div className="mt-2 flex gap-2">
            <button
              disabled={reject.isPending}
              onClick={() => reject.mutate({ draftId: draft.id, notes: notes || undefined }, { onSuccess: () => setRejecting(false) })}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              Send back for changes
            </button>
            <button onClick={() => { setRejecting(false); setNotes(""); }} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100">
              Cancel
            </button>
          </div>
        </div>
      )}
      {(approve.isError || reject.isError || edit.isError) && (
        <p className="mt-2 text-xs text-red-600">Action failed — please retry.</p>
      )}
    </Card>
  );
}
