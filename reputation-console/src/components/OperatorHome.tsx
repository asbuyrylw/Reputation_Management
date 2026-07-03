"use client";

// The operator/staff home — a "Today / work queue" instead of the owner's outcomes dashboard.
// Surfaces everything waiting on the person doing the work: impact-ranked tasks, approvals,
// drafts to review, and new mentions. Each block links straight into the relevant hub.

import Link from "next/link";
import { useRoadmap, useApprovalQueue, useContentDrafts, useMentions } from "@/lib/hooks";
import { Card, PageHeader } from "@/components/ui";

const DRAFT_TERMINAL = new Set(["approved", "published", "rejected"]);

function QueuePeek({
  title,
  href,
  items,
  empty,
}: {
  title: string;
  href: string;
  items: { key: string; primary: string; secondary?: string | null }[];
  empty: string;
}) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-tight text-slate-900">{title}</h3>
        <Link href={href} className="text-xs font-medium text-indigo-600 hover:text-indigo-700">Open →</Link>
      </div>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((it) => (
            <li key={it.key} className="border-t border-slate-100 pt-2 first:border-0 first:pt-0">
              <div className="truncate text-sm text-slate-800">{it.primary}</div>
              {it.secondary && <div className="truncate text-[11px] text-slate-400">{it.secondary}</div>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function OperatorHome({ businessId, onViewOwner }: { businessId: number | null; onViewOwner?: () => void }) {
  const { data: roadmap } = useRoadmap(businessId);
  const { data: queue } = useApprovalQueue(businessId);
  const { data: drafts } = useContentDrafts(businessId);
  const { data: mentions } = useMentions(businessId);

  const tasks = roadmap?.items ?? [];
  const approvals = queue?.items ?? [];
  const reviewable = (drafts ?? []).filter((d) => !DRAFT_TERMINAL.has(d.status));
  const newMentions = (mentions ?? []).filter((m) => (m.status ?? "new") === "new");

  const stats = [
    { n: tasks.length, label: "tasks to do", href: "/content/work-orders" },
    { n: approvals.length, label: "approvals waiting", href: "/approvals" },
    { n: reviewable.length, label: "drafts to review", href: "/content/drafts" },
    { n: newMentions.length, label: "new mentions", href: "/sustain/mentions" },
  ];

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <PageHeader eyebrow="Today" title="Your work queue" subtitle="Everything waiting on you — tasks, approvals, drafts and mentions." />
        {onViewOwner && (
          <button
            onClick={onViewOwner}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            View owner dashboard →
          </button>
        )}
      </div>

      {/* quick counts */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <Link
            key={s.label}
            href={s.href}
            className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-900/5 transition hover:-translate-y-0.5"
          >
            <div className="text-3xl font-bold tabular-nums text-slate-900">{s.n}</div>
            <div className="mt-0.5 text-xs text-slate-500">{s.label}</div>
          </Link>
        ))}
      </div>

      {/* Today's focus — impact-ranked tasks */}
      <Card className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold tracking-tight text-slate-900">Today&apos;s focus</h2>
          <Link href="/content/work-orders" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">All tasks →</Link>
        </div>
        {tasks.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No open tasks right now — you&apos;re clear.</p>
        ) : (
          <ol className="mt-3 space-y-2.5">
            {tasks.slice(0, 6).map((t, i) => (
              <li key={t.wo_id} className="flex items-center gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-slate-900">{t.title}</div>
                  {t.why && <div className="truncate text-xs text-slate-500">{t.why}</div>}
                </div>
                <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium tabular-nums text-slate-600">+{Math.round(t.expected_points)} pts</span>
              </li>
            ))}
          </ol>
        )}
      </Card>

      {/* Needs you — approvals + drafts + mentions */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <QueuePeek
          title="Approvals waiting"
          href="/approvals"
          empty="Nothing to approve."
          items={approvals.slice(0, 4).map((a) => ({
            key: `${a.kind}-${a.id}`,
            primary: a.title || a.source || a.kind,
            secondary: a.surface === "third_party" ? "alert only — you post" : a.capability,
          }))}
        />
        <QueuePeek
          title="Drafts to review"
          href="/content/drafts"
          empty="No drafts waiting."
          items={reviewable.slice(0, 4).map((d) => ({
            key: String(d.id),
            primary: d.title || `Draft #${d.id}`,
            secondary: d.compliance_pass === false ? "needs fixes first" : "ready to review",
          }))}
        />
        <QueuePeek
          title="New mentions"
          href="/sustain/mentions"
          empty="No new mentions."
          items={newMentions.slice(0, 4).map((m) => ({
            key: String(m.id),
            primary: m.title || (m.body ? m.body.slice(0, 60) : null) || m.source || "Mention",
            secondary: m.sentiment || m.source,
          }))}
        />
      </div>
    </div>
  );
}
