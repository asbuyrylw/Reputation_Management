"use client";

import { useBusiness } from "@/lib/business";
import { useSetWorkOrderStatus, useWorkOrders } from "@/lib/hooks";
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

function WorkOrderCard({ wo, canEdit, onStatus }: { wo: WorkOrder; canEdit: boolean; onStatus: (s: string) => void }) {
  return (
    <Card className="p-3">
      <div className="flex items-center justify-between">
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] font-medium text-gray-600">{capLabel(wo.capability)}</span>
        {wo.target_date && <span className="text-[11px] text-gray-400">by {wo.target_date}</span>}
      </div>
      <div className="mt-1 text-sm font-medium text-gray-900">{wo.title}</div>
      {wo.instruction && <div className="mt-1 text-xs text-gray-600">{wo.instruction}</div>}
      <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-gray-400">
        {wo.recommended_tool && <span>Tool: {wo.recommended_tool}</span>}
        {wo.assignee && <span>Owner: {wo.assignee}</span>}
        {wo.phase && <span>{wo.phase}</span>}
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
        title="Your action plan"
        subtitle="Every task that improves your AI reputation, and where each one stands. Change a status to move it."
      />
      {total === 0 ? (
        <EmptyState
          title="No tasks yet"
          why="Your action plan is built from the gaps an audit finds."
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
