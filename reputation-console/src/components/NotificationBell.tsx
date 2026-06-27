"use client";

// Per-user notifications bell for the console header. Shows the unread count as a badge;
// clicking opens a dropdown panel of recent notifications (title, body, severity color,
// relative time) with per-item "mark read" + a "mark all read" affordance. Notifications
// are already scoped to the current user server-side.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useNotifications, useMarkNotificationRead, useMarkAllNotificationsRead } from "@/lib/hooks";
import type { Notification } from "@/lib/types";

// "3m ago" / "2h ago" / "5d ago" — compact relative time, falls back to a date string.
function relTime(iso: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const secs = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

// Severity -> the small left dot color on each row.
const sevDot = (s: string) =>
  s === "critical" ? "bg-rose-500" : s === "warning" ? "bg-amber-500" : "bg-slate-300";

// Deep-link target for a notification. Task-assignment alerts (or any whose body
// references a task) take you straight to the task board; others have no link.
function notificationHref(n: Notification): string | null {
  if (n.kind === "task_assigned") return "/content/work-orders";
  if (n.body && /\btasks?\b/i.test(n.body)) return "/content/work-orders";
  return null;
}

function NotificationRow({
  n,
  canEdit,
  onRead,
  onNavigate,
}: {
  n: Notification;
  canEdit: boolean;
  onRead: (id: number) => void;
  onNavigate: () => void;
}) {
  const href = notificationHref(n);
  const body = (
    <div className="min-w-0 flex-1">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-semibold text-slate-900">{n.title}</div>
        {!n.read && canEdit && (
          <button
            // stop the click from following the row's deep-link / closing first
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onRead(n.id);
            }}
            className="shrink-0 text-[11px] font-medium text-indigo-600 hover:underline"
          >
            Mark read
          </button>
        )}
      </div>
      {n.body && <div className="mt-0.5 text-xs leading-snug text-slate-600">{n.body}</div>}
      <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
        {n.created_at && <span>{relTime(n.created_at)}</span>}
        {href && <span className="font-medium text-indigo-600">Open task board →</span>}
      </div>
    </div>
  );

  if (href) {
    return (
      <Link
        href={href}
        onClick={onNavigate}
        className={`flex gap-2.5 px-3 py-2.5 transition hover:bg-slate-50 ${n.read ? "opacity-60" : ""}`}
      >
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${sevDot(n.severity)}`} aria-hidden />
        {body}
      </Link>
    );
  }

  return (
    <div className={`flex gap-2.5 px-3 py-2.5 ${n.read ? "opacity-60" : ""}`}>
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${sevDot(n.severity)}`} aria-hidden />
      {body}
    </div>
  );
}

export function NotificationBell() {
  const { businessId, canEdit } = useBusiness();
  const { data } = useNotifications(businessId);
  const read = useMarkNotificationRead(businessId);
  const readAll = useMarkAllNotificationsRead(businessId);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unread = data?.unread ?? 0;
  const items = (data?.items ?? []).slice(0, 8);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ""}`}
        aria-expanded={open}
        className="relative rounded-md border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-100"
      >
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-slate-900/[0.08]">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-sm font-semibold text-slate-900">Notifications</span>
            {unread > 0 && canEdit && (
              <button
                onClick={() => readAll.mutate()}
                disabled={readAll.isPending}
                className="text-[11px] font-medium text-indigo-600 hover:underline disabled:opacity-50"
              >
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <div className="px-3 py-6 text-center text-sm text-slate-500">You&apos;re all caught up.</div>
          ) : (
            <div className="max-h-96 divide-y divide-slate-50 overflow-y-auto">
              {items.map((n) => (
                <NotificationRow
                  key={n.id}
                  n={n}
                  canEdit={canEdit}
                  onRead={(id) => read.mutate({ id })}
                  onNavigate={() => setOpen(false)}
                />
              ))}
            </div>
          )}
          <Link
            href="/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-slate-100 px-3 py-2 text-center text-xs font-medium text-indigo-600 hover:bg-slate-50"
          >
            View all notifications →
          </Link>
        </div>
      )}
    </div>
  );
}
