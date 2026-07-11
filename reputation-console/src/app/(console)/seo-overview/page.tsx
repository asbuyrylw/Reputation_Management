"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useLocalRankings, useCompare, useSiteAudit, useLocalSeoGoal, useTargetKeywords, useReviews, useReviewRequest, useOurContentImpact, useReviewSla, useSendReviewRequests, useSiteHealthTrend, useSchemaVerify, useGscSummary, usePageSpeed, useRunPageSpeed, useIndexHealth, useSubmitSitemap } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, CopyButton, DataSection } from "@/components/primitives";
import { SecHead } from "@/components/DashboardV2";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { RunJobButton } from "@/components/RunJobButton";
import { SearchPerformanceCard } from "@/components/SearchPerformanceCard";
import { AiCrawlerReadinessCard } from "@/components/AiCrawlerReadinessCard";
import { NapBlock } from "@/components/NapBlock";
import type { TargetKeyword, ReviewsSummary, ReviewRequestKit, OurContentImpact, ReviewSla, LocalSeoGoal } from "@/lib/types";

const healthColor = (s: number | null) => (s == null ? "#94A3B8" : s >= 60 ? "#059669" : s >= 40 ? "#D97706" : "#E0672E");
const healthLabel = (s: number | null) => (s == null ? "—" : s >= 75 ? "Strong" : s >= 60 ? "Good" : s >= 40 ? "Fair" : "Poor");
const fmtDate = (d?: string | null) => (d ? new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—");

function Tile({ k, value, small, sub, color }: { k: string; value: string; small?: string; sub: string; color?: string }) {
  return (
    <div className="rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">{k}</div>
      <div className="font-display text-[26px] font-semibold leading-none tracking-[-0.02em]" style={{ color: color ?? "var(--ink)" }}>{value}{small && <small className="text-[14px] text-ink-4">{small}</small>}</div>
      <div className="mt-1.5 text-[12px] text-ink-3">{sub}</div>
    </div>
  );
}

function SiteHealthGauge({ score }: { score: number | null }) {
  const s = Math.max(0, Math.min(100, score ?? 0));
  const R = 40, C = 2 * Math.PI * R;
  const col = healthColor(score);
  return (
    <div className="relative h-24 w-24 shrink-0">
      <svg width="96" height="96" viewBox="0 0 96 96" className="-rotate-90">
        <circle cx="48" cy="48" r={R} fill="none" stroke="#EEF0F4" strokeWidth="9" />
        <circle cx="48" cy="48" r={R} fill="none" stroke={col} strokeWidth="9" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - s / 100)} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-display text-[30px] font-semibold" style={{ color: col }}>{score ?? "—"}</div>
        <div className="font-mono text-[10px] text-ink-4">/100</div>
      </div>
    </div>
  );
}

function SeoGoalCard({ goal, gscConnected }: { goal?: LocalSeoGoal; gscConnected: boolean }) {
  const exp = goal?.projection?.expected;
  const now = goal?.current_page_one_rate != null ? Math.round(goal.current_page_one_rate * 100) : 0;
  return (
    <Card className="flex flex-col">
      <div className="eyebrow mb-3">Goal · get to page 1 of Google</div>
      <div className="font-display text-[28px] font-semibold tracking-[-0.02em] text-ink">{fmtDate(exp?.target_date)}</div>
      <p className="mt-1 text-[13.5px] text-ink-3">{exp?.months ? `~${exp.months} months` : "Projection pending"} to rank on page 1 for 80% of your local searches.</p>
      <div className="my-4">
        <div className="mb-1.5 flex justify-between font-mono text-[12px]"><span className="text-ink-4">now · {now}% on page 1</span><span className="font-semibold text-indigo-strong">target 80%</span></div>
        <div className="h-2 overflow-hidden rounded-full bg-line"><i className="block h-full rounded-full bg-indigo" style={{ width: `${Math.max(2, Math.round((now / 80) * 100))}%` }} /></div>
      </div>
      {!gscConnected && (
        <div className="mt-auto rounded-[11px] border border-amber/30 bg-amber-bg px-3.5 py-3">
          <div className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold text-amber">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[15px] w-[15px]"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></svg>
            Get real Google numbers
          </div>
          <p className="mb-1.5 text-[12.5px] leading-relaxed text-ink-3">Connect Search Console to import real clicks, impressions and rankings.</p>
          <Link href="/integrations" className="inline-flex items-center gap-1 text-[13px] font-semibold text-indigo hover:text-indigo-strong">Connect Search Console<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3 w-3"><path d="M5 12h14M13 6l6 6-6 6" /></svg></Link>
        </div>
      )}
    </Card>
  );
}

