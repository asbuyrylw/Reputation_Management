"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { HUBS, hubForPath } from "@/lib/nav";

// Consolidated navigation: ~9 top-level HUBS (down from 8 groups / ~40 items). Each hub links to
// its Overview; the sub-pages live in the HubTabs bar (rendered in the console layout). Owners see
// plain-language labels; operators (role "admin") see the precise `opLabel`. Hub config + the
// active-hub resolver both live in `@/lib/nav` so the sidebar and the tab bar never drift.
export function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void } = {}) {
  const path = usePathname() || "";
  const { user } = useAuth();
  const isOperator = user?.role === "admin";
  const activeHub = hubForPath(path);
  const hubs = HUBS.filter((h) => !h.adminOnly || isOperator);

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-64 shrink-0 transform overflow-y-auto border-r border-slate-200/70 bg-white p-4 backdrop-blur-xl transition-transform lg:sticky lg:top-0 lg:h-screen lg:z-auto lg:translate-x-0 lg:bg-white/80 ${
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

      <nav className="space-y-1">
        {hubs.map((h) => {
          const active = activeHub?.key === h.key;
          const label = isOperator && h.opLabel ? h.opLabel : h.label;
          return (
            <Link
              key={h.key}
              href={h.href}
              onClick={() => onClose?.()}
              className={`group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-linear-to-r from-indigo-600 to-indigo-500 text-white shadow-sm shadow-indigo-500/20"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full transition-colors ${
                  active ? "bg-white" : "bg-slate-300 group-hover:bg-indigo-400"
                }`}
                aria-hidden
              />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
