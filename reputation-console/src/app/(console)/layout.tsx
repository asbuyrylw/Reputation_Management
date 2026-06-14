"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { BusinessProvider } from "@/lib/business";
import { Sidebar } from "@/components/Sidebar";
import { BusinessSwitcher } from "@/components/BusinessSwitcher";
import { Spinner } from "@/components/ui";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

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
      <div className="flex min-h-screen flex-1">
        <Sidebar />
        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
            <BusinessSwitcher />
            <div className="flex items-center gap-4 text-sm">
              <span className="text-gray-500">
                {user.email}
                {user.role === "admin" && (
                  <span className="ml-2 rounded bg-gray-900 px-1.5 py-0.5 text-[10px] font-medium uppercase text-white">
                    admin
                  </span>
                )}
              </span>
              <button
                onClick={() => {
                  logout();
                  router.replace("/login");
                }}
                className="rounded-md border border-gray-300 px-3 py-1 text-gray-700 hover:bg-gray-100"
              >
                Sign out
              </button>
            </div>
          </header>
          <main className="flex-1 p-6">{children}</main>
        </div>
      </div>
    </BusinessProvider>
  );
}
