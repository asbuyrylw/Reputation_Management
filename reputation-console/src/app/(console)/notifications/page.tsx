"use client";

import { useBusiness } from "@/lib/business";
import { useNotifications, useMarkNotificationRead, useMarkAllNotificationsRead } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

const sevCls = (s: string) =>
  s === "critical" ? "border-alert bg-alert-bg" : s === "warning" ? "border-amber bg-amber-bg" : "border-line bg-card";

export default function NotificationsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useNotifications(businessId);
  const read = useMarkNotificationRead(businessId);
  const readAll = useMarkAllNotificationsRead(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="Things that need your attention — score drops, new negative mentions, incidents, and drafts waiting."
      />
      {data.items.length === 0 ? (
        <EmptyState
          title="You're all caught up"
          why="We'll alert you here (and by email) when your score drops, a negative mention appears, an incident needs a reply, or drafts are waiting."
        />
      ) : (
        <>
          {data.unread > 0 && canEdit && (
            <div className="mb-3">
              <button onClick={() => readAll.mutate()} className="text-sm font-medium text-indigo hover:underline">
                Mark all read ({data.unread})
              </button>
            </div>
          )}
          <div className="space-y-2">
            {data.items.map((n) => (
              <Card key={n.id} className={`${sevCls(n.severity)} ${n.read ? "opacity-60" : ""}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-ink">{n.title}</div>
                    {n.body && <div className="mt-0.5 text-sm text-ink-3">{n.body}</div>}
                    {n.created_at && <div className="mt-1 text-xs text-ink-4">{new Date(n.created_at).toLocaleString()}</div>}
                  </div>
                  {!n.read && canEdit && (
                    <button onClick={() => read.mutate({ id: n.id })} className="shrink-0 text-xs font-medium text-indigo hover:underline">
                      Mark read
                    </button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
