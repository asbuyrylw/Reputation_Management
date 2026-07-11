"use client";

// Strategy = the detailed PLAN. It takes the diagnosis from Gap Analysis and lays out, per area
// (AI Visibility / SEO / Search), exactly how each gap gets closed: the approach, the objective,
// the tasks doing it, and — for every piece of content — the concrete spec (type, title, keywords,
// length, readability, structure, where it publishes). Each task anchors here (id="wo-N") so the
// task board's "why" link lands right on it. All the "why this task" detail that used to clutter
// the task cards lives here now.

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useStrategy, useDashboard, useTimeline, useRoadmap } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { AdvisorPanel } from "@/components/AdvisorPanel";
import { SecHead } from "@/components/DashboardV2";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { EmptyState } from "@/components/primitives";
import { repScore, dashboardScore } from "@/lib/repScore";
import type { StrategyGroup } from "@/lib/types";

type Json = Record<string, unknown>;
type StratRow = StrategyGroup & { sectionLabel: string; _id: number };

const fmtDate = (d?: string | null) => (d ? new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—");

const STATUS_LABEL: Record<string, string> = {
  pending: "To do", in_progress: "In progress", done: "Done", verified: "Verified", blocked: "Blocked", skipped: "Skipped",
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
function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-[12.5px] font-medium ${active ? "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}>
      {children}
    </button>
  );
}

// The strategy TABLE columns: one row per gap, with how we'll close it, why, the tasks (linked to
// the board), and the content to produce (type + title + where it publishes + link to the content
// detail). Wrap columns hold the multi-item task/content lists. Sortable via headers.
const STRATEGY_COLUMNS: DataGridColumn<StratRow>[] = [
  { key: "gap", label: "Gap", width: 190, wrap: true, hideable: false, sortValue: (r) => r.title.toLowerCase(),
    render: (r) => <span className="text-[13px] font-semibold text-slate-800">{r.title}</span> },
  { key: "section", label: "Gap section", width: 118, sortValue: (r) => r.sectionLabel,
    render: (r) => <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600">{r.sectionLabel}</span> },
  { key: "how", label: "How we'll close it", width: 300, wrap: true,
    render: (r) => <span className="text-[12.5px] leading-relaxed text-slate-600">{r.approach || "—"}</span> },
  { key: "why", label: "Why it matters", width: 200, wrap: true,
    render: (r) => <span className="text-[12px] leading-relaxed text-slate-500">{r.why || "—"}</span> },
  { key: "tasks", label: "Tasks", width: 250, wrap: true, sortValue: (r) => r.tasks.length,
    render: (r) => r.tasks.length ? (
      <div className="space-y-1">
        {r.tasks.map((t) => (
          <div key={t.id} className="text-[12px] leading-snug">
            <Link href={`/content/work-orders#wo-${t.id}`} className="text-indigo-600 hover:underline">{t.title}</Link>
            <span className="text-[10px] text-slate-400"> · {STATUS_LABEL[t.status] ?? t.status}</span>
          </div>
        ))}
        <Link href="/content/work-orders" className="text-[10.5px] font-semibold text-indigo-500 hover:underline">Manage on task board →</Link>
      </div>
    ) : <span className="text-slate-400">—</span> },
  { key: "content", label: "Content to produce", width: 250, wrap: true, sortValue: (r) => r.specs.length,
    render: (r) => r.specs.length ? (
      <div className="space-y-1.5">
        {r.specs.map((s) => (
          <div key={s.wo_id} className="text-[12px] leading-snug">
            <span className="rounded bg-indigo-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-indigo-700">{(s.content_type || "").replace(/_/g, " ")}</span>{" "}
            <Link href="/content/briefs" className="font-medium text-slate-700 hover:text-indigo-600 hover:underline" title="Full spec (keywords, length, structure) in the content section">{s.title}</Link>
            <span className="text-[10px] text-slate-400"> → {s.publish_to}</span>
          </div>
        ))}
      </div>
    ) : <span className="text-slate-400">—</span> },
];

export default function StrategyPage() {
  const { businessId, businesses, loading } = useBusiness();
  const { data: strat, isLoading: stratLoading } = useStrategy(businessId);
  const { data: dash, isLoading: dashLoading } = useDashboard(businessId);
  const { data: timeline } = useTimeline(businessId);
  const { data: roadmap } = useRoadmap(businessId);
  const [secTab, setSecTab] = useState("all");
  const [ctFilter, setCtFilter] = useState("all");

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

      {/* PDCA advisor — is the plan working, and what's needed next (live, data-driven). */}
      <div className="mb-5 mt-1">
        <AdvisorPanel businessId={businessId} />
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

      {/* ============ the detailed plan: per-area report + a sortable/filterable gap table ============ */}
      {totalGroups === 0 ? (
        <EmptyState title="No plan yet" why="Your plan is built from an audit of what AI and Google say about you." produces="Once an audit + gap analysis run, the approach and content for each gap appear here." timing="An audit takes a few minutes." cta={{ label: "Run an audit", href: "/runs" }} />
      ) : (() => {
        // one row per gap, tagged with its section; filter by section tab + content type.
        const allRows: StratRow[] = sections
          .filter((s) => s.groups.length > 0)
          .flatMap((s) => s.groups.map((g) => ({ ...g, sectionLabel: s.label })))
          .map((g, i) => ({ ...g, _id: i }));
        const contentTypes = Array.from(new Set(allRows.flatMap((r) => r.specs.map((s) => (s.content_type || "").replace(/_/g, " "))).filter(Boolean))).sort();
        const activeSection = sections.find((s) => s.key === secTab);
        let rows = secTab === "all" ? allRows : allRows.filter((r) => activeSection && r.section === secTab);
        if (ctFilter !== "all") rows = rows.filter((r) => r.specs.some((s) => (s.content_type || "").replace(/_/g, " ") === ctFilter));
        return (
          <div>
            {/* per-area tabs */}
            <div className="mb-3 flex flex-wrap gap-1.5">
              <TabBtn active={secTab === "all"} onClick={() => setSecTab("all")}>All areas ({totalGroups})</TabBtn>
              {sections.filter((s) => s.groups.length > 0).map((s) => (
                <TabBtn key={s.key} active={secTab === s.key} onClick={() => setSecTab(s.key)}>{s.label} ({s.groups.length})</TabBtn>
              ))}
            </div>

            {/* the per-area strategy REPORT (the overall plan narrative for this area) */}
            {activeSection && (
              <div className="mb-4 rounded-[14px] border border-indigo-100 bg-indigo-050/50 p-4">
                <div className="text-[13px] font-bold text-slate-800">The plan for {activeSection.label}</div>
                <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{activeSection.narrative}</p>
              </div>
            )}

            {/* content-type filter + count */}
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="font-semibold uppercase tracking-wide text-slate-400">Filter</span>
              <label className="inline-flex items-center gap-1">Content type
                <select value={ctFilter} onChange={(e) => setCtFilter(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs capitalize">
                  <option value="all">All</option>
                  {contentTypes.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              {ctFilter !== "all" && <button type="button" onClick={() => setCtFilter("all")} className="font-medium text-indigo-600 hover:underline">Clear</button>}
              <span className="text-slate-400">· {rows.length} gap{rows.length === 1 ? "" : "s"} · drag column edges to resize, click headers to sort</span>
            </div>

            <DataGrid columns={STRATEGY_COLUMNS} rows={rows} getId={(r) => r._id} storageKey="strategy" emptyText="No gaps in this area." />
          </div>
        );
      })()}
    </div>
  );
}
