"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { HUBS, hubForPath } from "@/lib/nav";

// v2 redesign: a DARK top-level hub rail (ink #0F172A) with an icon per hub, active = indigo.
// Renders the ~9 HUBS from @/lib/nav; Settings + Admin sit in the footer. Collapses to an
// icon-only rail on desktop (persisted); the mobile drawer always shows full.

const COLLAPSE_KEY = "rc-nav-collapsed";
function readCollapsed(): boolean {
  try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
}
function subscribeCollapsed(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener("rc-nav", cb);
  return () => { window.removeEventListener("storage", cb); window.removeEventListener("rc-nav", cb); };
}

// One SVG per hub (paths from the redesign spec).
function HubIcon({ hub }: { hub: string }) {
  const p: Record<string, React.ReactNode> = {
    dashboard: (<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>),
    ai: (<><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></>),
    search: (<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>),
    plan: (<path d="M12 2l2.4 6.5L21 9l-5 4.5L17.5 21 12 17l-5.5 4L8 13.5 3 9l6.6-.5z" />),
    content: (<><path d="M4 4h16v14H7l-3 3z" /><path d="M8 9h8M8 13h5" /></>),
    monitor: (<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>),
    proof: (<><path d="M4 4v16h16" /><path d="M8 15l3-4 3 2 4-6" /></>),
    settings: (<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 0 1-4 0v-.1A1.6 1.6 0 0 0 6.7 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 12.6H3a2 2 0 0 1 0-4h.1A1.6 1.6 0 0 0 4.6 6.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 12 3.4V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></>),
    admin: (<path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z" />),
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" className="h-[17px] w-[17px] shrink-0">
      {p[hub] ?? p.dashboard}
    </svg>
  );
}

export function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const path = usePathname() || "";
  const { user } = useAuth();
  const isOperator = user?.role === "admin";
  const activeHub = hubForPath(path);
  const railed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);
  const toggle = () => {
    try { localStorage.setItem(COLLAPSE_KEY, readCollapsed() ? "0" : "1"); } catch { /* ignore */ }
    window.dispatchEvent(new Event("rc-nav"));
  };

  const all = HUBS.filter((h) => !h.adminOnly || isOperator);
  const footKeys = new Set(["settings", "admin"]);
  const mainHubs = all.filter((h) => !footKeys.has(h.key));
  const footHubs = all.filter((h) => footKeys.has(h.key));

  const item = (h: (typeof HUBS)[number]) => {
    const active = activeHub?.key === h.key;
    const label = isOperator && h.opLabel ? h.opLabel : h.label;
    return (
      <Link
        key={h.key}
        href={h.href}
        onClick={() => onClose?.()}
        title={label}
        className={`group flex items-center gap-[11px] rounded-[9px] px-[11px] py-[9px] text-[13.5px] font-medium transition-colors ${
          active
            ? "bg-indigo text-white shadow-[0_4px_14px_-4px_rgba(79,70,229,0.7)]"
            : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
        } ${railed ? "lg:justify-center lg:gap-0 lg:px-0" : ""}`}
      >
        <HubIcon hub={h.key} />
        <span className={railed ? "lg:hidden" : ""}>{label}</span>
      </Link>
    );
  };

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex w-[236px] shrink-0 transform flex-col overflow-hidden bg-ink px-4 py-[22px] text-slate-300 transition-[transform,width] duration-200 lg:sticky lg:top-0 lg:z-auto lg:h-screen lg:translate-x-0 ${
        open ? "translate-x-0" : "-translate-x-full"
      } ${railed ? "lg:w-[68px] lg:px-2" : "lg:w-[236px]"}`}
    >
      {/* Brand */}
      <div className={`mb-[26px] flex shrink-0 items-center gap-[11px] px-2 py-1.5 ${railed ? "lg:justify-center lg:px-0" : ""}`}>
        <div className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[10px] bg-linear-to-br from-indigo to-[#7C74F0] font-display text-lg font-semibold text-white shadow-[0_4px_12px_-2px_rgba(79,70,229,0.6)]">
          R
        </div>
        <div className={`leading-[1.1] ${railed ? "lg:hidden" : ""}`}>
          <div className="font-display text-[16px] font-semibold tracking-[-0.01em] text-white">Reputation</div>
          <div className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.22em] text-slate-500">Console</div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-px overflow-y-auto overflow-x-hidden">
        {mainHubs.map(item)}
      </nav>

      <div className="mt-auto shrink-0 border-t border-white/10 pt-4">
        {footHubs.map(item)}
        <button
          onClick={toggle}
          aria-label={railed ? "Expand navigation" : "Collapse navigation"}
          className={`mt-1 hidden w-full items-center gap-[11px] rounded-[9px] px-[11px] py-[9px] text-[12.5px] font-medium text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300 lg:flex ${
            railed ? "lg:justify-center lg:px-0" : ""
          }`}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={`h-[17px] w-[17px] shrink-0 transition-transform ${railed ? "rotate-180" : ""}`}>
            <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className={railed ? "lg:hidden" : ""}>Collapse</span>
        </button>
      </div>
    </aside>
  );
}
