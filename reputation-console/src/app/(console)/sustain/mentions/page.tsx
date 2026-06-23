"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useMentions, useKeywords, useAddKeyword, useDeleteKeyword, useTriggerJob, useJobs } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SentimentBadge } from "@/components/SentimentBadge";
import { EmptyState } from "@/components/primitives";
import { KeywordSuggestions } from "@/components/KeywordSuggestions";
import { JobProgressBanner } from "@/components/JobProgressBanner";

function relevanceLabel(r: number | null): string {
  if (r == null) return "";
  if (r >= 0.8) return "Strong match";
  if (r >= 0.5) return "Likely about you";
  return "Possibly unrelated";
}

// Manage the terms we monitor + kick off a scan.
function KeywordManager({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data: keywords } = useKeywords(businessId);
  const add = useAddKeyword(businessId);
  const del = useDeleteKeyword(businessId);
  const scan = useTriggerJob(businessId);
  const qc = useQueryClient();
  const [kw, setKw] = useState("");
  const [neg, setNeg] = useState(false);

  const runScan = () =>
    scan.mutate(
      { jobType: "mentions_scan" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["mentions", businessId] }), 8000) },
    );

  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Monitoring keywords</h3>
        {canEdit && (
          <button
            onClick={runScan}
            disabled={scan.isPending || !(keywords && keywords.some((k) => !k.negative))}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {scan.isPending ? "Scanning…" : "Scan now"}
          </button>
        )}
      </div>
      <p className="mt-1 text-sm text-slate-600">
        We watch these terms across <span className="font-medium">Reddit</span> and{" "}
        <span className="font-medium">Google News</span> for free; add a search key (SERPER_API_KEY) and we also
        cover the broader <span className="font-medium">web, social (X / Facebook / YouTube / LinkedIn)</span>, and{" "}
        <span className="font-medium">review &amp; complaint sites</span> (BBB, Trustpilot, Yelp, RipoffReport,
        PissedConsumer, Glassdoor). Mark a term as &ldquo;exclude&rdquo; to filter out unrelated noise.
      </p>

      {canEdit && (
        <>
        <p className="mt-3 text-xs text-slate-400">Tip: separate multiple terms with commas — each is watched on its own.</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            value={kw}
            onChange={(e) => setKw(e.target.value)}
            placeholder="e.g. Team Unstoppable, Chris Koob, Primerica Cincinnati"
            className="min-w-[16rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            title="Separate multiple terms with commas — each is watched on its own."
            onKeyDown={(e) => {
              if (e.key === "Enter" && kw.trim()) add.mutate({ keyword: kw, negative: neg }, { onSuccess: () => setKw("") });
            }}
          />
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <input type="checkbox" checked={neg} onChange={(e) => setNeg(e.target.checked)} /> exclude term
          </label>
          <button
            onClick={() => kw.trim() && add.mutate({ keyword: kw, negative: neg }, { onSuccess: () => setKw("") })}
            disabled={add.isPending || !kw.trim()}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            Add
          </button>
        </div>
        </>
      )}

      {keywords && keywords.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {keywords.map((k) => (
            <span
              key={k.id}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                k.negative ? "border-slate-200 bg-slate-100 text-slate-500" : "border-indigo-200 bg-indigo-50 text-indigo-700"
              }`}
            >
              {k.negative ? "exclude: " : ""}{k.keyword}
              {canEdit && (
                <button onClick={() => del.mutate(k.id)} className="text-slate-400 hover:text-slate-700" aria-label="remove">
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No keywords yet — add your business name and key people to start.</p>
      )}

      <KeywordSuggestions
        businessId={businessId}
        existing={(keywords ?? []).map((k) => k.keyword)}
        canEdit={canEdit}
      />
    </Card>
  );
}

export default function MentionsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useMentions(businessId);
  const { data: jobsData } = useJobs(businessId);

  if (isLoading || !data) return <Spinner />;

  // Has a mention scan ever completed? Lets the empty state say "scanned, nothing found"
  // rather than "you haven't scanned yet" — two very different situations for the owner.
  const scanned = (jobsData?.jobs ?? []).some((j) => j.job_type === "mentions_scan" && j.status === "complete");

  const counts = { positive: 0, neutral: 0, negative: 0, mixed: 0 } as Record<string, number>;
  for (const m of data) if (m.sentiment && m.sentiment in counts) counts[m.sentiment]++;
  const sourceCounts: Record<string, number> = {};
  for (const m of data) if (m.source) sourceCounts[m.source] = (sourceCounts[m.source] ?? 0) + 1;
  const topSources = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]).slice(0, 6);

  return (
    <div>
      <PageHeader
        title="Mentions"
        subtitle="What's being said about you across the web — set the terms to watch, then scan."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      <KeywordManager businessId={businessId} canEdit={canEdit} />

      {data.length === 0 ? (
        scanned ? (
          <EmptyState
            title="Scan complete — no mentions found yet"
            why="We searched your monitored terms and didn't find anything new this run. That can be normal for a newer or low-profile brand. Try adding more specific terms (the person's full name, the brand + city) and scan again."
            produces="When a match turns up, it appears here with a positive/negative read and how sure we are it's really about you."
          />
        ) : (
          <EmptyState
            title="No mentions captured yet"
            why="Add a keyword above and click “Scan now.” We check Reddit + Google News instantly (free), plus the broader web, social, and review/complaint sites when a search key is configured."
            produces="New mentions appear here with a positive/negative read and how sure we are they're really about you."
          />
        )
      ) : (
        <>
          <Card className="mb-4">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-slate-500">{data.length} mentions</span>
              <span className="text-emerald-700">{counts.positive} positive</span>
              <span className="text-slate-600">{counts.neutral} neutral</span>
              <span className="text-amber-700">{counts.mixed} mixed</span>
              <span className="text-rose-600">{counts.negative} negative</span>
            </div>
            {topSources.length > 0 && (
              <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-500">
                <span className="font-medium text-slate-600">Top sources talking about you:</span>{" "}
                {topSources.map(([src, n]) => `${src} (${n})`).join(" · ")}
              </div>
            )}
          </Card>

          <div className="space-y-2">
            {data.map((m) => (
              <Card key={m.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{m.source}</span>
                  <SentimentBadge sentiment={m.sentiment} />
                  {m.relevance != null && <span className="text-xs text-slate-400">{relevanceLabel(m.relevance)}</span>}
                  {m.matched_keyword && <span className="text-xs text-slate-400">&ldquo;{m.matched_keyword}&rdquo;</span>}
                </div>
                {m.title && <div className="mt-1 text-sm font-medium text-slate-900">{m.title}</div>}
                {m.body && (
                  <p className="mt-1 text-sm text-slate-700">
                    {m.body.slice(0, 240)}
                    {m.body.length > 240 ? "…" : ""}
                  </p>
                )}
                {m.source_url && (
                  <a href={m.source_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-indigo-600 hover:underline">
                    {m.source_url}
                  </a>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
