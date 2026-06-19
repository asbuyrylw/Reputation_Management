"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

// Nav grouped by the client's mental model (not the DB). Items flagged `soon`
// are wired in later phases.
type NavItem = { href: string; label: string; soon?: boolean };
type NavGroup = { group: string; items: NavItem[] };

// Four top-level buckets (Analytics / Actions / Monitor / Settings); plain-language item
// labels kept so non-technical owners still read them at a glance.
const NAV: NavGroup[] = [
  {
    group: "Analytics",
    items: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/audits", label: "Audits & AI answers" },
      { href: "/prompts", label: "Prompts & topics" },
      { href: "/seo", label: "SEO / site" },
      { href: "/gaps", label: "Gaps" },
      { href: "/rankings", label: "Rankings" },
      { href: "/competitors", label: "Competitors" },
      { href: "/local-seo", label: "Local rankings" },
      { href: "/timeline", label: "Time to goal" },
    ],
  },
  {
    group: "Actions",
    items: [
      { href: "/next-steps", label: "Do this next" },
      { href: "/content/work-orders", label: "Improvement tasks" },
      { href: "/content/drafts", label: "Content drafts" },
      { href: "/content/finalized", label: "Published content" },
      { href: "/content/briefs", label: "Content to produce" },
      { href: "/content/outreach", label: "Outreach" },
    ],
  },
  {
    group: "Monitor",
    items: [
      { href: "/notifications", label: "Notifications" },
      { href: "/automation", label: "Automation" },
      { href: "/sustain/incidents", label: "Incidents" },
      { href: "/sustain/mentions", label: "Mentions" },
      { href: "/sustain/levers", label: "What's working" },
      { href: "/integrations", label: "Integrations" },
    ],
  },
  {
    group: "Settings",
    items: [
      { href: "/glossary", label: "Glossary" },
    ],
  },
];

const ADMIN_GROUP: NavGroup = {
  group: "Admin",
  items: [
    { href: "/admin/jobs", label: "Run jobs" },
    { href: "/admin/users", label: "Users" },
    { href: "/admin/businesses", label: "Businesses" },
  ],
};

export function Sidebar() {
  const path = usePathname();
  const { user } = useAuth();
  const groups = user?.role === "admin" ? [...NAV, ADMIN_GROUP] : NAV;
  return (
    <aside className="w-60 shrink-0 border-r border-gray-200 bg-white p-4">
      <div className="mb-6 px-2 text-lg font-semibold text-gray-900">Reputation Console</div>
      <nav className="space-y-5">
        {groups.map((g) => (
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
