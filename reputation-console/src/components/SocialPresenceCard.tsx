"use client";

import { useSocialAudit, useAuditSocials } from "@/lib/hooks";
import { Card } from "@/components/ui";
import type { SocialAudit } from "@/lib/types";

// Pretty platform names for the badge/heading.
const PLATFORM_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
  reddit: "Reddit",
  gbp: "Google Business Profile",
};
const platformLabel = (p: string) =>
  PLATFORM_LABEL[p] ?? p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// How the profile was found -> a short, plain-English provenance note next to the "found" badge.
function sourceNote(source: string | null): string | null {
  if (source === "website") return "confirmed (linked from your site)";
  if (source === "serper") return "Google Business Profile";
  if (source === "search") return "inferred from a web search";
  return null;
}

function PlatformRow({ a }: { a: SocialAudit }) {
  const pct = a.completeness != null ? Math.round(a.completeness * 100) : null;
  const note = a.exists ? sourceNote(a.source) : null;
  const topRec = a.audit?.recommendations?.[0] ?? null;
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-slate-900">{platformLabel(a.platform)}</span>
          {a.exists ? (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">✓ found</span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">✗ not found</span>
          )}
          {note && <span className="text-[11px] text-slate-400">{note}</span>}
        </div>
        {a.exists && a.profile_url && (
          <a href={a.profile_url} target="_blank" rel="noreferrer" className="text-[11px] font-medium text-indigo-600 hover:underline">
            View →
          </a>
        )}
      </div>

      {/* completeness bar + % (only when we have a profile to measure) */}
      {a.exists && pct != null && (
        <div className="mt-1.5 flex items-center gap-2">
          <div className="h-1.5 w-full max-w-[180px] overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
          </div>
          <span className="text-[11px] text-slate-500">{pct}% complete</span>
        </div>
      )}

      {/* the single most actionable next step */}
      {topRec && (
        <div className="mt-1 text-[11px] text-slate-600">
          <span className="font-medium text-slate-500">Next:</span> {topRec}
        </div>
      )}
    </li>
  );
}

// "Social presence" — per-platform existence/ownership + completeness + the top recommendation,
// with an "Audit socials" button that re-checks the profiles and cascades a plan refresh.
export function SocialPresenceCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useSocialAudit(businessId);
  const audit = useAuditSocials(businessId);

  const platforms = data ?? [];
  // Nothing to show and not loading -> render nothing rather than an empty shell.
  if (!isLoading && platforms.length === 0 && !canEdit) return null;

  const found = platforms.filter((p) => p.exists).length;

  return (
    <Card padded={false}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Social presence</h3>
          {platforms.length > 0 && (
            <p className="text-[11px] text-slate-400">{found} of {platforms.length} profiles found</p>
          )}
        </div>
        {canEdit && (
          <div className="flex flex-col items-end gap-0.5">
            <button
              type="button"
              onClick={() => audit.mutate()}
              disabled={audit.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {audit.isPending && (
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
              )}
              {audit.isPending ? "Queuing…" : audit.isSuccess ? "Queued ✓ — refreshing" : "Audit socials"}
            </button>
            <span className="text-[10px] text-slate-400">Re-checks your social profiles and updates the plan.</span>
          </div>
        )}
      </div>

      <div className="px-4 py-3">
        {isLoading ? (
          <p className="text-xs text-slate-400">Loading…</p>
        ) : platforms.length === 0 ? (
          <p className="text-xs text-slate-500">No social audit yet. Click “Audit socials” to check your profiles.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {platforms.map((a) => (
              <PlatformRow key={a.platform} a={a} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
