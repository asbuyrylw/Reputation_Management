"use client";

import { useBusiness } from "@/lib/business";
import { useSetWorkOrderStatus, useWorkOrders } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import type { WorkOrder } from "@/lib/types";

const COLUMNS = ["pending", "in_progress", "done", "verified", "blocked", "skipped"];
const LABEL: Record<string, string> = {
  pending: "Pending",
  in_progress: "In progress",
  done: "Done",
  verified: "Verified",
  blocked: "Blocked",
  skipped: "Skipped",
};

function WorkOrderCard({
  wo,
  canEdit,
  onStatus,
}: {
  wo: WorkOrder;
  canEdit: boolean;
  onStatus: (s: string) => void;
}) {
  return (
    <Card className="p-3">
      <div className="text-xs text-gray-400">
        {wo.wo_code}
        {wo.phase ? ` · ${wo.phase}` : ""}
      </div>
      <div className="mt-0.5 text-sm font-medium text-gray-900">{wo.title}</div>
      {wo.capability && (
        <div className="mt-1 text-xs text-gray-500">
          {wo.capability}
          {wo.assignee ? ` · ${wo.assignee}` : ""}
        </div>
      )}
      {canEdit && (
        <select
          value={wo.status}
          onChange={(e) => onStatus(e.target.value)}
          className="mt-2 w-full rounded border border-gray-200 px-2 py-1 text-xs"
        >
          {COLUMNS.map((s) => (
            <option key={s} value={s}>
              {LABEL[s]}
            </option>
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
  const visibleColumns = COLUMNS.filter(
    (s) => byStatus(s).length > 0 || ["pending", "in_progress", "done"].includes(s),
  );

  return (
    <div>
      <PageHeader
        title="Work orders"
        subtitle="The plan's tasks and where each stands. Move a task by changing its status."
      />
      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No work orders yet — they're created from the strategy plan.</p>
        </Card>
      ) : (
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
      )}
    </div>
  );
}
