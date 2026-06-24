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
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-slate-200 text-slate-600",
};

function quality(s: number | null): { label: string; cls: string } | null {
  if (s == null) return null;
  const v = Math.round(s * 100);
  if (s >= 0.8) return { label: `Strong ${v}/100`, cls: "text-emerald-700" };
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
  const added = Array.isArray(draft.highlighted_sections) ? draft.highlighted_sections : [];
  const placeholders = Array.isArray(draft.placeholders_pending) ? draft.placeholders_pending : [];
  // "Why this helps" — derived from the question it targets + the work-order instruction.
  const whyHelps = draft.target_query
    ? `Helps your AI reputation + SEO by publishing accurate, ownable content for “${draft.target_query}”.`
    : draft.wo_instruction
      ? `Supports the task: ${draft.wo_instruction.slice(0, 140)}${draft.wo_instruction.length > 140 ? "…" : ""}`
      : null;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">{draft.asset_type}</span>
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[draft.status] || "bg-slate-100 text-slate-700"}`}>
          {STATUS_WORDS[draft.status] ?? draft.status.replace(/_/g, " ")}
        </span>
        {q && <span className={`text-xs font-medium ${q.cls}`}>Quality: {q.label}</span>}
        {draft.compliance_pass === true && (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">checks passed ✓</span>
        )}
        {draft.compliance_pass === false && (
          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-xs text-rose-700">flagged — review ✗</span>
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
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium"
          />
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            rows={12}
            className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
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
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {edit.isPending ? "Saving…" : "Save changes"}
            </button>
            <button
              onClick={() => { setEditing(false); setEditTitle(draft.title || ""); setEditBody(draft.body || ""); }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <span className="text-xs text-slate-400">Edit the copy, then approve the revised version.</span>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-2 text-sm font-medium text-slate-900">{draft.title}</div>
          {draft.target_query && (
            <div className="text-xs text-slate-500">Answers the question: “{draft.target_query}”</div>
          )}
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
            {open || !long ? body : body.slice(0, 400) + "…"}
          </p>
          {long && (
            <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-indigo-600 hover:underline">
              {open ? "Show less" : "Show full draft"}
            </button>
          )}
        </>
      )}
      {flags.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-rose-700">
          {flags.map((f, i) => (
            <li key={i}>{String(f)}</li>
          ))}
        </ul>
      )}

      {/* compliance language the AI auto-added — the human confirms it's accurate */}
      {added.length > 0 && (
        <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          <div className="font-semibold">We added compliance language — please confirm it&apos;s accurate:</div>
          <ul className="mt-1 list-disc pl-5">
            {added.map((a, i) => <li key={i}>{a?.note || a?.type || "compliance edit"}</li>)}
          </ul>
        </div>
      )}

      {/* unresolved [INSERT: ...] placeholders — a red pre-publish checklist that blocks approval */}
      {placeholders.length > 0 && (
        <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">
          <div className="font-semibold">Fill these in before publishing ({placeholders.length}):</div>
          <ul className="mt-1 space-y-0.5">
            {placeholders.map((p, i) => (
              <li key={i} className="font-mono">☐ {p}</li>
            ))}
          </ul>
          <div className="mt-1 text-rose-500">Click “Edit” and replace each one, then approve.</div>
        </div>
      )}

      {whyHelps && <p className="mt-2 text-xs text-slate-500">💡 {whyHelps}</p>}

      {canEdit && pending && !rejecting && !editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            disabled={approve.isPending || placeholders.length > 0}
            title={placeholders.length > 0 ? "Fill in the placeholders first" : undefined}
            onClick={() => approve.mutate({ draftId: draft.id })}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Approve &amp; publish
          </button>
          <button
            onClick={() => { setEditTitle(draft.title || ""); setEditBody(draft.body || ""); setEditing(true); }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Edit
          </button>
          <button
            disabled={reject.isPending}
            onClick={() => setRejecting(true)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Send back
          </button>
          <span className="text-xs text-slate-400">Approving adds it to your published content.</span>
        </div>
      )}
      {canEdit && pending && rejecting && !editing && (
        <div className="mt-3">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What should change? (optional)"
            rows={2}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <div className="mt-2 flex gap-2">
            <button
              disabled={reject.isPending}
              onClick={() => reject.mutate({ draftId: draft.id, notes: notes || undefined }, { onSuccess: () => setRejecting(false) })}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              Send back for changes
            </button>
            <button onClick={() => { setRejecting(false); setNotes(""); }} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100">
              Cancel
            </button>
          </div>
        </div>
      )}
      {(approve.isError || reject.isError || edit.isError) && (
        <p className="mt-2 text-xs text-rose-600">Action failed — please retry.</p>
      )}
    </Card>
  );
}
