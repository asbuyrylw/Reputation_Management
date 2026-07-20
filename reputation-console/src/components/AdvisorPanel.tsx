"use client";

// Strategy Advisor panel — the PDCA "consultant in the app". Reads /advisor (goal + per-gap
// progress + impact predictions + recommended next content, all computed from real content-impact,
// GA/GSC/PageSpeed and keyword-demand data) and renders it as a plan-do-check-act view. Fully wired
// to live data; every number comes from the API, nothing is static.

import Link from "next/link";
import { useAdvisor } from "@/lib/hooks";
import { Card, Spinner } from "@/components/ui";
import { MarkdownBody } from "@/components/MarkdownBody";
import type { Advisor, AdvisorGap, AdvisorAction, PdcaStatus } from "@/lib/types";

// Each recommended action deep-links to exactly where the owner acts on it (the "dead text" fix).
function actionHref(a: AdvisorAction): string {
  switch (a.action) {
    case "publish": return "/content/drafts?status=approved";
    case "produce_more":
    case "new_content": return "/content/briefs";
    case "revise": return "/content/drafts";
    case "change_approach": return "/strategy";
    case "technical_fix":
    case "index_fix": return "/seo-overview";
    default: return "/strategy";
  }
}

const STATUS: Record<PdcaStatus, { label: string; tone: string; note: string }> = {
  on_track: { label: "On track", tone: "#0f9d63", note: "Content is moving the gaps toward the goal." },
  needs_action: { label: "Needs action", tone: "#c67c15", note: "Some gaps are stalled or regressing — act on the recommendations." },
  stalled: { label: "Stalled", tone: "#b1442f", note: "Most measured gaps aren't moving — change the approach." },
  awaiting_measurement: { label: "Awaiting measurement", tone: "#2563c9", note: "Content is live; the next full audit will measure its impact." },
  insufficient_data: { label: "Getting started", tone: "#5d6f77", note: "Publish content, then a follow-up audit measures the lift." },
};

const GAP_STATUS: Record<string, { label: string; tone: string }> = {
  not_published: { label: "Not published", tone: "#8698a0" },
  awaiting_measurement: { label: "Awaiting audit", tone: "#2563c9" },
  regressing: { label: "Regressing", tone: "#b1442f" },
  stalled: { label: "Stalled", tone: "#c67c15" },
  on_track: { label: "On track", tone: "#0f9d63" },
  gap_closing: { label: "Closing", tone: "#0a6b53" },
};

