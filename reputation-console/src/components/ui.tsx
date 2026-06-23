import { ReactNode } from "react";
import Link from "next/link";
import { Tone, toneAccentBar, toneBar, toneChip, toneDot, toneText } from "@/lib/uiTokens";

// ---------------------------------------------------------------------------
// Card — the surface everything sits on. Soft ring + shadow + generous radius so it
// lifts off the tinted canvas. Optional `accent` paints a semantic edge stripe.
// ---------------------------------------------------------------------------
export function Card({
  children,
  className = "",
  accent,
  hover = false,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  accent?: Tone;
  hover?: boolean;
  padded?: boolean;
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl bg-white ${padded ? "p-5" : ""} shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.12)] ring-1 ring-slate-900/[0.06] ${
        hover ? "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_2px_4px_rgba(15,23,42,0.06),0_18px_36px_-18px_rgba(15,23,42,0.22)]" : ""
      } ${className}`}
    >
      {accent && <span aria-hidden className={`absolute inset-y-0 left-0 w-1.5 ${toneAccentBar[accent]}`} />}
      {children}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center p-10">
      <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-600" />
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  eyebrow,
}: {
  title: string;
  subtitle?: string;
  eyebrow?: string;
}) {
  return (
    <div className="mb-6">
      {eyebrow && (
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-600">{eyebrow}</div>
      )}
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-[1.7rem]">{title}</h1>
      {subtitle && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-500">{subtitle}</p>}
    </div>
  );
}

// A standalone KPI tile: tiny dot + uppercase label, big toned value, optional sub-line,
// a slim progress bar, and a one-line meaning. The building block of stat rows.
export function StatTile({
  label,
  value,
  tone = "neutral",
  sub,
  bar,
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  sub?: ReactNode;
  bar?: number | null;
  hint?: string;
}) {
  return (
    <Card accent={tone} hover className="flex h-full flex-col">
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${toneDot[tone]}`} aria-hidden />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      </div>
      <div className={`mt-2 text-[28px] font-bold leading-none tracking-tight ${toneText[tone]}`}>{value}</div>
      {sub && <div className="mt-1 text-xs font-medium text-slate-500">{sub}</div>}
      {bar != null && (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full rounded-full ${toneBar[tone]}`} style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} />
        </div>
      )}
      {hint && <p className="mt-auto pt-2 text-xs leading-snug text-slate-500">{hint}</p>}
    </Card>
  );
}

// A titled section surface with a consistent header (title/subtitle + optional action link)
// and optional accent stripe. Standardizes the "card with a heading" pattern across pages.
export function SectionCard({
  title,
  subtitle,
  action,
  accent,
  children,
  className = "",
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: { label: string; href: string };
  accent?: Tone;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <Card accent={accent} className={className}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold tracking-tight text-slate-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{subtitle}</p>}
        </div>
        {action && (
          <Link href={action.href} className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
            {action.label} →
          </Link>
        )}
      </div>
      {children && <div className="mt-4">{children}</div>}
    </Card>
  );
}

export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${toneChip[tone]}`}>
      {children}
    </span>
  );
}
