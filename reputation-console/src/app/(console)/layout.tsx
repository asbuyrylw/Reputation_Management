"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { BusinessProvider } from "@/lib/business";
import { FilterProvider } from "@/lib/filters";
import { Sidebar } from "@/components/Sidebar";
import { BusinessSwitcher } from "@/components/BusinessSwitcher";
import { FilterBar } from "@/components/FilterBar";
import { NotificationBell } from "@/components/NotificationBell";
import { HubTabs } from "@/components/HubTabs";
import { Spinner } from "@/components/ui";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen flex-1 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <BusinessProvider>
      <FilterProvider>
        <div className="flex min-h-screen flex-1">
          {/* mobile backdrop when the nav drawer is open */}
          {navOpen && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setNavOpen(false)} />}
          <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-line bg-paper/85 px-4 py-3 backdrop-blur-md sm:px-6">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => setNavOpen(true)}
                  aria-label="Open menu"
                  className="rounded-md border border-slate-300 p-1.5 text-slate-700 hover:bg-slate-100 lg:hidden"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" /></svg>
                </button>
                <BusinessSwitcher />
                <FilterBar />
              </div>
              <div className="flex items-center gap-4 text-sm">
                <NotificationBell />
                <span className="text-slate-500">
                  {user.email}
                  {user.role === "admin" && (
                    <span className="ml-2 rounded bg-slate-900 px-1.5 py-0.5 text-[10px] font-medium uppercase text-white">
                      admin
                    </span>
                  )}
                </span>
                <button
                  onClick={async () => {
                    await logout();
                    router.replace("/login");
                  }}
                  className="rounded-md border border-slate-300 px-3 py-1 text-slate-700 hover:bg-slate-100"
                >
                  Sign out
                </button>
              </div>
            </header>
            <main className="flex-1 p-6"><HubTabs />{children}</main>
          </div>
        </div>
      </FilterProvider>
    </BusinessProvider>
  );
}
