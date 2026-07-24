"use client";

// Shared "Get listed (directories)" block: the NAP block (consistent name/address/phone) plus a
// curated list of high-authority directories to submit to. Consistent citations + trusted-directory
// listings are a core local-SEO + AI-trust signal. Rendered on BOTH the Outreach page (where
// submissions are tracked) and the Tasks board (which surfaces the action), so it's one component.

import { useState } from "react";
import Link from "next/link";
import { useDirectoryCitations } from "@/lib/hooks";
import { Card, Chip } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { NapBlock } from "@/components/NapBlock";

const COLLAPSE_AFTER = 5;

export function DirectoryCitationsSection({ businessId, outreachLink = false, className = "mb-4" }: {
  businessId: number | null;
  outreachLink?: boolean;   // show a "Connect these in Outreach →" link (used on the Tasks board)
  className?: string;
}) {
  const { data } = useDirectoryCitations(businessId);
  const [expanded, setExpanded] = useState(false);
  if (!data || data.directories.length === 0) return null;
  const { nap, directories, summary } = data;
  const shown = expanded ? directories : directories.slice(0, COLLAPSE_AFTER);
  const hidden = directories.length - COLLAPSE_AFTER;
  return (
    <Card className={className}>
      <SecHead title="Get listed (directories)" note={`${summary.essential} essential of ${summary.total} suggested`} />
      <p className="mx-0.5 -mt-1.5 mb-1 text-xs text-ink-3">
        Listings on trusted directories — with your name, address &amp; phone matching exactly everywhere — are a core
        local-SEO and AI-trust signal.
      </p>

      {/* NAP block — keep this identical on every directory you submit to (shared component) */}
      <NapBlock nap={nap} className="mt-3" />

      {/* curated directory rows */}
      <ul className="mt-3 divide-y divide-line">
        {shown.map((d) => (
          <li key={d.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-ink-2">{d.name}</span>
                {d.financial && <Chip tone="info">Financial</Chip>}
                <Chip tone="neutral" className="capitalize">{d.category.replace(/_/g, " ")}</Chip>
              </div>
              <div className="text-[11px] text-ink-4">{d.authority} authority</div>
            </div>
            {d.submit_url ? (
              <a href={d.submit_url} target="_blank" rel="noreferrer"
                className="shrink-0 rounded-md border border-line-2 bg-white px-2.5 py-1 text-xs font-medium text-indigo hover:bg-paper">
                Open submission ↗
              </a>
            ) : (
              <span className="shrink-0 text-[11px] text-ink-4">Search locally</span>
            )}
          </li>
        ))}
        {hidden > 0 && (
          <li className="py-2">
            <button type="button" onClick={() => setExpanded((e) => !e)}
              className="text-xs font-medium text-indigo hover:underline">
              {expanded ? "See less" : `See more (${hidden} directories)`}
            </button>
          </li>
        )}
      </ul>

      {data.note && <p className="mt-2 text-[11px] text-ink-4">{data.note}</p>}

      {outreachLink && (
        <div className="mt-3 border-t border-line pt-2 text-right">
          <Link href="/content/outreach" className="text-xs font-semibold text-indigo hover:underline">
            Connect these in Outreach →
          </Link>
        </div>
      )}
    </Card>
  );
}
