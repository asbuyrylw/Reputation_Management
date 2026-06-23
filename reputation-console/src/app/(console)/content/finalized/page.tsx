"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAssets, usePatchAsset } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import type { Asset } from "@/lib/types";

function fmtDate(d?: string | null): string {
  if (!d) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${m[2]}-${m[3]}-${m[1]}` : d;
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
    </Card>
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
    </div>
  );
}
