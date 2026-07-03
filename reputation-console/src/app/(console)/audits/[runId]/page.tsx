"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useBeforeAfter, usePerEngine, useRunAnswers } from "@/lib/hooks";
import { AnswersByPrompt } from "@/components/AnswersByPrompt";
import { BeforeAfterDiffCard } from "@/components/BeforeAfterDiffCard";
import { PerEnginePanel } from "@/components/PerEnginePanel";
import { Card, PageHeader, Spinner } from "@/components/ui";

// Normalize a cited-source URL to a bare host ("https://www.reddit.com/r/x" -> "reddit.com")
// so we can match the source_domain deep-link from the AI-citations page.
function srcHost(u: unknown): string {
  if (typeof u !== "string") return "";
  try {
    return new URL(u).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return u.toLowerCase();
  }
}
function citesDomain(cited: unknown, target: string): boolean {
  const t = target.toLowerCase();
  const list = Array.isArray(cited) ? cited : [];
  return list.some((u) => {
    const h = srcHost(u);
    return h === t || h.endsWith("." + t);
  });
}

export default function RunDetailPage() {
  // useParams works in client components and is unaffected by the Next 16 async-params change.
  const params = useParams<{ runId: string }>();
  const search = useSearchParams();
  const runId = Number(params.runId);
  const { businessId } = useBusiness();
  const [engine, setEngine] = useState("");
  const [sentiment, setSentiment] = useState("");
  // Deep-link from the AI-citations page: show only the answers that cited a given source.
  const sourceDomain = search.get("source_domain") || "";

  const { data: answers, isLoading } = useRunAnswers(businessId, runId);
  const { data: ba } = useBeforeAfter(businessId);
  const { data: perEngine } = usePerEngine(businessId, runId);

  if (isLoading || !answers) return <Spinner />;

  const engines = Array.from(new Set(answers.map((a) => a.engine))).sort();
  const sentiments = Array.from(new Set(answers.map((a) => a.sentiment).filter(Boolean))) as string[];
  const filtered = answers.filter(
    (a) =>
      (!engine || a.engine === engine) &&
      (!sentiment || a.sentiment === sentiment) &&
      (!sourceDomain || citesDomain(a.cited_sources, sourceDomain)),
  );

  return (
    <div>
      <Link href="/audits" className="text-sm text-indigo-600 hover:underline">
        ← All audits
      </Link>
      <PageHeader
        title={`Audit run #${runId}`}
        subtitle="What the AI engines answered about this business, with the scoring judge's read of each."
      />

      {perEngine && (
        <div className="mb-6">
          <PerEnginePanel data={perEngine} />
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={engine}
          onChange={(e) => setEngine(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">All engines</option>
          {engines.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
        <select
          value={sentiment}
          onChange={(e) => setSentiment(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">All sentiment</option>
          {sentiments.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {sourceDomain && (
          <Link
            href={`/audits/${runId}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
          >
            Citing: {sourceDomain}
            <span aria-hidden className="text-indigo-400">✕</span>
          </Link>
        )}
        <span className="text-xs text-slate-400">
          {filtered.length} of {answers.length} answers
        </span>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-500">No answers match these filters.</p>
        </Card>
      ) : (
        <AnswersByPrompt answers={filtered} />
      )}

      {ba && ba.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-1 text-lg font-semibold text-slate-900">Before &amp; now</h2>
          <p className="mb-3 text-sm text-slate-500">
            The same question on the same engine, first audit vs. the latest — how the answer changed.
          </p>
          <div className="space-y-3">
            {ba.map((pair, i) => (
              <BeforeAfterDiffCard key={i} pair={pair} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
