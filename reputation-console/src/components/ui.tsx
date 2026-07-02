import { ButtonHTMLAttributes, forwardRef, InputHTMLAttributes, ReactNode } from "react";
import Link from "next/link";
import { Tone, toneAccentBar, toneBar, toneChip, toneDot, toneText } from "@/lib/uiTokens";

// ---------------------------------------------------------------------------
// Shared form/control primitives — Button / Input / Badge / Skeleton. These
// consolidate the dozens of ad-hoc inline button/input/chip styles scattered
// across pages into one place so every surface looks the same. Adopt them on
// new/touched surfaces; existing pages migrate opportunistically.
// ---------------------------------------------------------------------------

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 focus-visible:ring-indigo-500 disabled:hover:bg-indigo-600",
  secondary:
    "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 focus-visible:ring-indigo-500",
  ghost: "bg-transparent text-slate-700 hover:bg-slate-100 focus-visible:ring-indigo-500",
  danger: "bg-rose-600 text-white hover:bg-rose-700 focus-visible:ring-rose-500 disabled:hover:bg-rose-600",
};
const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1 text-xs",
  md: "px-3.5 py-2 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  type = "button",
  ...rest
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`relative inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70"
        />
      )}
      {/* keep the label (and width) stable while loading */}
      <span className={loading ? "opacity-90" : ""}>{children}</span>
    </button>
  );
}

// Text input matching the polished onboarding `inputCls`: rounded-lg, slate-300
// border, px-3 py-2, indigo focus ring. Forwards ref + all native input props.
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = "", ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={`w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 placeholder:text-slate-400 ${className}`}
        {...rest}
      />
    );
  },
);

// Small pill. `tone` maps to a fixed bg/text/ring combo so chips stop drifting.
export type BadgeTone = "emerald" | "amber" | "rose" | "slate" | "indigo";
const BADGE_TONES: Record<BadgeTone, string> = {
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  rose: "bg-rose-50 text-rose-700 ring-rose-200",
  slate: "bg-slate-100 text-slate-600 ring-slate-200",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
};
export function Badge({
  tone = "slate",
  children,
  className = "",
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${BADGE_TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

// animate-pulse placeholder block. Compose for richer loading layouts.
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} aria-hidden />;
}

// A Card-shaped loading placeholder: header line + a few body lines.
export function CardSkeleton({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <Card className={className}>
      <Skeleton className="h-5 w-1/3" />
      <div className="mt-4 space-y-2.5">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className={`h-3.5 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
        ))}
      </div>
    </Card>
  );
}

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
  id,
}: {
  children: ReactNode;
  className?: string;
  accent?: Tone;
  hover?: boolean;
  padded?: boolean;
  id?: string;
}) {
  return (
    <div
      id={id}
      className={`relative overflow-hidden rounded-[18px] border border-line bg-card ${padded ? "p-5" : ""} shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_16px_-6px_rgba(15,23,42,0.08)] ${
        hover ? "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_2px_4px_rgba(15,23,42,0.05),0_12px_32px_-10px_rgba(15,23,42,0.14)]" : ""
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
    <div className="mb-[18px]">
      {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
      <h1 className="font-display text-[28px] font-semibold leading-[1.05] tracking-[-0.02em] text-ink sm:text-[32px]">{title}</h1>
      {subtitle && <p className="mt-1.5 max-w-[560px] text-[15px] leading-relaxed text-ink-3">{subtitle}</p>}
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

// Canonical status chip — ONE geometry + the semantic Tone system for every small pill. Prefer
// this in new code. Badge (fixed color names) and SeverityChip (high/med/low scale) remain for
// their existing call sites but share this exact geometry so chips read consistently app-wide.
export function Chip({ tone = "neutral", children, className = "" }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${toneChip[tone]} ${className}`}>
      {children}
    </span>
  );
}

// Pill is retained as an alias of the canonical Chip so existing imports keep working.
export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <Chip tone={tone}>{children}</Chip>;
}
