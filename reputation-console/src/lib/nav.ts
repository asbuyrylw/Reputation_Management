// Single source of truth for the consolidated navigation: ~9 top-level HUBS, each with a set
// of sub-tabs. The Sidebar renders the hubs; HubTabs renders the active hub's tabs. Routes are
// UNCHANGED — a hub just groups existing pages — so nothing breaks and every page stays
// deep-linkable. Owner-facing `label` vs operator `opLabel` mirrors the old Sidebar convention.

export type HubTab = { href: string; label: string; opLabel?: string; billingGated?: boolean };
export type Hub = {
  key: string;
  label: string;
  opLabel?: string;
  href: string;        // where the sidebar entry points (the hub's Overview tab)
  adminOnly?: boolean;
  tabs: HubTab[];      // [] = no sub-nav (e.g. Dashboard)
};

export const HUBS: Hub[] = [
  { key: "dashboard", label: "Dashboard", href: "/dashboard", tabs: [] },

  {
    key: "ai", label: "Where you stand with AI", opLabel: "AI Visibility", href: "/ai-overview",
    tabs: [
      { href: "/ai-overview", label: "Overview" },
      { href: "/audits", label: "What AI says", opLabel: "Audits & answers" },
      { href: "/prompts", label: "Questions asked", opLabel: "Prompts" },
      { href: "/rankings", label: "Who AI quotes", opLabel: "AI citations" },
      { href: "/competitors", label: "Vs. competitors", opLabel: "Competitors" },
    ],
  },
  {
    key: "search", label: "Where you stand on Google", opLabel: "Search & SEO", href: "/seo-overview",
    tabs: [
      { href: "/seo-overview", label: "Overview" },
      { href: "/search-performance", label: "Search traffic", opLabel: "Search Console" },
      { href: "/local-seo", label: "Local rankings" },
      { href: "/seo", label: "Site health" },
    ],
  },
  // Gap Analysis and Strategy are DISTINCT but aligned: the gap analysis is "what's wrong, where,
  // impact" (analysis only); the strategy is "what we'll do about it -> tasks". Two hubs, no route
  // moves -- /gaps and /strategy already exist.
  {
    key: "gaps", label: "Your gaps", opLabel: "Gap Analysis", href: "/gaps", tabs: [],
  },
  {
    key: "plan", label: "Your strategy & plan", opLabel: "Strategy", href: "/strategy",
    tabs: [
      { href: "/strategy", label: "Overview" },
      { href: "/content/work-orders", label: "Tasks" },
      { href: "/timeline", label: "Time to goal" },
      { href: "/social", label: "Social" },
    ],
  },
  {
    key: "content", label: "Getting it done", opLabel: "Content", href: "/content",
    tabs: [
      { href: "/content", label: "Overview" },
      { href: "/content/briefs", label: "To produce" },
      { href: "/content/batches", label: "Batches & impact" },
      { href: "/content/drafts", label: "Drafts" },
      { href: "/content/finalized", label: "Published" },
      { href: "/approvals", label: "Approvals" },
      { href: "/content/outreach", label: "Outreach" },
    ],
  },
  {
    key: "monitor", label: "Watch live", opLabel: "Monitor", href: "/notifications",
    tabs: [
      { href: "/notifications", label: "Attention", opLabel: "Notifications" },
      { href: "/sustain/mentions", label: "Mentions" },
      { href: "/sustain/incidents", label: "Incidents" },
    ],
  },
  {
    key: "proof", label: "Proof it's working", opLabel: "Proof & reports", href: "/sustain/levers",
    tabs: [
      { href: "/sustain/levers", label: "What's working" },
      { href: "/reports", label: "Reports" },
    ],
  },
  {
    key: "settings", label: "Settings", href: "/runs",
    tabs: [
      { href: "/runs", label: "Runs & jobs" },
      { href: "/account", label: "Account & data" },
      { href: "/integrations", label: "Integrations" },
      { href: "/automation", label: "Automation" },
      { href: "/billing", label: "Billing", opLabel: "Billing & plans", billingGated: true },
      { href: "/glossary", label: "Glossary" },
    ],
  },
  {
    key: "admin", label: "Admin", href: "/admin/jobs", adminOnly: true,
    tabs: [
      { href: "/admin/jobs", label: "Run jobs" },
      { href: "/admin/users", label: "Users" },
      { href: "/admin/businesses", label: "Businesses" },
    ],
  },
];

// A path "belongs" to a tab when it's the tab href exactly or a sub-route of it (e.g.
// /audits/123 -> the Audits tab). We match exact tab hrefs (never a bare /content prefix) so
// /content/work-orders resolves to Plan while /content/briefs resolves to Content.
function pathMatchesTab(path: string, href: string): boolean {
  return path === href || path.startsWith(href + "/");
}

export function hubForPath(path: string): Hub | undefined {
  // Most-specific match wins GLOBALLY (longest matching tab href across all hubs), so the
  // /content split (work-orders → Plan, briefs → Content) is order-independent and collision-proof.
  // Ties keep the earliest hub (strict >). Tab-less hubs match on their own href.
  let bestHub: Hub | undefined;
  let bestLen = -1;
  for (const h of HUBS) {
    for (const t of h.tabs) {
      if (pathMatchesTab(path, t.href) && t.href.length > bestLen) {
        bestHub = h;
        bestLen = t.href.length;
      }
    }
    if (h.tabs.length === 0 && pathMatchesTab(path, h.href) && h.href.length > bestLen) {
      bestHub = h;
      bestLen = h.href.length;
    }
  }
  return bestHub;
}

export function activeTabHref(hub: Hub, path: string): string | undefined {
  // longest matching tab href wins (so /content/work-orders beats a shorter sibling)
  let best: string | undefined;
  for (const t of hub.tabs) {
    if (pathMatchesTab(path, t.href) && (!best || t.href.length > best.length)) best = t.href;
  }
  return best;
}