const ACTION_TONE: Record<number, string> = { 1: "#b1442f", 2: "#c67c15", 3: "#0d8a6b" };

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}
function align100(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(((v + 1) / 2) * 100)}`;
}

function Tile({ k, value, sub, color }: { k: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-[12px] border border-line bg-card px-3.5 py-3">
      <div className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[24px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}</div>
      {sub ? <div className="mt-1 text-[11.5px] text-ink-3">{sub}</div> : null}
    </div>
  );
}

function GapRow({ g }: { g: AdvisorGap }) {
  const st = GAP_STATUS[g.status] ?? { label: g.status, tone: "#5d6f77" };
  const pred = g.prediction;
  return (
    <tr className="border-t border-line align-top">
      <td className="py-2.5 pr-3">
        <div className="font-medium text-ink">{g.topic}</div>
        <div className="mt-0.5 font-mono text-[11px] text-ink-4">{(g.content_types || []).slice(0, 4).join(" · ") || "—"}</div>
      </td>
      <td className="py-2.5 pr-3">
        <span className="inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ color: st.tone, background: `${st.tone}18` }}>{st.label}</span>
      </td>
      <td className="py-2.5 pr-3 text-center font-mono tabular-nums text-[13px]">{g.published}/{g.pieces}</td>
      <td className="py-2.5 pr-3 text-center font-mono tabular-nums text-[13px]" style={{ color: g.gap_pct_closed != null ? "var(--ink)" : "var(--ink-4)" }}>{pct(g.gap_pct_closed)}</td>
      <td className="py-2.5 text-[12.5px] text-ink-3">
        {pred?.pieces_needed != null && pred.pieces_needed > 0
          ? <><b className="text-ink">~{pred.pieces_needed} more</b>{pred.eta_weeks ? ` · ~${pred.eta_weeks}w` : ""}<div className="text-[11.5px] text-ink-4">{pred.basis}</div></>
          : <span className="text-ink-4">{pred?.basis || "—"}</span>}
      </td>
    </tr>
  );
}

function ActionRow({ a }: { a: AdvisorAction }) {
  const tone = ACTION_TONE[a.priority] ?? "#5d6f77";
  return (
    <li className="border-t border-line first:border-t-0">
      <Link href={actionHref(a)} className="group flex gap-3 py-2.5 transition hover:bg-paper/60">
        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: tone }} />
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] text-ink"><span className="font-mono text-[11px] uppercase tracking-[0.04em]" style={{ color: tone }}>{a.action.replace(/_/g, " ")}</span> — {a.detail}</div>
          <div className="mt-0.5 text-[11.5px] text-ink-4">Expected: {a.expected_impact}</div>
        </div>
        <span className="mt-0.5 shrink-0 self-center text-ink-4 opacity-0 transition group-hover:opacity-100">→</span>
      </Link>
    </li>
  );
}

export function AdvisorPanel({ businessId, compact = false, framing = "strategy" }: { businessId: number | null; compact?: boolean; framing?: "strategy" | "content" }) {
  const { data, isLoading } = useAdvisor(businessId, !compact);
  if (isLoading) return <Card><div className="flex items-center gap-2 py-6 text-ink-3"><Spinner /> Analyzing content performance…</div></Card>;
  if (!data) return null;
  const d: Advisor = data;
  const s = STATUS[d.pdca_status] ?? STATUS.insufficient_data;
  const o = d.overall;
  // Same live data, two framings: on the Content hub it reads as a content-performance monitor
  // (what's our published content doing between audits?); elsewhere as the strategy PDCA advisor.
  const isContent = framing === "content";
  const eyebrow = isContent ? "Content Performance · measured between audits" : "Strategy Advisor · Plan · Do · Check · Act";
  const heading = isContent ? "Is our published content working?" : "Are we on track to the goal?";
  const fullHref = isContent ? "/content/performance" : "/strategy";
  const fullLabel = isContent ? "Content performance →" : "Full strategy →";

  return (
    <Card className="flex flex-col gap-5">
      {/* header + PDCA status */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-1 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-4">{eyebrow}</div>
          <h2 className="font-display text-[20px] font-semibold tracking-[-0.01em] text-ink">{heading}</h2>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-semibold" style={{ color: s.tone, background: `${s.tone}16` }}>
          <span className="h-2 w-2 rounded-full" style={{ background: s.tone }} />{s.label}
        </span>
      </div>

      {/* briefing — full width, markdown so bullet/number lists render on their own indented lines */}
      {d.briefing ? <MarkdownBody text={d.briefing} className="w-full text-[14px] leading-relaxed text-ink-2" /> : <p className="text-[13px] text-ink-4">{s.note}</p>}

      {/* the numbers */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Tile k="AI reputation" value={align100(d.goal.current_alignment)} sub={`goal ${align100(d.goal.target_alignment)} / 100`} color={s.tone} />
        <Tile k="Avg gap closed" value={pct(o.avg_gap_closed)} sub={`${o.gaps_measured}/${o.gaps_worked} measured`} />
        <Tile k="Content live" value={String(o.published_pieces)} sub="published pieces" />
        <Tile k="To reach goal" value={o.projected_weeks_to_goal ? `~${o.projected_weeks_to_goal}w` : (o.total_pieces_recommended ? `${o.total_pieces_recommended} pcs` : "—")} sub={o.projected_weeks_to_goal ? "at current pace" : "recommended next"} />
      </div>

      {/* compact (Dashboard): top next-move + link to the full advisor */}
      {compact && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
          {d.recommended_actions[0]
            ? <Link href={actionHref(d.recommended_actions[0])} className="min-w-0 flex-1 text-[13px] text-ink-2 hover:text-ink"><span className="font-semibold text-ink">Next:</span> {d.recommended_actions[0].detail}</Link>
            : <span className="text-[13px] text-ink-4">No action needed right now.</span>}
          <Link href={fullHref} className="shrink-0 text-[13px] font-semibold text-indigo hover:text-indigo-strong">{fullLabel}</Link>
        </div>
      )}

      {!compact && (
        <>
          {/* per-gap progress */}
          {d.gaps.length > 0 && (
            <div>
              <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Gap progress — is each gap's content working?</div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead><tr className="font-mono text-[10.5px] uppercase tracking-[0.05em] text-ink-4">
                    <th className="pb-1.5 pr-3 font-normal">Gap</th><th className="pb-1.5 pr-3 font-normal">Status</th>
                    <th className="pb-1.5 pr-3 text-center font-normal">Live</th><th className="pb-1.5 pr-3 text-center font-normal">Closed</th>
                    <th className="pb-1.5 font-normal">Prediction — what's needed</th>
                  </tr></thead>
                  <tbody>{d.gaps.map((g) => <GapRow key={g.batch_id} g={g} />)}</tbody>
                </table>
              </div>
            </div>
          )}

          {/* recommended actions (ACT) */}
          {d.recommended_actions.length > 0 && (
            <div>
              <div className="mb-1 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Recommended next moves</div>
              <ul>{d.recommended_actions.map((a, i) => <ActionRow key={i} a={a} />)}</ul>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
