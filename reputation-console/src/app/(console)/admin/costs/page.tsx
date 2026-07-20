"use client";

// Admin cost dashboard — the real, itemized spend of the whole Reputation Console system: what each
// service costs (audits, gap analysis, strategy, content by type + API, keyword research, DataForSEO,
// Serper, image/video/audio), per audit run, and per tenant. Live-wired to /admin/costs; every figure
// is a recorded est_cost_usd (exact where the provider returns it, e.g. DataForSEO).

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useCostDashboard } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import type { CostCategoryRow, CostContentRow, CostRunRow, CostBusinessRow, CostLineItem } from "@/lib/types";

const usd = (n: number) => n >= 1 ? `$${n.toFixed(2)}` : n >= 0.01 ? `$${n.toFixed(3)}` : n > 0 ? `$${n.toFixed(5)}` : "$0";
const CAT_TONE: Record<string, string> = {
  llm_audit: "#6d4bd0", llm_gap: "#2563c9", llm_strategy: "#0a6b53", llm_content: "#0d8a6b",
  search: "#c67c15", keyword_volume: "#b1442f", image: "#0f9d63", video: "#8b3fd0", audio: "#c67c15",
};
const DAYS = [7, 30, 90];

function Bar({ frac, tone }: { frac: number; tone: string }) {
  return <div className="h-1.5 w-full overflow-hidden rounded-full bg-paper"><div className="h-full rounded-full" style={{ width: `${Math.max(2, frac * 100)}%`, background: tone }} /></div>;
}

function CategoryTable({ rows, total }: { rows: CostCategoryRow[]; total: number }) {
  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.category} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
          <div className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: CAT_TONE[r.category] ?? "#8698a0" }} /><span className="text-[13.5px] font-medium text-ink">{r.label}</span></div>
          <div className="text-right"><span className="font-mono text-[13px] font-semibold text-ink tabular-nums">{usd(r.cost_usd)}</span><span className="ml-2 font-mono text-[11px] text-ink-4">{r.events}×{r.units != null ? ` · ${r.units} ${r.unit_label ?? ""}` : ""}</span></div>
          <div className="col-span-2"><Bar frac={total ? r.cost_usd / total : 0} tone={CAT_TONE[r.category] ?? "#8698a0"} /></div>
        </div>
      ))}
      {rows.length === 0 && <p className="py-3 text-center text-[13px] text-ink-4">No spend recorded in this window yet.</p>}
    </div>
  );
}

