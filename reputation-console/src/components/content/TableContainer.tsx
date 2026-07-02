// A horizontally-scrollable table shell so wide content tables (finalized assets, outreach
// directories/contacts) scroll inside their own box and never make the page body h-scroll.
// Provides the v2 header/cell/divider styling; callers supply <thead>/<tbody> rows.

import type { ReactNode } from "react";

export function TableContainer({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto rounded-[14px] border border-line ${className}`}>
      <table className="w-full min-w-[560px] border-collapse text-left text-[13px]">{children}</table>
    </div>
  );
}

// Header row — uppercase mono eyebrow labels on the paper tint.
export function Th({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <th className={`border-b border-line bg-paper px-3.5 py-2.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.06em] text-ink-4 ${className}`}>
      {children}
    </th>
  );
}

// Body cell — readable ink on the card surface, subtle row divider.
export function Td({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return <td className={`border-b border-line px-3.5 py-3 align-top text-ink-2 ${className}`}>{children}</td>;
}
