"use client";

// Unified Social home — the single place an owner manages their social presence. Pulls
// together what used to be fragmented across three surfaces: the per-platform social audit
// (was only on the task board), the "recommended social presence" block (was buried in Gaps),
// and the connect-your-accounts flow (lives in Integrations, linked from here).

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useWorkOrders } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SocialPresenceCard } from "@/components/SocialPresenceCard";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { WorkOrder } from "@/lib/types";

// Pretty platform names — mirrors SocialPresenceCard so the page reads consistently.
const PLATFORM_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
  reddit: "Reddit",
  gbp: "Google Business Profile",
};
const platformLabel = (p: string) =>
  PLATFORM_LABEL[p.toLowerCase()] ?? p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// Group the social work orders by platform (falling back to "Other" when none is set), so the
// task list reads the same way the presence card does — one platform at a time.
function groupByPlatform(wos: WorkOrder[]): { key: string; label: string; items: WorkOrder[] }[] {
  const map = new Map<string, { label: string; items: WorkOrder[] }>();
  for (const w of wos) {
    const raw = (w.platform || "other").trim();
    const key = raw.toLowerCase();
    if (!map.has(key)) map.set(key, { label: raw.toLowerCase() === "other" ? "Other" : platformLabel(raw), items: [] });
    map.get(key)!.items.push(w);
  }
  return Array.from(map.entries())
    .map(([key, g]) => ({ key, ...g }))
    .sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label));
}

// A compact task row (intentionally NOT the full WorkOrderCard) — title + status + a link to the
// task board where the work actually gets managed.
function TaskRow({ wo }: { wo: WorkOrder }) {
  const done = wo.status === "done" || wo.status === "verified";
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
      <div className="flex min-w-0 items-center gap-2">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${done ? "bg-emerald-500" : "bg-slate-300"}`} aria-hidden />
        <span className="truncate text-sm text-slate-700">{wo.title ?? "Untitled task"}</span>
        {done && <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">done</span>}
      </div>
      <Link href="/content/work-orders" className="shrink-0 text-[11px] font-medium text-indigo-600 hover:underline">
        Open task →
      </Link>
    </li>
  );
}

export default function SocialPage() {
  const { businessId, canEdit } = useBusiness();
  const { data: workOrders, isLoading } = useWorkOrders(businessId);

  // Only the social work orders, freshest-meaningful first (open tasks ahead of completed).
  const social = (workOrders ?? []).filter((w) => (w.area ?? "").toLowerCase() === "social" && !w.superseded);
  const open = social.filter((w) => w.status !== "done" && w.status !== "verified" && w.status !== "skipped");
  const groups = groupByPlatform(open.length > 0 ? open : social);

  return (
    <div>
      <PageHeader
        eyebrow="Social"
        title="Your social presence"
        subtitle="What each platform looks like and what to improve — plus the social tasks on your plan, all in one place."
      />
      <JobProgressBanner businessId={businessId} className="mb-4" />

      <div className="space-y-4">
        {/* a) the existing per-platform discovery/completeness card (encapsulates the audit) */}
        <SocialPresenceCard businessId={businessId} canEdit={canEdit} />

        {/* b) connecting still lives in Integrations — reachable from here */}
        <Card>
          <h3 className="text-sm font-semibold text-slate-900">Connect your accounts</h3>
          <p className="mt-1 text-sm text-slate-600">
            Link your social profiles so we can publish on your behalf and keep them consistent. Connecting and managing
            accounts lives in Integrations.
          </p>
          <Link
            href="/integrations"
            className="mt-3 inline-flex items-center rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
          >
            Connect or manage social accounts →
          </Link>
        </Card>

        {/* c) the social work orders, grouped by platform, compact, each linking to the task board */}
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Social tasks</h3>
              <p className="text-[11px] text-slate-400">
                The social work on your plan — grouped by platform. Manage them on the task board.
              </p>
            </div>
            {social.length > 0 && (
              <Link href="/content/work-orders" className="text-[11px] font-medium text-indigo-600 hover:underline">
                Open task board →
              </Link>
            )}
          </div>
          <div className="px-4 py-3">
            {isLoading ? (
              <p className="text-xs text-slate-400">Loading…</p>
            ) : social.length === 0 ? (
              <p className="text-xs text-slate-500">
                No social tasks yet. Run an audit above — your plan will add social work where it finds gaps.
              </p>
            ) : (
              <div className="space-y-4">
                {groups.map((g) => (
                  <div key={g.key}>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-700">{g.label}</span>
                      <span className="text-[11px] text-slate-400">{g.items.length}</span>
                    </div>
                    <ul className="mt-1 divide-y divide-slate-100">
                      {g.items.map((w) => (
                        <TaskRow key={w.id} wo={w} />
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
