"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { HUBS, hubForPath } from "@/lib/nav";

// Consolidated navigation: ~9 top-level HUBS (down from 8 groups / ~40 items). Each hub links to
// its Overview; the sub-pages live in the HubTabs bar (rendered in the console layout). Owners see
// plain-language labels; operators (role "admin") see the precise `opLabel`. Hub config + the
// active-hub resolver both live in `@/lib/nav` so the sidebar and the tab bar never drift.
//
// The rail can COLLAPSE on desktop to reclaim horizontal space (persisted in localStorage). Collapse
// only toggles `lg:` classes, so the mobile drawer is always shown full-width and un-railed.
const COLLAPSE_KEY = "rc-nav-collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}
// Subscribe to same-tab ("rc-nav") + cross-tab ("storage") changes for useSyncExternalStore.
function subscribeCollapsed(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener("rc-nav", cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener("rc-nav", cb);
  };
}

export function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const path = usePathname() || "";
  const { user } = useAuth();
  const isOperator = user?.role === "admin";
  const activeHub = hubForPath(path);
  const hubs = HUBS.filter((h) => !h.adminOnly || isOperator);

  // Server snapshot is always "expanded" so the first client render matches (no hydration
  // mismatch); after hydration useSyncExternalStore reflects the saved localStorage value.
  const railed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);
  const toggle = () => {
    try {
      localStorage.setItem(COLLAPSE_KEY, readCollapsed() ? "0" : "1");
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event("rc-nav"));
  };

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 transform flex-col overflow-hidden border-r border-slate-200/70 bg-white p-4 backdrop-blur-xl transition-[transform,width] duration-200 lg:sticky lg:top-0 lg:z-auto lg:h-screen lg:translate-x-0 lg:bg-white/80 ${
        open ? "translate-x-0" : "-translate-x-full"
      } ${railed ? "lg:w-19 lg:px-2" : "lg:w-64"}`}
    >
      {/* Brand */}
      <div className={`mb-6 flex shrink-0 items-center gap-2.5 px-1.5 ${railed ? "lg:justify-center lg:px-0" : ""}`}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-indigo-500 to-violet-600 text-base font-bold text-white shadow-md shadow-indigo-500/25">
          R
        </div>
        <div className={`leading-tight ${railed ? "lg:hidden" : ""}`}>
          <div className="text-[15px] font-bold tracking-tight text-slate-900">Reputation</div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-indigo-500">Console</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto overflow-x-hidden">
        {hubs.map((h) => {
          const active = activeHub?.key === h.key;
          const label = isOperator && h.opLabel ? h.opLabel : h.label;
          return (
            <Link
              key={h.key}
              href={h.href}
              onClick={() => onClose?.()}
              title={label}
              className={`group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-linear-to-r from-indigo-600 to-indigo-500 text-white shadow-sm shadow-indigo-500/20"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              } ${railed ? "lg:justify-center lg:gap-0 lg:px-0" : ""}`}
            >
              {/* expanded: small dot */}
              <span
                className={`h-1.5 w-1.5 rounded-full transition-colors ${
                  active ? "bg-white" : "bg-slate-300 group-hover:bg-indigo-400"
                } ${railed ? "lg:hidden" : ""}`}
                aria-hidden
              />
              {/* railed: hub initial in a chip (desktop only) */}
              <span
                className={`hidden h-7 w-7 items-center justify-center rounded-md text-xs font-semibold ${
                  active ? "bg-white/25 text-white" : "bg-slate-100 text-slate-500 group-hover:text-indigo-600"
                } ${railed ? "lg:flex" : ""}`}
                aria-hidden
              >
                {label.charAt(0)}
              </span>
              <span className={railed ? "lg:hidden" : ""}>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle — desktop only */}
      <button
        onClick={toggle}
        aria-label={railed ? "Expand navigation" : "Collapse navigation"}
        title={railed ? "Expand navigation" : "Collapse navigation"}
        className={`mt-2 hidden shrink-0 items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:flex ${
          railed ? "lg:justify-center lg:px-0" : ""
        }`}
      >
        <svg
          className={`h-4 w-4 shrink-0 transition-transform ${railed ? "rotate-180" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className={railed ? "lg:hidden" : ""}>Collapse</span>
      </button>
    </aside>
  );
}