function TabSummary({ href, title, chip, chipTone, desc }: { href: string; title: string; chip: string; chipTone: "good" | "alert" | "amber" | "neutral"; desc: string }) {
  const tones = { good: "bg-good-bg text-good", alert: "bg-alert-bg text-alert", amber: "bg-amber-bg text-amber", neutral: "bg-paper text-ink-3 border border-line-2" };
  return (
    <Link href={href} className="group block rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-indigo hover:shadow-md">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <b className="text-[15px] text-ink group-hover:text-indigo">{title}</b>
        <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold ${tones[chipTone]}`}>{chip}</span>
      </div>
      <div className="text-[13px] text-ink-3">{desc} →</div>
    </Link>
  );
}

function Stars({ rating }: { rating: number | null }) {
  if (rating == null) return <span className="text-slate-400">—</span>;
  const full = Math.round(rating);
  return <span className="text-amber-500">{"★".repeat(full)}<span className="text-slate-300">{"★".repeat(5 - full)}</span></span>;
}

function ReviewsCard({ businessId, canEdit, data }: { businessId: number | null; canEdit: boolean; data: ReviewsSummary | undefined }) {
  const cur = data?.current;
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Google reviews &amp; rating</h3>
          <p className="mt-0.5 text-xs text-slate-500">Your live Google star rating and review count — the biggest local-reputation signal (and what AI repeats about you).</p>
        </div>
        {canEdit && <RunJobButton businessId={businessId} jobType="ingest_gbp_reviews" label="Check reviews" variant="secondary" />}
      </div>
      {cur ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <div className="flex items-baseline gap-2"><span className="text-2xl font-bold text-slate-900">{cur.rating ?? "—"}</span><Stars rating={cur.rating} /></div>
            <div className="text-[11px] text-slate-500">{cur.review_count ?? "—"} reviews{data?.rating_delta != null && data.rating_delta !== 0 ? ` · ${data.rating_delta > 0 ? "+" : ""}${data.rating_delta} since last check` : ""}{data?.new_reviews != null && data.new_reviews > 0 ? ` · +${data.new_reviews} new` : ""}</div>
            {data?.history && data.history.length >= 2 && (
              <div className="mt-0.5 text-[11px] text-slate-400">
                Rating over time: {data.history.filter((h) => h.rating != null).map((h) => h.rating).join(" → ")}
              </div>
            )}
          </div>
          {data?.reviews && data.reviews.length > 0 && (
            <ul className="flex-1 space-y-1.5">
              {data.reviews.slice(0, 3).map((r, i) => (
                <li key={i} className="text-xs text-slate-600">
                  <Stars rating={r.rating} /> <span className="text-slate-400">{r.author || "Google user"}:</span> {(r.body || "").slice(0, 120)}{(r.body || "").length > 120 ? "…" : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No Google rating captured yet. Click “Check reviews” to pull it from Google.</p>
      )}
    </Card>
  );
}

const KW_GROUPS: { key: string; label: string }[] = [
  { key: "primary", label: "Primary" },
  { key: "local", label: "Local" },
  { key: "question", label: "Questions customers ask" },
  { key: "secondary", label: "Secondary" },
  { key: "long_tail", label: "Long-tail" },
];

function KeywordsCard({ businessId, canEdit, kws }: { businessId: number | null; canEdit: boolean; kws: TargetKeyword[] | undefined }) {
  const list = kws ?? [];
  const grouped = KW_GROUPS.map((g) => ({ ...g, items: list.filter((k) => (k.kind || "secondary") === g.key) })).filter((g) => g.items.length > 0);
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Keywords to rank for</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            The SEO terms to weave into your website, blog, social &amp; Google Business Profile — found from your site, your
            competitors, and real Google searches. These feed every draft we generate.
          </p>
        </div>
        {canEdit && <RunJobButton businessId={businessId} jobType="keyword_research" label="Find keywords" variant="secondary" />}
      </div>
      {list.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No keywords yet. Click “Find keywords” to research the terms you should target.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {grouped.map((g) => (
            <div key={g.key}>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{g.label}</div>
              <div className="flex flex-wrap gap-1.5">
                {g.items.map((k) => (
                  <span key={k.keyword} title={[k.rationale, k.search_volume != null ? `${k.search_volume.toLocaleString()} searches/mo` : "", k.keyword_difficulty != null ? `difficulty ${k.keyword_difficulty}/100` : ""].filter(Boolean).join(" · ") || undefined}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                    {k.keyword}
                    {k.search_volume != null && <span className="font-mono text-[10px] font-semibold text-emerald-700">{k.search_volume >= 1000 ? `${(k.search_volume / 1000).toFixed(1)}k` : k.search_volume}/mo</span>}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// Multi-row email form that POSTs review-request emails. Handles the keyless `skipped` case
// (email not configured) by showing the preview of what WOULD have been sent.
function SendReviewRequestsForm({ businessId }: { businessId: number | null }) {
  const send = useSendReviewRequests(businessId);
  const [rows, setRows] = useState<{ email: string; first_name: string }[]>([{ email: "", first_name: "" }]);
  const [result, setResult] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(null);

  const update = (i: number, patch: Partial<{ email: string; first_name: string }>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const recipients = rows.filter((r) => r.email.trim()).map((r) => ({ email: r.email.trim(), first_name: r.first_name.trim() || undefined }));

  const submit = () => {
    setResult(null);
    setPreview(null);
    send.mutate(recipients, {
      onSuccess: (res) => {
        if ("skipped" in res && res.skipped) {
          setResult(`Email isn't set up on this server (${res.reason}). Here's what would have been sent:`);
          setPreview(res.preview);
        } else {
          const failed = "failed" in res && res.failed ? ` · ${res.failed} failed` : "";
          setResult(`Sent ${res.sent} review request${res.sent === 1 ? "" : "s"}${failed}.`);
          setRows([{ email: "", first_name: "" }]);
        }
      },
      onError: () => setResult("Couldn't send — please try again."),
    });
  };

  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Send review requests</div>
      <div className="space-y-1.5">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <input type="email" value={r.email} onChange={(e) => update(i, { email: e.target.value })} placeholder="customer@example.com"
              className="min-w-56 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
            <input value={r.first_name} onChange={(e) => update(i, { first_name: e.target.value })} placeholder="First name (optional)"
              className="w-40 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
            {rows.length > 1 && (
              <button onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} className="text-xs text-slate-400 hover:text-slate-600">remove</button>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button onClick={() => setRows((rs) => [...rs, { email: "", first_name: "" }])}
          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">+ Add recipient</button>
        <button onClick={submit} disabled={send.isPending || recipients.length === 0}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
          {send.isPending ? "Sending…" : `Send to ${recipients.length || 0}`}
        </button>
      </div>
      {result && <p className="mt-2 text-xs text-slate-500">{result}</p>}
      {preview && (
        <div className="mt-2 rounded-md bg-slate-50 p-2 text-xs text-slate-600 ring-1 ring-inset ring-slate-200">
          <div className="font-semibold text-slate-700">Subject: {preview.subject}</div>
          <p className="mt-1 whitespace-pre-wrap">{preview.body}</p>
        </div>
      )}
    </div>
  );
}

// "Get more reviews" — the write-review link + copy-paste SMS/email asks, plus the NAP block
// we keep consistent across directory citations (missing fields flagged in amber to fill in).
// Also surfaces negative reviews awaiting a reply (SLA) and a send-review-requests form.
function ReviewRequestCard({ kit, businessId, canEdit, sla }: { kit: ReviewRequestKit | undefined; businessId: number | null; canEdit: boolean; sla: ReviewSla | undefined }) {
  if (!kit) return null;
  const { link, templates, nap } = kit;
  const emailText = `Subject: ${templates.email_subject}\n\n${templates.email_body}`;
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Get more reviews</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            More 5-star reviews lift your local ranking — and they&apos;re what AI repeats about you. Send happy
            customers straight to your {link.source || "Google"} review page.
          </p>
        </div>
      </div>

      {/* Negative reviews awaiting a reply (SLA) — red when any have breached the response window */}
      {sla && sla.summary.awaiting > 0 && (
        <div className={`mt-3 rounded-md px-2.5 py-1.5 text-xs ring-1 ring-inset ${sla.summary.sla_breached > 0 ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-amber-50 text-amber-700 ring-amber-200"}`}>
          <span className="font-semibold">
            {sla.summary.awaiting} negative review{sla.summary.awaiting === 1 ? "" : "s"} awaiting a reply
          </span>
          {sla.summary.sla_breached > 0
            ? ` · ${sla.summary.sla_breached} past your ${sla.sla_hours}h response target — reply now.`
            : ` · respond within ${sla.sla_hours}h.`}
          <Link href="/approvals" className="ml-1 font-medium underline">Reply →</Link>
        </div>
      )}

      {/* write-review link (copyable) */}
      {link.write_review_url && (
        <div className="mt-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Your review link</div>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-md bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700 ring-1 ring-inset ring-slate-200">
              {link.write_review_url}
            </code>
            <CopyButton text={link.write_review_url} label="Copy link" />
            <a
              href={link.write_review_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-slate-50"
            >
              Open →
            </a>
          </div>
        </div>
      )}

      {/* copy-paste templates */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">Ask a customer:</span>
        <CopyButton text={templates.sms} label="Copy SMS" />
        <CopyButton text={emailText} label="Copy email" />
      </div>

      {/* NAP block — consistency across directory citations (shared component) */}
      <div className="mt-4 border-t border-slate-100 pt-3">
        <NapBlock nap={nap} className="bg-transparent p-0" />
      </div>

      {/* Send review-request emails (canEdit-gated) */}
      {canEdit && <SendReviewRequestsForm businessId={businessId} />}
    </Card>
  );
}


// One-line proof line: how many pages WE published are earning search traffic. The deep view
// (per-page clicks + sessions) lives on /search-performance. Hidden until something's published.
function OurContentImpactLine({ impact }: { impact: OurContentImpact | undefined }) {
  if (!impact || impact.totals.assets_published === 0) return null;
  const { assets_with_traffic, assets_published, our_content_clicks } = impact.totals;
  return (
    <Card accent="good">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Our content impact</h3>
          <p className="mt-0.5 text-sm text-slate-600">
            <span className="font-bold text-emerald-700">{assets_with_traffic} of {assets_published}</span> page
            {assets_published === 1 ? "" : "s"} we published {assets_with_traffic === 1 ? "is" : "are"} earning search
            traffic{our_content_clicks > 0 ? ` — ${our_content_clicks.toLocaleString()} Google clicks so far` : ""}.
          </p>
        </div>
        <Link href="/search-performance" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
          See proof →
        </Link>
      </div>
    </Card>
  );
}

function LinkCard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-900/[0.06] transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <span className="text-sm font-bold text-slate-900 group-hover:text-indigo-600">{title} →</span>
      <span className="mt-0.5 text-xs text-slate-500">{desc}</span>
    </Link>
  );
}

