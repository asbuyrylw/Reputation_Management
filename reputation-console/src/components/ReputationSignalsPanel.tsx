"use client";

// Reputation signals (DataForSEO) — brand mentions across the web + cross-platform review ratings,
// ingested and stored between audits. Self-hides until the dataforseo_intel / dataforseo_reviews
// jobs have run, so it never sits as an empty card.

import { useReputationSignals } from "@/lib/hooks";
import type { ReviewSnapshot } from "@/lib/types";
import { Card } from "@/components/ui";
import { RunJobButton } from "@/components/RunJobButton";

function ratingValue(r: ReviewSnapshot["rating"]): number | null {
  if (r == null) return null;
  if (typeof r === "number") return r;
  return typeof r.value === "number" ? r.value : null;
}

function Stars({ v }: { v: number | null }) {
  if (v == null) return <span className="text-ink-4">—</span>;
  const full = Math.round(v);
  return <span className="text-amber-500" title={`${v.toFixed(1)} / 5`}>{"★".repeat(Math.min(5, full))}<span className="text-line-2">{"★".repeat(Math.max(0, 5 - full))}</span></span>;
}

export function ReputationSignalsPanel({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data } = useReputationSignals(businessId);
  const mentions = data?.mentions ?? null;
  const reviews = data?.reviews ?? [];
  // Dormant until an ingest has stored something.
  if (!mentions && reviews.length === 0) return null;

  const sentiment = mentions?.sentiment ?? {};
  const sentimentPairs = Object.entries(sentiment).filter(([, v]) => typeof v === "number").slice(0, 4);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Reputation across the web</h3>
          <p className="mt-0.5 text-xs text-slate-500">Brand mentions + review ratings from around the web (Google, Trustpilot), refreshed between audits.</p>
        </div>
        {canEdit && <RunJobButton businessId={businessId} jobType="dataforseo_reviews" label="Refresh reviews" variant="secondary" />}
      </div>

      {/* reviews per platform */}
      {reviews.length > 0 && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {reviews.map((rv) => {
            const val = ratingValue(rv.rating);
            return (
              <div key={rv.platform} className="rounded-[10px] border border-line bg-paper px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-semibold capitalize text-ink">{rv.platform}</span>
                  <span className="font-mono text-[12px] text-ink-3">{rv.reviews_count ?? rv.reviews.length} reviews</span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <Stars v={val} />
                  <span className="font-mono text-[13px] font-semibold text-ink">{val != null ? val.toFixed(1) : "—"}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* mentions volume + sentiment */}
      {mentions && (
        <div className="mt-3 border-t border-line pt-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="text-[13px] text-ink-2"><b className="font-semibold text-ink">{(mentions.total_count ?? 0).toLocaleString()}</b> web mentions of &ldquo;{mentions.keyword}&rdquo;</span>
            {sentimentPairs.map(([k, v]) => (
              <span key={k} className="inline-flex items-center gap-1 text-[12px] text-ink-3">
                <span className="capitalize">{k}</span>
                <span className="font-mono text-[11px] text-ink-4">{Math.round((v as number) * 100)}%</span>
              </span>
            ))}
          </div>
          {(mentions.sample ?? []).length > 0 && (
            <ul className="mt-2 space-y-1">
              {mentions.sample.slice(0, 3).map((s, i) => (
                <li key={i} className="truncate text-[12.5px]">
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-indigo hover:underline">{s.title || s.url}</a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
