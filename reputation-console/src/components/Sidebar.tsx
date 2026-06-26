"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

// Nav grouped by the client's mental model (not the DB). Items flagged `soon`
// are wired in later phases. Structure follows the two visibility surfaces (AI vs
// Search) + strategy / content / monitoring / proof, so the flow reads top-to-bottom
// the way an owner thinks about the problem: understand -> diagnose -> plan ->
// execute -> watch -> prove.
//
// ROLE-BASED LABELS: the non-technical business OWNER (non-admin) sees plain-language
// labels; the OPERATOR / agency admin sees the precise terms they work in. `label` is
// the owner-facing string; `opLabel`/`opGroup` override it for admins (falling back to
// the owner label when absent). The STRUCTURE (grouping + ordering) is identical for
// both — only the wording changes — so there is one source of truth.
type NavItem = { href: string; label: string; opLabel?: string; soon?: boolean; billingGated?: boolean };
type NavGroup = { group: string; opGroup?: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    group: "Overview",
    items: [{ href: "/dashboard", label: "Dashboard" }],
  },
  {
    // Everything about what AI assistants say about you.
    group: "Where you stand with AI",
    opGroup: "AI Visibility",
    items: [
      { href: "/ai-overview", label: "AI overview" },
      { href: "/audits", label: "What AI says about you", opLabel: "Audits & AI answers" },
      { href: "/prompts", label: "Questions customers ask AI", opLabel: "Prompts & topics" },
      // /rankings is AI citations / share-of-voice (who AI quotes), NOT search position.
      { href: "/rankings", label: "Who AI quotes about you", opLabel: "AI citations" },
      // Moved from Search & SEO: this page benchmarks AI-answer share-of-voice (you vs.
      // rivals in what AI says), not Google rank, so it belongs with the AI surfaces.
      { href: "/competitors", label: "You vs. competitors in AI answers", opLabel: "Competitors (AI)" },
    ],
  },
  {
    // Traditional Google search visibility.
    group: "Where you stand on Google",
    opGroup: "Search & SEO",
    items: [
      { href: "/seo-overview", label: "Google overview", opLabel: "SEO overview" },
      // Real Google Search Console traffic — clicks, impressions, ranking (the measured proof).
      { href: "/search-performance", label: "Search traffic & clicks", opLabel: "Search Console" },
      // Local map-pack / organic rank is the headline concern for a local SMB, so it
      // leads; technical site health is the supporting detail.
      { href: "/local-seo", label: "Local map & search rankings", opLabel: "Local rankings" },
      { href: "/seo", label: "Website health", opLabel: "Site / technical SEO" },
    ],
  },
  {
    // What's wrong, what to fix, in what order, and when it pays off.
    group: "Your problems & plan",
    opGroup: "Strategy & Plan",
    items: [
      // Diagnosis precedes prescription.
      { href: "/gaps", label: "What's hurting you", opLabel: "Gaps" },
      { href: "/next-steps", label: "Do this next" },
      { href: "/content/work-orders", label: "Improvement tasks" },
      { href: "/timeline", label: "Time to your goal", opLabel: "Time to goal" },
    ],
  },
  {
    // The content production pipeline.
    group: "Getting it done",
    opGroup: "Content",
    items: [
      { href: "/content/briefs", label: "Content to produce" },
      { href: "/content/drafts", label: "Drafts to review", opLabel: "Content drafts" },
      { href: "/content/finalized", label: "Published content" },
      { href: "/content/outreach", label: "Outreach" },
    ],
  },
  {
    // Live signals that need a human's eyes (incidents first — higher severity).
    group: "Watch live",
    opGroup: "Monitor",
    items: [
      { href: "/notifications", label: "Needs your attention", opLabel: "Notifications" },
      { href: "/sustain/incidents", label: "Incidents" },
      { href: "/sustain/mentions", label: "Mentions" },
      { href: "/approvals", label: "Needs your approval", opLabel: "Approval queue" },
    ],
  },
  {
    // Did it work? — retrospective proof + the client deliverable.
    group: "Proof it's working",
    opGroup: "Proof & reports",
    items: [
      // Moved from Monitor: a retrospective ranking of which actions moved the score
      // (ROI evidence), not a live signal.
      { href: "/sustain/levers", label: "What's working" },
      { href: "/reports", label: "Reports" },
    ],
  },
  {
    group: "Settings",
    items: [
      { href: "/account", label: "Account & data" },
      // Billing is wired but hidden until the platform billing switch is on (the super-admin
      // always sees it so they can preview before flipping it on).
      { href: "/billing", label: "Billing", opLabel: "Billing & plans", billingGated: true },
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

export function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const path = usePathname();
  const { user } = useAuth();
  // Admins are the operator/agency persona (precise labels + Admin group); everyone else
  // is the client owner (plain-language labels). Same structure, role-specific wording.
  const isOperator = user?.role === "admin";
  const showBilling = !!(user?.billing_enabled || user?.is_super_admin);
  const groups = (isOperator ? [...NAV, ADMIN_GROUP] : NAV).map((g) => ({
    ...g,
    items: g.items.filter((it) => !it.billingGated || showBilling),
  }));
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-64 shrink-0 transform overflow-y-auto border-r border-slate-200/70 bg-white p-4 backdrop-blur-xl transition-transform lg:static lg:z-auto lg:translate-x-0 lg:bg-white/80 ${
        open ? "translate-x-0" : "-translate-x-full"
      }`}
    >
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
              {isOperator && g.opGroup ? g.opGroup : g.group}
            </div>
            <div className="mt-1.5 space-y-0.5">
              {g.items.map((it) => {
                const active = path === it.href;
                const label = isOperator && it.opLabel ? it.opLabel : it.label;
                return (
                  <Link
                    key={it.href}
                    href={it.soon ? "#" : it.href}
                    onClick={() => onClose?.()}
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
                      {label}
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
