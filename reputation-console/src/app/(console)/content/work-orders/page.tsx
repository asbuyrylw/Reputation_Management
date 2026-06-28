"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAddWorkOrder, useSetWorkOrderStatus, useWorkOrders, useGenerateDraftForWo, useEditWorkOrder, useAddWorkOrderNote, useContentDrafts, useAssets, useTeam, useActionsTaken, useTaskImpact, useRoadmap } from "@/lib/hooks";
import { downloadCsv } from "@/lib/download";
import { useAuth } from "@/lib/auth";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { Badge, Button, EmptyState, ToneBar } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { VisualContentPanel } from "@/components/VisualContentPanel";
import type { WorkOrder, ProgressNote, ContentDraft, Asset, ActionTaken, TaskImpact, RoadmapItem } from "@/lib/types";

// The draft/asset a task produced, as a small deep-linked status (the execution narrative:
// task -> draft -> published asset).
function ProducedLink({ draft, asset }: { draft?: ContentDraft; asset?: Asset }) {
  const published = asset && (asset.published_status === "live" || asset.published_url);
  if (published) {
    return asset?.published_url
      ? <a href={asset.published_url} target="_blank" rel="noreferrer" className="text-emerald-700 hover:underline">✓ Published →</a>
      : <Link href="/content/finalized" className="text-emerald-700 hover:underline">✓ Published →</Link>;
  }
  if (asset || draft?.status === "approved") return <Link href="/content/finalized" className="text-sky-700 hover:underline">Approved — publish →</Link>;
  if (draft) {
    const label = draft.status === "needs_fix" ? "Draft needs a fix" : draft.status === "rejected" ? "Draft rejected" : "Draft in review";
    return <Link href="/content/drafts" className="text-amber-700 hover:underline">{label} →</Link>;
  }
  return null;
}

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

// Plain labels + display order for the "by area" grouping. null/empty area -> "other".
const AREA_LABEL: Record<string, string> = {
  website: "Website",
  content: "Content",
  blog: "Blog",
  outreach: "Outreach",
  social: "Social",
  local: "Local",
  reviews: "Reviews",
  tracking: "Tracking",
  other: "Other",
};
const AREA_ORDER = ["website", "content", "blog", "outreach", "social", "local", "reviews", "tracking", "other"];
const areaKey = (a?: string | null) => {
  const k = (a || "").trim().toLowerCase();
  return k && AREA_LABEL[k] ? k : "other";
};
// Platforms get a small chip in the social/local groups so the owner sees which network each task targets.
const PLATFORM_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
  reddit: "Reddit",
  gbp: "GBP",
};
const platformLabel = (p?: string | null) =>
  p ? PLATFORM_LABEL[p] ?? p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : null;

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

// Today as a YYYY-MM-DD string in the local timezone (default for the completion date).
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

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

