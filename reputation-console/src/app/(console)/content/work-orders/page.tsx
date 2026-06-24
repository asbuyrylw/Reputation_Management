"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAddWorkOrder, useSetWorkOrderStatus, useWorkOrders, useGenerateDraftForWo, useEditWorkOrder } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, ToneBar } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { WorkOrder } from "@/lib/types";

// Capabilities whose work the AI can draft for you (the per-item "Generate draft" button).
const DRAFTABLE = new Set(["content_writing", "schema_markup", "review_generation", "local_content_creation"]);

const COLUMNS = ["pending", "in_progress", "done", "verified", "blocked", "skipped"];
const LABEL: Record<string, string> = {
  pending: "To do",
  in_progress: "In progress",
  done: "Done",
  verified: "Verified (AI improved)",
  blocked: "Blocked",
  skipped: "Skipped",
};

// internal capability codes -> plain category
const CAPABILITY: Record<string, string> = {
  ai_visibility_tracking: "Tracking",
  content_writing: "Website content",
  schema_markup: "Website code (schema)",
  review_generation: "Reviews",
  press_outreach: "PR / press",
  media_list_building: "PR / press",
  link_building: "Links & citations",
  social_posting: "Social media",
  gbp_optimization: "Google Business Profile",
};
const capLabel = (c?: string | null) =>
  c ? CAPABILITY[c] ?? c.replace(/_/g, " ").replace(/\b\w/g, (x) => x.toUpperCase()) : "Task";

// high-level tool TYPE + concrete examples, by capability
const TOOL_GUIDE: Record<string, { type: string; examples: string[] }> = {
  content_writing: { type: "Article / web-copy creation", examples: ["ChatGPT", "Jasper", "Google Docs", "Surfer SEO"] },
  schema_markup: { type: "Website code (schema)", examples: ["Schema.org generator", "Google Rich Results Test", "your web developer"] },
  review_generation: { type: "Review collection", examples: ["Google Business Profile", "Birdeye", "a follow-up email/SMS"] },
  press_outreach: { type: "PR / media outreach", examples: ["Connectively (HARO)", "Muck Rack", "a pitch email"] },
  media_list_building: { type: "PR / media research", examples: ["Muck Rack", "Prowly", "manual research"] },
  link_building: { type: "Links & citations", examples: ["directory listings", "guest posts", "BBB / industry registries"] },
  social_posting: { type: "Social media", examples: ["Buffer", "Hootsuite", "native schedulers"] },
  social_automation: { type: "Social-media automation", examples: ["Buffer", "Hootsuite", "Later"] },
  gbp_optimization: { type: "Google Business Profile", examples: ["Google Business Profile Manager"] },
  ai_visibility_tracking: { type: "AI-visibility tracking", examples: ["this console's audits"] },
  video_creation: { type: "Video creation", examples: ["Descript", "CapCut", "Synthesia"] },
};

