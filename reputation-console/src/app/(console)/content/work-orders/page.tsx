"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAddWorkOrder, useSetWorkOrderStatus, useWorkOrders } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, ToneBar } from "@/components/primitives";
import type { WorkOrder } from "@/lib/types";

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

function WorkOrderCard({ wo, canEdit, onStatus }: { wo: WorkOrder; canEdit: boolean; onStatus: (s: string) => void }) {
  const tool = TOOL_GUIDE[wo.capability ?? ""];
  const bullets = bulletize(wo.instruction || "");
  return (
    <Card className="p-3">
      {/* category (left) · phase above date (right) */}
      <div className="flex items-start justify-between gap-2">
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] font-medium text-gray-600">{capLabel(wo.capability)}</span>
        <div className="text-right">
          {wo.phase && <div className="text-[11px] font-medium text-gray-500">{wo.phase}</div>}
          {wo.target_date && <div className="text-[11px] text-gray-400">Due {fmtDate(wo.target_date)}</div>}
        </div>
      </div>

      {/* bold to-do heading */}
      <div className="mt-1.5 text-sm font-bold text-gray-900">{wo.title}</div>

      {/* instruction — bulleted when long */}
      {wo.instruction && (
        bullets ? (
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-gray-600">
            {bullets.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        ) : (
          <div className="mt-1 text-xs text-gray-600">{wo.instruction}</div>
        )
      )}

      {/* tool type + examples */}
      <div className="mt-1.5 text-[11px] text-gray-500">
        {tool ? (
          <span><span className="font-medium text-gray-600">{tool.type}</span> — e.g. {tool.examples.join(", ")}</span>
        ) : wo.recommended_tool ? (
          <span><span className="font-medium text-gray-600">Tool:</span> {wo.recommended_tool}</span>
        ) : null}
        {wo.assignee && <span> · Owner: {wo.assignee}</span>}
      </div>

      {wo.result_notes && <div className="mt-1 text-xs text-green-700">Result: {wo.result_notes}</div>}
      {canEdit && (
        <select
          value={wo.status}
          onChange={(e) => onStatus(e.target.value)}
          className="mt-2 w-full rounded border border-gray-200 px-2 py-1 text-xs"
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
        <button onClick={() => setOpen(true)} className="text-sm font-medium text-blue-600 hover:underline">
          + Add a task
        </button>
      ) : (
        <div className="space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title (e.g. Get 5 new Google reviews)"
            className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm" />
          <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="What to do (optional)"
            rows={2} className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm" />
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-gray-500">Due
              <input type="date" value={due} onChange={(e) => setDue(e.target.value)}
                className="ml-1 rounded-md border border-gray-300 px-2 py-1 text-sm" />
            </label>
            <button onClick={submit} disabled={add.isPending || !title.trim()}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50">
              {add.isPending ? "Adding…" : "Add task"}
            </button>
            <button onClick={() => setOpen(false)} className="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
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

  if (isLoading || !data) return <Spinner />;

  const byStatus = (s: string) => data.filter((w) => w.status === s);
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
              <span className="font-medium text-gray-700">Plan progress</span>
              <span className="text-gray-500">{done} of {total} done · {inProgress} in progress</span>
            </div>
            <ToneBar pct={donePct} tone="good" />
          </Card>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visibleColumns.map((s) => (
              <div key={s}>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-700">{LABEL[s]}</span>
                  <span className="text-xs text-gray-400">{byStatus(s).length}</span>
                </div>
                <div className="space-y-2">
                  {byStatus(s).map((w) => (
                    <WorkOrderCard
                      key={w.id}
                      wo={w}
                      canEdit={canEdit}
                      onStatus={(st) => setStatus.mutate({ woId: w.id, status: st })}
                    />
                  ))}
                  {byStatus(s).length === 0 && <p className="text-xs text-gray-300">—</p>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