// Section landing page for "Search & SEO" — the traditional-search rollup: local Google
// rankings scorecard, competitor standing, and site-audit freshness, with deep links.
// PageSpeed / Core Web Vitals — real Google Lighthouse scores for owned pages. Live-wired to
// /pagespeed; the "Grade pages now" button enqueues the ingest_pagespeed job. Needs PAGESPEED_API_KEY.
function TechnicalHealthCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const ps = usePageSpeed(businessId);
  const run = useRunPageSpeed(businessId);
  const d = ps.data;
  const scoreColor = (v: number | null | undefined) => v == null ? "var(--ink-4)" : v >= 90 ? "#0f9d63" : v >= 50 ? "#c67c15" : "#b1442f";
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Page speed &amp; Core Web Vitals</h3>
          <p className="mt-0.5 text-xs text-slate-500">Real Google Lighthouse scores for your published pages. Slow / failing pages quietly suppress their own ranking &amp; AI citation — these feed the gap model and the advisor.</p>
        </div>
        {canEdit && (
          <button onClick={() => run.mutate(undefined)} disabled={run.isPending}
            className="shrink-0 rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-slate-50 disabled:opacity-60">
            {run.isPending ? "Grading…" : "Grade pages now"}
          </button>
        )}
      </div>
      {d && d.enabled === false ? (
        <p className="mt-3 text-sm text-slate-500">PageSpeed is turned off (<span className="font-mono text-xs">PAGESPEED_ENABLED=0</span>).</p>
      ) : !d || !d.has_data ? (
        <p className="mt-3 text-sm text-slate-500">No page grades yet. Click “Grade pages now” — needs a <span className="font-mono text-xs">PAGESPEED_API_KEY</span> for live scores.</p>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Performance</div><div className="font-display text-[24px] font-semibold" style={{ color: scoreColor(d.avg_performance) }}>{d.avg_performance ?? "—"}</div></div>
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">SEO</div><div className="font-display text-[24px] font-semibold" style={{ color: scoreColor(d.avg_seo) }}>{d.avg_seo ?? "—"}</div></div>
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Pages graded</div><div className="font-display text-[24px] font-semibold text-ink">{d.owned_count ?? 0}</div></div>
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Failing CWV</div><div className="font-display text-[24px] font-semibold" style={{ color: (d.cwv_failing?.length || 0) ? "#b1442f" : "#0f9d63" }}>{d.cwv_failing?.length ?? 0}</div></div>
          </div>
          {(d.technical_gaps?.length || 0) > 0 && (
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Pages needing a fix</div>
              <ul className="space-y-1.5">
                {d.technical_gaps!.slice(0, 5).map((t) => (
                  <li key={t.url} className="flex flex-wrap items-baseline gap-x-2 text-[12.5px]">
                    <span className="truncate font-medium text-ink" style={{ maxWidth: "40ch" }}>{t.url.replace(/^https?:\/\//, "")}</span>
                    <span className="text-slate-500">{t.issues.join("; ")}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// GSC full-surface: index / canonical / schema health per owned page. Live-wired to /index-health;
// populated by the index_own_content job once a GSC connection exists.
function IndexHealthCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const ih = useIndexHealth(businessId);
  const submit = useSubmitSitemap(businessId);
  const d = ih.data;
  if (!d) return null;
  const gaps = d.technical_gaps ?? [];
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Index &amp; canonical health</h3>
          <p className="mt-0.5 text-xs text-slate-500">Straight from Google Search Console: which published pages Google has indexed, where it prefers a <em>different</em> URL (canonical loss), and whether your structured data is valid — the concrete reasons a page can&apos;t rank or be cited by AI.</p>
        </div>
        {canEdit && d.has_data && (
          <button onClick={() => submit.mutate()} disabled={submit.isPending}
            className="shrink-0 rounded-[10px] border border-line bg-white px-3 py-1.5 text-[13px] font-semibold text-ink hover:bg-slate-50 disabled:opacity-60">
            {submit.isPending ? "Submitting…" : "Submit sitemap"}
          </button>
        )}
      </div>
      {!d.has_data ? (
        <p className="mt-3 text-sm text-slate-500">No inspection data yet. Connect Google Search Console in <a href="/integrations" className="font-semibold text-indigo hover:underline">Integrations</a> — then the indexing job harvests per-page index, canonical &amp; schema status.</p>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Indexed</div><div className="font-display text-[24px] font-semibold text-ink">{d.indexed ?? 0}<span className="text-[13px] text-ink-4">/{d.checked ?? 0}</span></div></div>
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Not indexed</div><div className="font-display text-[24px] font-semibold" style={{ color: (d.not_indexed?.length || 0) ? "#c67c15" : "#0f9d63" }}>{d.not_indexed?.length ?? 0}</div></div>
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Canonical loss</div><div className="font-display text-[24px] font-semibold" style={{ color: (d.canonical_loss?.length || 0) ? "#b1442f" : "#0f9d63" }}>{d.canonical_loss?.length ?? 0}</div></div>
            <div className="rounded-[12px] border border-line bg-paper p-3"><div className="eyebrow mb-1">Schema invalid</div><div className="font-display text-[24px] font-semibold" style={{ color: (d.schema_invalid?.length || 0) ? "#b1442f" : "#0f9d63" }}>{d.schema_invalid?.length ?? 0}</div></div>
          </div>
          {gaps.length > 0 && (
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Pages needing a fix</div>
              <ul className="space-y-1.5">
                {gaps.slice(0, 5).map((t) => (
                  <li key={t.url} className="flex flex-wrap items-baseline gap-x-2 text-[12.5px]">
                    <span className="truncate font-medium text-ink" style={{ maxWidth: "40ch" }}>{t.url.replace(/^https?:\/\//, "")}</span>
                    <span className="text-slate-500">{t.issues.join("; ")}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function SeoOverviewPage() {
  const { businessId, businesses, loading, canEdit } = useBusiness();
  const ranks = useLocalRankings(businessId);
  const compare = useCompare(businessId);
  const site = useSiteAudit(businessId);
  const goal = useLocalSeoGoal(businessId);
  const kws = useTargetKeywords(businessId);
  const revs = useReviews(businessId);
  const reviewKit = useReviewRequest(businessId);
  const reviewSla = useReviewSla(businessId);
  const impact = useOurContentImpact(businessId);
  const health = useSiteHealthTrend(businessId);
  const schema = useSchemaVerify(businessId);
  const gsc = useGscSummary(businessId);

  if (loading) return <Spinner />;
  if (businesses.length === 0) {
    return (
      <div>
        <PageHeader eyebrow="Search & SEO · Overview" title="Your Google visibility" />
        <EmptyState
          title="No data yet"
          why="Set up a business and run a local rank check to see your search visibility."
          cta={{ label: "Set up a business", href: "/onboarding" }}
        />
      </div>
    );
  }
  if (ranks.isLoading) return <Spinner />;

  const s = ranks.data?.summary ?? null;
  const c = compare.data ?? {};
  const subjectRank = c.subject_rank ?? null;
  const fieldSize = c.field_size ?? null;
  const siteAsOf = site.data?.created_at ? new Date(site.data.created_at).toLocaleDateString() : null;

  // v2 top: readiness + delta, schema coverage, and connection state.
  const readiness = health.data?.length ? health.data[health.data.length - 1].score : null;
  const readinessDelta = health.data && health.data.length >= 2 ? Math.round((health.data[health.data.length - 1].score) - health.data[0].score) : null;
  const schemaDeployed = schema.data?.deployed_schema.length ?? null;
  const schemaTotal = schema.data ? schema.data.deployed_schema.length + schema.data.recommended_missing.length : null;
  const topMissingSchema = schema.data?.recommended_missing[0] ?? null;
  const pagesChecked = schema.data?.checked_pages ?? null;
  const gscConnected = !!(gsc.data?.has_data || gsc.data?.collecting);
  const p1 = s ? Math.round(s.page_one_rate * 100) : null;
  const mp = s ? Math.round(s.local_pack_rate * 100) : null;

  const seoActions: { title: string; note?: string | null; href: string }[] = [];
  if (reviewSla.data && reviewSla.data.summary.awaiting > 0) {
    const n = reviewSla.data.summary.awaiting;
    seoActions.push({ title: `Reply to ${n} negative review${n === 1 ? "" : "s"}`, note: "Protect your local rating — respond fast.", href: "/approvals" });
  }
  seoActions.push({ title: "Publish content targeting your priority keywords", note: "Turn target keywords into pages that rank.", href: "/content/briefs" });
  if (!s || s.page_one_rate < 0.5) {
    seoActions.push({ title: "Fix the technical SEO issues holding you back", note: "Indexing + on-page health.", href: "/seo" });
  }
  seoActions.push({ title: "Win the local searches you're losing to rivals", note: "Where competitors outrank you.", href: "/local-seo" });

  return (
    <div>
      <PageHeader
        eyebrow="Search & SEO · Overview"
        title="Your Google visibility"
        subtitle="Traditional search — your site's health for AI & Google crawlers, local rankings, and the moves to climb. A summary of every tab."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      <div className="space-y-5">
        {/* KPI tiles */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile k="AI-crawler readiness" value={readiness != null ? String(readiness) : "—"} small="/100" color={healthColor(readiness)} sub={readinessDelta != null ? `From site health · ${readinessDelta >= 0 ? "+" : ""}${readinessDelta}` : "From site health"} />
          <Tile k="On page one" value={p1 != null ? `${p1}%` : "—"} sub="Local searches, Google p.1" />
          <Tile k="In the map pack" value={mp != null ? `${mp}%` : "—"} sub="Local 3-pack" />
          <Tile k="Schema coverage" value={schemaDeployed != null ? String(schemaDeployed) : "—"} small={schemaTotal != null ? `/${schemaTotal}` : undefined} color={schemaDeployed === 0 ? "var(--alert)" : undefined} sub={schemaDeployed === 0 ? "No structured data yet" : "Structured-data types live"} />
        </div>

        {/* Site health — the important one */}
        <Card>
          <SecHead title="Site health" note="how readable your site is to AI & Google" link={{ label: "Full site audit", href: "/seo" }} />
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-4">
              <SiteHealthGauge score={readiness} />
              <div>
                <span className="inline-flex rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold uppercase" style={{ background: `${healthColor(readiness)}1a`, color: healthColor(readiness) }}>{healthLabel(readiness)}</span>
                {readinessDelta != null && readinessDelta !== 0 && <span className={`ml-1.5 inline-flex rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold ${readinessDelta >= 0 ? "bg-good-bg text-good" : "bg-alert-bg text-alert"}`}>{readinessDelta >= 0 ? "▲" : "▼"} {readinessDelta >= 0 ? "+" : ""}{readinessDelta}</span>}
                <p className="mt-2.5 max-w-[220px] text-[12.5px] leading-relaxed text-ink-3">When AI can&apos;t read your site, it uses forums and reviews you don&apos;t control.</p>
              </div>
            </div>
            <div className="grid min-w-[280px] flex-1 grid-cols-2 gap-3">
              <div className="rounded-[12px] border border-line bg-paper p-3.5">
                <div className="eyebrow mb-1.5">Pages checked</div>
                <div className="font-display text-[24px] font-semibold tracking-[-0.02em] text-ink">{pagesChecked ?? "—"}</div>
              </div>
              <div className="rounded-[12px] border border-line bg-paper p-3.5">
                <div className="eyebrow mb-1.5">Top fix</div>
                <div className="mt-1 text-[14px] font-semibold text-ink">{topMissingSchema ? `Add ${topMissingSchema} schema` : "Site is in good shape"}</div>
                {topMissingSchema && <div className="text-[12px] text-ink-4">helps AI extract your facts</div>}
              </div>
            </div>
          </div>
        </Card>

        {/* Page speed / Core Web Vitals — technical health of published pages */}
        <TechnicalHealthCard businessId={businessId} canEdit={canEdit} />

        {/* Index / canonical / schema health — GSC full-surface URL Inspection */}
        <IndexHealthCard businessId={businessId} canEdit={canEdit} />

        {/* Do this next + Goal */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Card>
            <SecHead title="Do this next" note="highest-impact SEO moves" />
            <div>
              {seoActions.slice(0, 3).map((a, i) => (
                <div key={i} className="flex gap-3 border-b border-line py-3 last:border-0">
                  <div className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-lg bg-ink font-mono text-[13px] font-semibold text-white">{i + 1}</div>
                  <div><div className="text-[14px] font-semibold text-ink">{a.title}</div>{a.note && <div className="mt-0.5 text-[12.5px] text-ink-3">{a.note}</div>}</div>
                </div>
              ))}
            </div>
            <Link href="/content/work-orders" className="mt-3 inline-flex items-center gap-1 text-[13px] font-semibold text-indigo hover:text-indigo-strong">Your tasks<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[13px] w-[13px]"><path d="M5 12h14M13 6l6 6-6 6" /></svg></Link>
          </Card>
          <SeoGoalCard goal={goal.data} gscConnected={gscConnected} />
        </div>

        {/* tab summaries */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <TabSummary href="/search-performance" title="Search Console" chip={gscConnected ? "Connected" : "Not connected"} chipTone={gscConnected ? "good" : "neutral"} desc={gscConnected ? "Real clicks & rankings" : "Connect to import real clicks & rankings"} />
          <TabSummary href="/local-seo" title="Local rankings" chip={p1 != null ? `${p1}% page 1` : "No data"} chipTone={p1 && p1 >= 50 ? "good" : "alert"} desc={s ? `${s.queries} tracked searches` : "Run a local rank check"} />
          <TabSummary href="/seo" title="Site health" chip={readiness != null ? `${readiness} · ${healthLabel(readiness)}` : "No crawl"} chipTone={readiness == null ? "neutral" : readiness >= 60 ? "good" : readiness >= 40 ? "amber" : "alert"} desc="Page-by-page audit & schema fixes" />
        </div>

        {/* real Google clicks + content-earned traffic (kept from the info-flow view) */}
        <SearchPerformanceCard businessId={businessId} />
        <OurContentImpactLine impact={impact.data} />

        {/* Supporting detail — collapsed by default; deep dives live in the Search & SEO hub tabs. */}
        <DataSection title="More detail — reviews, keywords, AI-readiness, competitors & site" headline="Your Google reviews + how to get more, the keywords to target, AI-crawler readiness, competitive standing, and site health." detailsLabel="Show detail">
          <div className="space-y-6">
            <ReviewsCard businessId={businessId} canEdit={canEdit} data={revs.data} />
            <ReviewRequestCard kit={reviewKit.data} businessId={businessId} canEdit={canEdit} sla={reviewSla.data} />
            <KeywordsCard businessId={businessId} canEdit={canEdit} kws={kws.data} />
            <AiCrawlerReadinessCard businessId={businessId} />

            {/* Competitor standing */}
            <Card accent={subjectRank != null && fieldSize != null && subjectRank <= Math.ceil(fieldSize / 2) ? "good" : "bad"}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold tracking-tight text-slate-900">Competitive standing (AI answers)</h3>
                  {subjectRank != null ? (
                    <p className="mt-1 text-sm text-slate-600">
                      AI surfaces you at{" "}
                      <span className="font-bold text-slate-900">rank {subjectRank} of {fieldSize}</span> for category questions.
                    </p>
                  ) : (
                    <p className="mt-1 text-sm text-slate-600">No competitor benchmark yet.</p>
                  )}
                </div>
                <Link href="/competitors" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">Compare →</Link>
              </div>
            </Card>

            {/* Site technical health */}
            <Card>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold tracking-tight text-slate-900">Site &amp; technical SEO</h3>
                  <p className="mt-1 text-sm text-slate-600">
                    {siteAsOf ? `Last crawled ${siteAsOf}. Review technical issues and on-page coverage.` : "No site crawl yet — run one to surface technical SEO issues."}
                  </p>
                </div>
                <Link href="/seo" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">Open →</Link>
              </div>
            </Card>
          </div>
        </DataSection>

        <div>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Go deeper</div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <LinkCard href="/seo" title="Site / technical SEO" desc="On-page + technical issues." />
            <LinkCard href="/local-seo" title="Local rankings" desc="Google organic + map pack." />
            <LinkCard href="/competitors" title="Competitors" desc="Benchmark vs. your rivals." />
          </div>
        </div>
      </div>
    </div>
  );
}
