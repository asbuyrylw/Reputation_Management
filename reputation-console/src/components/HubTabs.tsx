"use client";

// The hub sub-nav. Driven entirely by the current path: it finds which hub the route belongs
// to and renders that hub's tabs (underline style, premium + calm). Renders nothing on routes
// that aren't part of a multi-tab hub (e.g. /dashboard, /onboarding), so the layout can mount
// it unconditionally. Owner/operator labels + billing gating mirror the Sidebar.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { hubForPath, activeTabHref } from "@/lib/nav";

export function HubTabs() {
  const path = usePathname() || "";
  const { user } = useAuth();
  const isOperator = user?.role === "admin";
  const showBilling = !!(user?.billing_enabled || user?.is_super_admin);

  const hub = hubForPath(path);
  if (!hub) return null;
  const tabs = hub.tabs.filter((t) => !t.billingGated || showBilling);
  if (tabs.length < 2) return null; // no sub-nav worth showing

  const active = activeTabHref(hub, path);
  const hubLabel = isOperator && hub.opLabel ? hub.opLabel : hub.label;

  return (
    <div className="mb-6 border-b border-slate-200/80">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-500">{hubLabel}</div>
      <nav className="-mb-px mt-2 flex gap-1 overflow-x-auto" aria-label={hubLabel}>
        {tabs.map((t) => {
          const isActive = t.href === active;
          const label = isOperator && t.opLabel ? t.opLabel : t.label;
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={isActive ? "page" : undefined}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "border-indigo-600 text-indigo-700"
                  : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
