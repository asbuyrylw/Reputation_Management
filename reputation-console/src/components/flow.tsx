"use client";

// Reusable building blocks for the "information-flow" page recipe every hub Overview follows:
//   Status (where you stand) -> What it means -> What we'll do -> How we'll know it's working.
// Keeps the front-facing read streamlined; deep detail lives behind DataSection / the hub tabs.

import Link from "next/link";
import { repBand, type RepTone } from "@/lib/repScore";
import { Card } from "./ui";

const BAND_TEXT: Record<RepTone, string> = {
  red: "text-rose-600",
  orange: "text-orange-600",
  gray: "text-slate-600",
  green: "text-emerald-600",
  emerald: "text-emerald-600",
};

// The lead: where you stand in one glance — big number + band + delta, with a one-line read slot.
export function StatusHeader({
  label,
  score,
  delta,
  deltaLabel = "vs last audit",
  read,
  action,
}: {
  label: string;
  score: number | null;
  delta?: number | null;
  deltaLabel?: string;
  read?: React.ReactNode;
  action?: { label: string; href: string };
}) {
  const band = repBand(score);
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-500">{label}</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className={`text-5xl font-bold leading-none tracking-tight ${BAND_TEXT[band.tone]}`}>{score ?? "—"}</span>
            <span className="text-sm font-medium text-slate-400">/100</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{band.label}</span>
            {delta != null && Math.abs(delta) >= 0.5 && (
              <span className={`text-sm font-semibold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                {delta >= 0 ? "▲ +" : "▼ "}{Math.abs(delta)} pts {deltaLabel}
              </span>
            )}
          </div>
          {read && <div className="mt-2 max-w-2xl">{read}</div>}
        </div>
        {action && (
          <Link href={action.href} className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
            {action.label} →
          </Link>
        )}
      </div>
    </Card>
  );
}

// A labeled flow step — the spine that makes a page read as a story, not a data dump.
export function FlowStep({
  label,
  hint,
  action,
  children,
}: {
  label: string;
  hint?: string;
  action?: { label: string; href: string };
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</div>
          {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
        </div>
        {action && (
          <Link href={action.href} className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
            {action.label} →
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

// Top prioritized actions (numbered, linked) — the "what we'll do" content.
export function NextActions({ items }: { items: { title: string; note?: string | null; href: string }[] }) {
  if (items.length === 0) {
    return (
      <Card>
        <p className="text-sm text-slate-500">No actions queued right now — you&apos;re in good shape.</p>
      </Card>
    );
  }
  return (
    <Card>
      <ol className="space-y-3">
        {items.map((it, i) => (
          <li key={i} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <Link href={it.href} className="text-sm font-semibold text-slate-900 hover:text-indigo-600">{it.title}</Link>
              {it.note && <div className="mt-0.5 text-xs text-slate-500">{it.note}</div>}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
