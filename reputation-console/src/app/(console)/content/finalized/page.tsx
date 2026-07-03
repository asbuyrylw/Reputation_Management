"use client";

import Link from "next/link";
import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAssets, usePatchAsset, useAssetPlacements, useAddPlacement, useUpdatePlacement, useComplianceLedger, useOurContentImpact, useGscSummary } from "@/lib/hooks";
import { Card, PageHeader, Spinner, Chip, Input, Button } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { SecHead } from "@/components/DashboardV2";
import { AssetPublishPanel } from "@/components/AssetPublishPanel";
import { StatusBadge } from "@/components/content/StatusBadge";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";
import { ComplianceNotice } from "@/components/content/ComplianceNotice";
import type { Asset } from "@/lib/types";

const host = (u: string) => { try { return new URL(u).pathname || u; } catch { return u; } };

// Per-piece Google Search Console traffic for the content we published — the causal proof loop
// (did our content start earning clicks?). Reads /our-content-impact (assets ↔ latest gsc_page_stats).
function SearchTrafficSection({ businessId }: { businessId: number | null }) {
  const { data } = useOurContentImpact(businessId);
  const { data: gsc } = useGscSummary(businessId);
  const rows = (data?.assets ?? []).slice().sort((a, b) => b.gsc_clicks - a.gsc_clicks);
  if (rows.length === 0) return null; // nothing published-live with a URL yet
  const connected = !!(gsc?.has_data || gsc?.collecting);
  const t = data?.totals;
  return (
    <section>
      <SecHead title="Search traffic" note="the Google clicks each published piece earns" link={{ label: "Search Console", href: "/search-performance" }} />
      {!connected ? (
        <ComplianceNotice tone="info" title="Connect Google Search Console to see real traffic">
          Once connected, each published piece shows the clicks, impressions, and CTR it earns on Google — not zeros. <Link href="/integrations" className="font-semibold text-indigo hover:text-indigo-strong">Connect →</Link>
        </ComplianceNotice>
      ) : (
        <>
          {t && (
            <div className="mb-2 text-[13px] text-ink-3">
              <b className="font-semibold text-good">{t.assets_with_traffic} of {t.assets_published}</b> published piece{t.assets_published === 1 ? "" : "s"} earning search traffic
              {t.our_content_clicks > 0 ? <> · <b className="font-semibold text-ink-2">{t.our_content_clicks.toLocaleString()}</b> Google clicks so far</> : null}
            </div>
          )}
          <TableContainer>
            <thead>
              <tr><Th className="w-[42%]">Piece</Th><Th>Destination</Th><Th>Published</Th><Th>Clicks</Th><Th>Impressions</Th><Th>CTR</Th></tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.asset_id}>
                  <Td><span className="font-semibold text-ink">{a.title || "Untitled piece"}</span></Td>
                  <Td><a href={a.published_url} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-indigo hover:underline">{host(a.published_url)}</a></Td>
                  <Td className="whitespace-nowrap text-ink-3">{fmtDate(a.published_at)}</Td>
                  <Td><span className={`font-mono font-semibold ${a.gsc_clicks > 0 ? "text-good" : "text-ink-4"}`}>{a.gsc_clicks.toLocaleString()}</span></Td>
                  <Td className="font-mono text-ink-3">{a.gsc_impressions.toLocaleString()}</Td>
                  <Td className="font-mono text-ink-3">{a.gsc_ctr != null ? `${(a.gsc_ctr * 100).toFixed(1)}%` : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </TableContainer>
        </>
      )}
    </section>
  );
}