// YYYY-MM-DD -> MM-DD-YYYY
function fmtDate(d?: string | null): string {
  if (!d) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${m[2]}-${m[3]}-${m[1]}` : d;
}

// Break a long instruction into bullets on sentence / semicolon boundaries.
function bulletize(text: string): string[] | null {
  const t = (text || "").trim();
  if (t.length <= 140) return null;
  const parts = t.split(/(?:;\s+|\.\s+(?=[A-Z]))/).map((s) => s.trim().replace(/\.$/, "")).filter(Boolean);
  return parts.length > 1 ? parts : null;
}

function WorkOrderCard({ wo, businessId, canEdit, onStatus }: { wo: WorkOrder; businessId: number | null; canEdit: boolean; onStatus: (s: string) => void }) {
  const tool = TOOL_GUIDE[wo.capability ?? ""];
  const bullets = bulletize(wo.instruction || "");
  const gen = useGenerateDraftForWo(businessId);
  const edit = useEditWorkOrder(businessId);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignee, setAssignee] = useState(wo.assignee ?? "");
  const [startDate, setStartDate] = useState(wo.start_date ?? "");
  const [dueDate, setDueDate] = useState(wo.target_date ?? "");
  // Offer "Generate draft" on AI-draftable content tasks that aren't finished yet.
  const canDraft =
    canEdit &&
    DRAFTABLE.has(wo.capability ?? "") &&
    (wo.execution ?? "auto") !== "manual" &&
    !["done", "verified"].includes(wo.status);
  return (
    <Card className="p-3">
      {/* category (left) · phase above date (right) */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{capLabel(wo.capability)}</span>
          {wo.added_in_revision != null && wo.added_in_revision > 1 && (
            <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-700">Revision {wo.added_in_revision} · new</span>
          )}
        </div>
        <div className="text-right">
          {wo.phase && <div className="text-[11px] font-medium text-slate-500">{wo.phase}</div>}
          {wo.target_date && <div className="text-[11px] text-slate-400">Due {fmtDate(wo.target_date)}</div>}
        </div>
      </div>

      {/* bold to-do heading */}
      <div className="mt-1.5 text-sm font-bold text-slate-900">{wo.title}</div>

      {/* instruction — bulleted when long */}
      {wo.instruction && (
        bullets ? (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-slate-600">
            {bullets.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        ) : (
          <div className="mt-1 text-xs text-slate-600">{wo.instruction}</div>
        )
      )}

      {/* tool type + examples */}
      <div className="mt-1.5 text-[11px] text-slate-500">
        {tool ? (
          <span><span className="font-medium text-slate-600">{tool.type}</span> — e.g. {tool.examples.join(", ")}</span>
        ) : wo.recommended_tool ? (
          <span><span className="font-medium text-slate-600">Tool:</span> {wo.recommended_tool}</span>
        ) : null}
        {wo.assignee && <span> · Owner: {wo.assignee}</span>}
      </div>

      {wo.result_notes && <div className="mt-1 text-xs text-emerald-700">Result: {wo.result_notes}</div>}

      {/* Why this task — what it closes + how it helps (B1 + C10) */}
      {(wo.rationale?.why || wo.gap_source || wo.why_helps_ai_rep || wo.why_helps_seo) && (
        <details className="mt-1.5 text-[11px]">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-700">Why this task?</summary>
          <div className="mt-1 space-y-0.5 rounded bg-slate-50 p-2 text-slate-600">
            {wo.gap_source && (
              <div>
                <span className="font-medium text-slate-500">From:</span> {wo.gap_source}
                {wo.rationale?.source === "recommendation" && (
                  <span className="ml-1 rounded bg-amber-100 px-1 py-0.5 text-amber-700">recommendation</span>
                )}
              </div>
            )}
            {wo.rationale?.why && <div>{wo.rationale.why}</div>}
            {wo.why_helps_ai_rep && <div><span className="font-medium text-indigo-600">AI reputation:</span> {wo.why_helps_ai_rep}</div>}
            {wo.why_helps_seo && <div><span className="font-medium text-emerald-600">SEO:</span> {wo.why_helps_seo}</div>}
          </div>
        </details>
      )}

      {/* predicted impact + owner / dates */}
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
        {wo.predicted_ai_points != null && wo.predicted_ai_points > 0 && (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700" title={`AI-score estimate (${wo.predicted_basis || "estimate"})`}>
            ≈ +{wo.predicted_ai_points} AI pts
          </span>
        )}
        {wo.predicted_seo_impact && wo.predicted_seo_impact !== "—" && (
          <span className="rounded-full bg-sky-50 px-2 py-0.5 font-medium text-sky-700">SEO: {wo.predicted_seo_impact}</span>
        )}
        {wo.assignee && <span className="text-slate-500">👤 {wo.assignee}</span>}
        {wo.start_date && <span className="text-slate-400">{fmtDate(wo.start_date)} → {fmtDate(wo.target_date)}</span>}
        {canEdit && (
          <button onClick={() => setAssignOpen((o) => !o)} className="text-indigo-600 hover:underline">
            {assignOpen ? "close" : wo.assignee ? "reassign / dates" : "assign / dates"}
          </button>
        )}
      </div>
      {assignOpen && canEdit && (
        <div className="mt-2 space-y-1.5 rounded-md bg-slate-50 p-2">
          <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Owner (who's responsible)" className="w-full rounded border border-slate-300 px-2 py-1 text-xs" />
          <div className="flex gap-1.5">
            <label className="flex-1 text-[10px] text-slate-500">Start<input type="date" value={(startDate ?? "").slice(0, 10)} onChange={(e) => setStartDate(e.target.value)} className="mt-0.5 w-full rounded border border-slate-300 px-1.5 py-1 text-xs" /></label>
            <label className="flex-1 text-[10px] text-slate-500">Due<input type="date" value={(dueDate ?? "").slice(0, 10)} onChange={(e) => setDueDate(e.target.value)} className="mt-0.5 w-full rounded border border-slate-300 px-1.5 py-1 text-xs" /></label>
          </div>
          <button
            onClick={() => edit.mutate({ woId: wo.id, assignee, start_date: startDate, target_date: dueDate }, { onSuccess: () => setAssignOpen(false) })}
            disabled={edit.isPending}
            className="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {edit.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      )}

      {canDraft && (
        <div className="mt-2">
          <button
            onClick={() => gen.mutate({ woId: wo.id })}
            disabled={gen.isPending || gen.isSuccess}
            className="w-full rounded-md bg-indigo-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {gen.isPending ? "Generating draft…" : gen.isSuccess ? "Draft queued ✓" : "✨ Generate draft"}
          </button>
          {gen.isSuccess && (
            <p className="mt-1 text-[11px] text-slate-500">It’ll appear under <span className="font-medium">Content → Review drafts</span> in a minute.</p>
          )}
        </div>
      )}

      {canEdit && (
        <select
          value={wo.status}
          onChange={(e) => onStatus(e.target.value)}
          className="mt-2 w-full rounded border border-slate-200 px-2 py-1 text-xs"
        >
          {COLUMNS.map((s) => (
            <option key={s} value={s}>{LABEL[s]}</option>
          ))}
        </select>
      )}
    </Card>
  );
}

function AddTask({ businessId }: { businessId: number | null }) {
  const add = useAddWorkOrder(businessId);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [instruction, setInstruction] = useState("");
  const [due, setDue] = useState("");
  const submit = () =>
    title.trim() &&
    add.mutate(
      { title, instruction: instruction || undefined, target_date: due || undefined },
      { onSuccess: () => { setTitle(""); setInstruction(""); setDue(""); setOpen(false); } },
    );
  return (
    <Card className="mb-4">
      {!open ? (
        <button onClick={() => setOpen(true)} className="text-sm font-medium text-indigo-600 hover:underline">
          + Add a task
        </button>
      ) : (
        <div className="space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title (e.g. Get 5 new Google reviews)"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="What to do (optional)"
            rows={2} className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-slate-500">Due
              <input type="date" value={due} onChange={(e) => setDue(e.target.value)}
                className="ml-1 rounded-md border border-slate-300 px-2 py-1 text-sm" />
            </label>
            <button onClick={submit} disabled={add.isPending || !title.trim()}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
              {add.isPending ? "Adding…" : "Add task"}
            </button>
            <button onClick={() => setOpen(false)} className="text-sm text-slate-500 hover:text-slate-700">Cancel</button>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function WorkOrdersPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useWorkOrders(businessId);
  const setStatus = useSetWorkOrderStatus(businessId);
  const [sortRoi, setSortRoi] = useState(false);

  if (isLoading || !data) return <Spinner />;

  const byStatus = (s: string) => {
    const rows = data.filter((w) => w.status === s);
    return sortRoi ? [...rows].sort((a, b) => (b.predicted_ai_points ?? -1) - (a.predicted_ai_points ?? -1)) : rows;
  };
  const total = data.length;
  const done = byStatus("done").length + byStatus("verified").length;
  const inProgress = byStatus("in_progress").length;
  const donePct = total ? Math.round((done / total) * 100) : 0;
  const visibleColumns = COLUMNS.filter((s) => byStatus(s).length > 0 || ["pending", "in_progress", "done"].includes(s));

  return (
    <div>
      <PageHeader
        title="Reputation Improvement Task List"
        subtitle="Every task that improves your AI reputation, and where each one stands. Change a status to move it."
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />
      {canEdit && <AddTask businessId={businessId} />}
      {total === 0 ? (
        <EmptyState
          title="No tasks yet"
          why="Your task list is built from the gaps an audit finds."
          produces="Once an audit + plan run, your prioritized tasks appear here — what to do, what it fixes, and when."
          timing="An audit takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <>
          {/* progress roll-up */}
          <Card className="mb-4">
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="font-medium text-slate-700">Plan progress</span>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1 text-xs text-slate-500">
                  <input type="checkbox" checked={sortRoi} onChange={(e) => setSortRoi(e.target.checked)} />
                  Highest impact first
                </label>
                <span className="text-slate-500">{done} of {total} done · {inProgress} in progress</span>
              </div>
            </div>
            <ToneBar pct={donePct} tone="good" />
          </Card>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visibleColumns.map((s) => (
              <div key={s}>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-700">{LABEL[s]}</span>
                  <span className="text-xs text-slate-400">{byStatus(s).length}</span>
                </div>
                <div className="space-y-2">
                  {byStatus(s).map((w) => (
                    <WorkOrderCard
                      key={w.id}
                      wo={w}
                      businessId={businessId}
                      canEdit={canEdit}
                      onStatus={(st) => setStatus.mutate({ woId: w.id, status: st })}
                    />
                  ))}
                  {byStatus(s).length === 0 && <p className="text-xs text-slate-300">—</p>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
