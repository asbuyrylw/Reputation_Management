"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useWorkOrders, useGapModel, useAcceleration } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

type Json = Record<string, unknown>;
type Missing = { topic?: string; asset_type?: string; why?: string };
type Lever = { lever?: string; weeks_saved_range?: { low?: number; high?: number } };

const STATUS_WORDS: Record<string, string> = {
  pending: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
};
const humanize = (s?: string | null) => (s ? s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "");

export default function NextStepsPage() {
  const { businessId } = useBusiness();
  const { data: workOrders, isLoading } = useWorkOrders(businessId);
  const { data: gap } = useGapModel(businessId);
  const { data: acc } = useAcceleration(businessId);

  if (isLoading) return <Spinner />;

  const open = (workOrders ?? []).filter((w) => w.status !== "done" && w.status !== "verified");
  const ranked = [...open].sort((a, b) => (a.execution === "auto" ? 1 : 0) - (b.execution === "auto" ? 1 : 0));
  const pages = ((gap?.model as Json | undefined)?.missing_owned_content as Missing[] | undefined) ?? [];
  const levers = ((acc as Json | undefined)?.levers_ranked_by_impact as Lever[] | undefined) ?? [];

  const nothing = ranked.length === 0 && pages.length === 0 && levers.length === 0;

  return (
    <div>
      <PageHeader
        title="Do this next"
        subtitle="Your whole to-do list in one place — the tasks, the pages to create, and the fastest ways to move your score."
      />
      {nothing ? (
        <EmptyState
          title="Nothing to do yet"
          why="Your action list is built from an audit of what AI says about you."
          produces="After an audit, your prioritized tasks, pages to create, and speed-ups appear here."
          timing="An audit takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-6">
          {/* tasks */}
          <Card>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-900">Your tasks ({open.length})</h3>
              <Link href="/content/work-orders" className="text-sm font-medium text-indigo-600 hover:underline">Manage tasks →</Link>
            </div>
            {ranked.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No open tasks.</p>
            ) : (
              <ol className="mt-3 space-y-2">
                {ranked.slice(0, 10).map((w, i) => (
                  <li key={w.id} className="flex gap-2 text-sm">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">{i + 1}</span>
                    <div className="min-w-0">
                      <div className="font-medium text-slate-800">{w.title}</div>
                      {w.instruction && <div className="text-xs text-slate-500">{w.instruction}</div>}
                      <div className="text-[11px] text-slate-400">
                        {STATUS_WORDS[w.status] ?? humanize(w.status)}
                        {w.target_date ? ` · by ${w.target_date}` : ""}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {/* pages to create */}
          {pages.length > 0 && (
            <Card>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Pages to create ({pages.length})</h3>
                <Link href="/gaps" className="text-sm font-medium text-indigo-600 hover:underline">See details →</Link>
              </div>
              <ul className="mt-3 space-y-1.5">
                {pages.slice(0, 6).map((p, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-medium text-slate-800">{p.topic}</span>
                    {p.asset_type && <span className="text-xs text-slate-400"> · {p.asset_type}</span>}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {/* speed-ups */}
          {levers.length > 0 && (
            <Card>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Ways to go faster</h3>
                <Link href="/timeline" className="text-sm font-medium text-indigo-600 hover:underline">See projection →</Link>
              </div>
              <ul className="mt-3 space-y-1.5">
                {levers.slice(0, 4).map((l, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-slate-800">{humanize(l.lever)}</span>
                    {l.weeks_saved_range && (
                      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                        saves {l.weeks_saved_range.low}–{l.weeks_saved_range.high} wks
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