function fmtDate(d?: string | null): string {
  if (!d) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${m[2]}-${m[3]}-${m[1]}` : d;
}

const COMMON_CHANNELS = ["Website", "Google Business Profile", "Facebook", "Instagram", "LinkedIn", "X", "YouTube"];

// Per-asset multi-surface distribution checklist — track WHERE this asset was posted, not just
// that it exists. The amplification value of content is in its distribution.
function DistributionChecklist({ assetId, businessId, canEdit }: { assetId: number; businessId: number | null; canEdit: boolean }) {
  const { data: placements } = useAssetPlacements(businessId, assetId);
  const add = useAddPlacement(businessId);
  const update = useUpdatePlacement(businessId);
  const [urlFor, setUrlFor] = useState<Record<number, string>>({});
  const have = new Set((placements ?? []).map((p) => p.channel));
  const publishedN = (placements ?? []).filter((p) => p.status === "published").length;

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="text-xs font-medium text-ink-3">Distribution{placements && placements.length > 0 ? ` — ${publishedN}/${placements.length} posted` : ""}</div>
      {(placements ?? []).length > 0 && (
        <ul className="mt-1.5 space-y-1.5">
          {placements!.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-2 text-xs">
              <Chip tone={p.status === "published" ? "good" : p.status === "skipped" ? "neutral" : "info"}>{p.channel}</Chip>
              {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="break-all text-indigo hover:text-indigo-strong hover:underline">{p.url}</a> : <span className="text-ink-4">{p.status}</span>}
              {canEdit && p.status !== "published" && (
                <span className="flex items-center gap-1">
                  <Input value={urlFor[p.id] ?? ""} onChange={(e) => setUrlFor((s) => ({ ...s, [p.id]: e.target.value }))}
                    placeholder="link (optional)" className="w-40 px-1.5 py-0.5 text-[11px]" />
                  <Button variant="primary" onClick={() => update.mutate({ assetId, placementId: p.id, status: "published", url: urlFor[p.id]?.trim() || undefined })}
                    className="px-1.5 py-0.5 text-[11px]">Mark posted</Button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <div className="mt-2 flex flex-wrap gap-1">
          {COMMON_CHANNELS.filter((c) => !have.has(c)).map((c) => (
            <button key={c} onClick={() => add.mutate({ assetId, channel: c })}
              className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-3 hover:bg-line">+ {c}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function AssetRow({ a, businessId, canEdit }: { a: Asset; businessId: number | null; canEdit: boolean }) {
  const patch = usePatchAsset(businessId);
  const [open, setOpen] = useState(false);
  const [link, setLink] = useState(a.published_url ?? "");
  const live = (a.published_status ?? "pending") === "live" || !!a.published_url;
  const summary = a.summary || (a.body ? a.body.slice(0, 280) + (a.body.length > 280 ? "…" : "") : "");

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        {live ? <StatusBadge status="live" /> : <Chip tone="info">Pending link</Chip>}
        {a.asset_type && <span className="text-xs text-ink-3">{a.asset_type}</span>}
        {a.surface && <span className="text-xs text-ink-4">on {a.surface}</span>}
        {a.published_at && <span className="ml-auto text-xs text-ink-4">{fmtDate(a.published_at)}</span>}
      </div>

      <div className="mt-1 text-sm font-semibold text-ink">{a.title || "(untitled)"}</div>
      {a.target_query && <div className="text-xs text-ink-3">Answers: &ldquo;{a.target_query}&rdquo;</div>}
      {summary && <p className="mt-1 text-sm text-ink-2">{summary}</p>}

      {a.body && a.body.length > (summary?.length ?? 0) && (
        <>
          <button
            onClick={() => setOpen((o) => !o)}
            className="mt-1 text-xs font-medium text-indigo hover:text-indigo-strong"
          >
            {open ? "Hide full content" : "Read the full content"}
          </button>
          {open && <p className="mt-2 whitespace-pre-wrap rounded-lg bg-paper p-3 text-sm text-ink-2">{a.body}</p>}
        </>
      )}

      {/* where it was published — manual link entry (no live site/social integration yet) */}
      <div className="mt-3 border-t border-line pt-3">
        {a.published_url ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-xs font-medium text-ink-3">Published at:</span>
            <a href={a.published_url} target="_blank" rel="noreferrer" className="break-all text-indigo hover:text-indigo-strong hover:underline">
              {a.published_url}
            </a>
          </div>
        ) : (
          <div className="text-xs text-ink-4">Not linked yet — add where you published this so it&apos;s tracked.</div>
        )}
        {canEdit && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Input
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="https://… where you published it"
              className="min-w-[16rem] flex-1"
            />
            <Button
              variant="primary"
              onClick={() => link.trim() && patch.mutate({ assetId: a.id, published_url: link.trim() })}
              disabled={patch.isPending || !link.trim()}
            >
              {patch.isPending ? "Saving…" : a.published_url ? "Update link" : "Add published link"}
            </Button>
          </div>
        )}
      </div>

      {/* multi-surface distribution log */}
      <DistributionChecklist assetId={a.id} businessId={businessId} canEdit={canEdit} />

      {/* one-click publishing to connected channels (WordPress / GBP / social) */}
      <AssetPublishPanel assetId={a.id} businessId={businessId} canEdit={canEdit} />
    </Card>
  );
}

function ComplianceLedger({ businessId }: { businessId: number | null }) {
  const { data } = useComplianceLedger(businessId);
  if (!data || data.length === 0) return null;
  return (
    <details className="mt-6">
      <summary className="cursor-pointer text-sm font-semibold text-ink-2">Compliance sign-off record ({data.length})</summary>
      <TableContainer className="mt-2">
        <thead>
          <tr><Th>When</Th><Th>Title</Th><Th>Approver</Th><Th>Verdict</Th><Th>Override reason</Th></tr>
        </thead>
        <tbody>
          {data.map((s) => (
            <tr key={s.id}>
              <Td className="text-ink-3">{s.signed_at ? new Date(s.signed_at).toLocaleString() : "—"}</Td>
              <Td>{s.title || `draft ${s.draft_id}`}</Td>
              <Td>{s.approver || "—"}</Td>
              <Td>{s.compliance_pass === true ? <Chip tone="good">passed</Chip> : s.compliance_pass === false ? <Chip tone="bad">flagged</Chip> : <Chip tone="info">unscreened</Chip>}</Td>
              <Td className="text-ink-3">{s.override_reason || "—"}</Td>
            </tr>
          ))}
        </tbody>
      </TableContainer>
    </details>
  );
}

export default function FinalizedContentPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useAssets(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Published content"
        subtitle="The finished content you've approved — record where each piece went live so it's tracked as a reputation asset."
      />
      {data.length === 0 ? (
        <EmptyState
          title="No published content yet"
          why="When you approve a content draft, it's published as an asset and recorded here."
          produces="You'll see each piece, the question it answers, a summary, and a place to add where it was published."
          cta={{ label: "Review drafts", href: "/content/drafts" }}
        />
      ) : (
        <div className="space-y-6">
          <SearchTrafficSection businessId={businessId} />
          <div className="space-y-3">
            {data.map((a) => (
              <AssetRow key={a.id} a={a} businessId={businessId} canEdit={canEdit} />
            ))}
          </div>
        </div>
      )}
      <ComplianceLedger businessId={businessId} />
    </div>
  );
}