export default function AdminCostsPage() {
  const { user } = useAuth();
  const [days, setDays] = useState(30);
  const { data, isLoading } = useCostDashboard(days);
  const isAdmin = user?.role === "admin";

  if (!isAdmin) return <div><PageHeader eyebrow="Admin" title="Costs" /><Card><p className="py-4 text-[14px] text-ink-3">Admin access required.</p></Card></div>;
  if (isLoading || !data) return <Spinner />;
  const b = data.breakdown;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader eyebrow="Admin · Costs" title="What the system really costs" subtitle="Itemized spend across every service — LLM audits, gap analysis, strategy, content by type & API, keyword research, DataForSEO, Serper, image/video/audio — per run and per tenant." />
        <div className="flex shrink-0 gap-1">
          {DAYS.map((d) => (
            <button key={d} onClick={() => setDays(d)} className={`rounded-full px-3 py-1.5 text-[13px] font-semibold ${days === d ? "bg-ink text-white" : "border border-line bg-card text-ink-2 hover:bg-paper"}`}>{d}d</button>
          ))}
        </div>
      </div>

      {/* headline totals */}
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-[14px] border border-line bg-card p-4"><div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-4">Total spend · {days}d</div><div className="font-display text-[30px] font-semibold tracking-[-0.02em] text-ink">{usd(b.total_usd)}</div></div>
        <div className="rounded-[14px] border border-line bg-card p-4"><div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-4">Cost events</div><div className="font-display text-[30px] font-semibold tracking-[-0.02em] text-ink">{b.events.toLocaleString()}</div></div>
        <div className="rounded-[14px] border border-line bg-card p-4"><div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-4">Audit runs</div><div className="font-display text-[30px] font-semibold tracking-[-0.02em] text-ink">{b.by_run.length}</div></div>
        <div className="rounded-[14px] border border-line bg-card p-4"><div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-4">Avg / run</div><div className="font-display text-[30px] font-semibold tracking-[-0.02em] text-ink">{usd(b.by_run.length ? b.by_run.reduce((s, r) => s + r.cost_usd, 0) / b.by_run.length : 0)}</div></div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* by service category */}
        <Card>
          <h3 className="mb-3 text-base font-semibold tracking-tight text-slate-900">By service</h3>
          <CategoryTable rows={b.by_category} total={b.total_usd} />
        </Card>

        {/* by content type + API */}
        <Card>
          <h3 className="mb-1 text-base font-semibold tracking-tight text-slate-900">Content by type &amp; API</h3>
          <p className="mb-3 text-xs text-slate-500">Which content cost what, and which API produced it (Google/Gemini vs NotebookLM vs LLM).</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead><tr className="font-mono text-[10.5px] uppercase tracking-wider text-ink-4"><th className="pb-1.5 pr-3 font-normal">Type</th><th className="pb-1.5 pr-3 font-normal">API</th><th className="pb-1.5 text-right font-normal">Cost</th><th className="pb-1.5 pl-3 text-right font-normal">Count</th></tr></thead>
              <tbody>
                {b.by_content.map((r: CostContentRow, i) => (
                  <tr key={i} className="border-t border-line"><td className="py-2 pr-3 font-medium text-ink">{r.content_type}</td><td className="py-2 pr-3"><span className="rounded-full bg-paper px-2 py-0.5 font-mono text-[11px] text-ink-2">{r.api}</span></td><td className="py-2 text-right font-mono tabular-nums text-ink">{usd(r.cost_usd)}</td><td className="py-2 pl-3 text-right font-mono tabular-nums text-ink-3">{r.events}</td></tr>
                ))}
                {b.by_content.length === 0 && <tr><td colSpan={4} className="py-3 text-center text-ink-4">No content generated in this window.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>

        {/* cost per audit run */}
        <Card>
          <h3 className="mb-3 text-base font-semibold tracking-tight text-slate-900">Cost per audit run</h3>
          <div className="space-y-1.5">
            {b.by_run.slice(0, 12).map((r: CostRunRow) => (
              <div key={r.run_id} className="flex items-center justify-between border-b border-line py-1.5 text-[13px] last:border-0">
                <span className="font-mono text-ink-3">Run #{r.run_id}{r.started ? ` · ${new Date(r.started).toLocaleDateString()}` : ""}</span>
                <span className="font-mono font-semibold tabular-nums text-ink">{usd(r.cost_usd)} <span className="font-normal text-ink-4">({r.events})</span></span>
              </div>
            ))}
            {b.by_run.length === 0 && <p className="py-3 text-center text-[13px] text-ink-4">No runs recorded.</p>}
          </div>
        </Card>

        {/* per tenant */}
        <Card>
          <h3 className="mb-3 text-base font-semibold tracking-tight text-slate-900">By tenant</h3>
          <div className="space-y-1.5">
            {(data.by_business ?? []).slice(0, 15).map((r: CostBusinessRow) => (
              <div key={r.business_id} className="flex items-center justify-between border-b border-line py-1.5 text-[13px] last:border-0">
                <span className="font-medium text-ink">{r.name}</span>
                <span className="font-mono font-semibold tabular-nums text-ink">{usd(r.cost_usd)} <span className="font-normal text-ink-4">({r.events})</span></span>
              </div>
            ))}
            {(data.by_business ?? []).length === 0 && <p className="py-3 text-center text-[13px] text-ink-4">No tenant spend yet.</p>}
          </div>
        </Card>
      </div>

      {/* recent line items */}
      <Card className="mt-5">
        <h3 className="mb-3 text-base font-semibold tracking-tight text-slate-900">Recent line items</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[12.5px]">
            <thead><tr className="font-mono text-[10.5px] uppercase tracking-wider text-ink-4"><th className="pb-1.5 pr-3 font-normal">When</th><th className="pb-1.5 pr-3 font-normal">Service</th><th className="pb-1.5 pr-3 font-normal">Provider</th><th className="pb-1.5 pr-3 font-normal">Operation</th><th className="pb-1.5 pr-3 text-right font-normal">Units</th><th className="pb-1.5 text-right font-normal">Cost</th></tr></thead>
            <tbody>
              {data.recent.length === 0 && (
                <tr><td colSpan={6} className="py-4 text-center text-ink-4">No line items recorded in this window.</td></tr>
              )}
              {data.recent.map((r: CostLineItem, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-1.5 pr-3 font-mono text-ink-4">{r.at ? new Date(r.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                  <td className="py-1.5 pr-3"><span className="rounded-full px-2 py-0.5 font-mono text-[10.5px]" style={{ color: CAT_TONE[r.category ?? ""] ?? "#5d6f77", background: `${CAT_TONE[r.category ?? ""] ?? "#8698a0"}18` }}>{r.category}</span></td>
                  <td className="py-1.5 pr-3 text-ink-2">{r.provider}</td>
                  <td className="py-1.5 pr-3 text-ink-3">{r.operation}</td>
                  <td className="py-1.5 pr-3 text-right font-mono tabular-nums text-ink-4">{r.units != null ? `${r.units} ${r.unit_label ?? ""}` : "—"}</td>
                  <td className="py-1.5 text-right font-mono font-semibold tabular-nums text-ink">{usd(r.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