// Short timestamp for a progress note ("Jun 24, 3:10 PM").
function fmtWhen(at?: string | null): string {
  if (!at) return "";
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// Progress-notes timeline + an "add note" box, so a managed task carries its own work log.
function NotesSection({ wo, businessId, canEdit }: { wo: WorkOrder; businessId: number | null; canEdit: boolean }) {
  const addNote = useAddWorkOrderNote(businessId);
  const [text, setText] = useState("");
  const notes: ProgressNote[] = wo.progress_notes ?? [];
  const submit = () =>
    text.trim() && addNote.mutate({ woId: wo.id, text }, { onSuccess: () => setText("") });
  return (
    <details className="mt-1.5 text-[11px]">
      <summary className="cursor-pointer text-slate-500 hover:text-slate-700">Progress notes ({notes.length})</summary>
      <div className="mt-1 space-y-1.5 rounded bg-slate-50 p-2">
        {notes.length > 0 ? (
          <ul className="space-y-1">
            {notes.map((n, i) => (
              <li key={i} className="border-l-2 border-slate-200 pl-2">
                <div className="text-slate-700">{n.text}</div>
                <div className="text-[10px] text-slate-400">{[n.author, fmtWhen(n.at)].filter(Boolean).join(" · ")}</div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-slate-400">No notes yet.</div>
        )}
        {canEdit && (
          <div className="flex gap-1.5">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              placeholder="Add a progress note…"
              className="flex-1 rounded border border-slate-300 px-2 py-1 text-[11px]"
            />
            <button
              onClick={submit}
              disabled={addNote.isPending || !text.trim()}
              className="rounded bg-slate-900 px-2 py-1 text-[11px] font-medium text-white disabled:opacity-50"
            >
              {addNote.isPending ? "…" : "Add"}
            </button>
          </div>
        )}
      </div>
    </details>
  );
}

function WorkOrderCard({ wo, businessId, canEdit, onStatus, draft, asset }: { wo: WorkOrder; businessId: number | null; canEdit: boolean; onStatus: (s: string, completedOn?: string) => void; draft?: ContentDraft; asset?: Asset }) {
  const tool = TOOL_GUIDE[wo.capability ?? ""];
  const bullets = bulletize(wo.instruction || "");
  const gen = useGenerateDraftForWo(businessId);
  const edit = useEditWorkOrder(businessId);
  const { data: team } = useTeam(businessId);
  const hasTeam = (team?.length ?? 0) > 0;
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignee, setAssignee] = useState(wo.assignee ?? "");
  const [assigneeUserId, setAssigneeUserId] = useState(wo.assignee_user_id ? String(wo.assignee_user_id) : "");
  const [startDate, setStartDate] = useState(wo.start_date ?? "");
  const [dueDate, setDueDate] = useState(wo.target_date ?? "");
  // When the owner moves a task to done/verified, capture the completion date (default today,
  // back-datable for work done outside the system) before sending the status change.
  const [pendingDone, setPendingDone] = useState<string | null>(null); // the target status awaiting a date
  const [completedOn, setCompletedOn] = useState(todayISO());
  // The common case is "I finished this today" — a one-click complete with today's date. The
  // back-date input is an optional affordance, not a mandatory second step.
  const [backdateOpen, setBackdateOpen] = useState(false);
  const isDone = wo.status === "done" || wo.status === "verified";
  const onStatusChange = (next: string) => {
    if (next === "done" || next === "verified") {
      setCompletedOn(todayISO());
      setPendingDone(next);
    } else {
      onStatus(next);
    }
  };
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
          {/* platform chip — shown for social/local tasks so the owner sees the target network */}
          {(areaKey(wo.area) === "social" || areaKey(wo.area) === "local") && platformLabel(wo.platform) && (
            <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[11px] font-medium text-sky-700">{platformLabel(wo.platform)}</span>
          )}
          {wo.added_in_revision != null && wo.added_in_revision > 1 && (
            <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-700">Revision {wo.added_in_revision} · new</span>
          )}
          {wo.superseded && (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">archived (no longer in plan)</span>
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
          {hasTeam ? (
            <select value={assigneeUserId} onChange={(e) => setAssigneeUserId(e.target.value)} className="w-full rounded border border-slate-300 px-2 py-1 text-xs">
              <option value="">Unassigned</option>
              {team!.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          ) : (
            <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Owner (who's responsible)" className="w-full rounded border border-slate-300 px-2 py-1 text-xs" />
          )}
          <div className="flex gap-1.5">
            <label className="flex-1 text-[10px] text-slate-500">Start<input type="date" value={(startDate ?? "").slice(0, 10)} onChange={(e) => setStartDate(e.target.value)} className="mt-0.5 w-full rounded border border-slate-300 px-1.5 py-1 text-xs" /></label>
            <label className="flex-1 text-[10px] text-slate-500">Due<input type="date" value={(dueDate ?? "").slice(0, 10)} onChange={(e) => setDueDate(e.target.value)} className="mt-0.5 w-full rounded border border-slate-300 px-1.5 py-1 text-xs" /></label>
          </div>
          <button
            onClick={() => edit.mutate({ woId: wo.id, assignee_user_id: hasTeam && assigneeUserId ? Number(assigneeUserId) : (hasTeam ? null : undefined), assignee: hasTeam ? undefined : assignee, start_date: startDate, target_date: dueDate }, { onSuccess: () => setAssignOpen(false) })}
            disabled={edit.isPending}
            className="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {edit.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      )}

      {/* what this task produced (task -> draft -> published asset) */}
      {(draft || asset) && (
        <div className="mt-1.5 text-[11px] font-medium"><ProducedLink draft={draft} asset={asset} /></div>
      )}

      {/* per-task work log */}
      <NotesSection wo={wo} businessId={businessId} canEdit={canEdit} />

      {/* generate a visual (quote card / AI image / video brief) for this task */}
      <VisualContentPanel businessId={businessId} workOrderId={wo.id} canEdit={canEdit} />

      {canDraft && !draft && !asset && (
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

      {/* One-click complete: mark done with today's date. Back-dating is optional (the small
          "Done earlier?" toggle), so the common case is a single click. */}
      {canEdit && !isDone && !pendingDone && (
        <div className="mt-2">
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className="flex-1"
              onClick={() => { onStatus("done", todayISO()); setBackdateOpen(false); }}
            >
              ✓ Mark done
            </Button>
            <button
              type="button"
              onClick={() => setBackdateOpen((o) => !o)}
              className="shrink-0 text-[11px] font-medium text-slate-500 hover:text-slate-700"
            >
              {backdateOpen ? "close" : "Done earlier?"}
            </button>
          </div>
          {backdateOpen && (
            <div className="mt-1.5 flex items-center gap-1.5 rounded-md bg-slate-50 p-2">
              <label className="flex-1 text-[10px] text-slate-500">
                Completed on
                <input
                  type="date"
                  value={completedOn}
                  max={todayISO()}
                  onChange={(e) => setCompletedOn(e.target.value)}
                  className="mt-0.5 w-full rounded border border-slate-300 px-1.5 py-1 text-xs"
                />
              </label>
              <button
                type="button"
                onClick={() => { onStatus("done", completedOn || todayISO()); setBackdateOpen(false); }}
                className="mt-3 shrink-0 rounded bg-emerald-700 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-800"
              >
                Save
              </button>
            </div>
          )}
        </div>
      )}

      {/* Full status control — for the other states (in progress / blocked / verified / skipped)
          and to re-open an already-completed task. */}
      {canEdit && (
        <select
          value={wo.status}
          onChange={(e) => onStatusChange(e.target.value)}
          className="mt-2 w-full rounded border border-slate-200 px-2 py-1 text-xs"
        >
          {COLUMNS.map((s) => (
            <option key={s} value={s}>{LABEL[s]}</option>
          ))}
        </select>
      )}

      {/* completion date — shown when moving to done/verified; defaults to today, back-datable */}
      {canEdit && pendingDone && (
        <div className="mt-2 space-y-1.5 rounded-md bg-emerald-50 p-2 ring-1 ring-inset ring-emerald-200">
          <label className="block text-[11px] font-medium text-emerald-800">
            Mark “{LABEL[pendingDone]}” — completed on
            <input
              type="date"
              value={completedOn}
              max={todayISO()}
              onChange={(e) => setCompletedOn(e.target.value)}
              className="mt-0.5 w-full rounded border border-emerald-300 px-1.5 py-1 text-xs"
            />
          </label>
          <p className="text-[10px] text-emerald-700">Defaults to today — change it if the work was done earlier.</p>
          <div className="flex gap-1.5">
            <button
              onClick={() => { onStatus(pendingDone, completedOn || todayISO()); setPendingDone(null); }}
              className="rounded bg-emerald-700 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-800"
            >
              Confirm
            </button>
            <button onClick={() => setPendingDone(null)} className="text-[11px] text-slate-500 hover:text-slate-700">Cancel</button>
          </div>
        </div>
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

// "Work completed / what moved the needle" — a log of completed actions plus a correlational
// ranking of which task TYPES tend to coincide with score gains across audit windows. This is
// directional correlation (not causal proof), surfaced below the task board.
function WorkCompletedSection({ businessId }: { businessId: number | null }) {
  const { data: actions } = useActionsTaken(businessId);
  const { data: impact } = useTaskImpact(businessId);

  const actionRows: ActionTaken[] = actions ?? [];
  const taskTypes = impact?.task_types ?? [];
  const windows = impact?.windows ?? 0;
  const unattributed = impact?.unattributed_windows ?? 0;
  const notEnough = windows < 2 || taskTypes.length === 0;

  // Nothing logged yet AND no impact signal -> a single friendly empty state.
  if (actionRows.length === 0 && notEnough) {
    return (
      <section className="mt-8">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">Work completed / what moved the needle</h3>
        <Card>
          <p className="text-sm text-slate-600">Mark tasks complete and run another audit to see which task types move your score.</p>
        </Card>
      </section>
    );
  }

  return (
    <section className="mt-8">
      <h3 className="mb-2 text-sm font-semibold text-slate-900">Work completed / what moved the needle</h3>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* (1) Actions taken — the completed-work log */}
        <Card padded={false}>
          <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-700">
            Actions taken ({actionRows.length})
          </div>
          {actionRows.length === 0 ? (
            <p className="px-4 py-3 text-xs text-slate-400">No completed actions logged yet.</p>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">What</th>
                    <th className="px-3 py-2">Area</th>
                    <th className="px-3 py-2 whitespace-nowrap">Done</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {actionRows.map((a) => (
                    <tr key={`${a.source}-${a.id}`} className="align-top">
                      <td className="px-3 py-2">
                        <div className="font-medium text-slate-800">{a.title || capLabel(a.capability)}</div>
                        <div className="text-[10px] text-slate-400">{a.source === "production_brief" ? "Brief produced" : capLabel(a.capability)}</div>
                      </td>
                      <td className="px-3 py-2 text-slate-600">{[a.area, a.platform].filter(Boolean).join(" · ") || "—"}</td>
                      <td className="px-3 py-2 whitespace-nowrap text-slate-600">{fmtDate(a.completed_on) || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* (2) Task-impact ranking — which task types correlate with score gains */}
        <Card padded={false}>
          <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-700">
            What moved the needle
          </div>
          {notEnough ? (
            <p className="px-4 py-3 text-xs text-slate-500">
              Mark tasks complete and run another audit to see which task types move your score.
            </p>
          ) : (
            <>
              <ul className="divide-y divide-slate-100">
                {taskTypes.map((t) => (
                  <li key={t.capability} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800">{capLabel(t.capability)}</div>
                      <div className="text-[11px] text-slate-400">
                        {t.actions} action{t.actions === 1 ? "" : "s"} · {t.confidence} confidence
                      </div>
                    </div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${t.gain_per_action >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                      {t.gain_per_action >= 0 ? "+" : ""}{t.gain_per_action.toFixed(1)} pts / action
                    </span>
                  </li>
                ))}
              </ul>
              <p className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-400">
                Correlation across {windows} audit window{windows === 1 ? "" : "s"}, not proof of cause.
                {unattributed > 0 && ` ${unattributed} audit window${unattributed === 1 ? "" : "s"} moved with no logged actions.`}
              </p>
            </>
          )}
        </Card>
      </div>
    </section>
  );
}

type ViewMode = "status" | "priority" | "mine" | "area" | "assignee" | "due";

// Due-date buckets for the "by due date" view (computed against the local 'today').
function dueBucket(target: string | null | undefined): { key: string; label: string; order: number } {
  if (!target) return { key: "none", label: "No due date", order: 4 };
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const d = new Date(target.slice(0, 10) + "T00:00:00");
  const days = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (days < 0) return { key: "overdue", label: "Overdue", order: 0 };
  if (days <= 7) return { key: "week", label: "Due this week", order: 1 };
  if (days <= 30) return { key: "month", label: "Due this month", order: 2 };
  return { key: "later", label: "Later", order: 3 };
}

// -----------------------------------------------------------------------------
// Roadmap (impact-ranked) helpers — the "what should I do today?" layer.
// impact_score = expected_points / effort; effort 1 = a quick win.
// -----------------------------------------------------------------------------

// Plain caption for the ranking basis ("based on what's worked for you" etc).
const BASIS_CAPTION: Record<string, string> = {
  "this client": "based on what's worked for you",
  "cross-client": "across clients",
  "industry baseline": "industry baseline",
};
const basisCaption = (b?: string | null) => (b ? BASIS_CAPTION[b] ?? b : "");

// Short "High impact · quick win" style label derived from impact_score + effort.
function impactLabel(item: RoadmapItem): string {
  const tier = item.impact_score >= 6 ? "High impact" : item.impact_score >= 3 ? "Solid impact" : "Steady impact";
  return item.effort <= 1 ? `${tier} · quick win` : tier;
}

// One "Today's focus" item: title + area/platform badge + impact + basis + one-click act.
function FocusItem({
  item,
  canEdit,
  onDone,
  onOpen,
}: {
  item: RoadmapItem;
  canEdit: boolean;
  onDone: () => void;
  onOpen: () => void;
}) {
  const platform = platformLabel(item.platform);
  const areaLbl = AREA_LABEL[areaKey(item.area)];
  return (
    <div className="rounded-xl bg-white/70 p-3 ring-1 ring-inset ring-indigo-100">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="indigo">{areaLbl}</Badge>
        {platform && <Badge tone="slate">{platform}</Badge>}
        <span className="text-[11px] font-semibold text-indigo-700">{impactLabel(item)}</span>
      </div>
      <div className="mt-1.5 text-sm font-bold text-slate-900">{item.title}</div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-slate-500">
        {item.expected_points > 0 && <span className="font-medium text-emerald-700">≈ +{item.expected_points} AI pts</span>}
        {basisCaption(item.basis) && <span className="text-slate-400">{basisCaption(item.basis)}</span>}
      </div>
      {item.why && <div className="mt-1 text-xs text-slate-600">{item.why}</div>}
      <div className="mt-2 flex items-center gap-2">
        {canEdit && (
          <Button size="sm" onClick={onDone}>
            ✓ Mark done
          </Button>
        )}
        <a href="#board" onClick={onOpen} className="text-xs font-medium text-indigo-600 hover:underline">
          Open task →
        </a>
      </div>
    </div>
  );
}

export default function WorkOrdersPage() {
  const { businessId, canEdit } = useBusiness();
  const { user } = useAuth();
  const { data, isLoading } = useWorkOrders(businessId);
  const { data: drafts } = useContentDrafts(businessId);
  const { data: assets } = useAssets(businessId);
  const { data: roadmap } = useRoadmap(businessId);
  const setStatus = useSetWorkOrderStatus(businessId);
  const [sortRoi, setSortRoi] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [view, setView] = useState<ViewMode>("status");
  // Fast = just "Today's focus" (3 tasks); Deep = the full board + why/impact detail.
  const [mode, setMode] = useState<"fast" | "deep">("deep");

  if (isLoading || !data) return <Spinner />;

  // latest draft + published asset per work order (drafts come back newest-first) -> the stitch
  const draftByWo = new Map<number, ContentDraft>();
  for (const d of drafts ?? []) if (d.work_order_id != null && !draftByWo.has(d.work_order_id)) draftByWo.set(d.work_order_id, d);
  const assetByWo = new Map<number, Asset>();
  for (const a of assets ?? []) if (a.work_order_id != null && !assetByWo.has(a.work_order_id)) assetByWo.set(a.work_order_id, a);

  // The managed board = promoted recommendations + manual tasks + anything already engaged.
  // Un-promoted, still-pending recommendations live on "Do this next", not here.
  const managed = data.filter((w) => w.planned || w.status !== "pending");
  const archivedCount = managed.filter((w) => w.superseded).length;
  const visible = showArchived ? managed : managed.filter((w) => !w.superseded);
  const sortRows = (rows: WorkOrder[]) =>
    sortRoi ? [...rows].sort((a, b) => (b.predicted_ai_points ?? -1) - (a.predicted_ai_points ?? -1)) : rows;
  const byStatus = (s: string) => sortRows(visible.filter((w) => w.status === s));
  const total = visible.length;
  const done = visible.filter((w) => w.status === "done" || w.status === "verified").length;
  const inProgress = visible.filter((w) => w.status === "in_progress").length;
  const donePct = total ? Math.round((done / total) * 100) : 0;
  const visibleColumns = COLUMNS.filter((s) => byStatus(s).length > 0 || ["pending", "in_progress", "done"].includes(s));

  const renderCard = (w: WorkOrder) => (
    <WorkOrderCard
      key={w.id}
      wo={w}
      businessId={businessId}
      canEdit={canEdit}
      onStatus={(st, completedOn) => setStatus.mutate({ woId: w.id, status: st, completed_on: completedOn })}
      draft={draftByWo.get(w.id)}
      asset={assetByWo.get(w.id)}
    />
  );

  // Grouping for the "by area" view. Each area is a labeled, collapsible section (default open).
  const areaGroups = (() => {
    const map = new Map<string, WorkOrder[]>();
    for (const w of visible) {
      const k = areaKey(w.area);
      (map.get(k) ?? map.set(k, []).get(k)!).push(w);
    }
    return AREA_ORDER.filter((k) => map.has(k)).map((k) => ({
      key: k,
      label: AREA_LABEL[k],
      items: sortRows(map.get(k)!),
    }));
  })();

  // Grouping for the assignee / due views.
  const assigneeGroups = (() => {
    const map = new Map<string, WorkOrder[]>();
    for (const w of visible) {
      const k = w.assignee?.trim() || "Unassigned";
      (map.get(k) ?? map.set(k, []).get(k)!).push(w);
    }
    return Array.from(map.entries())
      .sort((a, b) => (a[0] === "Unassigned" ? 1 : b[0] === "Unassigned" ? -1 : a[0].localeCompare(b[0])))
      .map(([name, items]) => ({ name, items: sortRows(items) }));
  })();
  const dueGroups = (() => {
    const map = new Map<string, { label: string; order: number; items: WorkOrder[] }>();
    for (const w of visible) {
      const b = dueBucket(w.target_date);
      if (!map.has(b.key)) map.set(b.key, { label: b.label, order: b.order, items: [] });
      map.get(b.key)!.items.push(w);
    }
    return Array.from(map.values())
      .sort((a, b) => a.order - b.order)
      .map((g) => ({
        ...g,
        items: [...g.items].sort((a, b) => (a.target_date ?? "9999").localeCompare(b.target_date ?? "9999")),
      }));
  })();

  // "My tasks" — only the work orders assigned to the signed-in user (FK assignee_user_id).
  const myTasks = user ? sortRows(visible.filter((w) => w.assignee_user_id === user.id)) : [];

  // Roadmap = impact-ranked open tasks (server-sorted best-first by impact_score). The top 3
  // power "Today's focus"; the full list drives the "By priority" board view. We pair each
  // roadmap item back to its WorkOrder (by wo_id) so the board can reuse WorkOrderCard.
  const woById = new Map<number, WorkOrder>(visible.map((w) => [w.id, w]));
  const roadmapItems = roadmap?.items ?? [];
  const focusItems = roadmapItems.slice(0, 3);
  // Open tasks in roadmap impact order — the WorkOrders that still have a card to render.
  const priorityPairs = roadmapItems
    .map((item) => ({ item, wo: woById.get(item.wo_id) }))
    .filter((p): p is { item: RoadmapItem; wo: WorkOrder } => !!p.wo);

  const TABS: { key: ViewMode; label: string }[] = [
    { key: "status", label: "By status" },
    { key: "priority", label: "By priority" },
    { key: "mine", label: "My tasks" },
    { key: "area", label: "By area" },
    { key: "assignee", label: "By assignee" },
    { key: "due", label: "By due date" },
  ];

  return (
    <div>
      <PageHeader
        title="Your task board"
        subtitle="The one place for what to do — your tasks, ranked by impact, assigned, scheduled, and tracked. Add more from “Do this next.”"
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />

      {/* Today's focus — the top 3 impact-ranked tasks ("what should I do today?"). Shown in
          both Fast and Deep mode; it's the heart of the hub. */}
      {focusItems.length > 0 && (
        <Card accent="info" className="mb-4 bg-indigo-50/40">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold tracking-tight text-slate-900">Today’s focus</h2>
              <p className="text-xs text-slate-500">Your highest-impact tasks right now — start here.</p>
            </div>
            {/* Fast / Deep — Fast shows only this card; Deep adds the full board + detail. */}
            <div className="inline-flex rounded-md border border-indigo-200 bg-white p-0.5">
              {(["fast", "deep"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`rounded px-2.5 py-1 text-xs font-medium capitalize ${mode === m ? "bg-indigo-600 text-white" : "text-indigo-700 hover:bg-indigo-50"}`}
                  title={m === "fast" ? "Just today’s 3 tasks" : "Today’s focus + the full board"}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            {focusItems.map((item) => (
              <FocusItem
                key={item.wo_id}
                item={item}
                canEdit={canEdit}
                onDone={() => setStatus.mutate({ woId: item.wo_id, status: "done", completed_on: todayISO() })}
                // "Open task" drops into Deep mode (the full board) and scrolls to it.
                onOpen={() => setMode("deep")}
              />
            ))}
          </div>
        </Card>
      )}

      {canEdit && mode === "deep" && <AddTask businessId={businessId} />}
      {total === 0 ? (
        <EmptyState
          title="No tasks yet"
          why="Improvement tasks are the recommendations you've chosen to manage."
          produces="Open “Do this next,” pick a recommendation, and click “Add to my tasks” to assign an owner, set dates, and track progress here."
          timing="You can also add an ad-hoc task above."
          cta={{ label: "Go to Do this next", href: "/next-steps" }}
        />
      ) : mode === "fast" ? (
        // Fast mode = clean, just the focus card above + a way into the full board.
        <Card className="text-sm text-slate-600">
          Showing your top {focusItems.length} {focusItems.length === 1 ? "task" : "tasks"}.{" "}
          <button onClick={() => setMode("deep")} className="font-medium text-indigo-600 hover:underline">
            Switch to Deep
          </button>{" "}
          to see the full board ({total} tasks) with the why and impact behind each one.
        </Card>
      ) : (
        <div id="board">
          {/* progress roll-up + view switcher */}
          <Card className="mb-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="inline-flex rounded-md border border-slate-200 p-0.5">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setView(t.key)}
                    className={`rounded px-2.5 py-1 text-xs font-medium ${view === t.key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1 text-xs text-slate-500">
                  <input type="checkbox" checked={sortRoi} onChange={(e) => setSortRoi(e.target.checked)} />
                  Highest impact first
                </label>
                {archivedCount > 0 && (
                  <label className="flex items-center gap-1 text-xs text-slate-500">
                    <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
                    Show archived ({archivedCount})
                  </label>
                )}
                <button
                  onClick={() => businessId && downloadCsv(`/businesses/${businessId}/work-orders/export`, "work_orders.csv")}
                  className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
                >
                  Export CSV
                </button>
                <span className="text-slate-500">{done} of {total} done · {inProgress} in progress</span>
              </div>
            </div>
            <ToneBar pct={donePct} tone="good" />
          </Card>

          {view === "status" && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {visibleColumns.map((s) => (
                <div key={s}>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-700">{LABEL[s]}</span>
                    <span className="text-xs text-slate-400">{byStatus(s).length}</span>
                  </div>
                  <div className="space-y-2">
                    {byStatus(s).map(renderCard)}
                    {byStatus(s).length === 0 && <p className="text-xs text-slate-300">—</p>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* By priority — ALL open tasks in roadmap impact order. Each row prefixes the
              WorkOrderCard with the impact math (impact_score / expected_points / effort /
              basis / why) so the ranking is transparent. */}
          {view === "priority" && (
            priorityPairs.length > 0 ? (
              <div className="space-y-3">
                {priorityPairs.map(({ item, wo }, i) => (
                  <div key={item.wo_id} className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
                    <Card className="bg-indigo-50/30">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">{i + 1}</span>
                        <span className="text-sm font-semibold text-slate-900">{impactLabel(item)}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Badge tone="indigo">Impact {item.impact_score.toFixed(1)}</Badge>
                        {item.expected_points > 0 && <Badge tone="emerald">≈ +{item.expected_points} pts</Badge>}
                        <Badge tone="slate">Effort {item.effort}</Badge>
                      </div>
                      <div className="mt-1.5 text-[11px] text-slate-500">{basisCaption(item.basis)}</div>
                      {item.why && <div className="mt-1.5 text-xs text-slate-600">{item.why}</div>}
                    </Card>
                    {renderCard(wo)}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No ranked tasks yet"
                why="The priority view ranks your open tasks by predicted impact (points ÷ effort)."
                produces="Run an audit so the engine can score each task, then they’ll appear here best-first."
              />
            )
          )}

          {view === "mine" && (
            myTasks.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{myTasks.map(renderCard)}</div>
            ) : (
              <EmptyState
                title="Nothing assigned to you yet"
                why="Tasks show up here once they're assigned to your account."
                produces="Open a task and use “assign / dates” to make yourself the owner, or switch to “By assignee” to see who has what."
              />
            )
          )}

          {view === "area" && (
            <div className="space-y-4">
              {areaGroups.map((g) => (
                <details key={g.key} open className="group rounded-2xl bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.12)] ring-1 ring-slate-900/[0.06]">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3">
                    <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                      <span className="text-slate-400 transition-transform group-open:rotate-90" aria-hidden>▸</span>
                      {g.label}
                    </span>
                    <span className="text-xs text-slate-400">{g.items.length}</span>
                  </summary>
                  <div className="border-t border-slate-100 px-4 py-3">
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{g.items.map(renderCard)}</div>
                  </div>
                </details>
              ))}
            </div>
          )}

          {view === "assignee" && (
            <div className="space-y-5">
              {assigneeGroups.map((g) => (
                <div key={g.name}>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-700">👤 {g.name}</span>
                    <span className="text-xs text-slate-400">{g.items.length}</span>
                  </div>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{g.items.map(renderCard)}</div>
                </div>
              ))}
            </div>
          )}

          {view === "due" && (
            <div className="space-y-5">
              {dueGroups.map((g) => (
                <div key={g.label}>
                  <div className="mb-2 flex items-center justify-between">
                    <span className={`text-sm font-semibold ${g.label === "Overdue" ? "text-rose-600" : "text-slate-700"}`}>{g.label}</span>
                    <span className="text-xs text-slate-400">{g.items.length}</span>
                  </div>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{g.items.map(renderCard)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Work completed + which task types correlate with score gains (below the board) */}
      <WorkCompletedSection businessId={businessId} />
    </div>
  );
}
