// A tinted callout for compliance / placeholder / attention notices in the content pipeline.
// `info` = amber (added disclosures, confirm accuracy), `bad` = red (blocking, e.g. unresolved
// placeholders), `good` = emerald. Replaces the bespoke `bg-amber-50`/`border-rose-200` blocks.

import type { ReactNode } from "react";

type NoticeTone = "info" | "bad" | "good";

const TONE: Record<NoticeTone, { box: string; head: string }> = {
  info: { box: "border-amber/30 bg-amber-bg", head: "text-amber" },
  bad: { box: "border-alert/30 bg-alert-bg", head: "text-alert" },
  good: { box: "border-good/30 bg-good-bg", head: "text-good" },
};

export function ComplianceNotice({
  tone = "info",
  title,
  children,
  className = "",
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const t = TONE[tone];
  return (
    <div className={`rounded-[12px] border ${t.box} p-2.5 text-xs ${className}`}>
      {title && <div className={`font-semibold ${t.head}`}>{title}</div>}
      {children && <div className={`${title ? "mt-1 " : ""}text-ink-2`}>{children}</div>}
    </div>
  );
}
