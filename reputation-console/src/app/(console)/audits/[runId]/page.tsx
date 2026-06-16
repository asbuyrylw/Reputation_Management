"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useBeforeAfter, usePerEngine, useRunAnswers } from "@/lib/hooks";
import { AnswersByPrompt } from "@/components/AnswersByPrompt";
import { BeforeAfterDiffCard } from "@/components/BeforeAfterDiffCard";
import { PerEnginePanel } from "@/components/PerEnginePanel";
import { Card, PageHeader, Spinner } from "@/components/ui";

export default function RunDetailPage() {
  // useParams works in client components and is unaffected by the Next 16 async-params change.
  const params = useParams<{ runId: string }>();
  const runId = Number(params.runId);
  const { businessId } = useBusiness();
  const [engine, setEngine] = useState("");
  const [sentiment, setSentiment] = useState("");

  const { data: answers, isLoading } = useRunAnswers(businessId, runId);
  const { data: ba } = useBeforeAfter(businessId);
  const { data: perEngine } = usePerEngine(businessId, runId);

  if (isLoading || !answers) return <Spinner />;

  const engines = Array.from(new Set(answers.map((a) => a.engine))).sort();
  const sentiments = Array.from(new Set(answers.map((a) => a.sentiment).filter(Boolean))) as string[];
  const filtered = answers.filter(
    (a) => (!engine || a.engine === engine) && (!sentiment || a.sentiment === sentiment),
  );

  return (
    <div>
      <Link href="/audits" className="text-sm text-blue-600 hover:underline">
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
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm"
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
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">All sentiment</option>
          {sentiments.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <span className="text-xs text-gray-400">
          {filtered.length} of {answers.length} answers
        </span>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-500">No answers match these filters.</p>
        </Card>
      ) : (
        <AnswersByPrompt answers={filtered} />
      )}

      {ba && ba.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-1 text-lg font-semibold text-gray-900">Before &amp; now</h2>
          <p className="mb-3 text-sm text-gray-500">
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
