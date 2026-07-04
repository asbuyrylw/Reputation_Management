"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useGapModel, useWorkOrders, useDashboard, useTimeline } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";
import { EmptyState } from "@/components/primitives";
import { repScore, dashboardScore } from "@/lib/repScore";
import type { WorkOrder } from "@/lib/types";

type Json = Record<string, unknown>;
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const fmtDate = (d?: string | null) => (d ? new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");

function Tile({ k, value, sub, color }: { k: string; value: string; sub: string; color?: string }) {
  return (
    <div className="rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[28px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}</div>
      <div className="mt-1.5 text-[12px] text-ink-3">{sub}</div>
    </div>
  );
}

function GapPill({ n, label, tone }: { n: number; label: string; tone: "bad" | "info" }) {
  const cls = tone === "bad" ? "bg-alert-bg text-alert" : "bg-indigo-050 text-indigo-strong";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] ${cls}`}>
      <b className="font-semibold">{n}</b> {label}
    </span>
  );
}

const focusLabel = (w: WorkOrder) =>
  w.why_helps_ai_rep && w.why_helps_seo ? "AI + SEO" : w.why_helps_ai_rep ? "AI" : w.why_helps_seo ? "SEO" : "—";

// Strategy & Plan hub landing — "your plan at a glance": the gaps holding you back, what to do,
// what's on your board, and when it adds up to your goal. Same info-flow as the AI / Search /
// Content overviews. All read-only; deep links into the hub tabs.
export default function StrategyOverviewPage() {
  const { businessId, businesses, loading } = useBusiness();
  const { data: gm } = useGapModel(businessId);
  const { data: workOrders } = useWorkOrders(businessId);
  const { data: dash, isLoading: dashLoading } = useDashboard(businessId);
  const { data: timeline } = useTimeline(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Strategy & Plan · Overview" title="Your plan at a glance" />
        <EmptyState title="No plan yet" why="Set up a business and run an audit to build your gaps + action plan." cta={{ label: "Set up a business", href: "/onboarding" }} />
      </div>
    );
  }
  if (dashLoading) return <Spinner />;

  const model = (gm?.model ?? {}) as Json;
  const cats = [
    { n: arr(model.weak_queries).length, label: "questions AI gets wrong", tone: "bad" as const },
    { n: arr(model.missing_owned_content).length, label: "pages to create", tone: "info" as const },
    { n: arr(model.thin_corroboration).length, label: "claims needing proof", tone: "info" as const },
    { n: arr(model.competitor_defense).length, label: "questions rivals win", tone: "bad" as const },
    { n: arr(model.local_seo_gaps).length, label: "local searches to win", tone: "info" as const },
    { n: arr(model.site_technical_gaps).length, label: "website fixes", tone: "info" as const },
    { n: arr(model.schema_gaps).length, label: "schema types to add", tone: "info" as const },
  ].filter((c) => c.n > 0);
  const gapsToClose = cats.reduce((a, c) => a + c.n, 0);

  const open = (workOrders ?? []).filter((w) => w.status !== "done" && w.status !== "verified" && w.status !== "cancelled" && !w.superseded);
  const onBoard = open.filter((w) => w.planned);
  const recommendations = open.filter((w) => !w.planned);
  const openTasks = onBoard.length || open.length;
  const scoreLift = Math.round(open.reduce((a, w) => a + (w.predicted_ai_points ?? 0), 0));
  const todaysFocus = open.slice().sort((a, b) => (b.predicted_ai_points ?? 0) - (a.predicted_ai_points ?? 0)).slice(0, 5);

  const score = dash?.series ? dashboardScore(dash.series).score : null;
  const goalScore = repScore((timeline as Json | undefined)?.dominance_target as number);
  const exp = ((timeline as Json | undefined)?.projection as Json | undefined)?.expected as Json | undefined;
  const aiDate = exp?.target_date as string | undefined;
  const aiMonths = exp?.months as number | undefined;
  const fillPct = score != null && goalScore ? Math.max(2, Math.min(100, Math.round((score / goalScore) * 100))) : 0;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader eyebrow="Strategy & Plan · Overview" title="Your plan at a glance" subtitle="Everything that turns your score into action — the gaps holding you back, what to do, what's on your board, and when it all adds up to your goal." />
        <Link href="/content/work-orders" className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] bg-indigo px-4 text-[13.5px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(79,70,229,0.5)] hover:bg-indigo-strong">
          Open task board
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[13px] w-[13px]"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </Link>
      </div>

      {/* KPI tiles */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile k="Open tasks" value={String(openTasks)} sub="In your active plan" />
        <Tile k="Recommendations" value={String(recommendations.length)} sub="Not yet on your board" color="var(--indigo)" />
        <Tile k="Gaps to close" value={String(gapsToClose)} sub={`Across ${cats.length} categor${cats.length === 1 ? "y" : "ies"}`} color="var(--score)" />
        <Tile k="Est. score lift" value={scoreLift > 0 ? `+${scoreLift}` : "—"} sub="If plan completed" color="var(--good)" />
      </div>

      {/* biggest gaps + time to goal */}
      <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <SecHead title="Your biggest gaps" link={{ label: "All gaps", href: "/gaps" }} />
          {cats.length === 0 ? (
            <p className="text-[13px] text-ink-4">No gaps modeled yet — run an audit + gap analysis.</p>
          ) : (
            <div className="flex flex-wrap gap-2.5">
              {cats.map((c) => <GapPill key={c.label} n={c.n} label={c.label} tone={c.tone} />)}
            </div>
          )}
        </Card>
        <Card>
          <SecHead title="Time to goal" link={{ label: "Projection", href: "/timeline" }} />
          <div className="mb-3 flex items-baseline gap-3">
            <span className="font-display text-[30px] font-semibold tracking-[-0.02em] text-ink">{fmtDate(aiDate)}</span>
            {aiMonths != null && <span className="rounded-full bg-paper px-2.5 py-0.5 font-mono text-[12px] text-ink-3 ring-1 ring-inset ring-line-2">~{aiMonths} mo</span>}
          </div>
          <div className="relative mb-2 h-2.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full" style={{ width: `${fillPct}%`, background: "linear-gradient(90deg,var(--score),#EBA46A)" }} />
          </div>
          <div className="flex justify-between font-mono text-[12px]">
            <span className="font-semibold text-score">Today · {score ?? "—"}</span>
            <span className="font-semibold text-indigo-strong">Goal · {goalScore ?? "—"}</span>
          </div>
        </Card>
      </div>

      {/* today's focus — top of the task board */}
      <SecHead title="Today's focus" note="top of your task board" link={{ label: "All tasks", href: "/content/work-orders" }} />
      {todaysFocus.length === 0 ? (
        <Card className="text-[13px] text-ink-4">No open tasks — add recommendations from your plan.</Card>
      ) : (
        <TableContainer>
          <thead>
            <tr><Th className="w-[46%]">Task</Th><Th>Where</Th><Th>Impact</Th><Th>Focus</Th></tr>
          </thead>
          <tbody>
            {todaysFocus.map((w) => (
              <tr key={w.id}>
                <Td><Link href={`/content/work-orders#wo-${w.id}`} className="font-semibold text-ink hover:text-indigo hover:underline">{w.title || "Untitled task"}</Link></Td>
                <Td>{w.area ? <span className="rounded-[5px] border border-line-2 bg-paper px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-2">{w.area}</span> : "—"}</Td>
                <Td>{w.predicted_ai_points != null ? <span className="font-mono font-semibold text-good">+{w.predicted_ai_points.toFixed(1)}</span> : "—"}</Td>
                <Td className="text-ink-3">{focusLabel(w)}</Td>
              </tr>
            ))}
          </tbody>
        </TableContainer>
      )}
    </div>
  );
}
