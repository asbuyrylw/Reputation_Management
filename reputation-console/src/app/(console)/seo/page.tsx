"use client";

import { useBusiness } from "@/lib/business";
import { useSiteAudit, useInternalLinks, useIndexingStatus, useBacklinkProfile } from "@/lib/hooks";
import { apiBase } from "@/lib/api";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SiteAuditView } from "@/components/SiteAuditView";
import type { InternalLinks, IndexingStatus, BacklinkProfile } from "@/lib/types";

// "Internal linking" — owned pages with too few internal links + concrete link suggestions.
// Internal links spread authority across your site so more pages rank.
function InternalLinkingCard({ data }: { data: InternalLinks | undefined }) {
  if (!data || (data.summary.under_linked === 0 && data.suggestions.length === 0)) return null;
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Internal linking</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Linking your own pages to each other spreads ranking authority across the site — these owned pages have too few
            internal links pointing to them.
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
          {data.summary.under_linked} under-linked
        </span>
      </div>
      {data.under_linked.length > 0 && (
        <ul className="mt-3 space-y-1">
          {data.under_linked.slice(0, 5).map((p) => (
            <li key={p.url} className="flex items-center justify-between gap-2 text-sm">
              <a href={p.url} target="_blank" rel="noreferrer" className="truncate text-indigo-600 hover:underline">{p.title || p.url}</a>
              <span className="shrink-0 text-xs text-slate-400">{p.internal_links} link{p.internal_links === 1 ? "" : "s"} in</span>
            </li>
          ))}
        </ul>
      )}
      {data.suggestions.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Suggested links</div>
          <ul className="space-y-1.5 text-xs text-slate-700">
            {data.suggestions.slice(0, 5).map((s, i) => (
              <li key={i}>
                Link from <span className="font-medium">{s.from}</span> to <span className="font-medium">{s.to}</span> with anchor
                {" "}“<span className="text-indigo-600">{s.anchor}</span>” <span className="text-slate-400">— {s.why}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

// "Indexing" — which owned pages Google has indexed vs. needs a manual "Request indexing" in
// Search Console. When GSC isn't connected we show a connect hint instead. Includes the RSS
// feed link, which speeds up discovery of new pages.
function IndexingCard({ data, feedUrl }: { data: IndexingStatus | undefined; feedUrl: string }) {
  if (!data) return null;
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Indexing</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Pages Google has actually indexed can rank; un-indexed ones can&apos;t. Submitting them is a manual step in
            Search Console.
          </p>
        </div>
        {data.summary && (
          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
            {data.summary.indexed}/{data.summary.checked} indexed
          </span>
        )}
      </div>
      {data.skipped ? (
        <p className="mt-3 rounded-md bg-sky-50 px-2.5 py-1.5 text-xs text-sky-700 ring-1 ring-inset ring-sky-200">
          Connect Google Search Console to check indexing for your {data.urls ?? 0} published page
          {data.urls === 1 ? "" : "s"}. {data.reason}
        </p>
      ) : (
        <>
          {data.summary && data.summary.needs_request > 0 && (
            <p className="mt-3 text-sm text-slate-700">
              <span className="font-semibold text-amber-700">{data.summary.needs_request}</span> page
              {data.summary.needs_request === 1 ? "" : "s"} not indexed yet — open each in Search Console and click
              “Request indexing.”
            </p>
          )}
          {data.not_indexed && data.not_indexed.length > 0 && (
            <ul className="mt-2 space-y-1">
              {data.not_indexed.slice(0, 6).map((p) => (
                <li key={p.url} className="flex items-center justify-between gap-2 text-sm">
                  <a href={p.url} target="_blank" rel="noreferrer" className="truncate text-indigo-600 hover:underline">{p.title || p.url}</a>
                  <span className="shrink-0 text-xs text-amber-600">{p.coverage || "needs request"}</span>
                </li>
              ))}
            </ul>
          )}
          {data.summary && data.summary.needs_request === 0 && (
            <p className="mt-3 text-sm font-medium text-emerald-700">Every published page is indexed. 👍</p>
          )}
        </>
      )}
      <div className="mt-3 border-t border-slate-100 pt-2 text-xs text-slate-500">
        Speed up discovery by submitting your{" "}
        <a href={feedUrl} target="_blank" rel="noreferrer" className="font-medium text-indigo-600 hover:underline">content RSS feed</a>{" "}
        to Search Console.
      </div>
    </Card>
  );
}

// "Backlink profile" — a snapshot from a backlink data source (only shown when configured),
// surfacing lost referring domains worth reclaiming.
function BacklinkProfileCard({ data }: { data: BacklinkProfile | undefined }) {
  if (!data || !data.has_data) return null;
  const entries = Object.entries(data.profile ?? {}).filter(([, v]) => v != null && typeof v !== "object");
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Backlink profile</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Links from other sites are a core ranking + AI-trust signal.{data.source ? ` Source: ${data.source}.` : ""}
            {data.as_of ? ` As of ${new Date(data.as_of).toLocaleDateString()}.` : ""}
          </p>
        </div>
      </div>
      {entries.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          {entries.slice(0, 6).map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-2">
              <dt className="text-xs capitalize text-slate-500">{k.replace(/_/g, " ")}</dt>
              <dd className="font-semibold text-slate-900">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {data.lost_domains && data.lost_domains.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          <div className="font-semibold">Recently lost referring domains ({data.lost_domains.length}):</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {data.lost_domains.slice(0, 12).map((d) => (
              <span key={d} className="rounded-full bg-white px-1.5 py-0.5 text-[10px] text-amber-700 ring-1 ring-inset ring-amber-200">{d}</span>
            ))}
          </div>
          <div className="mt-1 text-amber-600">Worth re-earning these links — reach out or refresh the page they pointed to.</div>
        </div>
      )}
    </Card>
  );
}

export default function SeoPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useSiteAudit(businessId);
  const internalLinks = useInternalLinks(businessId);
  const indexing = useIndexingStatus(businessId);
  const backlinks = useBacklinkProfile(businessId);

  if (isLoading) return <Spinner />;

  const feedUrl = businessId ? `${apiBase()}/businesses/${businessId}/content-feed.xml` : "#";

  return (
    <div>
      <PageHeader
        title="SEO / site audit"
        subtitle="The technical and content health of your own website, from the latest crawl — what to fix, page by page."
      />

      <div className="space-y-4">
        {/* Internal linking + indexing + backlinks (render only when there's something to show) */}
        <InternalLinkingCard data={internalLinks.data} />
        <IndexingCard data={indexing.data} feedUrl={feedUrl} />
        <BacklinkProfileCard data={backlinks.data} />

        {!data ? (
          <Card>
            <p className="text-sm text-slate-600">No site audit yet — it runs as part of a full audit.</p>
          </Card>
        ) : (
          <div>
            <div className="mb-3 text-xs text-slate-400">As of {new Date(data.created_at).toLocaleDateString()}</div>
            <SiteAuditView summary={data.summary} />
          </div>
        )}
      </div>
    </div>
  );
}
