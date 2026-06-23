"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

// Nav grouped by the client's mental model (not the DB). Items flagged `soon`
// are wired in later phases. Structure follows the two visibility surfaces (AI vs
// Search) + strategy / content / monitoring / static outputs, so the flow reads
// top-to-bottom the way an owner thinks about the problem.
type NavItem = { href: string; label: string; soon?: boolean };
type NavGroup = { group: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    group: "Overview",
    items: [{ href: "/dashboard", label: "Dashboard" }],
  },
  {
    // Everything about what AI assistants say about you.
    group: "AI Visibility",
    items: [
      { href: "/ai-overview", label: "AI overview" },
      { href: "/audits", label: "Audits & AI answers" },
      { href: "/prompts", label: "Prompts & topics" },
      // Renamed from "Rankings": this page is AI citations / share-of-voice (who AI
      // quotes), NOT search position -- the old name collided with Search rankings.
      { href: "/rankings", label: "AI citations" },
    ],
  },
  {
    // Traditional search visibility.
    group: "Search & SEO",
    items: [
      { href: "/seo-overview", label: "SEO overview" },
      { href: "/seo", label: "Site / technical SEO" },
      { href: "/local-seo", label: "Local rankings" },
      { href: "/competitors", label: "Competitors" },
    ],
  },
  {
    // What to fix, in what order, and when it pays off.
    group: "Strategy & Plan",
    items: [
      { href: "/next-steps", label: "Do this next" },
      { href: "/gaps", label: "Gaps" },
      { href: "/content/work-orders", label: "Improvement tasks" },
      { href: "/timeline", label: "Time to goal" },
    ],
  },
  {
    // The content production pipeline.
    group: "Content",
    items: [
      { href: "/content/briefs", label: "Content to produce" },
      { href: "/content/drafts", label: "Content drafts" },
      { href: "/content/finalized", label: "Published content" },
      { href: "/content/outreach", label: "Outreach" },
    ],
  },
  {
    // Live signals that need a human's eyes.
    group: "Monitor",
    items: [
      { href: "/notifications", label: "Notifications" },
      { href: "/sustain/mentions", label: "Mentions" },
      { href: "/sustain/incidents", label: "Incidents" },
      { href: "/sustain/levers", label: "What's working" },
    ],
  },
  {
    group: "Reports",
    items: [{ href: "/reports", label: "Reports" }],
  },
  {
    group: "Settings",
    items: [
      { href: "/account", label: "Account & data" },
      { href: "/integrations", label: "Integrations" },
      { href: "/automation", label: "Automation" },
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
    <aside className="w-64 shrink-0 border-r border-slate-200/70 bg-white/80 p-4 backdrop-blur-xl">
      {/* Brand */}
      <div className="mb-7 flex items-center gap-2.5 px-1.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-linear-to-br from-indigo-500 to-violet-600 text-base font-bold text-white shadow-md shadow-indigo-500/25">
          R
        </div>
        <div className="leading-tight">
          <div className="text-[15px] font-bold tracking-tight text-slate-900">Reputation</div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-indigo-500">Console</div>
        </div>
      </div>
      <nav className="space-y-6">
        {groups.map((g) => (
          <div key={g.group}>
            <div className="px-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
              {g.group}
            </div>
            <div className="mt-1.5 space-y-0.5">
              {g.items.map((it) => {
                const active = path === it.href;
                return (
                  <Link
                    key={it.href}
                    href={it.soon ? "#" : it.href}
                    className={`group flex items-center justify-between rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
                      active
                        ? "bg-linear-to-r from-indigo-600 to-indigo-500 text-white shadow-sm shadow-indigo-500/20"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    } ${it.soon ? "pointer-events-none opacity-40" : ""}`}
                  >
                    <span className="flex items-center gap-2.5">
                      <span
                        className={`h-1.5 w-1.5 rounded-full transition-colors ${
                          active ? "bg-white" : "bg-slate-300 group-hover:bg-indigo-400"
                        }`}
                        aria-hidden
                      />
                      {it.label}
                    </span>
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
