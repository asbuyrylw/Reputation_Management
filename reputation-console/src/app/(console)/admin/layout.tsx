"use client";

import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return (
      <Card>
        <p className="text-sm text-slate-600">Admin access required.</p>
      </Card>
    );
  }
  return <>{children}</>;
}
