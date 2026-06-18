"use client";

import { useState } from "react";
import { Term } from "./Term";

// ---- shape of the crawl summary we render (subset we use) ----
type PageAudit = {
  url: string;
  status?: number;
  title?: string;
  meta_description?: string;
  h1_count?: number;
  word_count?: number;
  has_canonical?: boolean;
  schema_types?: string[];
  issues?: string[];
  semantic?: { citation_readiness_score?: number | null };
};
type SiteSummary = {
  pages_crawled?: number;
  schema_present?: string[];
  schema_gaps?: string[];
  issue_counts?: Record<string, number>;
  avg_semantic_readiness?: number | null;
  top_missing_entities?: string[];
  pages?: PageAudit[];
};

// issue code -> human label + the fix + severity
const ISSUE_META: Record<string, { label: string; fix: string; sev: "high" | "med" }> = {
  missing_title: { label: "Missing page title", fix: "Add a unique, descriptive <title> (50–60 characters).", sev: "high" },
  missing_meta_description: { label: "Missing meta description", fix: "Write a compelling ~155-character meta description.", sev: "high" },
  missing_h1: { label: "Missing H1 heading", fix: "Add one clear H1 that states the page’s topic.", sev: "high" },
  no_schema: { label: "No structured data (schema)", fix: "Add Organization / LocalBusiness / Review JSON-LD markup.", sev: "high" },
  thin_content: { label: "Thin content", fix: "Expand to 300+ words of substantive, original copy.", sev: "med" },
  missing_canonical: { label: "Missing canonical tag", fix: "Add a canonical <link> to avoid duplicate-content issues.", sev: "med" },
  missing_meta: { label: "Missing meta description", fix: "Write a compelling ~155-character meta description.", sev: "high" },
};
const issueLabel = (k: string) => ISSUE_META[k]?.label ?? k.replace(/[_:].*/, "").replace(/_/g, " ");
const issueFix = (k: string) => ISSUE_META[k]?.fix ?? "Review and resolve this issue.";
const issueSev = (k: string) => ISSUE_META[k]?.sev ?? "med";

// drop WordPress plumbing (feeds, json/xmlrpc, asset files) so the user sees real pages
const isContentUrl = (u: string) =>
  !/(\/feed\/|\/wp-json|xmlrpc|oembed)|\.(css|js|json|xml|png|jpe?g|gif|svg|ico|woff2?)(\?|$)/i.test(u);

const pathOf = (u: string) => {
  try {
    const url = new URL(u);
    return (url.pathname || "/") + (url.search ? url.search.slice(0, 24) : "");
  } catch {
    return u;
  }
};
const scoreOf = (p: PageAudit) =>
  typeof p.semantic?.citation_readiness_score === "number"
    ? Math.round(p.semantic.citation_readiness_score)
    : Math.max(0, 100 - (p.issues?.length ?? 0) * 18);

const band = (s: number) =>
  s >= 70 ? { t: "text-green-700", b: "bg-green-50 border-green-200", word: "Good" }
  : s >= 40 ? { t: "text-amber-700", b: "bg-amber-50 border-amber-200", word: "Needs work" }
  : { t: "text-red-700", b: "bg-red-50 border-red-200", word: "Poor" };

// ---- tiny inline icons ----
function Check() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5 shrink-0 text-green-600" fill="currentColor" aria-hidden>
      <path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0L3.3 9.7a1 1 0 111.4-1.4l3.8 3.8 6.8-6.8a1 1 0 011.4 0z" clipRule="evenodd" />
    </svg>
  );
}
function X() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5 shrink-0 text-red-500" fill="currentColor" aria-hidden>
      <path fillRule="evenodd" d="M10 8.6L5.7 4.3 4.3 5.7 8.6 10l-4.3 4.3 1.4 1.4L10 11.4l4.3 4.3 1.4-1.4L11.4 10l4.3-4.3-1.4-1.4L10 8.6z" clipRule="evenodd" />
    </svg>
  );
}

