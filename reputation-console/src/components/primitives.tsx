"use client";

import { ReactNode, useState } from "react";
import Link from "next/link";
import { Card } from "./ui";
import { Term } from "./Term";
import {
  Tone,
  Severity,
  toneText,
  toneChip,
  toneBar,
  severityChip,
  severityDot,
  deltaTone,
} from "@/lib/uiTokens";

// ---------------------------------------------------------------------------
// MetricCard — the canonical metric. Always answers the owner's five questions:
// plain label · big value · good/bad tone · worded timeframed change · why it matters ·
// what to do. Replaces the old KpiStatCard (raw decimal delta + tiny gray hint).
// ---------------------------------------------------------------------------
export interface MetricCardProps {
  label: string;
  value: string;
  tone?: Tone;
  /** numeric change vs the prior period (worded with deltaSuffix) */
  delta?: number | null;
  /** unit + timeframe, e.g. "pts since last audit" */
  deltaSuffix?: string;
  goodDirection?: "up" | "down";
  whyItMatters?: string;
  action?: { label: string; href: string };
  /** glossary key — turns the label into a tooltip term */
  term?: string;
}

export function MetricCard({
  label,
  value,
  tone = "neutral",
  delta,
  deltaSuffix = "",
  goodDirection = "up",
  whyItMatters,
  action,
  term,
}: MetricCardProps) {
  let change: ReactNode = null;
  if (delta != null && Math.abs(delta) >= 0.005) {
    const t = deltaTone(delta, goodDirection);
    const up = delta > 0;
    const shown = Number.isInteger(delta) ? Math.abs(delta) : Math.abs(delta).toFixed(2);
    change = (
      <span className={`text-sm font-medium ${toneText[t]}`}>
        {up ? "▲" : "▼"} {up ? "+" : "−"}
        {shown} {deltaSuffix}
      </span>
    );
  }
  return (
    <Card>
      <div className="text-sm font-medium text-gray-500">
        {term ? <Term name={term}>{label}</Term> : label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <div className={`text-3xl font-semibold ${toneText[tone]}`}>{value}</div>
      </div>
      {change && <div className="mt-0.5">{change}</div>}
      {whyItMatters && <p className="mt-2 text-sm leading-snug text-gray-600">{whyItMatters}</p>}
      {action && (
        <Link href={action.href} className="mt-2 inline-block text-sm font-medium text-blue-600 hover:underline">
          {action.label} →
        </Link>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// DataSection — the progressive-disclosure replacement for DataBlocks. Shows a scored
// header + plain-English verdict + a few highlights; the long/raw detail sits behind a
// collapsed "See the full breakdown". Kills the wall-of-text on the strategic pages.
// ---------------------------------------------------------------------------
export interface Highlight {
  label: string;
  value: string;
  tone?: Tone;
}

export function DataSection({
  title,
  headline,
  severity = "low",
  highlights = [],
  defaultOpen = false,
  action,
  children,
  detailsLabel = "See the full breakdown",
}: {
  title: string;
  headline?: string;
  severity?: Severity;
  highlights?: Highlight[];
  defaultOpen?: boolean;
  action?: { label: string; href: string };
  children?: ReactNode;
  detailsLabel?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${severityDot[severity]}`} aria-hidden />
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        </div>
        {action && (
          <Link href={action.href} className="shrink-0 text-sm font-medium text-blue-600 hover:underline">
            {action.label} →
          </Link>
        )}
      </div>
      {headline && <p className="mt-2 text-sm leading-relaxed text-gray-700">{headline}</p>}
      {highlights.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {highlights.map((h, i) => (
            <span
              key={i}
              className={`rounded-lg border px-2.5 py-1 text-xs font-medium ${toneChip[h.tone ?? "neutral"]}`}
            >
              {h.label}: <span className="font-semibold">{h.value}</span>
            </span>
          ))}
        </div>
      )}
      {children && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="text-sm font-medium text-gray-500 hover:text-gray-800"
          >
            {open ? "▾ Hide details" : `▸ ${detailsLabel}`}
          </button>
          {open && <div className="mt-2 border-t border-gray-100 pt-3">{children}</div>}
        </div>
      )}
    </Card>
  );
}

// A thin progress bar in tone color (for "you are here -> goal" and rate bars).
export function ToneBar({ pct, tone = "neutral" }: { pct: number; tone?: Tone }) {
  const w = Math.max(0, Math.min(100, Math.round(pct)));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
      <div className={`h-full rounded-full transition-all ${toneBar[tone]}`} style={{ width: `${w}%` }} />
    </div>
  );
}

// One-line legend so the color code is never a mystery.
export function ToneLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-green-500" /> Good for your reputation</span>
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-rose-500" /> Working against you</span>
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-gray-400" /> Neutral</span>
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmt(d: Date): string {
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

// "Last audited Jun 14 · next recheck ~Jul 14" — answers "when do I recheck?" consistently.
export function Freshness({ asOf, cadenceDays = 30 }: { asOf?: string | null; cadenceDays?: number }) {
  if (!asOf) return null;
  const d = new Date(asOf);
  if (Number.isNaN(d.getTime())) return null;
  const next = new Date(d.getTime() + cadenceDays * 86400000);
  return (
    <span className="text-xs text-gray-500">
      Last audited {fmt(d)} · next recheck ~{fmt(next)}
    </span>
  );
}

// Instructive empty state — never a dead-end gray sentence.
export function EmptyState({
  title,
  why,
  produces,
  timing,
  cta,
}: {
  title: string;
  why: string;
  produces?: string;
  timing?: string;
  cta?: { label: string; href: string };
}) {
  return (
    <Card>
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      <p className="mt-1 text-sm text-gray-600">{why}</p>
      {produces && <p className="mt-1 text-sm text-gray-500">{produces}</p>}
      {timing && <p className="mt-1 text-xs text-gray-400">{timing}</p>}
      {cta && (
        <Link
          href={cta.href}
          className="mt-3 inline-block rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700"
        >
          {cta.label}
        </Link>
      )}
    </Card>
  );
}

// Small reusable severity chip.
export function SeverityChip({ severity, children }: { severity: Severity; children: ReactNode }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${severityChip[severity]}`}>
      {children}
    </span>
  );
}
