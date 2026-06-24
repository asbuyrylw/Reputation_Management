"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useWorkOrders, useAcceleration } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import type { WorkOrder } from "@/lib/types";

type Json = Record<string, unknown>;
type Lever = { lever?: string; weeks_saved_range?: { low?: number; high?: number }; note?: string };

const STATUS_WORDS: Record<string, string> = { pending: "To do", in_progress: "In progress", blocked: "Blocked" };
const humanize = (s?: string | null) => (s ? s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "");

// Group every open task by the kind of work it is, so "Do this next" spans content, SEO,
// social, outreach, reviews and technical — not just a flat list of pages.
const CATS: { key: string; label: string; emoji: string }[] = [
  { key: "content", label: "Content to create", emoji: "✍️" },
  { key: "seo", label: "Local SEO (get to page 1)", emoji: "📍" },
  { key: "social", label: "Social media", emoji: "📣" },
  { key: "outreach", label: "Outreach & PR", emoji: "🤝" },
  { key: "reviews", label: "Reviews", emoji: "⭐" },
  { key: "technical", label: "Website / technical", emoji: "🛠️" },
  { key: "tracking", label: "Tracking", emoji: "📊" },
];

function categoryKey(w: WorkOrder): string {
  const cap = (w.capability ?? "").toLowerCase();
  const gs = (w.gap_source ?? "").toLowerCase();
  if (cap === "review_generation") return "reviews";
  if (cap === "social_publishing" || gs.includes("social")) return "social";
  if (cap.includes("press") || cap.includes("media_list") || cap.includes("link_building")) return "outreach";
  if (cap === "local_content_creation" || cap === "gbp_optimization" || gs.includes("local")) return "seo";
  if (cap === "schema_markup" || gs.includes("site crawl")) return "technical";
  if (cap === "ai_visibility_tracking") return "tracking";
  return "content";
}

function TaskRow({ w }: { w: WorkOrder }) {
  const why = w.why_helps_ai_rep || w.why_helps_seo;
  const isRec = w.rationale?.source === "recommendation";
  return (
    <li className="rounded-lg border border-slate-100 p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-slate-800">
          {w.title}
          {w.added_in_revision != null && w.added_in_revision > 1 && (
            <span className="rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-semibold text-indigo-700">Rev {w.added_in_revision}</span>
          )}
        </div>
        <span className="shrink-0 text-[11px] text-slate-400">{STATUS_WORDS[w.status] ?? humanize(w.status)}</span>
      </div>
      {w.gap_source && (
        <div className="mt-0.5 text-[11px] text-slate-400">
          From: {w.gap_source}
          {isRec && <span className="ml-1 rounded bg-amber-100 px-1 py-0.5 text-amber-700">recommendation</span>}
        </div>
      )}
      {why && <div className="mt-0.5 text-xs text-slate-500">💡 {why}</div>}
    </li>
  );
}

export default function NextStepsPage() {
  const { businessId } = useBusiness();
  const { data: workOrders, isLoading } = useWorkOrders(businessId);
  const { data: acc } = useAcceleration(businessId);

  if (isLoading) return <Spinner />;

  const open = (workOrders ?? []).filter((w) => w.status !== "done" && w.status !== "verified");
  const levers = ((acc as Json | undefined)?.levers_ranked_by_impact as Lever[] | undefined) ?? [];
  const grouped = CATS.map((c) => ({ ...c, items: open.filter((w) => categoryKey(w) === c.key) })).filter((c) => c.items.length > 0);
  const nothing = open.length === 0 && levers.length === 0;

  return (
    <div>
      <PageHeader
        title="Do this next"
        subtitle="Everything to improve your AI reputation and local ranking, grouped by type — content, SEO, social, outreach, reviews — and the fastest ways to move."
      />
      {nothing ? (
        <EmptyState
          title="Nothing to do yet"
          why="Your action list is built from an audit of what AI says about you."
          produces="After an audit, your prioritized tasks across content, SEO, social, and outreach appear here."
          timing="An audit takes a few minutes."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
              <span className="font-semibold text-slate-900">{open.length} open actions</span>
              {grouped.map((c) => (
                <span key={c.key} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">{c.emoji} {c.items.length} {c.label.split(" ")[0].toLowerCase()}</span>
              ))}
              <Link href="/content/work-orders" className="ml-auto text-sm font-medium text-indigo-600 hover:underline">Manage all tasks →</Link>
            </div>
          </Card>

          {grouped.map((c) => (
            <Card key={c.key}>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">{c.emoji} {c.label} ({c.items.length})</h3>
                {c.key === "outreach" && (
                  <Link href="/content/outreach" className="text-xs font-medium text-indigo-600 hover:underline">Find outreach targets →</Link>
                )}
                {c.key === "seo" && (
                  <Link href="/local-seo" className="text-xs font-medium text-indigo-600 hover:underline">Local rankings →</Link>
                )}
              </div>
              <ul className="mt-3 space-y-2">
                {c.items.slice(0, 8).map((w) => <TaskRow key={w.id} w={w} />)}
              </ul>
              {c.items.length > 8 && <div className="mt-2 text-xs text-slate-400">+{c.items.length - 8} more on the task board</div>}
            </Card>
          ))}

          {/* ways to go faster — link each lever to outreach */}
          {levers.length > 0 && (
            <Card>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">⚡ Ways to go faster</h3>
                <Link href="/timeline" className="text-sm font-medium text-indigo-600 hover:underline">See projection →</Link>
              </div>
              <p className="mt-0.5 text-xs text-slate-500">Outside actions (earned links, articles, reviews) that pull your timeline forward — find who to contact in Outreach.</p>
              <ul className="mt-3 space-y-1.5">
                {levers.slice(0, 5).map((l, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-sm">
                    <Link href="/content/outreach" className="text-slate-800 hover:text-indigo-600 hover:underline">{humanize(l.lever)}</Link>
                    {l.weeks_saved_range && (
                      <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
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
