"use client";

import { useEffect, useRef, useState } from "react";
import { useBusiness } from "@/lib/business";
import { useReports, useTriggerJob } from "@/lib/hooks";
import { apiDownload, ApiError } from "@/lib/api";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

function fmtDate(d: string): string {
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString();
}

export default function ReportsPage() {
  const { businessId, canEdit } = useBusiness();
  const [generating, setGenerating] = useState(false);
  const reports = useReports(businessId, generating); // poll while a report is building
  const trigger = useTriggerJob(businessId);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rows = reports.data ?? [];

  // stop polling once a new report appears (count grows past the baseline), or after a cap.
  const baseline = useRef<number | null>(null);
  useEffect(() => {
    if (!generating) return;
    if (baseline.current != null && rows.length > baseline.current) setGenerating(false);
    const cap = setTimeout(() => setGenerating(false), 240000); // safety: stop after 4 min
    return () => clearTimeout(cap);
  }, [generating, rows.length]);

  if (reports.isLoading) return <Spinner />;

  const generate = () => {
    baseline.current = rows.length;
    setGenerating(true);
    trigger.mutate({ jobType: "report" });
  };

  const download = async (id: number, filename: string) => {
    setBusyId(id);
    setError(null);
    try {
      await apiDownload(`/businesses/${businessId}/reports/${id}/download`, filename);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 410
          ? "That report file is no longer available — generate a fresh one."
          : "Download failed. Please try again.",
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Your polished monthly AI-visibility reports — download and share them, or generate a fresh one."
      />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-gray-600">Generate a new monthly report from the latest data.</span>
            <button
              onClick={generate}
              disabled={generating || trigger.isPending}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              {generating || trigger.isPending ? "Generating…" : "Generate report"}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-400">A report takes a minute or two to build; it appears here automatically when ready.</p>
        </Card>
      )}

      {error && (
        <div className="mb-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>
      )}

      {rows.length === 0 ? (
        <EmptyState
          title="No reports yet"
          why="Reports summarize where you stand with AI assistants and the progress since last month — the deliverable you can forward to stakeholders."
          produces="Each report is a polished .docx you can download and share."
          timing="Generate one above, or it's produced automatically as part of the monthly cycle."
        />
      ) : (
        <Card>
          <ul className="divide-y divide-gray-100">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-900">{r.filename}</p>
                  <p className="text-xs text-gray-500">{fmtDate(r.created_at)}</p>
                </div>
                <button
                  onClick={() => download(r.id, r.filename)}
                  disabled={busyId === r.id}
                  className="shrink-0 rounded-md border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
                >
                  {busyId === r.id ? "Downloading…" : "Download"}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
