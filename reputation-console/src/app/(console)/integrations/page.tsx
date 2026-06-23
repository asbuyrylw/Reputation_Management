"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useExternalSignals, useIngestSignal, useTriggerJob } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";

const TYPES = ["technical_seo", "keywords", "serp_rank", "backlinks", "brand", "visitors", "other"];
const TYPE_LABELS: Record<string, string> = {
  technical_seo: "Technical SEO health",
  keywords: "Keywords",
  serp_rank: "Google ranking",
  backlinks: "Links to your site",
  brand: "Brand mentions",
  visitors: "Website visitors",
  other: "Other",
};
const STATUS_WORDS: Record<string, string> = {
  raw: "Ready to process",
  normalized: "Processed",
  failed: "Couldn't read this",
};

// Clean key/value render of a normalized report (replaces the raw JSON dump).
function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return <p className="text-sm text-slate-400">No details.</p>;
  return (
    <dl className="space-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[160px_1fr]">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{k.replace(/_/g, " ")}</dt>
          <dd className="text-sm text-slate-700">
            {Array.isArray(v) ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ")
              : typeof v === "object" ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

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
        title="Connect your other data"
        subtitle="Already pay for an SEO or analytics tool? Paste its report here and we'll fold those real numbers into your reputation plan."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      <Card className="mb-4 bg-indigo-50/50">
        <div className="text-sm font-semibold text-slate-900">What this is for</div>
        <p className="mt-1 text-sm text-slate-700">
          If you already use an SEO or analytics tool (SiteGuru, Screpy, ClickRank, Google Analytics, Search
          Console…), paste its report here. We read the real numbers and fold them into your reputation plan.
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-sm text-slate-700">
          <li>
            <span className="font-medium">How it&apos;s used:</span> your real Google rankings, backlinks,
            technical-SEO issues, and traffic feed the gap model and site audit — so the plan targets what actually
            needs work instead of guessing.
          </li>
          <li>
            <span className="font-medium">The value:</span> sharper, evidence-based priorities (fix the pages and
            keywords that genuinely move your AI visibility) and hard numbers to prove progress over time.
          </li>
        </ul>
        <p className="mt-2 text-xs text-slate-500">
          Paste a report as CSV, JSON, or plain text — we normalize it for you. Optional; you don&apos;t need it to get started.
        </p>
      </Card>

      {canEdit && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-slate-700">Add a report</div>
          <div className="flex flex-wrap gap-2">
            <input
              placeholder="Source (e.g. siteguru)"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
            <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABELS[t] ?? t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <textarea
            placeholder="Paste the report (CSV / JSON / text)…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={5}
            className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              disabled={ingest.isPending || !source || !content}
              onClick={() => ingest.mutate({ source, signal_type: type, content }, { onSuccess: () => setContent("") })}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Upload
            </button>
            {rawCount > 0 && (
              <button
                disabled={normalize.isPending}
                onClick={() => normalize.mutate({ jobType: "normalize_signals" })}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                Normalize {rawCount} new with AI
              </button>
            )}
          </div>
        </Card>
      )}

      {data.length === 0 ? (
        <EmptyState
          title="No reports added yet"
          why="You don't need this to get started — but if you have data from another tool, it sharpens your plan."
          produces="Uploaded reports appear here once we've read them, with a plain summary of what we learned."
        />
      ) : (
        <div className="space-y-3">
          {data.map((s) => (
            <Card key={s.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">{s.source}</span>
                <span className="text-xs text-slate-500">{TYPE_LABELS[s.signal_type ?? ""] ?? (s.signal_type || "").replace(/_/g, " ")}</span>
                <span className={`text-xs ${s.status === "normalized" ? "text-emerald-700" : s.status === "failed" ? "text-rose-700" : "text-amber-700"}`}>
                  {STATUS_WORDS[s.status] ?? s.status}
                </span>
                <span className="text-xs text-slate-400">{s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}</span>
              </div>
              {s.normalized ? (
                <div className="mt-2 border-t border-slate-100 pt-2">
                  <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">What we learned</div>
                  <KeyValues data={s.normalized} />
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-400">
                  {s.status === "raw" ? "Ready to process — click ‘Normalize’ above." : "We couldn't read this report. Try pasting it as plain text."}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
