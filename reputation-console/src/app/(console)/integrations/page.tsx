"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useExternalSignals, useIngestSignal, useTriggerJob } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { DataBlocks } from "@/components/DataBlocks";

const TYPES = ["technical_seo", "keywords", "serp_rank", "backlinks", "brand", "visitors", "other"];

export default function IntegrationsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useExternalSignals(businessId);
  const ingest = useIngestSignal(businessId);
  const normalize = useTriggerJob(businessId);
  const [source, setSource] = useState("");
  const [type, setType] = useState("technical_seo");
  const [content, setContent] = useState("");

  if (isLoading || !data) return <Spinner />;
  const rawCount = data.filter((s) => s.status === "raw").length;

  return (
    <div>
      <PageHeader
        title="External data"
        subtitle="Paste or upload a report from a 3rd-party SEO / SERP / analytics tool (SiteGuru, Screpy, ClickRank, WriterZen, Branalyzer, Salespanel, …). The AI normalizes it so the engine can use it."
      />

      {canEdit && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-gray-700">Add a report</div>
          <div className="flex flex-wrap gap-2">
            <input
              placeholder="Source (e.g. siteguru)"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            />
            <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm">
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <textarea
            placeholder="Paste the report (CSV / JSON / text)…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={5}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              disabled={ingest.isPending || !source || !content}
              onClick={() => ingest.mutate({ source, signal_type: type, content }, { onSuccess: () => setContent("") })}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Upload
            </button>
            {rawCount > 0 && (
              <button
                disabled={normalize.isPending}
                onClick={() => normalize.mutate({ jobType: "normalize_signals" })}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
              >
                Normalize {rawCount} new with AI
              </button>
            )}
          </div>
        </Card>
      )}

      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No external reports yet.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {data.map((s) => (
            <Card key={s.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">{s.source}</span>
                <span className="text-xs text-gray-500">{(s.signal_type || "").replace(/_/g, " ")}</span>
                <span className={`text-xs ${s.status === "normalized" ? "text-green-700" : s.status === "failed" ? "text-red-700" : "text-amber-700"}`}>
                  {s.status}
                </span>
                <span className="text-xs text-gray-400">{s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}</span>
              </div>
              {s.normalized ? (
                <div className="mt-2">
                  <DataBlocks data={s.normalized} />
                </div>
              ) : (
                <p className="mt-2 text-xs text-gray-400">
                  {s.status === "raw" ? "Awaiting AI normalization — click ‘Normalize’ above." : "Could not normalize this report."}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
