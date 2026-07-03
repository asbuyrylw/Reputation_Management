"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useWorkOrders, useAcceleration, usePromoteWorkOrder, useTeam } from "@/lib/hooks";
import { Card, PageHeader, Spinner, Chip, Button } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { EmptyState } from "@/components/primitives";
import type { WorkOrder } from "@/lib/types";

type Json = Record<string, unknown>;
type Lever = { lever?: string; weeks_saved_range?: { low?: number; high?: number }; note?: string };

const STAGE: Record<string, string> = {
  pending: "To do",
  in_progress: "In progress",
  done: "Done",
  verified: "Verified",
  blocked: "Blocked",
  skipped: "Skipped",
};
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

// UX-3: clicking a category pill at the top scrolls to that category's section.
function scrollToCat(key: string) {
  if (typeof document === "undefined") return;
  document.getElementById(`cat-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

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

function TaskRow({ w, canEdit, onPromote, onDismiss }: { w: WorkOrder; canEdit: boolean; onPromote: (w: WorkOrder) => void; onDismiss: (w: WorkOrder) => void }) {
  const why = w.why_helps_ai_rep || w.why_helps_seo;
  const isRec = w.rationale?.source === "recommendation";
  return (
    <li className="rounded-lg border border-line p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-ink-2">
          {w.title}
          {w.added_in_revision != null && w.added_in_revision > 1 && (
            <span className="rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-semibold text-indigo-strong">Rev {w.added_in_revision}</span>
          )}
        </div>
        <span className="shrink-0 text-[11px] text-ink-4">{STATUS_WORDS[w.status] ?? humanize(w.status)}</span>
      </div>
      {w.gap_source && (
        <div className="mt-0.5 text-[11px] text-ink-4">
          From: {w.gap_source}
          {isRec && <span className="ml-1 rounded bg-amber-bg px-1 py-0.5 text-amber">recommendation</span>}
        </div>
      )}
      {why && <div className="mt-0.5 text-xs text-ink-3">💡 {why}</div>}
      {/* Triage: save (promote onto the board) or dismiss. The vidIQ "swipe-to-save/dismiss"
          idea, rendered as two fast buttons. */}
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        {w.planned ? (
          <Link
            href="/content/work-orders"
            className="inline-flex items-center gap-1 rounded-full bg-good-bg px-2 py-0.5 text-[11px] font-semibold text-good hover:bg-emerald-100"
            title="This recommendation is being managed on your task board"
          >
            ✓ In tasks · {STAGE[w.status] ?? humanize(w.status)}
          </Link>
        ) : canEdit ? (
          <>
            <button
              onClick={() => onPromote(w)}
              className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-strong hover:bg-indigo-100"
            >
              + Add to tasks
            </button>
            {/* Dismiss is session-local UI only — there is no dismiss endpoint yet, so it just
                hides the recommendation until the page is reloaded. */}
            <button
              onClick={() => onDismiss(w)}
              className="rounded-full border border-line px-2 py-0.5 text-[11px] font-medium text-ink-3 hover:bg-line hover:text-ink-2"
              title="Hide this for now (returns on reload)"
            >
              Dismiss
            </button>
          </>
        ) : null}
      </div>
    </li>
  );
}

// Modal that captures owner + start/due + a first note, then promotes the recommendation onto
// the managed Improvement-tasks board.
function PromoteModal({ wo, businessId, onClose }: { wo: WorkOrder; businessId: number | null; onClose: () => void }) {
  const promote = usePromoteWorkOrder(businessId);
  const { data: team } = useTeam(businessId);
  const [assignee, setAssignee] = useState(wo.assignee ?? "");
  const [assigneeUserId, setAssigneeUserId] = useState(wo.assignee_user_id ? String(wo.assignee_user_id) : "");
  const [startDate, setStartDate] = useState((wo.start_date ?? "").slice(0, 10));
  const [dueDate, setDueDate] = useState((wo.target_date ?? "").slice(0, 10));
  const [note, setNote] = useState("");
  const hasTeam = (team?.length ?? 0) > 0;
  const submit = () =>
    promote.mutate(
      {
        woId: wo.id,
        assignee_user_id: hasTeam && assigneeUserId ? Number(assigneeUserId) : null,
        assignee: hasTeam ? undefined : assignee,
        start_date: startDate, target_date: dueDate, note,
      },
      { onSuccess: onClose },
    );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-card p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold text-ink">Add to Improvement tasks</h3>
        <p className="mt-1 text-sm text-ink-3">{wo.title}</p>
        <div className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-ink-3">
            Assign to
            {hasTeam ? (
              <select
                value={assigneeUserId}
                onChange={(e) => setAssigneeUserId(e.target.value)}
                className="mt-1 w-full rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2"
              >
                <option value="">Unassigned</option>
                {team!.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            ) : (
              <input
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                placeholder="Who's responsible?"
                className="mt-1 w-full rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2"
              />
            )}
          </label>
          <div className="flex gap-2">
            <label className="flex-1 text-xs font-medium text-ink-3">
              Start
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 w-full rounded-md border border-line-2 px-2 py-1.5 text-sm text-ink-2" />
            </label>
            <label className="flex-1 text-xs font-medium text-ink-3">
              Due
              <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
                className="mt-1 w-full rounded-md border border-line-2 px-2 py-1.5 text-sm text-ink-2" />
            </label>
          </div>
          <label className="block text-xs font-medium text-ink-3">
            First note (optional)
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="e.g. Start with the About page"
              className="mt-1 w-full rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2" />
          </label>
        </div>
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            onClick={submit}
            disabled={promote.isPending}
            size="sm"
          >
            {promote.isPending ? "Adding…" : "Add to tasks"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function NextStepsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data: workOrders, isLoading } = useWorkOrders(businessId);
  const { data: acc } = useAcceleration(businessId);
  const [promoting, setPromoting] = useState<WorkOrder | null>(null);
  // Session-local dismiss set. There's no dismiss endpoint yet, so dismissing only hides the
  // recommendation for this session (it returns on reload). Keyed by work-order id.
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());

  if (isLoading) return <Spinner />;

  // Recommendations feed: open tasks that haven't been archived (superseded) or session-dismissed.
  const open = (workOrders ?? []).filter(
    (w) => w.status !== "done" && w.status !== "verified" && !w.superseded && !dismissed.has(w.id),
  );
  const levers = ((acc as Json | undefined)?.levers_ranked_by_impact as Lever[] | undefined) ?? [];
  const grouped = CATS.map((c) => ({ ...c, items: open.filter((w) => categoryKey(w) === c.key) })).filter((c) => c.items.length > 0);
  const promotedCount = open.filter((w) => w.planned).length;
  const nothing = open.length === 0 && levers.length === 0;

  return (
    <div>
      <PageHeader
        title="Do this next"
        subtitle="Recommendations to improve your AI reputation and local ranking, grouped by type."
      />
      {/* Intake banner — this page is the inbox; the task board is the canonical hub. */}
      <Card className="mb-4 border-l-4 border-indigo-400 bg-indigo-050/40">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-ink-2">
            <span className="font-semibold text-ink">Recommendations</span> — add the ones you’ll do to your task board.
          </p>
          <Link href="/content/work-orders" className="text-sm font-semibold text-indigo hover:text-indigo-strong">
            View your task board →
          </Link>
        </div>
      </Card>
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
            <div className="flex flex-wrap items-center gap-2 text-sm text-ink-3">
              <span className="font-semibold text-ink">{open.length} recommendations</span>
              {promotedCount > 0 && (
                <Chip tone="good">{promotedCount} in tasks</Chip>
              )}
              {grouped.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  onClick={() => scrollToCat(c.key)}
                  className="rounded-full bg-line px-2 py-0.5 text-xs transition hover:bg-indigo-100 hover:text-indigo-strong"
                  title={`Jump to ${c.label}`}
                >
                  {c.emoji} {c.items.length} {c.label.split(" ")[0].toLowerCase()} <span aria-hidden className="text-ink-4">↓</span>
                </button>
              ))}
              <Link href="/content/work-orders" className="ml-auto text-sm font-medium text-indigo hover:text-indigo-strong">Manage my tasks →</Link>
            </div>
          </Card>

          {grouped.map((c) => (
            <div key={c.key} id={`cat-${c.key}`} className="scroll-mt-24">
            <Card>
              <SecHead
                title={`${c.emoji} ${c.label} (${c.items.length})`}
                link={
                  c.key === "outreach"
                    ? { label: "Find outreach targets →", href: "/content/outreach" }
                    : c.key === "seo"
                      ? { label: "Local rankings →", href: "/local-seo" }
                      : undefined
                }
              />
              <ul className="mt-3 space-y-2">
                {c.items.slice(0, 8).map((w) => (
                  <TaskRow
                    key={w.id}
                    w={w}
                    canEdit={canEdit}
                    onPromote={setPromoting}
                    onDismiss={(d) => setDismissed((prev) => new Set(prev).add(d.id))}
                  />
                ))}
              </ul>
              {c.items.length > 8 && <div className="mt-2 text-xs text-ink-4">+{c.items.length - 8} more on the task board</div>}
            </Card>
            </div>
          ))}

          {/* ways to go faster — link each lever to outreach */}
          {levers.length > 0 && (
            <Card>
              <SecHead title="⚡ Ways to go faster" link={{ label: "See projection →", href: "/timeline" }} />
              <p className="mt-0.5 text-xs text-ink-3">Outside actions (earned links, articles, reviews) that pull your timeline forward — find who to contact in Outreach.</p>
              <ul className="mt-3 space-y-1.5">
                {levers.slice(0, 5).map((l, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-sm">
                    <Link href="/content/outreach" className="text-ink-2 hover:text-indigo hover:underline">{humanize(l.lever)}</Link>
                    {l.weeks_saved_range && (
                      <Chip tone="good" className="shrink-0">
                        saves {l.weeks_saved_range.low}–{l.weeks_saved_range.high} wks
                      </Chip>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      {promoting && <PromoteModal wo={promoting} businessId={businessId} onClose={() => setPromoting(null)} />}
    </div>
  );
}
