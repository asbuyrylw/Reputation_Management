"use client";

// Strategy = the detailed PLAN. It takes the diagnosis from Gap Analysis and lays out, per area
// (AI Visibility / SEO / Search), exactly how each gap gets closed: the approach, the objective,
// the tasks doing it, and — for every piece of content — the concrete spec (type, title, keywords,
// length, readability, structure, where it publishes). Each task anchors here (id="wo-N") so the
// task board's "why" link lands right on it. All the "why this task" detail that used to clutter
// the task cards lives here now.

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useStrategy, useDashboard, useTimeline, useRoadmap } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";
import { EmptyState } from "@/components/primitives";
import { repScore, dashboardScore } from "@/lib/repScore";
import type { StrategyGroup, StrategySpec } from "@/lib/types";

type Json = Record<string, unknown>;

const fmtDate = (d?: string | null) => (d ? new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—");

const STATUS_LABEL: Record<string, string> = {
  pending: "To do", in_progress: "In progress", done: "Done", verified: "Verified", blocked: "Blocked", skipped: "Skipped",
};
const STATUS_TONE: Record<string, string> = {
  pending: "bg-slate-100 text-slate-600", in_progress: "bg-sky-50 text-sky-700",
  done: "bg-emerald-50 text-emerald-700", verified: "bg-emerald-50 text-emerald-700",
  blocked: "bg-rose-50 text-rose-700", skipped: "bg-slate-100 text-slate-400",
};

function Tile({ k, value, sub, color }: { k: string; value: string; sub: string; color?: string }) {
  return (
    <div className="rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[28px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}</div>
      <div className="mt-1.5 text-[12px] text-ink-3">{sub}</div>
    </div>
  );
}

// One content piece's production spec — the concrete "what to make": type, keywords, length,
// readability, structure, and where it publishes.
function SpecCard({ spec }: { spec: StrategySpec }) {
  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-050/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {spec.content_type && <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-strong">{spec.content_type.replace(/_/g, " ")}</span>}
        <span className="text-[11px] text-ink-4">Publishes to: <span className="font-medium text-ink-3">{spec.publish_to}</span></span>
      </div>
      <div className="mt-1 text-sm font-semibold text-ink">{spec.title}</div>
      <dl className="mt-1.5 space-y-0.5 text-[11.5px] text-ink-2">
        {spec.keywords.length > 0 && (
          <div><span className="font-semibold text-ink-3">Keywords:</span> {spec.keywords.join(", ")}</div>
        )}
        <div className="flex flex-wrap gap-x-4">
          {spec.word_count_target != null && <span><span className="font-semibold text-ink-3">Length:</span> ~{spec.word_count_target} words</span>}
          {spec.readability_target && <span><span className="font-semibold text-ink-3">Readability:</span> {spec.readability_target}</span>}
        </div>
        {spec.structure && <div><span className="font-semibold text-ink-3">Structure:</span> {spec.structure}</div>}
        {spec.objective && <div><span className="font-semibold text-emerald-700">Objective:</span> {spec.objective}</div>}
      </dl>
    </div>
  );
}

// One gap and how we close it: the approach, the objective, the tasks (each anchored so the task
// board can deep-link to it), and the content specs.
function GroupCard({ group }: { group: StrategyGroup }) {
  return (
    <Card className="border-l-[3px] border-l-indigo-300">
      <div className="text-sm font-bold text-ink">{group.title}</div>
      {group.approach && (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-indigo-strong">How we&apos;ll close it</div>
          <p className="mt-0.5 text-sm leading-relaxed text-ink-2">{group.approach}</p>
        </div>
      )}
      {group.why && (
        <div className="mt-1.5 text-[12.5px] text-ink-3"><span className="font-semibold text-emerald-700">Why it matters:</span> {group.why}</div>
      )}

      {/* the content to produce for this gap */}
      {group.specs.length > 0 && (
        <div className="mt-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-4">Content to produce ({group.specs.length})</div>
          <div className="space-y-2">
            {group.specs.map((s) => <SpecCard key={s.wo_id} spec={s} />)}
          </div>
        </div>
      )}

      {/* the tasks that carry this out — each anchored for the task board's "why" deep-link */}
      {group.tasks.length > 0 && (
        <div className="mt-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-4">Tasks ({group.tasks.length})</div>
          <ul className="space-y-1.5">
            {group.tasks.map((t) => (
              <li key={t.id} id={`wo-${t.id}`} className="scroll-mt-24 rounded-md border border-line px-2.5 py-1.5 target:ring-2 target:ring-indigo-400">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[13px] font-medium text-ink-2">{t.title}</span>
                  <div className="flex items-center gap-2">
                    {t.predicted_ai_points != null && t.predicted_ai_points > 0 && (
                      <span className="font-mono text-[11px] font-semibold text-emerald-700">+{t.predicted_ai_points.toFixed(1)}</span>
                    )}
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_TONE[t.status] ?? "bg-slate-100 text-slate-600"}`}>{STATUS_LABEL[t.status] ?? t.status}</span>
                  </div>
                </div>
                {t.instruction && <div className="mt-0.5 text-[12px] leading-relaxed text-ink-3">{t.instruction}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Link href="/content/work-orders" className="mt-2 inline-block text-[11.5px] font-semibold text-indigo-600 hover:underline">Manage these on the task board →</Link>
    </Card>
  );
}

export default function StrategyPage() {
  const { businessId, businesses, loading } = useBusiness();
  const { data: strat, isLoading: stratLoading } = useStrategy(businessId);
  const { data: dash, isLoading: dashLoading } = useDashboard(businessId);
  const { data: timeline } = useTimeline(businessId);
  const { data: roadmap } = useRoadmap(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Strategy" title="Your plan" />
        <EmptyState title="No plan yet" why="Set up a business and run an audit to build your gaps + plan." cta={{ label: "Set up a business", href: "/onboarding" }} />
      </div>
    );
  }
  if (dashLoading || stratLoading) return <Spinner />;

  const summary = strat?.summary || "";
  const sections = strat?.sections ?? [];
  const totalGroups = sections.reduce((a, s) => a + s.groups.length, 0);
  const allTasks = sections.flatMap((s) => s.groups.flatMap((g) => g.tasks));
  const openTasks = allTasks.length;
  const scoreLift = Math.round(allTasks.reduce((a, t) => a + (t.predicted_ai_points ?? 0), 0));
  const todaysFocus = (roadmap?.items ?? []).slice(0, 5);

  const score = dash?.series ? dashboardScore(dash.series).score : null;
  const goalScore = repScore((timeline as Json | undefined)?.dominance_target as number);
  const exp = ((timeline as Json | undefined)?.projection as Json | undefined)?.expected as Json | undefined;
  const aiDate = exp?.target_date as string | undefined;
  const aiMonths = exp?.months as number | undefined;
  const fillPct = score != null && goalScore ? Math.max(2, Math.min(100, Math.round((score / goalScore) * 100))) : 0;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader eyebrow="Strategy" title="Your plan to close the gaps" subtitle="Exactly how we close each gap — the approach, the content to produce (with keywords, length, and where it publishes), and the tasks that carry it out." />
        <Link href="/content/work-orders" className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(79,70,229,0.5)] hover:bg-indigo-strong">
          Open task board
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[13px] w-[13px]"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </Link>
      </div>

      {summary && (
        <div className="mb-5 rounded-[14px] border border-indigo-100 bg-indigo-050/60 p-4 text-sm leading-relaxed text-slate-700">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-indigo-strong">The situation &amp; strategy</div>
          <p>{summary}</p>
          <Link href="/gaps" className="mt-2 inline-flex items-center gap-1 text-[12.5px] font-semibold text-indigo hover:text-indigo-strong">See the full gap analysis →</Link>
        </div>
      )}

      {/* compact overview */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile k="Gaps to close" value={String(totalGroups)} sub="Across the three areas" color="var(--score)" />
        <Tile k="Open tasks" value={String(openTasks)} sub="Every gap is already a task" />
        <Tile k="Est. score lift" value={scoreLift > 0 ? `+${scoreLift}` : "—"} sub="If the plan is completed" color="var(--good)" />
        <Tile k="Time to goal" value={aiDate ? fmtDate(aiDate) : "—"} sub={aiMonths != null ? `~${aiMonths} months out` : "Run an audit to project"} color="var(--indigo)" />
      </div>

      {/* time-to-goal bar */}
      {score != null && goalScore != null && (
        <Card className="mb-6">
          <SecHead title="Time to goal" link={{ label: "Full projection", href: "/timeline" }} />
          <div className="relative mb-2 mt-2 h-2.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full" style={{ width: `${fillPct}%`, background: "linear-gradient(90deg,var(--score),#EBA46A)" }} />
          </div>
          <div className="flex justify-between font-mono text-[12px]">
            <span className="font-semibold text-score">Today · {score ?? "—"}</span>
            <span className="font-semibold text-indigo-strong">Goal · {goalScore ?? "—"}</span>
          </div>
        </Card>
      )}

      {/* today's focus — SAME ranked source (useRoadmap) as the task board, so it never shows
          something that isn't on the board */}
      {todaysFocus.length > 0 && (
        <div className="mb-6">
          <SecHead title="Today's focus" note="top of your task board, by impact" link={{ label: "All tasks", href: "/content/work-orders" }} />
          <TableContainer>
            <thead>
              <tr><Th className="w-[60%]">Task</Th><Th>Where</Th><Th>Impact</Th></tr>
            </thead>
            <tbody>
              {todaysFocus.map((w) => (
                <tr key={w.wo_id}>
                  <Td><Link href={`/content/work-orders#wo-${w.wo_id}`} className="font-semibold text-ink hover:text-indigo hover:underline">{w.title || "Untitled task"}</Link></Td>
                  <Td>{w.area ? <span className="rounded-[5px] border border-line-2 bg-paper px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-2">{w.area}</span> : "—"}</Td>
                  <Td>{w.expected_points ? <span className="font-mono font-semibold text-good">+{w.expected_points.toFixed(1)}</span> : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </TableContainer>
        </div>
      )}

      {/* ============ the detailed plan, by area ============ */}
      {totalGroups === 0 ? (
        <EmptyState title="No plan yet" why="Your plan is built from an audit of what AI and Google say about you." produces="Once an audit + gap analysis run, the approach and content for each gap appear here." timing="An audit takes a few minutes." cta={{ label: "Run an audit", href: "/runs" }} />
      ) : (
        <div className="space-y-8">
          {sections.filter((s) => s.groups.length > 0).map((s) => (
            <section key={s.key} id={s.key} className="scroll-mt-24">
              <div className="mb-2 border-b border-slate-200 pb-2">
                <h2 className="text-[15px] font-bold text-slate-800">{s.label} <span className="ml-1 font-mono text-[12px] font-normal text-slate-400">{s.groups.length} gap{s.groups.length === 1 ? "" : "s"}</span></h2>
                <p className="mt-0.5 text-[13px] text-ink-3">{s.narrative}</p>
              </div>
              <div className="space-y-3">
                {s.groups.map((g, i) => <GroupCard key={`${s.key}-${i}`} group={g} />)}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