function Stat({ label, value, sub }: { label: React.ReactNode; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-gray-900">{value}</div>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

export function SiteAuditView({ summary }: { summary: Record<string, unknown> }) {
  const s = summary as SiteSummary;
  const allPages = s.pages ?? [];
  const pages = allPages.filter((p) => isContentUrl(p.url)).sort((a, b) => scoreOf(a) - scoreOf(b));
  const needWork = pages.filter((p) => (p.issues?.length ?? 0) > 0).length;
  const overall = typeof s.avg_semantic_readiness === "number" ? Math.round(s.avg_semantic_readiness) : null;
  const issues = Object.entries(s.issue_counts ?? {})
    .filter(([k]) => !k.startsWith("fetch_failed"))
    .sort((a, b) => b[1] - a[1]);
  const schemaPresent = s.schema_present ?? [];
  const schemaGaps = s.schema_gaps ?? [];
  const [open, setOpen] = useState<string | null>(null);

  const verdict =
    overall == null
      ? "We couldn't score your site's readiness this run."
      : overall >= 60
        ? `Your website is easy for AI to read and quote (${overall}/100). Keep it fresh.`
        : overall >= 40
          ? `Your website is only moderately easy for AI to quote (${overall}/100). Healthy sites score 60+ — the fixes below close the gap.`
          : `Your website is hard for AI to read and quote (${overall}/100). When AI can't pull a clean answer from your site, it uses forums and reviews you don't control. Healthy sites score 60+.`;

  return (
    <div className="space-y-6">
      {/* ---- plain-English verdict ---- */}
      <div className={`rounded-xl border p-4 ${overall == null ? "border-gray-200 bg-gray-50" : band(overall).b}`}>
        <p className={`text-sm font-medium ${overall == null ? "text-gray-600" : band(overall).t}`}>{verdict}</p>
      </div>

      {/* ---- scorecard band ---- */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label={<Term name="semantic readiness">Overall readiness</Term>}
          value={
            <span className={overall === null ? "text-gray-400" : band(overall).t}>
              {overall === null ? "—" : `${overall}`}
              <span className="text-base font-normal text-gray-400">/100</span>
            </span>
          }
          sub={overall === null ? undefined : band(overall).word}
        />
        <Stat label="Content pages reviewed" value={pages.length} sub={`of ${s.pages_crawled ?? allPages.length} found`} />
        <Stat label="Pages needing work" value={<span className={needWork ? "text-amber-700" : "text-green-700"}>{needWork}</span>} sub="have ≥1 issue" />
        <Stat
          label={<Term name="schema">Schema coverage</Term>}
          value={<span className={schemaPresent.length ? "text-green-700" : "text-red-600"}>{schemaPresent.length}/{schemaPresent.length + schemaGaps.length}</span>}
          sub={schemaPresent.length ? "types present" : "none present"}
        />
      </div>
      <p className="-mt-3 text-xs text-gray-400">
        We found {s.pages_crawled ?? allPages.length} URLs and reviewed the {pages.length} that are real content
        pages — system files (feeds, code, images) and any that failed to load are skipped.
      </p>
      {pages.length > 0 && pages.length <= 2 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Only {pages.length} content {pages.length === 1 ? "page" : "pages"} could be analyzed this run, so treat
          this as a partial snapshot. As your site grows (or the crawler reaches more pages), the picture fills in.
        </div>
      )}

      {/* ---- site-wide priority fixes ---- */}
      {issues.length > 0 && (
        <div>
          <h2 className="mb-1 text-base font-semibold text-gray-900">Top fixes across the site</h2>
          <p className="mb-3 text-sm text-gray-500">Ordered by how many pages are affected.</p>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            {issues.map(([code, count], i) => (
              <div key={code} className={`flex items-start gap-3 px-4 py-3 ${i ? "border-t border-gray-100" : ""}`}>
                <span className={`mt-0.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${issueSev(code) === "high" ? "bg-red-500" : "bg-amber-400"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">{issueLabel(code)}</span>
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">{count} {count === 1 ? "page" : "pages"}</span>
                  </div>
                  <div className="text-sm text-gray-500">{issueFix(code)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ---- schema + missing topics ---- */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-gray-200 p-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-900">Structured data (schema)</h3>
          {schemaPresent.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {schemaPresent.map((t) => (
                <span key={t} className="inline-flex items-center gap-1 rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-xs text-green-700"><Check />{t}</span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {schemaGaps.map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs text-red-700"><X />{t}</span>
            ))}
          </div>
          {schemaGaps.length > 0 && <p className="mt-2 text-xs text-gray-500">Add these JSON-LD types so AI + search engines can read the business clearly.</p>}
        </div>
        <div className="rounded-lg border border-gray-200 p-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-900">
            <Term name="missing topics">Topics the site barely covers</Term>
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {(s.top_missing_entities ?? []).map((e) => (
              <span key={e} className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-700">{e}</span>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-500">
            AI expects a business like yours to cover these. Where your site doesn&apos;t, AI fills the gap from
            outside sources you don&apos;t control — so a page on each is a content opportunity.
          </p>
        </div>
      </div>

      {/* ---- per-page breakdown ---- */}
      <div>
        <h2 className="mb-1 text-base font-semibold text-gray-900">Page-by-page</h2>
        <p className="mb-3 text-sm text-gray-500">Lowest-scoring pages first — click a page for the fixes.</p>
        <div className="space-y-2">
          {pages.map((p) => {
            const score = scoreOf(p);
            const c = band(score);
            const isOpen = open === p.url;
            const good: string[] = [];
            if (p.title) good.push("Title");
            if (p.meta_description) good.push("Meta description");
            if ((p.h1_count ?? 0) > 0) good.push("H1");
            if (p.has_canonical) good.push("Canonical");
            if ((p.schema_types?.length ?? 0) > 0) good.push("Schema");
            if ((p.word_count ?? 0) >= 300) good.push("Enough content");
            return (
              <div key={p.url} className="overflow-hidden rounded-lg border border-gray-200">
                <button
                  onClick={() => setOpen(isOpen ? null : p.url)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50"
                >
                  <span className={`flex h-9 w-12 shrink-0 flex-col items-center justify-center rounded-md border text-sm font-semibold ${c.b} ${c.t}`}>
                    {score}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-gray-900">{pathOf(p.url)}</div>
                    <div className="truncate text-xs text-gray-400">{p.title || "(no title)"} · {p.word_count ?? 0} words</div>
                  </div>
                  <span className={`hidden shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium sm:inline ${c.b} ${c.t}`}>{c.word}</span>
                  {(p.issues?.length ?? 0) > 0 && (
                    <span className="shrink-0 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">{p.issues!.length} {p.issues!.length === 1 ? "issue" : "issues"}</span>
                  )}
                  <svg viewBox="0 0 20 20" className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`} fill="currentColor" aria-hidden><path d="M5.2 7.5L10 12.3l4.8-4.8 1.2 1.2-6 6-6-6z" /></svg>
                </button>
                {isOpen && (
                  <div className="border-t border-gray-100 bg-gray-50/60 px-4 py-3">
                    <a href={p.url} target="_blank" rel="noreferrer" className="mb-3 inline-block break-all text-xs text-blue-600 hover:underline">{p.url}</a>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">Working well</div>
                        {good.length ? (
                          <ul className="space-y-1">
                            {good.map((g) => (<li key={g} className="flex items-center gap-1.5 text-sm text-gray-700"><Check />{g}</li>))}
                          </ul>
                        ) : <p className="text-sm text-gray-400">—</p>}
                      </div>
                      <div>
                        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">Fix these</div>
                        {(p.issues?.length ?? 0) ? (
                          <ul className="space-y-2">
                            {p.issues!.map((iss) => (
                              <li key={iss} className="flex items-start gap-1.5 text-sm">
                                <X />
                                <span><span className="font-medium text-gray-800">{issueLabel(iss)}.</span> <span className="text-gray-500">{issueFix(iss)}</span></span>
                              </li>
                            ))}
                          </ul>
                        ) : <p className="flex items-center gap-1.5 text-sm text-green-700"><Check />No issues found.</p>}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {pages.length === 0 && <p className="text-sm text-gray-500">No content pages found in the crawl.</p>}
        </div>
      </div>
    </div>
  );
}
