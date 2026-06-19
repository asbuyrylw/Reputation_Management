"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useBusiness } from "@/lib/business";
import { useRevokeSessions, useDeleteBusiness } from "@/lib/hooks";
import { apiDownload } from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";

export default function AccountPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { businessId, businesses } = useBusiness();
  const revoke = useRevokeSessions();
  const del = useDeleteBusiness(businessId);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");

  const biz = businesses.find((b) => b.id === businessId);
  const isAdmin = user?.role === "admin";

  const signOutEverywhere = () =>
    revoke.mutate(undefined, { onSuccess: () => router.replace("/login") });

  const exportData = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const name = (biz?.name || "business").replace(/\s+/g, "_");
      await apiDownload(`/businesses/${businessId}/export`, `${name}_data_export.json`);
    } catch {
      setExportError("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  const deleteBusiness = () =>
    del.mutate(undefined, { onSuccess: () => router.replace("/dashboard") });

  return (
    <div className="max-w-2xl">
      <PageHeader title="Account & data" subtitle="Manage your sessions and your data." />

      <div className="space-y-4">
        {/* sessions */}
        <Card>
          <h3 className="text-sm font-semibold text-gray-900">Sessions</h3>
          <p className="mt-1 text-sm text-gray-600">
            Sign out of every device and browser. Anyone currently signed in (including you) will need to log in again.
          </p>
          <button
            onClick={signOutEverywhere}
            disabled={revoke.isPending}
            className="mt-3 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            {revoke.isPending ? "Signing out…" : "Sign out everywhere"}
          </button>
          {revoke.isError && (
            <p className="mt-2 text-xs text-rose-600">Could not sign out everywhere — please try again.</p>
          )}
        </Card>

        {/* data export */}
        <Card>
          <h3 className="text-sm font-semibold text-gray-900">Export your data</h3>
          <p className="mt-1 text-sm text-gray-600">
            Download everything we hold for <span className="font-medium">{biz?.name ?? "this business"}</span> as a
            single JSON file (audits, prompts, content, mentions, and more).
          </p>
          <button
            onClick={exportData}
            disabled={exporting || !businessId}
            className="mt-3 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            {exporting ? "Preparing…" : "Export business data"}
          </button>
          {exportError && <p className="mt-2 text-xs text-rose-600">{exportError}</p>}
        </Card>

        {/* danger zone (admin only) */}
        {isAdmin && (
          <Card className="border-rose-200">
            <h3 className="text-sm font-semibold text-rose-700">Delete this business</h3>
            <p className="mt-1 text-sm text-gray-600">
              Permanently erase <span className="font-medium">{biz?.name ?? "this business"}</span> and all of its
              data. This cannot be undone. Type the business name to confirm.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={biz?.name ?? "business name"}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
              />
              <button
                onClick={deleteBusiness}
                disabled={del.isPending || !biz || confirmText !== biz.name}
                className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
              >
                {del.isPending ? "Deleting…" : "Delete business"}
              </button>
            </div>
            {del.isError && <p className="mt-2 text-xs text-rose-600">{(del.error as Error)?.message}</p>}
          </Card>
        )}
      </div>
    </div>
  );
}
