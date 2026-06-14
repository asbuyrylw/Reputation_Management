"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Nav grouped by the client's mental model (not the DB). Items flagged `soon`
// are wired in later phases.
type NavItem = { href: string; label: string; soon?: boolean };
type NavGroup = { group: string; items: NavItem[] };

const NAV: NavGroup[] = [
  { group: "Overview", items: [{ href: "/dashboard", label: "Dashboard" }] },
  {
    group: "What AI Says",
    items: [
      { href: "/audits", label: "Audits & AI answers" },
      { href: "/seo", label: "SEO / site" },
      { href: "/gaps", label: "Gaps" },
    ],
  },
  {
    group: "What We're Doing",
    items: [
      { href: "/content/work-orders", label: "Work orders" },
      { href: "/content/drafts", label: "Content drafts" },
      { href: "/content/briefs", label: "Content to produce" },
      { href: "/content/outreach", label: "Outreach" },
    ],
  },
  {
    group: "Are We Winning",
    items: [
      { href: "/rankings", label: "Rankings" },
      { href: "/timeline", label: "Time to goal" },
    ],
  },
  {
    group: "Keeping It",
    items: [
      { href: "/sustain/incidents", label: "Incidents" },
      { href: "/sustain/mentions", label: "Mentions" },
      { href: "/sustain/levers", label: "What's working" },
    ],
  },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-60 shrink-0 border-r border-gray-200 bg-white p-4">
      <div className="mb-6 px-2 text-lg font-semibold text-gray-900">Reputation Console</div>
      <nav className="space-y-5">
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="px-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              {g.group}
            </div>
            <div className="mt-1 space-y-0.5">
              {g.items.map((it) => {
                const active = path === it.href;
                return (
                  <Link
                    key={it.href}
                    href={it.soon ? "#" : it.href}
                    className={`flex items-center justify-between rounded-md px-2 py-1.5 text-sm ${
                      active ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-100"
                    } ${it.soon ? "pointer-events-none opacity-40" : ""}`}
                  >
                    <span>{it.label}</span>
                    {it.soon && <span className="text-[10px] uppercase">soon</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
