"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAssets, usePatchAsset, useAssetPlacements, useAddPlacement, useUpdatePlacement, useComplianceLedger } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import type { Asset } from "@/lib/types";

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
    <div className="mt-3 border-t border-slate-100 pt-3">
      <div className="text-xs font-medium text-slate-500">Distribution{placements && placements.length > 0 ? ` — ${publishedN}/${placements.length} posted` : ""}</div>
      {(placements ?? []).length > 0 && (
        <ul className="mt-1.5 space-y-1.5">
          {placements!.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded-full px-1.5 py-0.5 font-medium ${p.status === "published" ? "bg-emerald-100 text-emerald-700" : p.status === "skipped" ? "bg-slate-200 text-slate-500" : "bg-amber-100 text-amber-700"}`}>{p.channel}</span>
              {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="break-all text-indigo-600 hover:underline">{p.url}</a> : <span className="text-slate-400">{p.status}</span>}
              {canEdit && p.status !== "published" && (
                <span className="flex items-center gap-1">
                  <input value={urlFor[p.id] ?? ""} onChange={(e) => setUrlFor((s) => ({ ...s, [p.id]: e.target.value }))}
                    placeholder="link (optional)" className="w-40 rounded border border-slate-300 px-1.5 py-0.5 text-[11px]" />
                  <button onClick={() => update.mutate({ assetId, placementId: p.id, status: "published", url: urlFor[p.id]?.trim() || undefined })}
                    className="rounded bg-emerald-600 px-1.5 py-0.5 text-[11px] font-medium text-white hover:bg-emerald-700">Mark posted</button>
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
              className="rounded-full border border-slate-200 px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-100">+ {c}</button>
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
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
            live ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
          }`}
        >
          {live ? "Live" : "Pending link"}
        </span>
        {a.asset_type && <span className="text-xs text-slate-500">{a.asset_type}</span>}
        {a.surface && <span className="text-xs text-slate-400">on {a.surface}</span>}
        {a.published_at && <span className="ml-auto text-xs text-slate-400">{fmtDate(a.published_at)}</span>}
      </div>

      <div className="mt-1 text-sm font-semibold text-slate-900">{a.title || "(untitled)"}</div>
      {a.target_query && <div className="text-xs text-slate-500">Answers: &ldquo;{a.target_query}&rdquo;</div>}
      {summary && <p className="mt-1 text-sm text-slate-700">{summary}</p>}

      {a.body && a.body.length > (summary?.length ?? 0) && (
        <>
          <button
            onClick={() => setOpen((o) => !o)}
            className="mt-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
          >
            {open ? "Hide full content" : "Read the full content"}
          </button>
          {open && <p className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{a.body}</p>}
        </>
      )}

      {/* where it was published — manual link entry (no live site/social integration yet) */}
      <div className="mt-3 border-t border-slate-100 pt-3">
        {a.published_url ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-xs font-medium text-slate-500">Published at:</span>
            <a href={a.published_url} target="_blank" rel="noreferrer" className="break-all text-indigo-600 hover:underline">
              {a.published_url}
            </a>
          </div>
        ) : (
          <div className="text-xs text-slate-400">Not linked yet — add where you published this so it&apos;s tracked.</div>
        )}
        {canEdit && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="https://… where you published it"
              className="min-w-[16rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
            <button
              onClick={() => link.trim() && patch.mutate({ assetId: a.id, published_url: link.trim() })}
              disabled={patch.isPending || !link.trim()}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {patch.isPending ? "Saving…" : a.published_url ? "Update link" : "Add published link"}
            </button>
          </div>
        )}
      </div>

      {/* multi-surface distribution log */}
      <DistributionChecklist assetId={a.id} businessId={businessId} canEdit={canEdit} />
    </Card>
  );
}

function ComplianceLedger({ businessId }: { businessId: number | null }) {
  const { data } = useComplianceLedger(businessId);
  if (!data || data.length === 0) return null;
  return (
    <details className="mt-6">
      <summary className="cursor-pointer text-sm font-semibold text-slate-700">Compliance sign-off record ({data.length})</summary>
      <Card className="mt-2 overflow-hidden p-0">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 text-left uppercase tracking-wide text-slate-500">
            <tr><th className="px-3 py-2">When</th><th className="px-3 py-2">Title</th><th className="px-3 py-2">Approver</th><th className="px-3 py-2">Verdict</th><th className="px-3 py-2">Override reason</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((s) => (
              <tr key={s.id}>
                <td className="px-3 py-2 text-slate-500">{s.signed_at ? new Date(s.signed_at).toLocaleString() : "—"}</td>
                <td className="px-3 py-2 text-slate-700">{s.title || `draft ${s.draft_id}`}</td>
                <td className="px-3 py-2 text-slate-700">{s.approver || "—"}</td>
                <td className="px-3 py-2">{s.compliance_pass === true ? <span className="text-emerald-700">passed</span> : s.compliance_pass === false ? <span className="text-rose-600">flagged</span> : <span className="text-amber-600">unscreened</span>}</td>
                <td className="px-3 py-2 text-slate-500">{s.override_reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
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
        <div className="space-y-3">
          {data.map((a) => (
            <AssetRow key={a.id} a={a} businessId={businessId} canEdit={canEdit} />
          ))}
        </div>
      )}
      <ComplianceLedger businessId={businessId} />
    </div>
  );
}
